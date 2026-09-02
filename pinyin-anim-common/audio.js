/* Formant / noise synthesis for initials & finals. TTS is only used for 例词. */
(function (global) {
  'use strict';

  const FORMANTS = {
    a:      { f1: 800, f2: 1200, f3: 2500 },
    aFront: { f1: 750, f2: 1550, f3: 2500 },
    aBack:  { f1: 750, f2: 1000, f3: 2450 },
    o:      { f1: 500, f2: 850,  f3: 2500 },
    oLow:   { f1: 560, f2: 880,  f3: 2480 },
    e:      { f1: 450, f2: 1150, f3: 2400 },   /* ɤ */
    schwa:  { f1: 500, f2: 1500, f3: 2500 },   /* ə */
    eFront: { f1: 470, f2: 2350, f3: 2900 },   /* e 偏前、偏亮 */
    eLax:   { f1: 600, f2: 1800, f3: 2500 },   /* ɛ 前、半低；ie 靠 i→ɛ 长动程，勿过早停在开口 */
    i:      { f1: 280, f2: 2300, f3: 3000 },
    iLax:   { f1: 330, f2: 2450, f3: 3050 },
    u:      { f1: 300, f2: 650,  f3: 2400 },
    uLax:   { f1: 400, f2: 800,  f3: 2400 },
    ü:      { f1: 270, f2: 1720, f3: 2100 },   /* 圆唇，与 i 分开 */
    er:     { f1: 480, f2: 1450, f3: 1750 },
    iq:     { f1: 390, f2: 1220, f3: 2850 },   /* ɿ 舌尖前：高 F3 */
    ih:     { f1: 380, f2: 1650, f3: 1720 },   /* ʅ 舌尖后：F3 贴近 F2 */
    nEnd:   { f1: 270, f2: 1680, f3: 2650, nasal: true },  /* 前鼻音 */
    ngEnd:  { f1: 310, f2: 680,  f3: 2150, nasal: true }   /* 后鼻音 */
  };

  /* 强频集中区（教学用中心频率）：
     塞音爆发由后腔决定：部位越靠后腔越小、强峰越高 → g/k > d/t > b/p。
     擦音/塞擦仍按缝隙噪声：s/z/c 最高，x/j/q 次之，sh/zh/ch 居中，h 最低。 */
  const PLACE = {
    '双唇音':     { burstF: 800,  burstBw: 1800, fricF: 1200, fricBw: 1600 },
    '唇齿音':     { burstF: 1800, burstBw: 1600, fricF: 6000, fricBw: 2400 },
    '舌尖前音':   { burstF: 5000, burstBw: 1800, fricF: 7000, fricBw: 2000 },
    '舌尖中音':   { burstF: 2400, burstBw: 1400, fricF: 2800, fricBw: 1600 },
    '舌尖后音':   { burstF: 2800, burstBw: 1200, fricF: 3400, fricBw: 1500 },
    '舌面音':     { burstF: 4200, burstBw: 1600, fricF: 5600, fricBw: 1900 },
    '舌根音':     { burstF: 4600, burstBw: 1100, fricF: 1500, fricBw: 1100 },
    '零声母（介音）': { burstF: 2200, burstBw: 1200, fricF: 2200, fricBw: 1000 }
  };

  /* 所有音同一基频，不因舌尖元音抬高。 */
  const F0 = 158;

  let ac = null;
  let currentNodes = [];
  let zhVoice = null;

  function ensure() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!ac) ac = new AC();
    if (ac.state === 'suspended') ac.resume();
    return ac;
  }

  function stop() {
    for (let i = 0; i < currentNodes.length; i++) {
      try { currentNodes[i].stop(); } catch (e) {}
      try { currentNodes[i].disconnect(); } catch (e) {}
    }
    currentNodes = [];
    try { if ('speechSynthesis' in window) speechSynthesis.cancel(); } catch (e) {}
  }

  function playBuffer(buf, gainVal) {
    const ctx = ensure();
    if (!ctx) return;
    stop();
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const g = ctx.createGain();
    const now = ctx.currentTime;
    const amp = gainVal == null ? 0.85 : gainVal;
    const dur = buf.duration;
    g.gain.setValueAtTime(amp, now);
    if (dur > 0.08) {
      g.gain.setValueAtTime(amp, now + Math.max(0, dur - 0.06));
      g.gain.linearRampToValueAtTime(0.0001, now + dur);
    }
    src.connect(g); g.connect(ctx.destination);
    src.start();
    currentNodes.push(src);
  }

  function normalize(d, peak) {
    let m = 0;
    for (let i = 0; i < d.length; i++) if (Math.abs(d[i]) > m) m = Math.abs(d[i]);
    if (m < 1e-8) return;
    const s = (peak || 0.38) / m;
    for (let i = 0; i < d.length; i++) d[i] *= s;
  }

  function fade(d, sr, ain, aout) {
    const ni = Math.max(1, Math.floor(sr * ain));
    const no = Math.max(1, Math.floor(sr * aout));
    for (let i = 0; i < ni && i < d.length; i++) {
      d[i] *= 0.5 - 0.5 * Math.cos(Math.PI * (i / ni));
    }
    for (let i = 0; i < no && i < d.length; i++) {
      d[d.length - 1 - i] *= 0.5 - 0.5 * Math.cos(Math.PI * (i / no));
    }
  }

  function dcBlock(d) {
    let x1 = 0, y1 = 0;
    const R = 0.995;
    for (let i = 0; i < d.length; i++) {
      const x = d[i];
      const y = x - x1 + R * y1;
      x1 = x; y1 = y;
      d[i] = y;
    }
  }

  function lowpass(d, sr, hz) {
    const a = Math.exp(-2 * Math.PI * hz / sr);
    let y = 0;
    for (let i = 0; i < d.length; i++) {
      y = (1 - a) * d[i] + a * y;
      d[i] = y;
    }
  }

  function analogBiquadToDigital(b2, b1, b0, a2, a1, a0, sr) {
    const K = 2 * sr, K2 = K * K;
    const B0 = b2 * K2 + b1 * K + b0;
    const B1 = 2 * (b0 - b2 * K2);
    const B2 = b2 * K2 - b1 * K + b0;
    const A0 = a2 * K2 + a1 * K + a0;
    const A1 = 2 * (a0 - a2 * K2);
    const A2 = a2 * K2 - a1 * K + a0;
    return { b0: B0 / A0, b1: B1 / A0, b2: B2 / A0, a1: A1 / A0, a2: A2 / A0 };
  }

  function applyBiquad(d, c) {
    let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (let i = 0; i < d.length; i++) {
      const x = d[i];
      const y = c.b0 * x + c.b1 * x1 + c.b2 * x2 - c.a1 * y1 - c.a2 * y2;
      x2 = x1; x1 = x; y2 = y1; y1 = y;
      d[i] = y;
    }
  }

  const awCache = {};
  function getAWeight(sr) {
    if (awCache[sr]) return awCache[sr];
    function wp(f) { return 2 * sr * Math.tan(Math.PI * Math.min(f / sr, 0.49)); }
    const w1 = wp(20.598997), w2 = wp(107.65265), w3 = wp(737.86223), w4 = wp(12194.217);
    const sections = [
      analogBiquadToDigital(1, 0, 0, 1, 2 * w1, w1 * w1, sr),
      analogBiquadToDigital(1, 0, 0, 1, 2 * w4, w4 * w4, sr),
      analogBiquadToDigital(0, 0, w4 * w4, 1, w2 + w3, w2 * w3, sr)
    ];
    const n = Math.max(2048, Math.round(sr * 0.08));
    const sine = new Float32Array(n);
    for (let i = 0; i < n; i++) sine[i] = Math.sin(2 * Math.PI * 1000 * i / sr);
    const y = new Float32Array(sine);
    for (let i = 0; i < sections.length; i++) applyBiquad(y, sections[i]);
    const skip = Math.round(sr * 0.02);
    let accY = 0, accX = 0, c = 0;
    for (let i = skip; i < n; i++) { accY += y[i] * y[i]; accX += sine[i] * sine[i]; c++; }
    const g = Math.sqrt(accX / c) / (Math.sqrt(accY / c) || 1e-12);
    awCache[sr] = { sections: sections, g: g };
    return awCache[sr];
  }

  function aWeightedRms(d, sr) {
    const aw = getAWeight(sr);
    const y = new Float32Array(d);
    for (let i = 0; i < aw.sections.length; i++) applyBiquad(y, aw.sections[i]);
    let acc = 0;
    const g = aw.g;
    for (let i = 0; i < y.length; i++) {
      const v = y[i] * g;
      acc += v * v;
    }
    return Math.sqrt(acc / y.length);
  }

  function dbGain(db) {
    return Math.pow(10, db / 20);
  }

  function consonantLoudnessTarget(s) {
    const k = (s && (s.letter || s.key)) || '';
    const target = 0.075;
    return (k === 'sh' || k === 'h') ? target * dbGain(-5) : target;
  }

  function vowelLoudnessTarget(s) {
    const k = (s && (s.letter || s.key)) || '';
    const target = 0.09;
    return k === 'h' ? target * dbGain(3) : target;
  }

  function perceptualNormalizeRange(d, sr, start, end, target, maxPeak) {
    start = Math.max(0, Math.min(d.length, Math.floor(start || 0)));
    end = Math.max(start, Math.min(d.length, Math.ceil(end == null ? d.length : end)));
    if (end - start < 8) return 1;
    const segment = new Float32Array(d.subarray(start, end));
    const r = aWeightedRms(segment, sr);
    if (r < 1e-8) return 1;
    let g = target / r;
    if (g > 12) g = 12;
    if (g < 0.02) g = 0.02;
    let peak = 0;
    for (let i = start; i < end; i++) {
      const a = Math.abs(d[i]);
      if (a > peak) peak = a;
    }
    if (peak * g > maxPeak) g = maxPeak / peak;
    for (let i = 0; i < d.length; i++) d[i] *= g;
    return g;
  }

  function limitPeak(d, maxPeak) {
    let peak = 0;
    for (let i = 0; i < d.length; i++) {
      const a = Math.abs(d[i]);
      if (a > peak) peak = a;
    }
    if (peak <= maxPeak || peak < 1e-8) return 1;
    const g = maxPeak / peak;
    for (let i = 0; i < d.length; i++) d[i] *= g;
    return g;
  }

  function sourceEnv(t) {
    const att = 0.04, rel = 0.12;
    if (t < att) return t / att;
    if (t > 1 - rel) {
      const u = (1 - t) / rel;
      return u * u;
    }
    return 1;
  }

  /* 补偿级联共振峰在 u 等后高元音上的过响，避免 ua/uai 里 a 被压没。 */
  function formantAmp(f) {
    const f1 = Math.max(200, f.f1 || 500);
    const f2 = Math.max(400, f.f2 || 1500);
    const a = Math.pow(f1 / 400, 1.4) * Math.pow(f2 / 900, 2.4);
    return Math.max(0.22, Math.min(9, a));
  }

  function loudnessComp(d, sr) {
    const win = Math.max(24, Math.floor(sr * 0.018));
    const buf = new Float32Array(win);
    let acc = 0, w = 0, idx = 0, g = 1;
    const target = 0.10, maxG = 2.4, minRms = 0.008;
    const atk = Math.exp(-1 / (sr * 0.006));
    const relc = Math.exp(-1 / (sr * 0.05));
    for (let i = 0; i < d.length; i++) {
      const x2 = d[i] * d[i];
      if (w === win) acc -= buf[idx];
      else w++;
      buf[idx] = x2;
      acc += x2;
      idx++;
      if (idx === win) idx = 0;
      const rms = Math.sqrt(acc / w);
      let want = g;
      if (rms > minRms) want = Math.min(maxG, Math.max(0.25, target / rms));
      const coeff = want < g ? atk : relc;
      g = coeff * g + (1 - coeff) * want;
      d[i] *= g;
    }
  }

  function resonatorCoeff(sr, F, bw) {
    const r = Math.exp(-Math.PI * bw / sr);
    return { a1: 2 * r * Math.cos(2 * Math.PI * F / sr), a2: -r * r, g: 1 - r };
  }

  function applyResonator(src, sr, F, bw) {
    const c = resonatorCoeff(sr, F, bw);
    const out = new Float32Array(src.length);
    let y1 = 0, y2 = 0;
    for (let i = 0; i < src.length; i++) {
      const y = c.g * src[i] + c.a1 * y1 + c.a2 * y2;
      y2 = y1; y1 = y;
      out[i] = y;
    }
    return out;
  }

  function glottal(n, sr, f0) {
    const y = new Float32Array(n);
    let phase = 0;
    for (let i = 0; i < n; i++) {
      const jitter = 1 + (Math.random() - 0.5) * 0.003;
      phase += (f0 * jitter) / sr;
      if (phase >= 1) phase -= 1;
      const Tp = 0.42, Tn = 0.16;
      let g = 0;
      if (phase < Tp) g = 0.5 * (1 - Math.cos(Math.PI * phase / Tp));
      else if (phase < Tp + Tn) g = Math.cos(Math.PI * (phase - Tp) / (2 * Tn));
      y[i] = (g - 0.35) * sourceEnv(i / (n - 1 || 1));
    }
    return y;
  }

  function noise(n) {
    const y = new Float32Array(n);
    for (let i = 0; i < n; i++) y[i] = Math.random() * 2 - 1;
    return y;
  }

  function bandNoise(n, sr, F, bw, amp) {
    const y = applyResonator(noise(n), sr, F, bw);
    for (let i = 0; i < n; i++) y[i] *= amp;
    return y;
  }

  function mixInto(dst, src, at, amp) {
    amp = amp == null ? 1 : amp;
    for (let i = 0; i < src.length; i++) {
      const j = at + i;
      if (j >= 0 && j < dst.length) dst[j] += src[i] * amp;
    }
  }

  function formantVowel(n, sr, fAt, f0) {
    const src = glottal(n, sr, f0 == null ? F0 : f0);
    const out = new Float32Array(n);
    let y1a = 0, y2a = 0, y1b = 0, y2b = 0, y1c = 0, y2c = 0;
    for (let i = 0; i < n; i++) {
      const t = i / (n - 1 || 1);
      const f = fAt(t);
      const nasal = !!f.nasal;
      const c1 = resonatorCoeff(sr, f.f1, nasal ? 80 : 90);
      const c2 = resonatorCoeff(sr, f.f2, 110);
      const c3 = resonatorCoeff(sr, f.f3 || 2500, 220);
      let x = src[i];
      let y = c1.g * x + c1.a1 * y1a + c1.a2 * y2a; y2a = y1a; y1a = y; x = y;
      y = c2.g * x + c2.a1 * y1b + c2.a2 * y2b; y2b = y1b; y1b = y; x = y;
      y = c3.g * x + c3.a1 * y1c + c3.a2 * y2c; y2c = y1c; y1c = y;
      if (nasal) y *= 0.72;
      out[i] = y * formantAmp(f);
    }
    return out;
  }

  function lerpFormant(a, b, t) {
    if (!a) a = FORMANTS.schwa;
    if (!b) b = a;
    return {
      f1: a.f1 + (b.f1 - a.f1) * t,
      f2: a.f2 + (b.f2 - a.f2) * t,
      f3: (a.f3 || 2500) + ((b.f3 || 2500) - (a.f3 || 2500)) * t,
      nasal: b.nasal ? t > 0.28 : !!(a.nasal && t < 0.75)
    };
  }

  /* 教材呼读韵腹：玻坡摸佛→o，得特…喝→ɤ，基欺希→i，知吃诗日→ʅ，资雌思→ɿ。 */
  function huduFormant(s) {
    const k = (s && (s.letter || s.key)) || '';
    if (k === 'w') return FORMANTS.u;
    if (k === 'y' || k === 'j' || k === 'q' || k === 'x') return FORMANTS.i;
    if (k === 'zh' || k === 'ch' || k === 'sh' || k === 'r') return FORMANTS.ih;
    if (k === 'z' || k === 'c' || k === 's') return FORMANTS.iq;
    if (k === 'b' || k === 'p' || k === 'm' || k === 'f') return FORMANTS.o;
    return FORMANTS.e;
  }

  function nasalFormant(s) {
    const k = (s && (s.letter || s.key)) || '';
    if (k === 'm') return { f1: 250, f2: 1050, f3: 2400, nasal: true };
    if (k === 'ng') return FORMANTS.ngEnd;
    return { f1: 270, f2: 1600, f3: 2500, nasal: true };
  }

  function consonantSpec(s, phase, u) {
    const place = PLACE[(s && s.place) || ''] || PLACE['舌尖中音'];
    const isStop = ((s && s.group) || '').indexOf('stop') === 0;
    const isAffr = ((s && s.group) || '').indexOf('affr') === 0;
    const isFric = s && (s.manner === '清擦音' || s.manner === '浊擦音');
    const isNasal = !!(s && s.nasal);
    const isLat = !!(s && s.lateral);
    const isSemi = !!(s && s.semi);
    const fm = huduFormant(s);
    u = Math.max(0, Math.min(1, u || 0));
    const peaks = [];
    let gain = 0;
    let note = '';
    function addFric(a) {
      if (a > 0.02) peaks.push({ k: '强频', f: place.fricF, bw: place.fricBw, a: a, c: '#7fd8ff' });
    }
    function addBurst(a) {
      if (a > 0.02) peaks.push({ k: '爆发', f: place.burstF, bw: place.burstBw, a: a, c: '#ffd166' });
    }
    function addVow(a, src) {
      if (a < 0.04) return;
      const v = src || fm;
      peaks.push({ k: 'F1', f: v.f1, bw: 90, a: a, c: '#ffb86b' });
      peaks.push({ k: 'F2', f: v.f2, bw: 120, a: a * 0.92, c: '#7fd8ff' });
      peaks.push({ k: 'F3', f: v.f3 || 2500, bw: 180, a: a * 0.8, c: '#ff7aa8' });
    }
    if (isStop) {
      if (phase === 'A' || phase === 'B') {
        gain = 0.42; addBurst(0.85); note = '闭塞·部位';
      } else if (phase === 'C') {
        if (u < 0.22) {
          gain = 1; addBurst(1); if (s.asp) addFric(0.55); note = s.asp ? '爆发·送气' : '爆发';
        } else {
          const t = (u - 0.22) / 0.78;
          gain = 0.95;
          addBurst(Math.max(0, 1 - t * 3) * 0.3);
          if (s.asp) addFric(Math.max(0, 1 - t * 2) * 0.35);
          addVow(Math.min(1, t * 1.5));
          note = '元音';
        }
      } else { gain = 0.12; addVow(0.28); note = '静息'; }
    } else if (isAffr) {
      if (phase === 'A' || phase === 'B') {
        gain = 0.42; addFric(0.85); note = '闭塞·部位';
      }
      else if (phase === 'C') {
        if (u < 0.48) {
          gain = 1; addBurst(0.65); addFric(1); note = s.asp ? '塞擦·送气' : '塞擦';
        } else {
          const t = (u - 0.48) / 0.52;
          gain = 0.95;
          addFric(Math.max(0, 1 - t) * 0.45);
          addVow(Math.min(1, t * 1.6));
          note = '元音';
        }
      } else { gain = 0.12; addVow(0.28); note = '静息'; }
    } else if (isFric) {
      const fricScale = s.voiced ? 0.5 : 1;
      if (phase === 'A') { gain = 0.2 + 0.7 * u; addFric(fricScale); note = '起阻'; }
      else if (phase === 'B') { gain = 1; addFric(fricScale); if (s.voiced) addVow(0.85, { f1: 380, f2: 1380, f3: 1800 }); note = s.voiced ? '浊化摩擦' : '摩擦'; }
      else if (phase === 'C') { gain = 1; addFric(Math.max(0.12, 1 - u * 0.9) * fricScale); addVow(u); note = '接元音'; }
      else { gain = 0.14; addVow(0.28); note = '静息'; }
    } else if (isNasal || isLat || isSemi) {
      const nf = isNasal
        ? nasalFormant(s)
        : (isLat ? { f1: 380, f2: 1200, f3: 2600 } : (s.letter === 'w' ? FORMANTS.u : FORMANTS.i));
      if (phase === 'A') { gain = 0.25 + 0.7 * u; addVow(1, nf); note = '起阻'; }
      else if (phase === 'B') { gain = 1; addVow(1, nf); note = isNasal ? '鼻音' : (isLat ? '边音' : '通音'); }
      else if (phase === 'C') { gain = 1 - 0.35 * u; addVow(1 - 0.3 * u, nf); addVow(u * 0.7); note = '放松'; }
      else { gain = 0.14; addVow(0.28, nf); note = '静息'; }
    } else {
      gain = 0.2; addVow(0.5);
    }
    return { peaks: peaks, gain: gain, note: note, fmax: 8000 };
  }

  function formantAtPath(path, t) {
    const P = Math.max(0, Math.min(1, t));
    const last = path[path.length - 1];
    if (P <= path[0][1]) return FORMANTS[path[0][0]] || FORMANTS.schwa;
    if (P >= last[1]) return FORMANTS[last[0]] || FORMANTS.schwa;
    for (let i = 0; i < path.length - 1; i++) {
      const k1 = path[i][0], f1 = path[i][1], k2 = path[i + 1][0], f2 = path[i + 1][1];
      if (P >= f1 && P <= f2) {
        const u = (P - f1) / ((f2 - f1) || 1);
        return lerpFormant(FORMANTS[k1], FORMANTS[k2], u);
      }
    }
    return FORMANTS[last[0]] || FORMANTS.schwa;
  }

  function playConsonant(s, opts) {
    const ctx = ensure();
    if (!ctx) return false;
    const sr = ctx.sampleRate;
    const place = PLACE[s.place] || PLACE['舌尖中音'];
    const isStop = (s.group || '').indexOf('stop') === 0;
    const isAffr = (s.group || '').indexOf('affr') === 0;
    const isFric = s.manner === '清擦音' || s.manner === '浊擦音';
    const isNasal = !!s.nasal;
    const isLat = !!s.lateral;
    const isSemi = !!s.semi;

    let dur = 0.28;
    if (isStop) dur = s.asp ? 0.26 : 0.16;
    else if (isAffr) dur = s.asp ? 0.32 : 0.24;
    else if (isFric) dur = 0.52;
    else if (isNasal || isLat) dur = 0.36;
    else if (isSemi) dur = 0.28;

    const n = Math.floor(sr * dur);
    const consonant = new Float32Array(n);
    const vowel = new Float32Array(n);
    const d = new Float32Array(n);
    let consonantEnd = n;
    let vowelStart = -1;

    if (isStop || isAffr) {
      const burstN = Math.floor(sr * 0.012);
      const burst = bandNoise(burstN, sr, place.burstF, place.burstBw, 1);
      mixInto(consonant, burst, 0, 0.42);
      const vot = s.asp ? 0.065 : 0.008;
      consonantEnd = burstN;
      if (s.asp) {
        const aspN = Math.floor(sr * vot);
        const asp = bandNoise(aspN, sr, place.fricF, place.fricBw, 0.55);
        mixInto(consonant, asp, burstN, 0.42);
        consonantEnd = Math.max(consonantEnd, burstN + aspN);
      }
      if (isAffr) {
        const frN = Math.floor(sr * (s.asp ? 0.12 : 0.09));
        const fr = bandNoise(frN, sr, place.fricF, place.fricBw, 0.7);
        const frStart = burstN + Math.floor(sr * vot * 0.4);
        mixInto(consonant, fr, frStart, 0.7);
        consonantEnd = Math.max(consonantEnd, frStart + frN);
      }
      vowelStart = burstN + Math.floor(sr * vot);
      const vowN = Math.max(8, n - vowelStart);
      const fm = huduFormant(s);
      const vow = formantVowel(vowN, sr, function () { return fm; }, F0);
      mixInto(vowel, vow, vowelStart, 0.85);
    } else if (isFric) {
      const frN = Math.floor(sr * 0.30);
      const fr = bandNoise(n, sr, place.fricF, place.fricBw, 1);
      const voicedFric = s.letter === 'r';
      for (let i = 0; i < n; i++) {
        const t = i / (n - 1 || 1);
        const env = t < 0.56 ? 0.92 : 0.92 * Math.max(0, 1 - (t - 0.56) / 0.20);
        const frAmp = env * (voicedFric ? 0.42 : 1);
        consonant[i] += fr[i] * frAmp;
      }
      consonantEnd = Math.floor(n * 0.76);
      if (s.voiced) {
        const v0 = formantVowel(frN, sr, function () { return { f1: 380, f2: 1380, f3: 1800 }; }, F0);
        mixInto(consonant, v0, 0, voicedFric ? 0.78 : 0.32);
      }
      const vowN = Math.max(8, n - frN);
      const fm = huduFormant(s);
      const vow = formantVowel(vowN, sr, function () { return fm; }, F0);
      vowelStart = frN;
      mixInto(vowel, vow, vowelStart, 0.72);
    } else if (isNasal) {
      const key = nasalFormant(s);
      const v = formantVowel(n, sr, function () { return key; }, F0);
      mixInto(consonant, v, 0, 1);
    } else if (isLat) {
      const v = formantVowel(n, sr, function () { return { f1: 380, f2: 1200, f3: 2600 }; }, F0);
      mixInto(consonant, v, 0, 1);
    } else if (isSemi) {
      const fm = s.letter === 'w' ? FORMANTS.u : FORMANTS.i;
      const v = formantVowel(n, sr, function () { return fm; }, F0);
      mixInto(consonant, v, 0, 1);
    } else {
      const v = formantVowel(n, sr, function () { return FORMANTS.schwa; }, F0);
      mixInto(consonant, v, 0, 1);
    }

    const needHz = Math.max(place.burstF || 0, place.fricF || 0) + 900;
    const lpHz = Math.max(4500, Math.min(10000, needHz));
    dcBlock(consonant);
    lowpass(consonant, sr, lpHz);
    perceptualNormalizeRange(consonant, sr, 0, consonantEnd, consonantLoudnessTarget(s), 0.72);
    if (vowelStart >= 0) {
      dcBlock(vowel);
      lowpass(vowel, sr, lpHz);
      const vowelMeasureStart = Math.min(n - 8, vowelStart + Math.floor(sr * 0.035));
      const vowelMeasureEnd = Math.max(vowelMeasureStart + 8, n - Math.floor(sr * 0.045));
      perceptualNormalizeRange(vowel, sr, vowelMeasureStart, vowelMeasureEnd, vowelLoudnessTarget(s), 0.76);
    }
    for (let i = 0; i < n; i++) d[i] = consonant[i] + vowel[i];
    fade(d, sr, 0.008, 0.06);
    limitPeak(d, 0.85);
    if (opts && opts.silent) {
      let peak = 0, acc = 0;
      for (let i = 0; i < d.length; i++) {
        const a = Math.abs(d[i]);
        if (a > peak) peak = a;
        acc += d[i] * d[i];
      }
      return { peak: peak, rms: Math.sqrt(acc / d.length), aRms: aWeightedRms(d, sr), n: n, sr: sr };
    }
    const buf = ctx.createBuffer(1, n, sr);
    buf.getChannelData(0).set(d);
    playBuffer(buf, 0.9);
    return true;
  }

  function playFinal(s) {
    const ctx = ensure();
    if (!ctx) return false;
    const sr = ctx.sampleRate;
    const path = s.path;
    const glide = path.length > 2 || path[0][0] !== path[path.length - 1][0];
    const nasal = (path[path.length - 1][0] === 'nEnd' || path[path.length - 1][0] === 'ngEnd');
    const apical = s.key === 'iq' || s.key === 'ih';
    const dur = apical ? 0.62 : (nasal ? 0.78 : (glide ? 0.66 : 0.50));
    const n = Math.floor(sr * dur);
    const v = formantVowel(n, sr, function (t) { return formantAtPath(path, t); }, F0);
    if (s.key === 'iq') {
      const buzz = bandNoise(n, sr, 4300, 1600, 0.14);
      for (let i = 0; i < n; i++) v[i] += buzz[i] * 0.18 * sourceEnv(i / (n - 1 || 1));
    }
    if (nasal) {
      const pole = resonatorCoeff(sr, 270, 80);
      let y1 = 0, y2 = 0, w = 0;
      for (let i = 0; i < n; i++) {
        const t = i / (n - 1 || 1);
        const f = formantAtPath(path, t);
        const want = f.nasal ? 1 : 0;
        w += (want - w) * 0.04;
        const x = v[i];
        const y = pole.g * x + pole.a1 * y1 + pole.a2 * y2;
        y2 = y1; y1 = y;
        v[i] = x * (1 - 0.22 * w) + y * 0.32 * w;
      }
    }
    dcBlock(v);
    lowpass(v, sr, apical ? 6500 : 4500);
    if (!apical) loudnessComp(v, sr);
    normalize(v, 0.38);
    fade(v, sr, 0.02, apical ? 0.05 : 0.07);
    const buf = ctx.createBuffer(1, n, sr);
    buf.getChannelData(0).set(v);
    playBuffer(buf, 0.85);
    return true;
  }

  function refreshVoices() {
    try {
      const vs = speechSynthesis.getVoices();
      zhVoice = vs.find(function (v) { return /^zh/i.test(v.lang) && /huihui|xiaoxiao|xiaoyi|xiaobei|xiaoni|yunxi|yunyang|yunjian|yunxia|yunye|hiuhi|google/i.test(v.name); })
        || vs.find(function (v) { return /^zh/i.test(v.lang); })
        || null;
      return { voices: vs, zhVoice: zhVoice };
    } catch (e) {
      return { voices: [], zhVoice: null };
    }
  }

  function speak(text, rate) {
    if (!('speechSynthesis' in window) || !text) return false;
    refreshVoices();
    try { speechSynthesis.cancel(); } catch (e) {}
    const u = new SpeechSynthesisUtterance(text);
    u.lang = zhVoice ? zhVoice.lang : 'zh-CN';
    u.rate = rate || 0.85;
    if (zhVoice) u.voice = zhVoice;
    try { speechSynthesis.speak(u); } catch (e) { return false; }
    return true;
  }

  if (typeof speechSynthesis !== 'undefined') {
    speechSynthesis.onvoiceschanged = refreshVoices;
    refreshVoices();
  }

  global.PinyinAudio = {
    F0: F0,
    FORMANTS: FORMANTS,
    PLACE: PLACE,
    formantAtPath: formantAtPath,
    lerpFormant: lerpFormant,
    huduFormant: huduFormant,
    consonantSpec: consonantSpec,
    ensure: ensure,
    stop: stop,
    playConsonant: playConsonant,
    playFinal: playFinal,
    speak: speak,
    refreshVoices: refreshVoices,
    hasSynth: function () { return !!(window.AudioContext || window.webkitAudioContext); }
  };
})(window);
