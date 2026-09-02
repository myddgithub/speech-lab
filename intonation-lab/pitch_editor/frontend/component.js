/* 语调调试实验室 —— 音高曲线编辑器前端
 * 纯原生 JS + Canvas，无构建依赖，直接与 Streamlit 通过 postMessage 通信。
 * 协议与 streamlit-component-lib v2 保持一致：
 *   out: streamlit:componentReady / streamlit:setFrameHeight / streamlit:setComponentValue
 *   in : streamlit:render
 *
 * 功能：
 *  - 波形 + 音高曲线（对数/半音刻度）绘制，滚轮缩放，重置缩放
 *  - 拖拽手柄调音高、双击/A 键加点、Shift+点击/Delete 删点、↑↓ 半音微调
 *  - 播放编辑后/解码后原始音频并显示播放游标
 *  - 下方音节标注轨：标注模式拖拽创建/移动/缩放音节框，文本输入（如 liu4）
 */
(() => {
  "use strict";

  // ---------------- Streamlit 协议 ----------------
  const SCL = {
    API_VERSION: 1,
    send(type, data) {
      const msg = Object.assign({ isStreamlitMessage: true, type: type }, data);
      window.parent.postMessage(msg, "*");
    },
    ready() { this.send("streamlit:componentReady", { apiVersion: this.API_VERSION }); },
    setFrameHeight(h) { this.send("streamlit:setFrameHeight", { height: h }); },
    setValue(value) { this.send("streamlit:setComponentValue", { value: value, dataType: "json" }); },
  };

  // ---------------- DOM ----------------
  const canvas = document.getElementById("cv");
  const ctx = canvas.getContext("2d");
  const cvSyl = document.getElementById("cvSyl");
  const sctx = cvSyl.getContext("2d");
  const wrap = document.getElementById("wrap");
  const tooltip = document.getElementById("tooltip");
  const chkOrig = document.getElementById("chkOrig");
  const btnPlay = document.getElementById("btnPlay");
  const btnPlayOrig = document.getElementById("btnPlayOrig");
  const btnPlaySel = document.getElementById("btnPlaySel");
  const btnPlaySelO = document.getElementById("btnPlaySelO");
  const btnFit = document.getElementById("btnFit");
  const btnAnnotate = document.getElementById("btnAnnotate");
  const sylText = document.getElementById("sylText");
  const titleEl = document.getElementById("title");

  // ---------------- 界面语言（由 Python 传入 zh/en） ----------------
  const UI = {
    zh: {
      play: "▶ 播放编辑后", playOrig: "▶ 播放原始",
      playSel: "▶ 播放选中·编辑后", playSelO: "▶ 播放选中·原始",
      pause: "⏸ 暂停", pauseSel: "⏸ 暂停选中",
      annotate: "📝 标注音节", chk: "显示原始", textLbl: "标注:",
      ph: "如 liu4（数字=声调）", fit: "重置缩放",
      hint: "拖拽调音高 · 双击或按 A 加点 · Delete 删点 · ↑↓ 半音微调 · 滚轮缩放时间 · Shift+滚轮前后平移 · Ctrl+滚轮调音高刻度 · 点选 PY 边界按 B：区间层加边界 / 点层加点",
      tPlay: "播放编辑后的音频", tPlayOrig: "播放原始音频",
      tSel: "播放选中段（编辑后音频）", tSelO: "播放选中段（解码后原始音频）",
      tAnnotate: "在下方音节轨拖拽创建/调整音节，Delete 删除", tFit: "重置视图缩放",
      dSt: "半音",
    },
    en: {
      play: "▶ Play edited", playOrig: "▶ Play original",
      playSel: "▶ Play sel. (edited)", playSelO: "▶ Play sel. (original)",
      pause: "⏸ Pause", pauseSel: "⏸ Pause selection",
      annotate: "📝 Mark syllables", chk: "Show original", textLbl: "Text:",
      ph: "e.g. liu4 (digit = tone)", fit: "Reset zoom",
      hint: "drag to edit pitch · A / double-click adds a point · Delete removes · ↑↓ ±1 st · wheel zooms time · Shift+wheel pans · Ctrl+wheel scales pitch · click a PY boundary + B: boundary into interval tiers / point into point tiers",
      tPlay: "Play edited audio", tPlayOrig: "Play decoded original audio",
      tSel: "Play selected segment (edited audio)", tSelO: "Play selected segment (decoded original audio)",
      tAnnotate: "Drag to create/adjust syllables in the track below; Delete removes", tFit: "Reset view zoom",
      dSt: "st",
    },
  };
  let lang = "zh";
  function ui() { return UI[lang] || UI.zh; }
  function applyLang() {
    const u = ui();
    btnPlay.textContent = u.play;
    btnPlayOrig.textContent = u.playOrig;
    btnPlaySel.textContent = u.playSel;
    btnPlaySelO.textContent = u.playSelO;
    btnAnnotate.textContent = u.annotate;
    document.querySelector("label.chk").lastChild.textContent = " " + u.chk;
    document.getElementById("sylLabel").textContent = u.textLbl;
    sylText.placeholder = u.ph;
    btnFit.textContent = u.fit;
    document.getElementById("hint").textContent = u.hint;
    btnPlay.title = u.tPlay;
    btnPlayOrig.title = u.tPlayOrig;
    btnPlaySel.title = u.tSel;
    btnPlaySelO.title = u.tSelO;
    btnAnnotate.title = u.tAnnotate;
    btnFit.title = u.tFit;
  }

  // ---------------- 状态 ----------------
  const state = {
    points: [],        // [[t, f0], ...] 当前可编辑音高点
    syllables: [],     // [{id, text, t0, t1}] 第 0 层（音节）项
    layers: [],        // [{name, kind, def, items}] 多层标注（layers[0] 与 syllables 同数组）
    orig: [],          // [[t, f0], ...] 原始参考曲线
    wave: [],          // [[t, amp], ...]
    dur: 0,
    minF0: 60,
    maxF0: 500,
    urlEdit: null,
    urlOrig: null,
    label: "音高曲线",
    editable: true,
  };
  let lastSentPointsJson = null;  // 最近一次发送给 Python 的点集 JSON（识别外部修改）
  let lastSentSylJson = null;     // 最近一次发送给 Python 的音节 JSON
  let lastSentLayersJson = null;  // 最近一次发送给 Python 的多层标注 JSON
  let adoptPoints = true;         // 首次渲染时采用 Python 数据
  let adoptSyl = true;
  let adoptLayers = true;
  let seq = 0;                    // 用户操作序号（单调递增，供 Python 端去重/防回退）

  // 视图（CSS 像素坐标）
  const pad = { L: 54, R: 14, T: 10, B: 26 };
  const view = { t0: 0, t1: 1, loLog: 0, hiLog: 1 };

  const dpr = Math.max(1, window.devicePixelRatio || 1);
  let W = 0, H = 360, SYL_H = 48;   // 音节层（第 0 层）带高
  const EXT_B = 34;                 // 额外标注层带高
  let SYL_TOTAL = 48;               // 音节轨总高（随层数变化）

  // 交互（主画布）
  let selected = -1;
  let dragging = false;
  let drag = null;
  let lastMouse = { x: -1, y: -1 };   // 主画布内最近鼠标位置（供 A 键加点）

  // 交互（音节轨）
  let annotateMode = false;
  let selectedSyl = -1;
  let sylDrag = null; // {mode: create|move|resizeL|resizeR, idx, cursorT, t0, t1}
  let extraSel = null;      // {bi, idx} 额外层选中项
  let extraDrag = null;     // {bi, mode, idx, cursorT, initT0, initT1}
  let selBoundary = null;   // 第 0 层（PY）被选中的边界时间（供 B 键复制到下方区间层）
  let hoverB = null;        // 当前悬停的 PY 边界（未选中时虚线预览）
  let lastSylMouse = { x: -1 };  // 音节轨内最近鼠标位置（供 B 键快速复制）

  // 音频
  const audio = new Audio();
  let playToken = "none";
  let playing = false;
  let rafId = null;
  let selPlay = null;   // {token:'selE'|'selO', t0, t1} 当前选中段播放区间

  // ---------------- 工具函数 ----------------
  const log2 = Math.log2;
  function clamp(v, a, b) { return Math.min(Math.max(v, a), b); }

  function xOf(t) { return pad.L + ((t - view.t0) / (view.t1 - view.t0)) * (W - pad.L - pad.R); }
  function tOf(x) { return view.t0 + ((x - pad.L) / (W - pad.L - pad.R)) * (view.t1 - view.t0); }
  // 主画布上下分两块：上 1/4 波形、下 3/4 音高（总高度不变）
  function pitchY0() { return Math.round(H * 0.25) + 4; }
  function yOf(f) {
    const y0 = pitchY0();
    return y0 + (1 - (log2(f) - view.loLog) / (view.hiLog - view.loLog)) * (H - y0 - pad.B);
  }
  function fOf(y) {
    const y0 = pitchY0();
    return Math.pow(2, view.loLog + (1 - (y - y0) / (H - y0 - pad.B)) * (view.hiLog - view.loLog));
  }

  function resize() {
    const w = wrap.clientWidth;
    if (w <= 0) return;
    W = w;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(H * dpr);
    canvas.style.width = w + "px";
    canvas.style.height = H + "px";
    cvSyl.width = Math.round(w * dpr);
    SYL_TOTAL = SYL_H + EXT_B * Math.max(0, (state.layers ? state.layers.length : 1) - 1);
    cvSyl.height = Math.round(SYL_TOTAL * dpr);
    cvSyl.style.width = w + "px";
    cvSyl.style.height = SYL_TOTAL + "px";
    draw();
    drawSyl();
    SCL.setFrameHeight(document.body.scrollHeight);
  }

  function fitView() {
    view.t0 = -0.03;
    view.t1 = state.dur + 0.03;
    if (view.t1 - view.t0 < 0.1) view.t1 = view.t0 + 0.1;
    view.loLog = log2(state.minF0);
    view.hiLog = log2(state.maxF0);
    if (view.hiLog - view.loLog < 0.5) view.hiLog = view.loLog + 0.5;
    draw();
    drawSyl();
  }

  // ---------------- 绘制（主画布） ----------------
  const COLOR = {
    text: "#31333f", bg: "#ffffff", grid: "rgba(128,128,128,0.18)",
    wave: "rgba(96,120,255,0.35)", waveFill: "rgba(96,120,255,0.08)",
    orig: "rgba(255,176,0,0.95)", curve: "#ff4b4b", handle: "#ff4b4b",
    handleBorder: "#ffffff", playhead: "rgba(0,180,120,0.9)",
    syl: "rgba(96,130,255,0.75)", sylFill: "rgba(96,130,255,0.12)",
  };
  function cssVar(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }
  function refreshColors() {
    COLOR.text = cssVar("--text-color", COLOR.text);
    COLOR.bg = cssVar("--background-color", COLOR.bg);
    COLOR.curve = cssVar("--primary-color", COLOR.curve);
    COLOR.handle = COLOR.curve;
  }

  const HZ_MARKS = [40, 50, 60, 70, 80, 90, 100, 120, 140, 160, 180, 200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 900, 1000, 1200, 1500, 2000];
  function niceTimeStep(range) {
    for (const s of [0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 30, 60]) {
      if (range / s <= 12) return s;
    }
    return range / 12;
  }

  function draw() {
    if (!W) return;
    refreshColors();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = COLOR.bg;
    ctx.fillRect(0, 0, W, H);

    drawWaveform();
    drawGrid();
    drawSylBoundaries();  // 音节边界竖线（把波形分段）
    if (chkOrig.checked && state.orig.length > 1) drawPolyline(state.orig, COLOR.orig, 1.2, [5, 4]);
    drawSegments();
    if (state.editable) drawHandles();
    drawPlayhead();
  }

  function drawSylBoundaries() {
    // 在每个音节边界（相邻音节交界 / 独立音节两端）画一条竖线，
    // 贯穿上方波形图与下方音高图；音频首尾边缘不画。
    if (!state.syllables.length) return;
    const times = [];
    for (const s of state.syllables) {
      if (s.t0 > 0.005 && s.t0 < state.dur - 0.005) times.push(s.t0);
      if (s.t1 > 0.005 && s.t1 < state.dur - 0.005) times.push(s.t1);
    }
    if (!times.length) return;
    times.sort((a, b) => a - b);
    const uniq = [];
    for (const t of times) {
      if (!uniq.length || t - uniq[uniq.length - 1] > 0.005) uniq.push(t); // 相邻框共享边界去重
    }
    ctx.strokeStyle = "rgba(96,130,255,0.55)";
    ctx.lineWidth = 1;
    for (const t of uniq) {
      const x = xOf(t);
      ctx.beginPath();
      ctx.moveTo(x, 2);
      ctx.lineTo(x, H - pad.B);
      ctx.stroke();
    }
  }

  function drawWaveform() {
    // 波形独立显示在上 1/4 区域；幅度按数据自动归一化：
    // 全波形最大能量恰好扩展到显示高度的 ~90%（其余幅度按比例变细）
    if (!state.wave.length) return;
    const y0 = 4, y1 = pitchY0() - 5;
    if (y1 <= y0) return;
    const mid = (y0 + y1) / 2;
    let peak = 0;
    for (const [, a] of state.wave) {
      const v = Math.abs(a);
      if (v > peak) peak = v;
    }
    if (!(peak > 0)) return;
    const amp = ((y1 - y0) * 0.5 * 0.9) / peak; // 峰值 → 带高 90%
    ctx.beginPath();
    ctx.moveTo(xOf(state.wave[0][0]), mid);
    for (const [t, a] of state.wave) {
      ctx.lineTo(xOf(t), mid - a * amp);
    }
    ctx.strokeStyle = COLOR.wave;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.lineTo(xOf(state.wave[state.wave.length - 1][0]), mid);
    ctx.lineTo(xOf(state.wave[0][0]), mid);
    ctx.closePath();
    ctx.fillStyle = COLOR.waveFill;
    ctx.fill();
    // 波形/音高分隔线
    ctx.strokeStyle = "rgba(128,128,128,0.28)";
    ctx.beginPath();
    ctx.moveTo(pad.L, y1 + 4);
    ctx.lineTo(W - pad.R, y1 + 4);
    ctx.stroke();
  }

  function drawGrid() {
    ctx.font = "11px " + (cssVar("--font", "sans-serif"));
    const lo = Math.pow(2, view.loLog), hi = Math.pow(2, view.hiLog);
    ctx.strokeStyle = COLOR.grid;
    ctx.fillStyle = COLOR.text;
    ctx.lineWidth = 1;
    for (const f of HZ_MARKS) {
      if (f < lo * 0.95 || f > hi * 1.05) continue;
      const y = yOf(f);
      ctx.beginPath();
      ctx.moveTo(pad.L, y);
      ctx.lineTo(W - pad.R, y);
      ctx.stroke();
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(String(f), pad.L - 6, y);
    }
    const step = niceTimeStep(view.t1 - view.t0);
    const tStart = Math.ceil(view.t0 / step) * step;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let t = tStart; t <= view.t1; t += step) {
      const x = xOf(t);
      ctx.beginPath();
      ctx.moveTo(x, 2);
      ctx.lineTo(x, H - pad.B);
      ctx.stroke();
      ctx.fillText(t.toFixed(t < 1 ? 2 : 1) + "s", x, H - pad.B + 5);
    }
  }

  function segmentsOf(pts) {
    const segs = [];
    let cur = [];
    for (const p of pts) {
      if (cur.length && p[0] - cur[cur.length - 1][0] > 0.3) {
        segs.push(cur);
        cur = [];
      }
      cur.push(p);
    }
    if (cur.length) segs.push(cur);
    return segs;
  }

  function drawPolyline(pts, color, width, dash) {
    if (pts.length < 1) return;
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.setLineDash(dash || []);
    ctx.beginPath();
    let started = false;
    for (const [t, f] of pts) {
      if (!(f > 0)) { started = false; continue; }
      const x = xOf(t), y = yOf(f);
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function drawSegments() {
    for (const seg of segmentsOf(state.points)) {
      drawPolyline(seg, COLOR.curve, 2, []);
    }
  }

  function drawHandles() {
    const r = 4.5;
    for (let i = 0; i < state.points.length; i++) {
      const [t, f] = state.points[i];
      const x = xOf(t), y = yOf(f);
      ctx.beginPath();
      ctx.arc(x, y, i === selected ? r + 2.5 : r, 0, Math.PI * 2);
      ctx.fillStyle = COLOR.handle;
      ctx.fill();
      ctx.lineWidth = i === selected ? 2 : 1.5;
      ctx.strokeStyle = COLOR.handleBorder;
      ctx.stroke();
    }
  }

  function drawPlayhead() {
    if (!playing || !audio.currentTime || state.dur <= 0) return;
    const t = clamp(audio.currentTime, 0, state.dur);
    if (t < view.t0 || t > view.t1) return;
    const x = xOf(t);
    ctx.strokeStyle = COLOR.playhead;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, 2);
    ctx.lineTo(x, H - pad.B);
    ctx.stroke();
  }

  // ---------------- 绘制（音节轨 · 多层） ----------------
  const LAYER_COLORS = [
    "rgba(96,130,255,0.85)", "rgba(0,180,150,0.9)", "rgba(190,110,220,0.9)",
    "rgba(220,120,60,0.9)", "rgba(60,150,220,0.9)", "rgba(160,140,0,0.95)",
  ];
  function layerColor(bi) { return LAYER_COLORS[bi % LAYER_COLORS.length]; }

  function clipText(x, y, text, maxW, font) {
    sctx.fillStyle = COLOR.text;
    sctx.font = font || "11px " + (cssVar("--font", "sans-serif"));
    sctx.textAlign = "center";
    sctx.textBaseline = "middle";
    let t = String(text || "");
    if (sctx.measureText(t).width > maxW) {
      while (t.length > 1 && sctx.measureText(t + "…").width > maxW) t = t.slice(0, -1);
      t += "…";
    }
    sctx.fillText(t, x, y);
  }

  function drawExtraBands() {
    const layers = state.layers || [];
    for (let bi = 1; bi < layers.length; bi++) {
      const L = layers[bi];
      const top = SYL_H + (bi - 1) * EXT_B;
      // 分隔线
      sctx.strokeStyle = "rgba(128,128,128,0.35)";
      sctx.lineWidth = 1;
      sctx.beginPath();
      sctx.moveTo(0, top - 1);
      sctx.lineTo(W, top - 1);
      sctx.stroke();
      // 层名
      sctx.fillStyle = "rgba(128,128,128,0.85)";
      sctx.font = "10px " + (cssVar("--font", "sans-serif"));
      sctx.textAlign = "left";
      sctx.textBaseline = "middle";
      sctx.fillText(String(L.name || "层" + bi), 2, top + EXT_B / 2);
      const cX = pad.L; // 内容区起点
      if (L.kind === "point") {
        // 点标记（竖直菱形）
        for (let i = 0; i < L.items.length; i++) {
          const it = L.items[i];
          const x = xOf(it.t);
          if (x < cX - 4 || x > W - pad.R + 4) continue;
          const sel = extraSel && extraSel.bi === bi && extraSel.idx === i;
          sctx.fillStyle = sel ? COLOR.curve : layerColor(bi);
          sctx.beginPath();
          sctx.moveTo(x, top + 6);
          sctx.lineTo(x + 5, top + EXT_B / 2);
          sctx.lineTo(x, top + EXT_B - 6);
          sctx.lineTo(x - 5, top + EXT_B / 2);
          sctx.closePath();
          sctx.fill();
          if (it.text) clipText(x, top + EXT_B - 6, it.text, 60, "10px " + (cssVar("--font", "sans-serif")));
        }
      } else {
        for (let i = 0; i < L.items.length; i++) {
          const it = L.items[i];
          const x0 = Math.max(cX, xOf(it.t0)), x1 = Math.min(W - pad.R, xOf(it.t1));
          if (x1 <= cX) continue;
          const sel = extraSel && extraSel.bi === bi && extraSel.idx === i;
          sctx.fillStyle = sel ? "rgba(255,75,75,0.20)" : "rgba(128,128,128,0.12)";
          sctx.strokeStyle = sel ? COLOR.curve : layerColor(bi);
          sctx.lineWidth = sel ? 2 : 1;
          sctx.beginPath();
          sctx.roundRect(x0, top + 4, Math.max(4, x1 - x0), EXT_B - 8, 4);
          sctx.fill();
          sctx.stroke();
          clipText((x0 + x1) / 2, top + EXT_B / 2, it.text, Math.max(2, x1 - x0 - 5),
                   "11px " + (cssVar("--font", "sans-serif")));
          if (annotateMode) {
            sctx.fillStyle = layerColor(bi);
            sctx.beginPath();
            sctx.moveTo(x0 + 1, top + EXT_B / 2 - 5);
            sctx.lineTo(x0 + 5, top + EXT_B / 2);
            sctx.lineTo(x0 + 1, top + EXT_B / 2 + 5);
            sctx.closePath();
            sctx.fill();
            sctx.beginPath();
            sctx.moveTo(x1 - 1, top + EXT_B / 2 - 5);
            sctx.lineTo(x1 - 5, top + EXT_B / 2);
            sctx.lineTo(x1 - 1, top + EXT_B / 2 + 5);
            sctx.closePath();
            sctx.fill();
          }
        }
      }
    }
  }

  function drawSyl() {
    if (!W) return;
    sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    sctx.clearRect(0, 0, W, SYL_TOTAL);
    sctx.fillStyle = COLOR.bg;
    sctx.fillRect(0, 0, W, SYL_TOTAL);

    // 时间网格（贯穿全部带）
    sctx.strokeStyle = COLOR.grid;
    sctx.lineWidth = 1;
    sctx.beginPath();
    const step = niceTimeStep(view.t1 - view.t0);
    for (let t = Math.ceil(view.t0 / step) * step; t <= view.t1; t += step) {
      const x = xOf(t);
      sctx.moveTo(x, 0);
      sctx.lineTo(x, SYL_TOTAL);
    }
    sctx.stroke();

    // 第 0 层（PY）层名
    if (state.layers && state.layers[0]) {
      sctx.fillStyle = "rgba(128,128,128,0.85)";
      sctx.font = "10px " + (cssVar("--font", "sans-serif"));
      sctx.textAlign = "left";
      sctx.textBaseline = "middle";
      sctx.fillText(String(state.layers[0].name || "PY"), 2, SYL_H / 2);
    }

    // 音节框
    for (let i = 0; i < state.syllables.length; i++) {
      const s = state.syllables[i];
      const x0 = xOf(s.t0), x1 = xOf(s.t1);
      if (x1 < pad.L || x0 > W - pad.R) continue;
      const sel = i === selectedSyl;
      sctx.fillStyle = sel ? "rgba(255,75,75,0.18)" : COLOR.sylFill;
      sctx.strokeStyle = sel ? COLOR.curve : COLOR.syl;
      sctx.lineWidth = sel ? 2 : 1;
      sctx.beginPath();
      sctx.roundRect(x0, 5, Math.max(6, x1 - x0), SYL_H - 10, 5);
      sctx.fill();
      sctx.stroke();
      // 文本（超出截断）
      sctx.fillStyle = COLOR.text;
      sctx.font = "12px " + (cssVar("--font", "sans-serif"));
      sctx.textAlign = "center";
      sctx.textBaseline = "middle";
      const label = s.text || "音" + (i + 1);
      const maxW = Math.max(2, x1 - x0 - 6);
      let text = label;
      if (sctx.measureText(text).width > maxW) {
        while (text.length > 1 && sctx.measureText(text + "…").width > maxW) {
          text = text.slice(0, -1);
        }
        text += "…";
      }
      sctx.fillText(text, (x0 + x1) / 2, SYL_H / 2 + 1);
      // 标注模式下手柄
      if (annotateMode) {
        sctx.fillStyle = COLOR.syl;
        sctx.beginPath();
        sctx.moveTo(x0 + 1, SYL_H / 2 - 6);
        sctx.lineTo(x0 + 6, SYL_H / 2);
        sctx.lineTo(x0 + 1, SYL_H / 2 + 6);
        sctx.closePath();
        sctx.fill();
        sctx.beginPath();
        sctx.moveTo(x1 - 1, SYL_H / 2 - 6);
        sctx.lineTo(x1 - 6, SYL_H / 2);
        sctx.lineTo(x1 - 1, SYL_H / 2 + 6);
        sctx.closePath();
        sctx.fill();
      }
    }

    // 创建中的预览框
    if (sylDrag && sylDrag.mode === "create") {
      const x0 = xOf(Math.min(sylDrag.t0, sylDrag.t1));
      const x1 = xOf(Math.max(sylDrag.t0, sylDrag.t1));
      sctx.setLineDash([5, 4]);
      sctx.strokeStyle = COLOR.syl;
      sctx.lineWidth = 1.5;
      sctx.strokeRect(x0, 5, Math.max(4, x1 - x0), SYL_H - 10);
      sctx.setLineDash([]);
    }

    // 额外标注层（第 1..n 层）
    drawExtraBands();

    // PY 边界参考线（选中=红色高亮；悬停=淡虚线）：贯穿全部色带
    const guide = selBoundary !== null ? selBoundary : hoverB;
    if (guide !== null) {
      const gx = xOf(guide);
      sctx.strokeStyle = selBoundary !== null ? "rgba(255,75,75,0.95)" : "rgba(255,75,75,0.4)";
      sctx.lineWidth = selBoundary !== null ? 2 : 1;
      sctx.setLineDash([6, 4]);
      sctx.beginPath();
      sctx.moveTo(gx, 0);
      sctx.lineTo(gx, SYL_TOTAL);
      sctx.stroke();
      sctx.setLineDash([]);
    }

    // 播放游标延伸
    if (playing && audio.currentTime && state.dur > 0) {
      const t = clamp(audio.currentTime, 0, state.dur);
      if (t >= view.t0 && t <= view.t1) {
        const x = xOf(t);
        sctx.strokeStyle = COLOR.playhead;
        sctx.lineWidth = 2;
        sctx.beginPath();
        sctx.moveTo(x, 0);
        sctx.lineTo(x, SYL_TOTAL);
        sctx.stroke();
      }
    }
    updateSelButtons(); // 选中项变化时同步“播放选中”按钮可用状态
  }

  // ---------------- 交互（主画布） ----------------
  function hitTest(cx, cy) {
    for (let i = 0; i < state.points.length; i++) {
      const [t, f] = state.points[i];
      const dx = xOf(t) - cx, dy = yOf(f) - cy;
      if (dx * dx + dy * dy <= 81) return i; // 9px
    }
    return -1;
  }

  function interpF0(t) {
    const pts = state.points;
    if (!pts.length) return null;
    for (const seg of segmentsOf(pts)) {
      if (t < seg[0][0] || t > seg[seg.length - 1][0]) continue;
      if (t <= seg[0][0]) return seg[0][1];
      if (t >= seg[seg.length - 1][0]) return seg[seg.length - 1][1];
      for (let i = 0; i < seg.length - 1; i++) {
        if (t >= seg[i][0] && t <= seg[i + 1][0]) {
          const [t0, f0] = seg[i], [t1, f1] = seg[i + 1];
          if (t1 - t0 < 1e-9) return f0;
          const ratio = (t - t0) / (t1 - t0);
          return Math.pow(2, log2(f0) + (log2(f1) - log2(f0)) * ratio);
        }
      }
    }
    return null;
  }

  function origF0At(t) {
    if (!state.orig.length) return null;
    for (const seg of segmentsOf(state.orig)) {
      if (t < seg[0][0] || t > seg[seg.length - 1][0]) continue;
      if (t <= seg[0][0]) return seg[0][1] > 0 ? seg[0][1] : null;
      if (t >= seg[seg.length - 1][0]) return seg[seg.length - 1][1] > 0 ? seg[seg.length - 1][1] : null;
      for (let i = 0; i < seg.length - 1; i++) {
        if (t >= seg[i][0] && t <= seg[i + 1][0]) {
          const [t0, f0] = seg[i], [t1, f1] = seg[i + 1];
          if (!(f0 > 0) || !(f1 > 0)) return null;
          if (t1 - t0 < 1e-9) return f0;
          const ratio = (t - t0) / (t1 - t0);
          return Math.pow(2, log2(f0) + (log2(f1) - log2(f0)) * ratio);
        }
      }
    }
    return null;
  }

  function semis(f1, f2) { return f1 > 0 && f2 > 0 ? 12 * log2(f1 / f2) : null; }

  function showTooltip(x, y, text) {
    tooltip.style.display = "block";
    tooltip.textContent = text;
    const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
    tooltip.style.left = clamp(x + 14, 2, W - tw - 2) + "px";
    tooltip.style.top = clamp(y - th - 10, 2, H - th - 2) + "px";
  }
  function hideTooltip() { tooltip.style.display = "none"; }

  // 规范化比较（仅含几何/文本，避免 id 等杂项造成误判）
  function canonSyl(a) {
    return JSON.stringify((a || []).map((s) => ({ text: s.text || "", t0: s.t0, t1: s.t1 })));
  }
  function canonLayers(a) {
    return JSON.stringify((a || []).map((L) => ({
      name: L.name || "", kind: L.kind || "interval", def: L.def || "",
      items: (L.items || []).map((it) =>
        L.kind === "point"
          ? { t: it.t, text: it.text || "" }
          : { t0: it.t0, t1: it.t1, text: it.text || "" }
      ),
    })));
  }
  function canonPts(a) {
    return JSON.stringify((a || []).map((p) => [p[0], p[1]]));
  }
  function sendUpdate(event) {
    const pts = canonPts(state.points);
    const ljs = canonLayers(state.layers);
    if (event === "drag" && pts === lastSentPointsJson && ljs === lastSentLayersJson) return; // 无变化不发
    lastSentPointsJson = pts;
    lastSentLayersJson = ljs;
    lastSentSylJson = canonSyl(state.layers[0] && state.layers[0].items ? state.layers[0].items : []);
    seq += 1;
    const layers = (state.layers || []).map((L) => ({
      name: L.name || "", kind: L.kind || "interval", def: L.def || "",
      items: (L.items || []).map((it) =>
        L.kind === "point"
          ? { t: Math.round(it.t * 1e9) / 1e9, text: it.text || "" }
          : { t0: Math.round(it.t0 * 1e9) / 1e9, t1: Math.round(it.t1 * 1e9) / 1e9, text: it.text || "" }
      ),
    }));
    SCL.setValue({
      points: (state.points || []).map((p) => [Math.round(p[0] * 1e4) / 1e4, Math.round(p[1] * 1e3) / 1e3]),
      syllables: layers[0] && layers[0].items ? layers[0].items : [],
      layers: layers,
      event: event,
      seq: seq,
      annotate: annotateMode,      // 标注模式状态（持久化，防重跑后重置）
      draft: sylText.value,        // 音节文本输入框草稿
    });
  }

  function f0Clamp(f) {
    // 纵轴可独立缩放用于观察，但可编辑值始终服从 Python 传入的分析范围。
    return clamp(f, state.minF0, state.maxF0);
  }

  function insertPointAt(t, f) {
    const pts = state.points;
    const roundedT = Math.round(clamp(t, 0, state.dur) * 1e4) / 1e4;
    const existing = pts.findIndex((q) => Math.abs(q[0] - roundedT) < 5e-5);
    if (existing >= 0) {
      pts[existing][1] = Math.round(f * 1e3) / 1e3;
      selected = existing;
      return;
    }
    let i = pts.findIndex((q) => q[0] > t);
    if (i < 0) i = pts.length;
    pts.splice(i, 0, [roundedT, Math.round(f * 1e3) / 1e3]);
    selected = i;
  }

  function onPointerDown(e) {
    if (!state.editable || state.points.length === 0) return;
    const rect = canvas.getBoundingClientRect();
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
    lastMouse = { x: cx, y: cy };
    const idx = hitTest(cx, cy);
    if (e.shiftKey && idx >= 0) {
      state.points.splice(idx, 1);
      if (selected === idx) selected = -1;
      draw();
      sendUpdate("remove");
      return;
    }
    if (idx >= 0) {
      selected = idx;
      dragging = true;
      const [t, f] = state.points[idx];
      drag = { idx: idx };
      canvas.setPointerCapture(e.pointerId);
      draw();
      showTooltip(cx, cy, fmtTip(t, f));
    } else {
      selected = -1;
      draw();
      hideTooltip();
    }
  }

  function fmtTip(t, f) {
    const o = origF0At(t);
    const d = semis(f, o);
    let s = `t=${t.toFixed(2)}s  f0=${f.toFixed(1)} Hz`;
    if (d !== null && Math.abs(d) > 0.01) s += `  (Δ${d >= 0 ? "+" : ""}${d.toFixed(2)} ${ui().dSt})`;
    return s;
  }

  function onPointerMove(e) {
    const rect = canvas.getBoundingClientRect();
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
    lastMouse = { x: cx, y: cy };
    if (!dragging || !drag) return;
    const p = state.points[drag.idx];
    const lo = drag.idx > 0 ? state.points[drag.idx - 1][0] + 0.02 : 0;
    const hi = drag.idx < state.points.length - 1 ? state.points[drag.idx + 1][0] - 0.02 : state.dur;
    let f = f0Clamp(fOf(cy));
    // 用户可能插入了间距不足 20ms 的点；此时锁定横向位置，仍允许上下调音高，
    // 避免 min > max 时通用 clamp 把点推过相邻点。
    const t = lo <= hi ? clamp(tOf(cx), lo, hi) : p[0];
    p[0] = Math.round(t * 1e4) / 1e4;
    p[1] = Math.round(f * 1e3) / 1e3;
    draw();
    showTooltip(cx, cy, fmtTip(p[0], p[1]));
  }

  function onPointerUp(e) {
    if (!dragging) return;
    dragging = false;
    drag = null;
    hideTooltip();
    sendUpdate("drag");
    try { canvas.releasePointerCapture(e.pointerId); } catch (err) { /* noop */ }
  }

  function onDblClick(e) {
    if (!state.editable || dragging) return;
    const rect = canvas.getBoundingClientRect();
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
    lastMouse = { x: cx, y: cy };
    const t = tOf(cx);
    if (t < 0 || t > state.dur) return;
    const f = interpF0(t);
    if (f === null) return;
    insertPointAt(t, f0Clamp(fOf(cy)));
    draw();
    sendUpdate("add");
  }

  // ---------------- 交互（音节轨） ----------------
  function sylHit(cx) {
    for (let i = state.syllables.length - 1; i >= 0; i--) {
      const s = state.syllables[i];
      const x0 = xOf(s.t0), x1 = xOf(s.t1);
      if (annotateMode && Math.abs(cx - x0) < 8) return { idx: i, edge: "L" };
      if (annotateMode && Math.abs(cx - x1) < 8) return { idx: i, edge: "R" };
      if (cx >= x0 && cx <= x1) return { idx: i, edge: null };
    }
    return null;
  }

  function sylNeighbors(idx) {
    // 按 t0 排序后的相邻音节（用于移动/缩放夹紧）
    const prev = idx > 0 ? state.syllables[idx - 1] : null;
    const next = idx < state.syllables.length - 1 ? state.syllables[idx + 1] : null;
    return { prev, next };
  }

  function isTouching(a, b) {
    // 两音节框是否共享边界（连续铺满时相邻框 t1 == t0）
    return !!a && !!b && Math.abs(a.t1 - b.t0) < 1e-6;
  }

  // PY 层内部边界时刻（首尾 0 / dur 不计入）
  function pyBoundaries() {
    const out = [];
    const dur = state.dur;
    for (const s of state.syllables) {
      if (s.t0 > 0.005 && s.t0 < dur - 0.005) out.push(s.t0);
      if (s.t1 > 0.005 && s.t1 < dur - 0.005) out.push(s.t1);
    }
    if (!out.length) return [];
    out.sort((a, b) => a - b);
    const uniq = [];
    for (const t of out) {
      if (!uniq.length || t - uniq[uniq.length - 1] > 0.005) uniq.push(t);
    }
    return uniq;
  }

  // 离光标最近的 PY 边界（容差 ~7px），无则 null
  function nearestBoundary(cx) {
    let best = null, bestD = 7.5;
    for (const t of pyBoundaries()) {
      const d = Math.abs(xOf(t) - cx);
      if (d < bestD) { bestD = d; best = t; }
    }
    return best;
  }

  // 默认编号文本（音N）在结构变化后按时间顺序自动重排，
  // 例如在“音2”内部插入边界后变为 音1 音2 音3 音4 ……（后续顺延）
  const _DEFNUM_RE = /^音\d+$/;
  function renumberDefaultLabels() {
    const items = state.syllables;
    if (!items.length || !items.every((s) => _DEFNUM_RE.test((s.text || "").trim()))) return false;
    let changed = false;
    items.forEach((s, i) => {
      const txt = "音" + (i + 1);
      if (s.text !== txt) { s.text = txt; changed = true; }
    });
    return changed;
  }

  function onSylPointerDown(e) {
    const rect = cvSyl.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    // 额外标注层带（第 1..n 层）
    const bi = extraBandIndex(cy);
    if (bi >= 1) {
      onExtraDown(e, cx, bi);
      return;
    }
    const t = tOf(cx);
    // 点选 PY 层边界（供 B 键复制到下方区间层）；点框体/空白/其他带则清除
    hoverB = null;
    selBoundary = nearestBoundary(cx);
    selectedSyl = -1;
    extraSel = null;
    const hit = sylHit(cx);
    if (hit) {
      selectedSyl = hit.idx;
      sylText.value = state.syllables[hit.idx].text || "";
      if (annotateMode) {
        const s = state.syllables[hit.idx];
        sylDrag = {
          mode: hit.edge === "L" ? "resizeL" : hit.edge === "R" ? "resizeR" : "move",
          idx: hit.idx, cursorT: t, initT0: s.t0, initT1: s.t1,
        };
        cvSyl.setPointerCapture(e.pointerId);
      }
    } else if (annotateMode) {
      sylDrag = { mode: "create", idx: -1, t0: t, t1: t, cursorT: t };
      cvSyl.setPointerCapture(e.pointerId);
    }
    draw();
    drawSyl();
  }

  function onSylPointerMove(e) {
    const rect = cvSyl.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    if (extraDrag) {
      onExtraMove(e);
      return;
    }
    if (!sylDrag) {
      // 空闲悬停：记录位置（B 键快速复制用）并预览最近的 PY 边界
      lastSylMouse.x = cx;
      const cy = e.clientY - rect.top;
      const nb = cy < SYL_H && selBoundary === null ? nearestBoundary(cx) : null;
      if (nb !== hoverB) { hoverB = nb; drawSyl(); }
      return;
    }
    const t = clamp(tOf(cx), 0, state.dur);
    if (sylDrag.mode === "create") {
      sylDrag.t1 = t;
    } else {
      const s = state.syllables[sylDrag.idx];
      if (!s) { sylDrag = null; return; }
      const { prev, next } = sylNeighbors(sylDrag.idx);
      const touchL = isTouching(prev, s);
      const touchR = isTouching(s, next);
      if (sylDrag.mode === "move") {
        // 以按下时的 origin/宽度平移，避免一帧 dt 过大时 t0 先被卡在旧 t1 上把框拉长。
        // cursorT 保持按下瞬间的时间，不逐帧改写。
        const width = sylDrag.initT1 - sylDrag.initT0;
        const dt = t - sylDrag.cursorT;
        const lo = prev ? (touchL ? prev.t0 + 0.06 : prev.t1 + 0.05) : 0;
        const hi = next ? (touchR ? next.t1 - 0.06 : next.t0 - 0.05) : state.dur;
        const maxT0 = hi - width;
        const t0 = Math.round(clamp(sylDrag.initT0 + dt, lo, maxT0) * 1e4) / 1e4;
        s.t0 = t0;
        s.t1 = Math.round((t0 + width) * 1e4) / 1e4;
        if (touchL) prev.t1 = s.t0;
        if (touchR) next.t0 = s.t1;
      } else if (sylDrag.mode === "resizeL") {
        // 调整左边界；若与左邻共享边界则联动（同时改左邻的右边界）
        const lo = touchL ? (prev ? prev.t0 + 0.06 : 0) : (prev ? prev.t1 + 0.05 : 0);
        const hi = s.t1 - 0.06;
        s.t0 = Math.round(clamp(t, lo, hi) * 1e4) / 1e4;
        if (touchL && prev) prev.t1 = s.t0;
      } else if (sylDrag.mode === "resizeR") {
        const lo = s.t0 + 0.06;
        const hi = touchR ? (next ? next.t1 - 0.06 : state.dur) : (next ? next.t0 - 0.05 : state.dur);
        s.t1 = Math.round(clamp(t, lo, hi) * 1e4) / 1e4;
        if (touchR && next) next.t0 = s.t1;
      }
    }
    draw();
    drawSyl();
  }

  function onSylDblClick(e) {
    if (!annotateMode) return;
    const rect = cvSyl.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const bi = extraBandIndex(cy);
    if (bi >= 1) {
      onExtraDblClick(e, cx, bi);
      return;
    }
    const t = tOf(cx);
    if (t < 0 || t > state.dur) return;
    const hit = sylHit(cx);
    if (!hit || hit.edge !== null) return; // 只对框体内部分割
    const s = state.syllables[hit.idx];
    if (!s || t - s.t0 < 0.06 || s.t1 - t < 0.06) return;
    const tR = Math.round(t * 1e4) / 1e4;
    const left = {
      id: "syl-" + Date.now() + "-l" + Math.floor(Math.random() * 1e4),
      text: s.text, t0: s.t0, t1: tR,
    };
    const right = {
      id: "syl-" + Date.now() + "-r" + Math.floor(Math.random() * 1e4),
      text: s.text, t0: tR, t1: s.t1,
    };
    state.syllables.splice(hit.idx, 1, left, right);
    selectedSyl = hit.idx; // 选中左段
    selBoundary = null;    // 分裂产生新边界，旧选择失效
    renumberDefaultLabels(); // 默认编号(音N)自动顺延
    sendUpdate("syl_split");
    draw();
    drawSyl();
  }

  function onSylPointerUp(e) {
    if (extraDrag) {
      onExtraUp(e);
      return;
    }
    if (!sylDrag) return;
    const d = sylDrag;
    sylDrag = null;
    if (d.mode === "create") {
      let t0 = Math.min(d.t0, d.t1);
      let t1 = Math.max(d.t0, d.t1);
      // 插入位置与相邻夹紧
      let ins = state.syllables.findIndex((s) => s.t0 > t0);
      if (ins < 0) ins = state.syllables.length;
      const prev = ins > 0 ? state.syllables[ins - 1] : null;
      const next = ins < state.syllables.length ? state.syllables[ins] : null;
      t0 = clamp(t0, prev ? prev.t1 + 0.05 : 0, state.dur);
      t1 = clamp(t1, 0, next ? next.t0 - 0.05 : state.dur);
      if (t1 - t0 >= 0.06) {
        const syl = {
          id: "syl-" + Date.now() + "-" + Math.floor(Math.random() * 1e4),
          text: sylText.value.trim() || "音" + (state.syllables.length + 1),
          t0: Math.round(t0 * 1e4) / 1e4,
          t1: Math.round(t1 * 1e4) / 1e4,
        };
        state.syllables.push(syl);
        state.syllables.sort((a, b) => a.t0 - b.t0);
        selectedSyl = state.syllables.findIndex((s) => s.id === syl.id);
        selBoundary = null;
        renumberDefaultLabels(); // 默认编号(音N)自动顺延
        sendUpdate("syl_add");
      }
    } else if (d.mode !== "create") {
      // 仅在实际移动/缩放时发送，避免单纯点击（如双击）触发无谓重跑
      const s = state.syllables[d.idx];
      if (s && (s.t0 !== d.initT0 || s.t1 !== d.initT1)) {
        selBoundary = null; // 边界已移动，旧选择失效
        sendUpdate("syl_move");
      }
    }
    draw();
    drawSyl();
    try { cvSyl.releasePointerCapture(e.pointerId); } catch (err) { /* noop */ }
  }

  // ---------------- 交互（额外标注层 第1..n层） ----------------
  function extraBandIndex(cy) {
    if (cy < SYL_H) return 0;
    const n = (state.layers ? state.layers.length : 1) - 1;
    const k = Math.floor((cy - SYL_H) / EXT_B);
    return k >= 0 && k < n ? k + 1 : -1;
  }
  function extraBandTop(bi) { return SYL_H + (bi - 1) * EXT_B; }

  function extraLayer(bi) { return state.layers && state.layers[bi]; }

  function extraHit(cx, bi) {
    const L = extraLayer(bi);
    if (!L) return null;
    const items = L.items || [];
    for (let i = items.length - 1; i >= 0; i--) {
      const it = items[i];
      if (L.kind === "point") {
        const px = xOf(it.t);
        if (Math.abs(cx - px) <= 7) return { idx: i, edge: null };
      } else {
        const x0 = xOf(it.t0), x1 = xOf(it.t1);
        if (annotateMode && Math.abs(cx - x0) < 7) return { idx: i, edge: "L" };
        if (annotateMode && Math.abs(cx - x1) < 7) return { idx: i, edge: "R" };
        if (cx >= x0 && cx <= x1) return { idx: i, edge: null };
      }
    }
    return null;
  }

  function onExtraDown(e, cx, bi) {
    const t = tOf(cx);
    selectedSyl = -1;
    const L = extraLayer(bi);
    const hit = extraHit(cx, bi);
    extraSel = hit ? { bi: bi, idx: hit.idx } : null;
    if (hit) {
      sylText.value = L.items[hit.idx].text || "";
    }
    if (!annotateMode || !L) {
      draw();
      drawSyl();
      return;
    }
    if (hit) {
      const it = L.items[hit.idx];
      const init = { t0: it.t0, t1: it.t1, t: it.t };
      extraDrag = {
        bi: bi,
        mode: L.kind === "point" ? "movePt"
          : hit.edge === "L" ? "resizeL" : hit.edge === "R" ? "resizeR" : "move",
        idx: hit.idx, cursorT: t, initT0: it.t0, initT1: it.t1, initT: it.t,
      };
      cvSyl.setPointerCapture(e.pointerId);
    } else if (L.kind === "point") {
      // 点层：点击空白处新增一个点
      const pointT = Math.round(clamp(t, 0, state.dur) * 1e9) / 1e9;
      const duplicate = L.items.findIndex((x) => Math.abs(x.t - pointT) <= 1e-9);
      if (duplicate >= 0) {
        extraSel = { bi: bi, idx: duplicate };
        sylText.value = L.items[duplicate].text || "";
        draw();
        drawSyl();
        return;
      }
      const newPoint = { t: pointT, text: "" };
      L.items.push(newPoint);
      L.items.sort((a, b) => a.t - b.t);
      extraSel = { bi: bi, idx: L.items.indexOf(newPoint) };
      sylText.value = "";
      sendUpdate("extra_add");
      draw();
      drawSyl();
      return;
    } else {
      extraDrag = { bi: bi, mode: "create", idx: -1, cursorT: t, t0: t, t1: t };
      cvSyl.setPointerCapture(e.pointerId);
    }
    draw();
    drawSyl();
  }

  function onExtraMove(e) {
    const d = extraDrag;
    const rect = cvSyl.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const t = clamp(tOf(cx), 0, state.dur);
    const L = extraLayer(d.bi);
    if (!L) { extraDrag = null; return; }
    if (d.mode === "create") {
      d.t1 = t;
    } else {
      const it = L.items[d.idx];
      if (!it) { extraDrag = null; return; }
      if (d.mode === "movePt") {
        const lo = d.idx > 0 ? L.items[d.idx - 1].t + 1e-9 : 0;
        const hi = d.idx < L.items.length - 1 ? L.items[d.idx + 1].t - 1e-9 : state.dur;
        it.t = Math.round(clamp(t, lo, hi) * 1e9) / 1e9;
      } else if (d.mode === "move") {
        const width = d.initT1 - d.initT0;
        const dt = t - d.cursorT;
        const lo = d.idx > 0 ? L.items[d.idx - 1].t1 : 0;
        const hi = d.idx < L.items.length - 1 ? L.items[d.idx + 1].t0 : state.dur;
        const t0 = Math.round(clamp(d.initT0 + dt, lo, hi - width) * 1e4) / 1e4;
        it.t0 = t0;
        it.t1 = Math.round((t0 + width) * 1e4) / 1e4;
      } else if (d.mode === "resizeL") {
        const lo = d.idx > 0 ? L.items[d.idx - 1].t1 + 0.01 : 0;
        it.t0 = Math.round(clamp(t, lo, it.t1 - 0.02) * 1e4) / 1e4;
      } else if (d.mode === "resizeR") {
        const hi = d.idx < L.items.length - 1 ? L.items[d.idx + 1].t0 - 0.01 : state.dur;
        it.t1 = Math.round(clamp(t, it.t0 + 0.02, hi) * 1e4) / 1e4;
      }
    }
    draw();
    drawSyl();
  }

  function onExtraUp(e) {
    if (!extraDrag) return;
    const d = extraDrag;
    extraDrag = null;
    const L = extraLayer(d.bi);
    if (L) {
      if (d.mode === "create") {
        let t0 = clamp(Math.min(d.t0, d.t1), 0, state.dur);
        let t1 = clamp(Math.max(d.t0, d.t1), 0, state.dur);
        if (d.idx >= 0) { /* unused */ }
        if (t1 - t0 >= 0.06) {
          // 夹紧避免重叠
          const items = L.items;
          let ins = items.findIndex((x) => x.t0 > t0);
          if (ins < 0) ins = items.length;
          const prev = ins > 0 ? items[ins - 1] : null;
          const next = ins < items.length ? items[ins] : null;
          t0 = clamp(t0, prev ? prev.t1 + 0.01 : 0, state.dur);
          t1 = clamp(t1, 0, next ? next.t0 - 0.01 : state.dur);
          if (t1 - t0 >= 0.05) {
            const nItem = { t0: Math.round(t0 * 1e4) / 1e4, t1: Math.round(t1 * 1e4) / 1e4, text: "" };
            items.push(nItem);
            items.sort((a, b) => a.t0 - b.t0);
            extraSel = { bi: d.bi, idx: items.indexOf(nItem) };
            sendUpdate("extra_add");
          }
        }
      } else if (d.mode !== "create") {
        const it = L.items[d.idx];
        const moved = it && (it.t0 !== d.initT0 || it.t1 !== d.initT1 || it.t !== d.initT);
        if (moved) sendUpdate("extra_move");
      }
    }
    draw();
    drawSyl();
    try { cvSyl.releasePointerCapture(e.pointerId); } catch (err) { /* noop */ }
  }

  function onExtraDblClick(e, cx, bi) {
    const L = extraLayer(bi);
    if (!L || L.kind !== "interval") return;
    const t = tOf(cx);
    if (t < 0 || t > state.dur) return;
    const hit = extraHit(cx, bi);
    if (!hit || hit.edge !== null) return;
    const it = L.items[hit.idx];
    if (!it || t - it.t0 < 0.04 || it.t1 - t < 0.04) return;
    const tR = Math.round(t * 1e4) / 1e4;
    const left = { t0: it.t0, t1: tR, text: it.text };
    const right = { t0: tR, t1: it.t1, text: it.text };
    L.items.splice(hit.idx, 1, left, right);
    extraSel = { bi: bi, idx: hit.idx };
    sendUpdate("extra_split");
    draw();
    drawSyl();
  }

  // 把第 0 层（PY）的边界时刻 t 复制到下方各层：
  //   区间层（IntervalTier）→ 加一条边界（空层先铺满再切分）
  //   点层（TextTier）→ 加一个点标记
  function copyBoundaryDown(t) {
    const eps = 0.005, minW = 0.02;
    let changed = false;
    const layers = state.layers || [];
    for (let bi = 1; bi < layers.length; bi++) {
      const L = layers[bi];
      if (!L) continue;
      const items = L.items || [];
      if (L.kind === "point") {
        // 点层：在 t 处添加点（与手工加点一致：同一时刻已有点则跳过）
        const tR = Math.round(clamp(t, 0, state.dur) * 1e9) / 1e9;
        const dup = items.findIndex((x) => Math.abs(x.t - tR) <= 1e-9);
        if (dup >= 0) {
          if (!extraSel) extraSel = { bi: bi, idx: dup };
          continue;
        }
        const np = { t: tR, text: "" };
        items.push(np);
        items.sort((a, b) => a.t - b.t);
        if (!extraSel) extraSel = { bi: bi, idx: items.indexOf(np) };
        changed = true;
        continue;
      }
      if (L.kind !== "interval") continue;
      // 该层为空：先铺满整条时间轴，再在 t 处切分为两段
      if (!items.length) {
        if (t < 0.005 || t > state.dur - 0.005) continue;
        const tR = Math.round(t * 1e4) / 1e4;
        items.push({ t0: 0, t1: tR, text: "" }, { t0: tR, t1: Math.round(state.dur * 1e4) / 1e4, text: "" });
        if (!extraSel) extraSel = { bi: bi, idx: 0 };
        changed = true;
        continue;
      }
      // 已有边界（容差内）则跳过
      const exists = items.some((it) => Math.abs(it.t0 - t) <= eps || Math.abs(it.t1 - t) <= eps);
      if (exists) continue;
      const idx = items.findIndex((it) => it.t0 <= t + eps && it.t1 >= t - eps);
      if (idx < 0) continue;
      const it = items[idx];
      if (t - it.t0 < minW || it.t1 - t < minW) continue;
      const tR = Math.round(t * 1e4) / 1e4;
      items.splice(idx, 1, { t0: it.t0, t1: tR, text: it.text }, { t0: tR, t1: it.t1, text: it.text });
      if (!extraSel) extraSel = { bi: bi, idx: idx };
      changed = true;
    }
    if (changed) {
      sendUpdate("extra_boundary");
      draw();
      drawSyl();
    }
  }

  // ---------------- 键盘快捷键 ----------------
  function onKeyDown(e) {
    const tag = e.target && e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (!state.editable) return;

    // Delete/Backspace：优先删选中额外层项 / 音节，否则删选中音高点
    if (e.key === "Delete" || e.key === "Backspace") {
      if (extraSel) {
        const L = extraLayer(extraSel.bi);
        if (L && L.items && L.items[extraSel.idx]) {
          L.items.splice(extraSel.idx, 1);
          extraSel = null;
          sylText.value = "";
          sendUpdate("extra_del");
          draw();
          drawSyl();
          return;
        }
      }
      if (selectedSyl >= 0 && state.syllables[selectedSyl]) {
        state.syllables.splice(selectedSyl, 1);
        selectedSyl = -1;
        sylText.value = "";
        selBoundary = null;
        renumberDefaultLabels(); // 默认编号(音N)自动顺延
        sendUpdate("syl_del");
        draw();
        drawSyl();
        return;
      }
      if (selected >= 0 && selected < state.points.length) {
        state.points.splice(selected, 1);
        selected = -1;
        draw();
        sendUpdate("remove");
        return;
      }
      return;
    }

    // A / Insert：在鼠标位置插入音高点
    if (e.key === "a" || e.key === "A" || e.key === "Insert") {
      e.preventDefault();
      if (lastMouse.x < 0) return;
      const t = tOf(lastMouse.x);
      if (t < 0 || t > state.dur) return;
      const f = interpF0(t);
      if (f === null) return;
      insertPointAt(t, f0Clamp(fOf(lastMouse.y)));
      draw();
      sendUpdate("add");
      return;
    }

    // B：把选中的（或悬停的）PY 边界同步到下方各层（区间层加边界 / 点层加点）
    if (e.key === "b" || e.key === "B") {
      e.preventDefault();
      const bt = selBoundary !== null ? selBoundary
        : (lastSylMouse.x >= 0 ? nearestBoundary(lastSylMouse.x) : null);
      if (bt !== null) {
        hoverB = null;
        copyBoundaryDown(bt);
      }
      return;
    }

    if (selected < 0 || selected >= state.points.length) return;
    let semis = null;
    if (e.key === "ArrowUp") { semis = 1; e.preventDefault(); }
    else if (e.key === "ArrowDown") { semis = -1; e.preventDefault(); }
    else if (e.key === "PageUp") { semis = 5; e.preventDefault(); }
    else if (e.key === "PageDown") { semis = -5; e.preventDefault(); }
    else return;
    const p = state.points[selected];
    p[1] = Math.round(f0Clamp(p[1] * Math.pow(2, semis / 12)) * 1e3) / 1e3;
    draw();
    const rect = canvas.getBoundingClientRect();
    showTooltip(xOf(p[0]), yOf(p[1]), fmtTip(p[0], p[1]));
    sendUpdate("drag");
  }

  function onWheel(e) {
    e.preventDefault();
    // 波形 / 标注层（时间轴）缩放与平移；Ctrl+滚轮=音高刻度缩放
    const rect = (e.currentTarget === cvSyl ? cvSyl : canvas).getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const span = view.t1 - view.t0;
    const LO = -0.05, HI = state.dur + 0.05, FULL = HI - LO;
    const down = e.deltaY > 0;

    if (e.shiftKey) {
      // Shift+滚轮：时间轴前后平移（内容随滚轮方向移动）
      const step = span * 0.22 * (down ? 1 : -1);
      let t0 = view.t0 + step, t1 = view.t1 + step;
      if (span >= FULL - 1e-6) { t0 = LO; t1 = HI; }
      else {
        if (t0 < LO) { t1 += LO - t0; t0 = LO; }
        if (t1 > HI) { t0 -= t1 - HI; t1 = HI; }
      }
      view.t0 = t0;
      view.t1 = t1;
    } else if (!e.ctrlKey) {
      // 滚轮：波形与标注层（时间）缩放，光标位置保持不动
      const ns = span * (down ? 1.18 : 0.85); // 下滚=缩小视野/上滚=放大
      if (ns >= FULL - 1e-6) {
        view.t0 = LO;
        view.t1 = HI;
      } else {
        const r = ns / span;
        const t = tOf(cx);
        let t0 = t - (t - view.t0) * r;
        let t1 = t0 + ns;
        if (t0 < LO) { t0 = LO; t1 = t0 + ns; }
        if (t1 > HI) { t1 = HI; t0 = t1 - ns; }
        view.t0 = t0;
        view.t1 = t1;
      }
    } else {
      // Ctrl+滚轮：音高刻度（纵轴，对数）缩放
      const factor = down ? 1.18 : 0.85;
      const f = fOf(cy);
      const halfLog = ((view.hiLog - view.loLog) * factor) / 2;
      let newLoLog = log2(f) - halfLog, newHiLog = log2(f) + halfLog;
      newLoLog = Math.max(newLoLog, log2(40));
      newHiLog = Math.min(newHiLog, log2(2500));
      if (newHiLog - newLoLog < 0.1) return;
      view.loLog = newLoLog;
      view.hiLog = newHiLog;
    }
    draw();
    drawSyl();
  }

  // ---------------- 音频播放 ----------------
  function setupAudio(btn, token, urlGetter) {
    btn.addEventListener("click", () => {
      const url = urlGetter();
      if (!url) return;
      if (playToken === token) {
        if (audio.paused) audio.play();
        else audio.pause();
      } else {
        audio.src = url;
        playToken = token;
        audio.currentTime = 0;
        audio.play();
      }
    });
  }

  // ---------------- 选中段播放（IntervalTier 项 / PY 音节框） ----------------
  function currentSegment() {
    if (extraSel && extraSel.bi > 0) {
      const L = extraLayer(extraSel.bi);
      if (L && L.kind === "interval" && L.items && L.items[extraSel.idx]) {
        const it = L.items[extraSel.idx];
        if (it.t1 > it.t0) return { t0: it.t0, t1: it.t1 };
      }
    } else if (selectedSyl >= 0 && state.syllables[selectedSyl]) {
      const s = state.syllables[selectedSyl];
      if (s.t1 > s.t0) return { t0: s.t0, t1: s.t1 };
    }
    return null;
  }

  function updateSelButtons() {
    const ok = !!currentSegment() && !!state.urlEdit && !!state.urlOrig;
    btnPlaySel.disabled = !ok;
    btnPlaySelO.disabled = !ok;
  }

  function startSelPlay(token) {
    const seg = currentSegment();
    if (!seg) return;
    const url = token === "selE" ? state.urlEdit : state.urlOrig;
    if (!url) return;
    if (playToken === token && playing) { audio.pause(); return; }
    if (audio.src !== url) audio.src = url;
    playToken = token;
    selPlay = { token: token, t0: seg.t0, t1: seg.t1 };
    audio.currentTime = seg.t0;
    audio.play();
    onAudioState();
  }

  function onAudioState() {
    const u = ui();
    const isEdit = playToken === "edit";
    const isOrig = playToken === "orig";
    const isSelE = playToken === "selE";
    const isSelO = playToken === "selO";
    playing = !audio.paused && !audio.ended;
    btnPlay.textContent = isEdit && playing ? u.pause : u.play;
    btnPlayOrig.textContent = isOrig && playing ? u.pause : u.playOrig;
    btnPlaySel.textContent = isSelE && playing ? u.pauseSel : u.playSel;
    btnPlaySelO.textContent = isSelO && playing ? u.pauseSel : u.playSelO;
    if (playing && rafId === null) {
      rafId = requestAnimationFrame(loop);
    }
    if (!playing && rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
      draw();
      drawSyl();
    }
  }
  function loop() {
    if (!playing) { onAudioState(); return; }
    draw();
    drawSyl();
    rafId = requestAnimationFrame(loop);
  }

  // ---------------- 渲染事件（来自 Python） ----------------
  function onRender(args) {
    if (args.lang === "en") lang = "en"; else lang = "zh";
    applyLang();
    const incomingDuration = Number(args.duration) || 0;
    const changedDuration = Math.abs(incomingDuration - state.dur) > 1e-9;
    const changedRange =
      Math.abs(args.min_f0 - state.minF0) > 1e-9 ||
      Math.abs(args.max_f0 - state.maxF0) > 1e-9;
    state.minF0 = args.min_f0;
    state.maxF0 = args.max_f0;
    state.dur = incomingDuration;
    state.label = args.label || "音高曲线";
    state.editable = args.editable !== false;
    state.orig = args.original || [];
    state.wave = args.waveform || [];
    // url_*: 非空字符串=设置；"same"（仅 edit）=与 orig 相同；""=清除；null/undefined=保持上次
    function applyAudioUrl(kind, incoming) {
      const isOrig = kind === "orig";
      const prev = isOrig ? state.urlOrig : state.urlEdit;
      const playKinds = isOrig ? ["orig", "selO"] : ["edit", "selE"];
      let next = prev;
      if (incoming === "") {
        next = null;
      } else if (incoming === "same" && !isOrig) {
        next = state.urlOrig;
      } else if (typeof incoming === "string" && incoming.length) {
        next = incoming;
      }
      if (isOrig) state.urlOrig = next;
      else state.urlEdit = next;
      if (next !== prev && playKinds.indexOf(playToken) >= 0) {
        if (!next) {
          audio.pause();
          playToken = "none";
        } else if (playing) {
          const t = audio.currentTime;
          audio.src = next;
          audio.currentTime = t;
        }
      }
    }
    applyAudioUrl("orig", args.url_orig);
    applyAudioUrl("edit", args.url_edit);

    // 外部修改（Python 侧操作）→ 采纳新数据（规范化比较，避免无谓抖动）
    const incPts = canonPts(args.points || []);
    if (adoptPoints || incPts !== lastSentPointsJson) {
      state.points = (args.points || []).map((p) => [p[0], p[1]]);
      lastSentPointsJson = incPts;
      adoptPoints = false;
    }
    const incLayers = canonLayers(args.layers || []);
    if (adoptLayers || incLayers !== lastSentLayersJson) {
      const mapped = (args.layers || []).map((L) => ({
        name: L.name || "",
        kind: L.kind || "interval",
        def: L.def || "",
        items: (L.items || []).map((it) => ({
          text: it.text || "",
          t: it.t, t0: it.t0, t1: it.t1,
        })),
      }));
      if (!mapped.length || mapped[0].kind !== "interval") {
        mapped.unshift({ name: "PY", kind: "interval", def: "", items: [] });
      }
      state.layers = mapped;
      // 第 0 层（PY）与主轨共享同一数组，保证改动同步
      state.syllables = mapped[0].items;
      lastSentLayersJson = incLayers;
      lastSentSylJson = canonSyl(mapped[0].items);
      adoptLayers = false;
      adoptSyl = false;
      if (selectedSyl >= state.syllables.length) selectedSyl = state.syllables.length - 1;
      if (!(extraSel && mapped[extraSel.bi] && mapped[extraSel.bi].items
            && extraSel.idx >= 0 && extraSel.idx < mapped[extraSel.bi].items.length)) {
        extraSel = null;
      }
      if (selBoundary !== null) {
        const still = pyBoundaries().some((bt) => Math.abs(bt - selBoundary) <= 0.005);
        if (!still) selBoundary = null;
      }
      hoverB = null;
    }
    const incSyl = canonSyl(args.syllables || []);
    if (incSyl !== lastSentSylJson && !state.layers.length) {
      state.syllables = (args.syllables || []).map((s, i) => ({ id: "s" + i, text: s.text, t0: s.t0, t1: s.t1 }));
      state.layers = [{ name: "PY", kind: "interval", def: "", items: state.syllables }];
      lastSentSylJson = incSyl;
      adoptSyl = false;
      if (selectedSyl >= state.syllables.length) selectedSyl = state.syllables.length - 1;
    }
    // 保证下一次用户操作的 seq 大于 Python 已接受的最后序号
    const pySeq = Number(args.seq) || 0;
    if (pySeq >= seq) seq = pySeq + 1;

    // 标注模式与文本草稿：由 Python 持久化，重跑后恢复（避免每次操作后重置）
    if (typeof args.annotate === "boolean") {
      annotateMode = args.annotate;
      btnAnnotate.classList.toggle("active", annotateMode);
    }
    if (typeof args.draft === "string" && args.draft !== sylText.value) {
      sylText.value = args.draft;
    }

    sylDrag = null;
    titleEl.textContent = state.label || "音高曲线";
    btnPlay.disabled = !state.urlEdit;
    btnPlayOrig.disabled = !state.urlOrig;
    if (changedRange || changedDuration) fitView(); else { draw(); drawSyl(); }
    resize();
  }

  // ---------------- 启动 ----------------
  window.addEventListener("message", (ev) => {
    const data = ev.data || {};
    if (data.type === "streamlit:render") {
      injectTheme(data.theme);
      onRender(data.args || {});
    }
  });

  function injectTheme(t) {
    if (!t) return;
    let style = document.getElementById("streamlit-theme-vars");
    if (!style) {
      style = document.createElement("style");
      style.id = "streamlit-theme-vars";
      document.head.appendChild(style);
    }
    style.innerHTML =
      `:root{` +
      `--primary-color:${t.primaryColor};` +
      `--background-color:${t.backgroundColor};` +
      `--secondary-background-color:${t.secondaryBackgroundColor};` +
      `--text-color:${t.textColor};` +
      `--font:${t.font};}` +
      `body{background-color:var(--background-color);color:var(--text-color);}`;
  }

  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerUp);
  canvas.addEventListener("dblclick", onDblClick);
  canvas.addEventListener("wheel", onWheel, { passive: false });
  cvSyl.addEventListener("wheel", onWheel, { passive: false });
  cvSyl.addEventListener("pointerdown", onSylPointerDown);
  cvSyl.addEventListener("pointermove", onSylPointerMove);
  cvSyl.addEventListener("pointerup", onSylPointerUp);
  cvSyl.addEventListener("pointercancel", onSylPointerUp);
  cvSyl.addEventListener("dblclick", onSylDblClick);
  window.addEventListener("keydown", onKeyDown);
  chkOrig.addEventListener("change", () => { draw(); drawSyl(); });
  btnFit.addEventListener("click", fitView);
  btnAnnotate.addEventListener("click", () => {
    annotateMode = !annotateMode;
    btnAnnotate.classList.toggle("active", annotateMode);
    if (!annotateMode) { sylDrag = null; selectedSyl = -1; }
    drawSyl();
    sendUpdate("annotate");   // 通知 Python 持久化标注模式
  });
  sylText.addEventListener("change", () => {
    const txt = sylText.value.trim();
    if (extraSel) {
      const L = extraLayer(extraSel.bi);
      if (L && L.items && L.items[extraSel.idx]) {
        L.items[extraSel.idx].text = txt;
      }
    } else if (selectedSyl >= 0 && state.syllables[selectedSyl]) {
      state.syllables[selectedSyl].text = txt;
    }
    if (sylDrag || extraDrag) {
      // 拖拽进行中（输入框失焦触发 change）：本地已应用，不发送以免中断拖拽
      draw();
      drawSyl();
      return;
    }
    sendUpdate("syl_text");   // 同时持久化草稿文本
    draw();
    drawSyl();
  });
  audio.addEventListener("play", onAudioState);
  audio.addEventListener("pause", onAudioState);
  audio.addEventListener("ended", onAudioState);
  audio.addEventListener("timeupdate", () => {
    if ((playToken === "selE" || playToken === "selO") && selPlay && !audio.paused) {
      if (audio.currentTime >= selPlay.t1 - 0.003) {
        audio.pause();
        audio.currentTime = selPlay.t1; // 停在段末
      }
    }
    if (playing) { draw(); drawSyl(); }
  });
  setupAudio(btnPlay, "edit", () => state.urlEdit);
  setupAudio(btnPlayOrig, "orig", () => state.urlOrig);
  btnPlaySel.addEventListener("click", () => startSelPlay("selE"));
  btnPlaySelO.addEventListener("click", () => startSelPlay("selO"));

  new ResizeObserver(() => resize()).observe(wrap);

  SCL.ready();
  resize();
})();
