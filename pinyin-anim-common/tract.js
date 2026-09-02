/* Shared sagittal-tract drawing + particle airflow for 声母/韵母 pages. */
(function (global) {
  'use strict';

  const W = 780, H = 560;
  const VEL_UP = { x: 492, y: 298 };
  const VEL_DOWN = { x: 452, y: 258 };
  const VEL_PIVOT = { x: 432, y: 240 };

  const TONGUE_BOTTOM = [[470, 412], [448, 450], [376, 472], [300, 474], [242, 464], [216, 438], [210, 414]];
  const NASAL_PATH = [[480, 262], [452, 246], [420, 228], [372, 216], [330, 206], [282, 204], [240, 212], [214, 218], [198, 228], [188, 240], [196, 252], [238, 260], [290, 258], [350, 246], [400, 240], [430, 236], [458, 246]];

  const ROUTE_ORAL = [[516, 545], [518, 470], [512, 400], [500, 360], [470, 340], [430, 330], [370, 318], [310, 314], [255, 322], [212, 334], [178, 346], [128, 356]];
  const ROUTE_NASAL = [[516, 545], [518, 470], [512, 400], [500, 330], [470, 280], [430, 240], [370, 212], [300, 200], [240, 212], [205, 232], [182, 248], [158, 266]];
  const ROUTE_LATERAL = [[516, 545], [518, 470], [512, 400], [500, 360], [468, 342], [425, 325], [370, 305], [312, 292], [272, 292], [240, 290], [212, 306], [186, 330], [172, 344], [130, 350], [96, 356]];

  function pt(p) { return { x: p[0], y: p[1] }; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function lerpPt(a, b, t) { return { x: lerp(a[0], b[0], t), y: lerp(a[1], b[1], t) }; }
  function easeIO(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }

  function smoothPath(ctx, pts, close) {
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length - 1; i++) {
      const mx = (pts[i].x + pts[i + 1].x) / 2, my = (pts[i].y + pts[i + 1].y) / 2;
      ctx.quadraticCurveTo(pts[i].x, pts[i].y, mx, my);
    }
    const last = pts[pts.length - 1];
    ctx.quadraticCurveTo(pts[pts.length - 2].x, pts[pts.length - 2].y, last.x, last.y);
    if (close) ctx.closePath();
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function blendPath(path, p, poses) {
    const P = Math.max(0, Math.min(1, p));
    const last = path[path.length - 1];
    if (P <= path[0][1]) return poses[path[0][0]].map(function (q) { return q.slice(); });
    if (P >= last[1]) return poses[last[0]].map(function (q) { return q.slice(); });
    for (let i = 0; i < path.length - 1; i++) {
      const k1 = path[i][0], f1 = path[i][1], k2 = path[i + 1][0], f2 = path[i + 1][1];
      if (P >= f1 && P <= f2) {
        const t = (P - f1) / ((f2 - f1) || 1);
        const a = poses[k1], b = poses[k2];
        return a.map(function (pp, j) { return [lerp(pp[0], b[j][0], t), lerp(pp[1], b[j][1], t)]; });
      }
    }
    return poses[last[0]].map(function (q) { return q.slice(); });
  }

  function currentKey(path, p) {
    const P = Math.max(0, Math.min(1, p));
    for (let i = 0; i < path.length - 1; i++) {
      const k1 = path[i][0], f1 = path[i][1], k2 = path[i + 1][0], f2 = path[i + 1][1];
      if (P >= f1 && P <= f2) {
        const t = (P - f1) / ((f2 - f1) || 1);
        return t < 0.5 ? k1 : k2;
      }
    }
    return path[path.length - 1][0];
  }

  /* ---------- particles ---------- */
  class Particles {
    constructor() { this.reset(); }
    reset() {
      this.list = [];
      this.pressure = 0;
      this.tick = 0;
      this.released = false;
      this.puff = null;
    }
    segLen(a, b) { return Math.hypot(b[0] - a[0], b[1] - a[1]); }
    spawnStream(spec, nasal, boost) {
      let route;
      if (nasal) route = ROUTE_NASAL;
      else if (spec.lateral) route = ROUTE_LATERAL;
      else {
        route = ROUTE_ORAL.slice();
        const gp = spec.gapPoint;
        if (gp) {
          let idx = route.length;
          for (let i = 0; i < route.length; i++) {
            if (route[i][0] < gp.x) { idx = i; break; }
          }
          if (idx > 0 && idx < route.length) route.splice(idx, 0, [gp.x, gp.y]);
        }
      }
      this.list.push({
        kind: 'stream', route: route, seg: 0, t: Math.random() * 0.5,
        base: 175 * (boost || 1), zone: spec.zone || [150, 240], life: 4, j: 0
      });
    }
    spawnBurstAt(x, y, spec) {
      const mouth = { x: 184, y: 338 + (spec.jaw || 0) * 16 };
      const dx = mouth.x - x, dy = mouth.y - y, len = Math.hypot(dx, dy) || 1;
      let ux = dx / len, uy = dy / len;
      if (len < 30) { ux = -1; uy = 0; }
      const strong = !!spec.asp;
      const n = strong ? 60 : 16;
      for (let i = 0; i < n; i++) {
        const sp = (strong ? 260 : 130) + Math.random() * (strong ? 340 : 150);
        const ang = (Math.random() - 0.5) * (strong ? 1.1 : 0.6);
        const c = Math.cos(ang), sn = Math.sin(ang);
        this.list.push({
          kind: 'burst', x: x, y: y,
          vx: (ux * c - uy * sn) * sp, vy: (uy * c + ux * sn) * sp,
          life: 0.8, color: strong ? '#ffd166' : '#7fd8ff'
        });
      }
      if (strong) this.puff = { x: mouth.x, y: mouth.y, r: 6, life: 0.5 };
    }
    burst(spec, closurePt) {
      for (let i = 0; i < this.list.length; i++) {
        const p = this.list[i];
        if (p.kind === 'pressure') {
          p.kind = 'burst';
          p.color = spec.asp ? '#ffd166' : '#7fd8ff';
          const sp = (spec.asp ? 420 : 240) + Math.random() * 180;
          p.vx = -sp * (0.85 + Math.random() * 0.3);
          p.vy = (Math.random() - 0.5) * 120;
          p.life = 0.7;
        }
      }
      const cp = closurePt || { x: 200, y: 330 };
      this.spawnBurstAt(cp.x, cp.y, spec);
    }
    update(dt, spec) {
      const list = this.list;
      const phase = spec.phase;
      for (let i = list.length - 1; i >= 0; i--) {
        const p = list[i];
        p.life -= dt;
        if (p.life <= 0) { list.splice(i, 1); continue; }
        if (p.kind === 'stream') {
          const route = p.route;
          const a = route[p.seg], b = route[p.seg + 1];
          const sl = this.segLen(a, b) || 1;
          let sp = p.base;
          const x = a[0] + (b[0] - a[0]) * p.t;
          if (x > p.zone[0] && x < p.zone[1]) {
            sp *= 2.9;
            p.j = (Math.random() - 0.5) * (spec.lateral ? 22 : 10);
          }
          p.t += sp * dt / sl;
          if (p.t >= 1) {
            p.seg++;
            p.t = 0;
            if (p.seg >= route.length - 1) { list.splice(i, 1); continue; }
          }
        } else if (p.kind === 'burst') {
          p.vx *= Math.pow(0.2, dt);
          p.vy *= Math.pow(0.2, dt);
          p.x += p.vx * dt;
          p.y += p.vy * dt;
        }
      }
      this.tick += dt;
      const mode = spec.mode || 'consonant';
      if (mode === 'vowel') {
        const nasalOn = !!spec.nasalOn;
        if (phase === 'B' || phase === 'A') {
          const rate = nasalOn ? 0.020 : 0.022;
          while (this.tick > rate) {
            this.spawnStream({ lateral: false, zone: [180, 260], gapPoint: null }, nasalOn, nasalOn ? 0.85 : 1);
            this.tick -= rate;
          }
        } else if (phase === 'C') {
          while (this.tick > 0.05) {
            this.spawnStream({ lateral: false, zone: [180, 260], gapPoint: null }, nasalOn, 0.5);
            this.tick -= 0.05;
          }
        } else this.tick = 0;
      } else {
        const isFric = spec.manner === '清擦音' || spec.manner === '浊擦音';
        const isStopLike = (spec.group || '').indexOf('stop') === 0 || (spec.group || '').indexOf('affr') === 0;
        if (phase === 'B') {
          if (isFric || spec.lateral || spec.semi) {
            while (this.tick > 0.010) { this.spawnStream(spec, false, spec.lateral ? 0.95 : 1); this.tick -= 0.010; }
          } else if (spec.nasal) {
            while (this.tick > 0.017) { this.spawnStream(spec, true, 0.9); this.tick -= 0.017; }
          } else if (isStopLike) {
            if (this.pressure < 48) this.pressure = Math.min(48, this.pressure + dt * 150);
            const n = Math.floor(this.pressure);
            let pc = 0;
            for (let qi = 0; qi < list.length; qi++) if (list[qi].kind === 'pressure') pc++;
            const zone = spec.zone || [150, 240];
            const px0 = Math.max(220, zone[0] + 20);
            const px1 = Math.min(420, zone[1] + 40);
            while (pc < n) {
              this.list.push({
                kind: 'pressure',
                x: px0 + Math.random() * Math.max(30, px1 - px0),
                y: 318 + Math.random() * 40,
                hx: px0 + Math.random() * Math.max(30, px1 - px0),
                hy: 318 + Math.random() * 40,
                life: 2, color: '#7fd8ff'
              });
              pc++;
            }
          }
        } else if (phase === 'C') {
          if (isStopLike) {
            if (!this.released) { this.released = true; this.burst(spec, spec.closurePt); }
            if ((spec.group || '').indexOf('affr') === 0) {
              while (this.tick > 0.025) { this.spawnStream(spec, false, 0.7); this.tick -= 0.025; }
            }
          } else if (isFric || spec.lateral || spec.semi) {
            while (this.tick > 0.035) { this.spawnStream(spec, false, 0.5); this.tick -= 0.035; }
          }
        } else if (phase === 'A' && (isFric || spec.semi)) {
          while (this.tick > 0.04) { this.spawnStream(spec, false, 0.4); this.tick -= 0.04; }
        }
        if (phase !== 'B' && phase !== 'C') this.tick = 0;
      }
      for (let i = 0; i < list.length; i++) {
        const p = list[i];
        if (p.kind === 'pressure') {
          p.x += (p.hx - p.x) * 2.2 * dt + (Math.random() - 0.5) * 2;
          p.y += (p.hy - p.y) * 2.2 * dt + (Math.random() - 0.5) * 2;
        }
      }
      if (this.puff) {
        this.puff.r += 220 * dt;
        this.puff.life -= dt;
        if (this.puff.life <= 0) this.puff = null;
      }
    }
    draw(ctx, inv) {
      for (let i = 0; i < this.list.length; i++) {
        const p = this.list[i];
        let x, y, r = 2.6 * inv;
        if (p.kind === 'stream') {
          const a = p.route[p.seg], b = p.route[p.seg + 1];
          x = a[0] + (b[0] - a[0]) * p.t;
          y = a[1] + (b[1] - a[1]) * p.t + p.j;
        } else {
          x = p.x; y = p.y;
          r = p.kind === 'burst' ? 3.8 * inv : 2.9 * inv;
        }
        const alpha = Math.min(1, p.life * 2.2);
        const col = p.color || '#7fd8ff';
        ctx.globalAlpha = alpha * 0.28;
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.arc(x, y, r * 2.4, 0, 6.283); ctx.fill();
        ctx.globalAlpha = alpha;
        ctx.beginPath(); ctx.arc(x, y, r, 0, 6.283); ctx.fill();
      }
      if (this.puff) {
        ctx.globalAlpha = Math.max(0, this.puff.life) * 0.7;
        ctx.strokeStyle = '#ffd166';
        ctx.lineWidth = 2.5 * inv;
        ctx.beginPath(); ctx.arc(this.puff.x, this.puff.y, this.puff.r, 0, 6.283); ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }
  }

  function chip(ctx, x, y, w, h, text, inv) {
    ctx.fillStyle = 'rgba(30,25,41,.92)';
    roundRect(ctx, x, y, w, h, h / 2); ctx.fill();
    ctx.strokeStyle = 'rgba(255,177,104,.8)'; ctx.lineWidth = 1.2 * inv; ctx.stroke();
    ctx.fillStyle = '#ffb86b';
    ctx.font = '600 ' + (12 * inv) + 'px "Segoe UI","PingFang SC",sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(text, x + w / 2, y + h / 2 + 0.5);
  }

  function drawHead(ctx, jaw, inv) {
    const j = (jaw || 0) * 26;
    const head = new Path2D();
    head.moveTo(302, 64);
    head.bezierCurveTo(368, 56, 470, 58, 522, 80);
    head.bezierCurveTo(570, 100, 604, 136, 618, 184);
    head.bezierCurveTo(628, 222, 636, 272, 643, 322);
    head.bezierCurveTo(649, 372, 652, 434, 654, 486);
    head.lineTo(654, 544 + j * 0.25);
    head.lineTo(336, 544 + j);
    head.bezierCurveTo(300, 522 + j, 268, 474 + j, 240, 436 + j);
    head.bezierCurveTo(216, 404 + j * 0.7, 200, 384 + j * 0.45, 192, 366 + j * 0.25);
    head.bezierCurveTo(186, 352, 181, 342, 179, 330);
    head.bezierCurveTo(177, 318, 177, 308, 180, 298);
    head.bezierCurveTo(178, 288, 175, 278, 173, 268);
    head.bezierCurveTo(171, 256, 167, 248, 166, 240);
    head.bezierCurveTo(168, 228, 174, 220, 182, 214);
    head.bezierCurveTo(196, 205, 212, 191, 228, 179);
    head.bezierCurveTo(240, 170, 252, 156, 262, 138);
    head.bezierCurveTo(274, 116, 286, 88, 302, 64);
    head.closePath();
    const hg = ctx.createLinearGradient(160, 60, 600, 540);
    hg.addColorStop(0, '#262036'); hg.addColorStop(1, '#1a1526');
    ctx.fillStyle = hg; ctx.fill(head);
    ctx.strokeStyle = '#3d3552'; ctx.lineWidth = 1.6 * inv; ctx.stroke(head);
  }

  function drawLips(ctx, lip, inv) {
    const jaw = lip.jaw || 0;
    const yM = 336 + jaw * 16;
    const hu = lip.g / 2;
    const off = lip.round ? 10 : 0;
    if (lip.raise) {
      const up = ctx.createLinearGradient(150, 288, 215, 308);
      up.addColorStop(0, '#8a4567'); up.addColorStop(1, '#b06385');
      ctx.fillStyle = up;
      ctx.beginPath();
      ctx.moveTo(156, 296);
      ctx.quadraticCurveTo(180, 290, 214, 288);
      ctx.quadraticCurveTo(208, 300, 196, 302);
      ctx.quadraticCurveTo(176, 304, 158, 302);
      ctx.closePath(); ctx.fill();
      const dn = ctx.createLinearGradient(150, 300, 215, 352);
      dn.addColorStop(0, '#c07a9c'); dn.addColorStop(1, '#7c3a58');
      ctx.fillStyle = dn;
      ctx.beginPath();
      ctx.moveTo(158, 304);
      ctx.quadraticCurveTo(182, 298, 212, 300);
      ctx.quadraticCurveTo(216, 316, 210, 330);
      ctx.quadraticCurveTo(200, 348, 186, 354);
      ctx.quadraticCurveTo(168, 356, 156, 348);
      ctx.quadraticCurveTo(150, 338, 158, 304);
      ctx.closePath(); ctx.fill();
      return;
    }
    if (lip.g < 1.8) {
      const body = ctx.createLinearGradient(150, yM - 16, 215, yM + 18);
      body.addColorStop(0, '#8a4567'); body.addColorStop(0.5, '#c07a9c'); body.addColorStop(1, '#7c3a58');
      ctx.fillStyle = body;
      ctx.beginPath();
      ctx.ellipse(176 - off * 0.3, yM, 24, 9.5, 0, 0, 6.283);
      ctx.fill();
      ctx.strokeStyle = 'rgba(80,30,50,.55)';
      ctx.lineWidth = 1.2 * inv;
      ctx.beginPath();
      ctx.moveTo(156 - off * 0.2, yM);
      ctx.quadraticCurveTo(176, yM + 1, 196 - off * 0.2, yM);
      ctx.stroke();
      return;
    }
    const upperBottom = yM - hu;
    const lowerTop = yM + hu;
    const up = ctx.createLinearGradient(150, 296, 215, 318);
    up.addColorStop(0, '#8a4567'); up.addColorStop(1, '#b06385');
    ctx.fillStyle = up;
    ctx.beginPath();
    ctx.moveTo(156 - off, 306);
    ctx.quadraticCurveTo(180, 300, 214 - off, 298);
    ctx.quadraticCurveTo(206 - off, upperBottom + 4, 196 - off, upperBottom + 2);
    ctx.quadraticCurveTo(176 - off, upperBottom - 2, 158 - off, upperBottom + 6);
    ctx.quadraticCurveTo(152 - off, 306, 156 - off, 306);
    ctx.closePath(); ctx.fill();
    const dn = ctx.createLinearGradient(150, 340, 215, 364);
    dn.addColorStop(0, '#b06385'); dn.addColorStop(1, '#7c3a58');
    ctx.fillStyle = dn;
    ctx.beginPath();
    ctx.moveTo(158 - off, lowerTop + 2);
    ctx.quadraticCurveTo(178 - off, lowerTop - 2, 198 - off, lowerTop + 2);
    ctx.quadraticCurveTo(210 - off, lowerTop + 6, 214 - off, 344 + jaw * 16);
    ctx.quadraticCurveTo(206 - off, 356 + jaw * 16, 192 - off, 360 + jaw * 16);
    ctx.quadraticCurveTo(172 - off, 362 + jaw * 16, 158 - off, 352 + jaw * 14);
    ctx.quadraticCurveTo(150 - off, 346 + jaw * 10, 158 - off, lowerTop + 2);
    ctx.closePath(); ctx.fill();
    if (lip.round) {
      ctx.fillStyle = '#0e0c16';
      ctx.beginPath(); ctx.ellipse(170 - off, yM, 8, Math.max(3, hu * 0.7), 0, 0, 6.283); ctx.fill();
    }
  }

  function drawFolds(ctx, voiced, time, inv) {
    const gap = voiced ? Math.abs(Math.sin(time * 9)) * 10 : 10;
    const lx = 512 + gap / 2, rx = 538 - gap / 2;
    const glow = ctx.createRadialGradient(525, 447, 2, 525, 447, 26);
    glow.addColorStop(0, voiced ? 'rgba(255,177,104,.5)' : 'rgba(255,177,104,.08)');
    glow.addColorStop(1, 'rgba(255,177,104,0)');
    ctx.fillStyle = glow;
    ctx.beginPath(); ctx.arc(525, 447, 26 * inv, 0, 6.283); ctx.fill();
    ctx.strokeStyle = '#ffb86b'; ctx.lineWidth = 2.4 * inv; ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(512, 458); ctx.quadraticCurveTo(508, 450, lx, 446);
    ctx.moveTo(538, 458); ctx.quadraticCurveTo(542, 450, rx, 446);
    ctx.stroke();
    ctx.lineCap = 'butt';
  }

  function drawLabels(ctx, inv, jaw, lang) {
    const j = (jaw || 0) * 10;
    const L = lang === 'en' ? {
      nasal:'Nasal cavity', palate:'Hard palate', soft:'Soft palate', alveolar:'Alveolar ridge', lips:'Lips', pharynx:'Pharynx', tongue:'Tongue', folds:'Vocal folds', trachea:'Trachea'
    } : {
      nasal:'鼻腔', palate:'硬腭', soft:'软腭', alveolar:'齿龈', lips:'双唇', pharynx:'咽腔', tongue:'舌', folds:'声带', trachea:'气管'
    };
    const items = [
      [L.nasal, 295, 196, 272, 212], [L.palate, 338, 228, 325, 250], [L.soft, 478, 262, 448, 272],
      [L.alveolar, 246, 268, 233, 284], [L.lips, 118, 336 + j, 168, 330 + j], [L.pharynx, 596, 340, 556, 352],
      [L.tongue, 336, 436 + j, 320, 414 + j], [L.folds, 598, 450, 538, 448], [L.trachea, 598, 508, 552, 506]
    ];
    ctx.font = (10.5 * inv) + 'px "Segoe UI","PingFang SC",sans-serif';
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      ctx.strokeStyle = 'rgba(154,144,173,.45)'; ctx.lineWidth = 1 * inv;
      ctx.beginPath(); ctx.moveTo(it[1], it[2]); ctx.lineTo(it[3], it[4]); ctx.stroke();
      ctx.fillStyle = 'rgba(154,144,173,.9)';
      ctx.fillText(it[0], it[1] - 4, it[2]);
    }
  }

  function drawScene(ctx, state) {
    const inv = state.inv;
    const jaw = (state.lip && state.lip.jaw) || 0;
    const surf = state.tongueSurf;
    const ci = state.contactIdx;
    const drawSurf = [];
    for (let i = 0; i < surf.length; i++) {
      drawSurf.push(surf[i]);
      if (ci !== undefined && ci !== null && i === ci) drawSurf.push(surf[i]);
    }
    const vel = state.vel;
    const lip = state.lip;

    const bg = ctx.createRadialGradient(390, 120, 60, 390, 280, 520);
    bg.addColorStop(0, '#12101c'); bg.addColorStop(1, '#0b0a10');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);

    drawHead(ctx, jaw, inv);

    const nasal = NASAL_PATH.map(pt);
    ctx.fillStyle = '#0e0c16';
    smoothPath(ctx, nasal, true); ctx.fill();
    ctx.strokeStyle = 'rgba(106,94,140,.55)'; ctx.lineWidth = 1.2 * inv; ctx.stroke();

    const jY = jaw * 10;
    const bottom = TONGUE_BOTTOM.slice(1).map(function (p) { return { x: p[0], y: p[1] + jY }; });
    const tonguePts = drawSurf.concat(bottom);
    const tg = ctx.createLinearGradient(200, 250, 460, 470);
    tg.addColorStop(0, '#d97aa8'); tg.addColorStop(1, '#a14a76');
    ctx.fillStyle = tg;
    smoothPath(ctx, tonguePts, true); ctx.fill();
    ctx.strokeStyle = '#ff9ec2'; ctx.lineWidth = 1.4 * inv; ctx.stroke();

    const cav = [
      { x: 176, y: 322 }, { x: 202, y: 310 }, { x: 230, y: 286 }, { x: 300, y: 252 }, { x: 398, y: 242 },
      { x: VEL_PIVOT.x, y: VEL_PIVOT.y }, vel,
      { x: 540, y: 305 }, { x: 560, y: 360 }, { x: 564, y: 440 }, { x: 564, y: 540 },
      { x: 520, y: 540 }, { x: 520, y: 445 }, { x: 505, y: 330 }
    ].concat(drawSurf.slice().reverse()).concat([{ x: 188, y: 350 + jY }]);
    ctx.fillStyle = '#0e0c16';
    smoothPath(ctx, cav, true); ctx.fill();
    if (vel.y > 272) {
      ctx.fillStyle = '#0e0c16';
      ctx.beginPath();
      ctx.moveTo(480, 262);
      ctx.quadraticCurveTo(500, 290, 505, 300);
      ctx.lineTo(468, 300);
      ctx.quadraticCurveTo(470, 280, 480, 262);
      ctx.closePath(); ctx.fill();
    }

    ctx.strokeStyle = 'rgba(139,124,178,.75)'; ctx.lineWidth = 1.5 * inv;
    ctx.beginPath();
    ctx.moveTo(176, 322);
    ctx.quadraticCurveTo(202, 310, 230, 286);
    ctx.quadraticCurveTo(300, 252, 398, 242);
    ctx.lineTo(432, 240);
    ctx.stroke();

    const vg = ctx.createLinearGradient(430, 240, 490, 300);
    vg.addColorStop(0, '#4a3f66'); vg.addColorStop(1, '#352c4d');
    ctx.fillStyle = vg;
    ctx.beginPath();
    ctx.moveTo(VEL_PIVOT.x, VEL_PIVOT.y);
    ctx.lineTo(vel.x, vel.y);
    ctx.quadraticCurveTo((vel.x + VEL_PIVOT.x) / 2 + 4, (vel.y + VEL_PIVOT.y) / 2, VEL_PIVOT.x, VEL_PIVOT.y + 4);
    ctx.closePath(); ctx.fill();
    ctx.strokeStyle = 'rgba(139,124,178,.6)'; ctx.lineWidth = 1.2 * inv; ctx.stroke();

    ctx.fillStyle = 'rgba(216,210,230,.5)';
    const upperTeeth = [[200, 298, 11, 16], [214, 294, 11, 15], [228, 290, 11, 14], [242, 288, 10, 13]];
    for (let i = 0; i < upperTeeth.length; i++) {
      const t = upperTeeth[i];
      roundRect(ctx, t[0], t[1], t[2], t[3], 2); ctx.fill();
    }
    const showLower = !lip.raise && lip.g > 4.5;
    if (showLower) {
      ctx.fillStyle = 'rgba(216,210,230,.42)';
      const ly = 348 + jaw * 22;
      const lowerTeeth = [[176, ly, 10, 13], [188, ly + 2, 10, 12], [200, ly + 3, 9, 11]];
      for (let i = 0; i < lowerTeeth.length; i++) {
        const t = lowerTeeth[i];
        roundRect(ctx, t[0], t[1], t[2], t[3], 2); ctx.fill();
      }
    }

    drawLips(ctx, lip, inv);

    ctx.fillStyle = 'rgba(46,38,66,.8)';
    roundRect(ctx, 505, 436, 62, 34, 8); ctx.fill();
    ctx.strokeStyle = 'rgba(106,94,140,.5)'; ctx.lineWidth = 1.2 * inv; ctx.stroke();
    drawFolds(ctx, !!state.voicedOn, state.time || 0, inv);

    if (state.particles) state.particles.draw(ctx, inv);

    if (state.highlight && state.highlight.act > 0.05) {
      const gp = state.highlight;
      const pulse = 0.65 + 0.35 * Math.sin((state.time || 0) * 7);
      const gg = ctx.createRadialGradient(gp.x, gp.y, 1, gp.x, gp.y, 15 * inv);
      gg.addColorStop(0, 'rgba(127,216,255,' + (0.55 * gp.act * pulse) + ')');
      gg.addColorStop(1, 'rgba(127,216,255,0)');
      ctx.fillStyle = gg;
      ctx.beginPath(); ctx.arc(gp.x, gp.y, 15 * inv, 0, 6.283); ctx.fill();
      ctx.fillStyle = 'rgba(127,216,255,' + (0.95 * gp.act) + ')';
      ctx.beginPath(); ctx.arc(gp.x, gp.y, 2.4 * inv, 0, 6.283); ctx.fill();
    }

    if (state.phaseName && !state.compact) {
      chip(ctx, W - 118, 16, 96, 26, state.phaseName, inv);
    } else if (state.phaseName && state.compact) {
      chip(ctx, W - 108, 12, 88, 22, state.phaseName, inv);
    }

    if (!state.compact) {
      ctx.font = (11 * inv) + 'px "Segoe UI","PingFang SC",sans-serif';
      ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      ctx.fillStyle = 'rgba(154,144,173,.85)';
      if (state.footerLeft) ctx.fillText(state.footerLeft, 14, H - 14);
      ctx.textAlign = 'right';
      ctx.fillStyle = 'rgba(154,144,173,.7)';
      if (state.footerRight) ctx.fillText(state.footerRight, W - 14, H - 14);
      if (state.labels) drawLabels(ctx, inv, jaw, state.lang);
    }
  }

  function drawFrontView(ctx, w, h, lp, u, title, roundText, lang) {
    ctx.clearRect(0, 0, w, h);
    const bg = ctx.createRadialGradient(w / 2, h / 2, 8, w / 2, h / 2, 110);
    bg.addColorStop(0, '#161322'); bg.addColorStop(1, '#0b0a10');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    const openW = Math.max(2, lp.w * u), openH = Math.max(2, lp.h * u);
    const roundF = lp.round * u;
    ctx.strokeStyle = 'rgba(154,144,173,.35)'; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.ellipse(w / 2, h / 2 + 3, 96, 64, 0, 0, 6.283); ctx.stroke();
    const prot = roundF * 11;
    const cx = w / 2, cy = h / 2 + 3;
    ctx.fillStyle = '#b06385';
    if (roundF > 0.35) {
      const ringW = 30 + prot, ringH = 15 + prot * 0.8;
      ctx.beginPath(); ctx.ellipse(cx, cy, ringW, ringH, 0, 0, 6.283); ctx.fill();
      ctx.strokeStyle = 'rgba(255,158,194,.55)'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.ellipse(cx, cy, ringW - 4, ringH - 4, 0, 0, 6.283); ctx.stroke();
      ctx.fillStyle = '#0e0c16';
      ctx.beginPath(); ctx.ellipse(cx, cy, openW / 2 + 3, openH / 2 + 3, 0, 0, 6.283); ctx.fill();
    } else {
      const lw = 26 + prot;
      ctx.beginPath(); ctx.ellipse(cx, cy - openH / 2 - 2, lw, 9 + prot, 0, Math.PI, 0); ctx.fill();
      ctx.beginPath(); ctx.ellipse(cx, cy + openH / 2 + 2, lw, 9 + prot, 0, 0, Math.PI); ctx.fill();
      ctx.fillStyle = '#0e0c16';
      roundRect(ctx, cx - openW / 2, cy - openH / 2, openW, openH, Math.min(8, openH / 2)); ctx.fill();
    }
    ctx.font = '12px "Segoe UI","PingFang SC",sans-serif';
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillStyle = '#e8e2ef';
    if (title) ctx.fillText(title, 12, 16);
    ctx.font = '10px "Segoe UI","PingFang SC",sans-serif';
    ctx.fillStyle = 'rgba(154,144,173,.85)';
    ctx.fillText(roundText || (lang === 'en' ? (roundF > 0.35 ? 'Rounded' : 'Spread / neutral') : (roundF > 0.35 ? '圆唇' : '展唇/自然')), 12, 32);
  }

  /* 教学用三峰示意图：三峰高度接近，避免真实频谱倾斜把高 F2/F3 压没。 */
  function schematicAmp(f, fm) {
    function peak(hz, Fn, a) {
      const bw = 70 + Fn * 0.08;
      const x = (hz - Fn) / bw;
      return a * Math.exp(-0.5 * x * x);
    }
    let y = peak(f, fm.f1, 1) + peak(f, fm.f2, 0.92) + peak(f, fm.f3 || 2500, 0.8);
    if (fm.nasal) y += peak(f, 250, 0.42);
    return y;
  }

  function drawFormantSchematic(ctx, w, h, state) {
    ctx.clearRect(0, 0, w, h);
    const bg = ctx.createLinearGradient(0, 0, 0, h);
    bg.addColorStop(0, '#161322');
    bg.addColorStop(1, '#0b0a10');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    const fm = state.fm || { f1: 500, f2: 1500, f3: 2500 };
    const f0 = state.f0 == null ? 158 : state.f0;
    const FMIN = 0, FMAX = 3400;
    const col = { f1: '#ffb86b', f2: '#7fd8ff', f3: '#ff7aa8' };
    const padL = 36, padR = 8, hudH = 18, foot = 14;
    const hasTrack = typeof state.formantAt === 'function';
    const trackH = hasTrack ? Math.max(48, Math.floor(h * 0.34)) : 0;
    const specT = 6 + hudH;
    const specB = h - (hasTrack ? trackH + foot + 4 : foot);
    const specL = padL, specR = w - padR;
    const trackT = specB + 14;
    const trackB = h - foot;
    const trackL = padL, trackR = w - padR;

    function specX(f) {
      return specL + (Math.max(FMIN, Math.min(FMAX, f)) - FMIN) / (FMAX - FMIN) * (specR - specL);
    }

    const peaks = [
      { k: 'F1', f: fm.f1, c: col.f1 },
      { k: 'F2', f: fm.f2, c: col.f2 },
      { k: 'F3', f: fm.f3 || 2500, c: col.f3 }
    ];

    ctx.font = '10px "Segoe UI","PingFang SC",sans-serif';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    let hx = 8;
    if (state.label) {
      ctx.fillStyle = '#e8e2ef';
      ctx.fillText(state.label, hx, 12);
      hx += ctx.measureText(state.label).width + 12;
    }
    peaks.forEach(function (p) {
      ctx.fillStyle = p.c;
      ctx.beginPath(); ctx.arc(hx + 4, 12, 3.2, 0, 6.283); ctx.fill();
      ctx.fillText(p.k + ' ' + Math.round(p.f), hx + 10, 12);
      hx += ctx.measureText(p.k + ' ' + Math.round(p.f)).width + 22;
    });
    if (fm.nasal) {
      ctx.fillStyle = 'rgba(255,122,168,.9)';
      ctx.fillText('鼻', hx, 12);
    }
    ctx.textAlign = 'right';
    ctx.fillStyle = 'rgba(154,144,173,.9)';
    ctx.fillText('F0 ' + Math.round(f0) + ' Hz', w - 8, 12);

    const N = Math.max(80, Math.floor(specR - specL));
    const amps = [];
    let aMax = 0.001;
    for (let i = 0; i < N; i++) {
      const f = FMIN + (FMAX - FMIN) * (i / (N - 1));
      const a = schematicAmp(f, fm);
      amps.push(a);
      if (a > aMax) aMax = a;
    }
    aMax *= 1.12;
    function specY(a) {
      return specB - (a / aMax) * (specB - specT);
    }

    ctx.strokeStyle = 'rgba(154,144,173,.16)';
    ctx.lineWidth = 1;
    [500, 1000, 1500, 2000, 2500, 3000].forEach(function (f) {
      const x = specX(f);
      ctx.beginPath(); ctx.moveTo(x, specT); ctx.lineTo(x, specB); ctx.stroke();
    });

    ctx.beginPath();
    for (let i = 0; i < N; i++) {
      const f = FMIN + (FMAX - FMIN) * (i / (N - 1));
      const x = specX(f), y = specY(amps[i]);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.lineTo(specX(FMAX), specB);
    ctx.lineTo(specX(FMIN), specB);
    ctx.closePath();
    const fill = ctx.createLinearGradient(0, specT, 0, specB);
    fill.addColorStop(0, 'rgba(127,216,255,.30)');
    fill.addColorStop(1, 'rgba(127,216,255,.02)');
    ctx.fillStyle = fill;
    ctx.fill();

    ctx.beginPath();
    for (let i = 0; i < N; i++) {
      const f = FMIN + (FMAX - FMIN) * (i / (N - 1));
      const x = specX(f), y = specY(amps[i]);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = 'rgba(232,226,239,.88)';
    ctx.lineWidth = 1.6;
    ctx.stroke();

    peaks.forEach(function (p) {
      const x = specX(p.f);
      ctx.strokeStyle = p.c;
      ctx.globalAlpha = 0.65;
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(x, specT); ctx.lineTo(x, specB); ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
      ctx.fillStyle = p.c;
      ctx.beginPath(); ctx.arc(x, specY(schematicAmp(p.f, fm)), 3.4, 0, 6.283); ctx.fill();
    });

    ctx.fillStyle = 'rgba(154,144,173,.7)';
    ctx.font = '8px "Segoe UI",sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    [0, 1000, 2000, 3000].forEach(function (f) {
      ctx.fillText(f === 0 ? '0' : (f / 1000) + 'k', specX(f), specB + 2);
    });
    ctx.textAlign = 'right';
    ctx.fillText('Hz', specR, specB + 2);

    if (hasTrack) {
      function trY(f) {
        return trackB - (Math.max(FMIN, Math.min(FMAX, f)) - FMIN) / (FMAX - FMIN) * (trackB - trackT);
      }
      function trX(t) { return trackL + t * (trackR - trackL); }

      ctx.fillStyle = 'rgba(255,255,255,.03)';
      ctx.fillRect(trackL, trackT, trackR - trackL, trackB - trackT);
      ctx.strokeStyle = 'rgba(154,144,173,.22)';
      ctx.strokeRect(trackL, trackT, trackR - trackL, trackB - trackT);

      const steps = 48;
      ['f1', 'f2', 'f3'].forEach(function (k) {
        ctx.beginPath();
        for (let i = 0; i <= steps; i++) {
          const t = i / steps;
          const cur = state.formantAt(t);
          const y = trY(k === 'f3' ? (cur.f3 || 2500) : cur[k]);
          const x = trX(t);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = col[k];
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });

      const u = Math.max(0, Math.min(1, state.u || 0));
      const px = trX(u);
      ctx.strokeStyle = 'rgba(255,209,102,.9)';
      ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(px, trackT); ctx.lineTo(px, trackB); ctx.stroke();
      ctx.fillStyle = '#ffd166';
      ctx.beginPath();
      ctx.moveTo(px, trackT);
      ctx.lineTo(px - 4, trackT - 5);
      ctx.lineTo(px + 4, trackT - 5);
      ctx.closePath();
      ctx.fill();

      ctx.fillStyle = 'rgba(154,144,173,.75)';
      ctx.font = '8px "Segoe UI","PingFang SC",sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText('动程 F1–F3', trackL, trackB + 2);
    }
  }

  function drawConsonantSchematic(ctx, w, h, state) {
    ctx.clearRect(0, 0, w, h);
    const bg = ctx.createLinearGradient(0, 0, 0, h);
    bg.addColorStop(0, '#161322');
    bg.addColorStop(1, '#0b0a10');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    const spec = state.spec || { peaks: [], gain: 0, note: '', fmax: 8000 };
    const enSpec = state.lang === 'en';
    const peakName = function (k) {
      if (!enSpec) return k;
      return ({ '强频':'Frication', '爆发':'Burst', 'F1':'F1', 'F2':'F2', 'F3':'F3' })[k] || k;
    };
    const noteName = function (n) {
      if (!enSpec) return n;
      return ({ '闭塞·部位':'Closure · place', '爆发·送气':'Burst · aspiration', '爆发':'Burst', '浊化摩擦':'Voiced frication', '摩擦':'Frication', '接元音':'Vowel transition', '元音':'Vowel', '静息':'Rest', '塞擦·送气':'Affricate · aspiration', '塞擦':'Affricate', '起阻':'Onset', '鼻音':'Nasal', '边音':'Lateral', '通音':'Approximant', '放松':'Relax' })[n] || n;
    };
    const placeName = function (p) {
      if (!enSpec) return p;
      return ({ '双唇音':'Bilabial', '唇齿音':'Labiodental', '舌尖前音':'Dental/alveolar', '舌尖中音':'Alveolar', '舌尖后音':'Retroflex', '舌面音':'Palatal', '舌根音':'Velar', '零声母（介音）':'Glide' })[p] || p;
    };
    const FMIN = 0, FMAX = spec.fmax || 8000;
    const padL = 36, padR = 16, hudH = 18, foot = 16;
    const hasTrack = state.track && state.track.length;
    const trackH = hasTrack ? Math.max(52, Math.floor(h * 0.30)) : 0;
    const specT = 6 + hudH;
    const specB = h - (hasTrack ? trackH + foot + 6 : foot);
    const specL = padL, specR = w - padR;
    const trackT = specB + 16;
    const trackB = h - foot;
    const trackL = padL, trackR = w - padR;
    const peaks = spec.peaks || [];
    const gain = spec.gain == null ? 1 : spec.gain;

    function specX(f) {
      return specL + (Math.max(FMIN, Math.min(FMAX, f)) - FMIN) / (FMAX - FMIN) * (specR - specL);
    }
    function peakAmp(f) {
      let y = 0;
      for (let i = 0; i < peaks.length; i++) {
        const p = peaks[i];
        const bw = Math.max(80, p.bw || (70 + p.f * 0.08));
        const x = (f - p.f) / bw;
        y += (p.a || 1) * Math.exp(-0.5 * x * x);
      }
      return y * gain;
    }

    ctx.font = '10px "Segoe UI","PingFang SC",sans-serif';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    let hx = 8;
    if (state.label) {
      ctx.fillStyle = '#e8e2ef';
      ctx.fillText(state.label, hx, 12);
      hx += ctx.measureText(state.label).width + 10;
    }
    const shown = [];
    peaks.forEach(function (p) {
      if (p.a < 0.18) return;
      if (shown.indexOf(p.k) >= 0) return;
      shown.push(p.k);
      ctx.fillStyle = p.c || '#7fd8ff';
      ctx.beginPath(); ctx.arc(hx + 4, 12, 3.2, 0, 6.283); ctx.fill();
      const txt = peakName(p.k) + ' ' + Math.round(p.f);
      ctx.fillText(txt, hx + 10, 12);
      hx += ctx.measureText(txt).width + 18;
    });
    if (spec.note) {
      ctx.fillStyle = 'rgba(255,122,168,.95)';
      ctx.fillText(noteName(spec.note), hx, 12);
    }
    ctx.textAlign = 'right';
    ctx.fillStyle = 'rgba(154,144,173,.9)';
    ctx.fillText(placeName(state.place || ''), w - 8, 12);

    const N = Math.max(80, Math.floor(specR - specL));
    const amps = [];
    let aMax = 0.001;
    for (let i = 0; i < N; i++) {
      const f = FMIN + (FMAX - FMIN) * (i / (N - 1));
      const a = peakAmp(f);
      amps.push(a);
      if (a > aMax) aMax = a;
    }
    aMax *= 1.12;
    function specY(a) { return specB - (a / aMax) * (specB - specT); }

    ctx.strokeStyle = 'rgba(154,144,173,.16)';
    ctx.lineWidth = 1;
    [2000, 4000, 6000].forEach(function (f) {
      const x = specX(f);
      ctx.beginPath(); ctx.moveTo(x, specT); ctx.lineTo(x, specB); ctx.stroke();
    });

    ctx.beginPath();
    for (let i = 0; i < N; i++) {
      const f = FMIN + (FMAX - FMIN) * (i / (N - 1));
      const x = specX(f), y = specY(amps[i]);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.lineTo(specX(FMAX), specB);
    ctx.lineTo(specX(FMIN), specB);
    ctx.closePath();
    const fill = ctx.createLinearGradient(0, specT, 0, specB);
    fill.addColorStop(0, 'rgba(127,216,255,.30)');
    fill.addColorStop(1, 'rgba(127,216,255,.02)');
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.beginPath();
    for (let i = 0; i < N; i++) {
      const f = FMIN + (FMAX - FMIN) * (i / (N - 1));
      const x = specX(f), y = specY(amps[i]);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = 'rgba(232,226,239,.88)';
    ctx.lineWidth = 1.6;
    ctx.stroke();

    peaks.forEach(function (p) {
      if (p.a < 0.18) return;
      const x = specX(p.f);
      ctx.strokeStyle = p.c || '#7fd8ff';
      ctx.globalAlpha = 0.6;
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(x, specT); ctx.lineTo(x, specB); ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
      ctx.fillStyle = p.c || '#7fd8ff';
      ctx.beginPath(); ctx.arc(x, specY(peakAmp(p.f)), 3.4, 0, 6.283); ctx.fill();
    });

    ctx.fillStyle = 'rgba(154,144,173,.7)';
    ctx.font = '8px "Segoe UI",sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    [0, 2000, 4000, 6000].forEach(function (f) {
      ctx.fillText(f === 0 ? '0' : (f / 1000) + 'k', specX(f), specB + 2);
    });
    ctx.textAlign = 'right';
    ctx.fillText('8k Hz', specR, specB + 2);

    if (hasTrack) {
      function trY(f) {
        return trackB - (Math.max(FMIN, Math.min(FMAX, f)) - FMIN) / (FMAX - FMIN) * (trackB - trackT);
      }
      function trX(t) { return trackL + t * (trackR - trackL); }

      ctx.fillStyle = 'rgba(255,255,255,.03)';
      ctx.fillRect(trackL, trackT, trackR - trackL, trackB - trackT);
      ctx.strokeStyle = 'rgba(154,144,173,.22)';
      ctx.strokeRect(trackL, trackT, trackR - trackL, trackB - trackT);

      ctx.strokeStyle = 'rgba(154,144,173,.18)';
      for (let i = 1; i < 4; i++) {
        const x = trX(i / 4);
        ctx.beginPath(); ctx.moveTo(x, trackT); ctx.lineTo(x, trackB); ctx.stroke();
      }

      ctx.beginPath();
      let started = false;
      const tr = state.track;
      for (let i = 0; i < tr.length; i++) {
        if (!(tr[i].a > 0.08) || !tr[i].f) continue;
        const x = trX(tr[i].t), y = trY(tr[i].f);
        if (!started) { ctx.moveTo(x, y); started = true; }
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = '#7fd8ff';
      ctx.lineWidth = 1.6;
      ctx.stroke();

      const tNow = Math.max(0, Math.min(1, state.t || 0));
      const px = trX(tNow);
      ctx.strokeStyle = 'rgba(255,209,102,.9)';
      ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(px, trackT); ctx.lineTo(px, trackB); ctx.stroke();
      ctx.fillStyle = '#ffd166';
      ctx.beginPath();
      ctx.moveTo(px, trackT);
      ctx.lineTo(px - 4, trackT - 5);
      ctx.lineTo(px + 4, trackT - 5);
      ctx.closePath();
      ctx.fill();

      const names = state.phaseNames || (state.lang === 'en' ? ['Closure', 'Hold', 'Release', 'Rest'] : ['成阻', '持阻', '除阻', '静息']);
      ctx.fillStyle = 'rgba(154,144,173,.8)';
      ctx.font = '8px "Segoe UI","PingFang SC",sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      for (let i = 0; i < 4; i++) ctx.fillText(names[i] || '', trX((i + 0.5) / 4), trackB + 2);
    }
  }

  function setupCanvas(cv, w, h) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = (w || W) * dpr;
    cv.height = (h || H) * dpr;
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, dpr: dpr };
  }

  function invFor(cv, zoom) {
    const k = cv.clientWidth / W;
    return (1 / Math.max(0.35, Math.min(1.4, k))) * (zoom || 1);
  }

  function bindHelp(overlayId, openId, closeId) {
    const help = document.getElementById(overlayId);
    const opener = document.getElementById(openId);
    const closer = document.getElementById(closeId);
    function open() {
      help.classList.remove('hidden');
      help.setAttribute('aria-hidden', 'false');
      opener.setAttribute('aria-expanded', 'true');
      document.body.classList.add('help-open');
      closer.focus();
    }
    function close() {
      const wasOpen = !help.classList.contains('hidden');
      help.classList.add('hidden');
      help.setAttribute('aria-hidden', 'true');
      opener.setAttribute('aria-expanded', 'false');
      document.body.classList.remove('help-open');
      if (wasOpen) opener.focus();
    }
    opener.addEventListener('click', open);
    closer.addEventListener('click', close);
    help.addEventListener('click', function (e) { if (e.target === help) close(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') close();
    });
    return { open: open, close: close };
  }

  global.PinyinTract = {
    W: W, H: H,
    VEL_UP: VEL_UP, VEL_DOWN: VEL_DOWN, VEL_PIVOT: VEL_PIVOT,
    TONGUE_BOTTOM: TONGUE_BOTTOM, NASAL_PATH: NASAL_PATH,
    ROUTE_ORAL: ROUTE_ORAL, ROUTE_NASAL: ROUTE_NASAL, ROUTE_LATERAL: ROUTE_LATERAL,
    pt: pt, lerp: lerp, lerpPt: lerpPt, easeIO: easeIO,
    smoothPath: smoothPath, roundRect: roundRect,
    blendPath: blendPath, currentKey: currentKey,
    Particles: Particles,
    chip: chip, drawScene: drawScene, drawFrontView: drawFrontView,
    drawFormantSchematic: drawFormantSchematic,
    drawConsonantSchematic: drawConsonantSchematic,
    setupCanvas: setupCanvas, invFor: invFor, bindHelp: bindHelp
  };
})(window);
