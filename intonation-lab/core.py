"""语调调试实验室 —— 核心音频处理模块。

技术栈：
- 基频提取：归一化自相关法（FFT 分帧 + 首峰选择 + 抛物线插值），
  带时间域中值滤波抑制毛刺；按块分析以限制长音频的峰值内存。
- 重合成：TD-PSOLA（时域基音同步叠加）。先按原始基频在浊音段定位
  基音标记（pitch marks），再用“编辑后基频”决定输出窗间距，
  窗内信号取自源波形，叠加后按窗和归一化；清音段直接拷贝原信号。
  —— 时长、清浊结构保持不变，仅替换音高。
- soundfile: 音频解码 / 编码 (libsndfile, 支持 wav/mp3/flac/ogg)。

主要函数：
    load_audio_bytes(data)          字节流 -> (float32 单声道样本, 采样率, 解码方式)
    analyze_pitch(...)              自相关基频提取 -> (times, f0)，f0=0 表示清音
    make_edit_points(...)           分析网格抽稀为可拖拽编辑点
    build_f0_tier(...)              编辑点插值回分析帧网格（重合成用）
    synthesize_with_f0(...)         TD-PSOLA 用修改后的 F0 重合成音频
    smooth_points / shift_semitones 编辑点后处理
    decimate_waveform(...)          波形抽稀（前端显示）
    wav_bytes / to_data_url / bytes_hash
    generate_sample_audio()         生成示例哼鸣音频
"""

from __future__ import annotations

import base64
import hashlib
import io

import numpy as np
import soundfile as sf

SUPPORTED_EXTS = ("wav", "mp3", "flac", "ogg")
SUPPORTED_HINT = "支持 wav / mp3 / flac / ogg（具体压缩编码取决于 libsndfile）"


# ---------------------------------------------------------------------------
# 加载与编码
# ---------------------------------------------------------------------------
def load_audio_bytes(data: bytes) -> tuple[np.ndarray, int, str]:
    """从字节流解码音频 -> (float32 单声道样本, 采样率, 解码方式)。

    优先 libsndfile (soundfile)；失败后回退纯 Python wave 解析。
    """
    errs: list[str] = []
    try:
        samples, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
        if samples.shape[0] == 0 or sr <= 0:
            raise ValueError("空音频或无有效采样率")
        if samples.shape[1] > 1:
            samples = samples.mean(axis=1)
        samples = samples.reshape(-1)
        return samples.astype(np.float32), int(sr), "libsndfile"
    except Exception as e:  # noqa: BLE001
        errs.append(f"libsndfile: {e}")

    try:
        import wave

        with wave.open(io.BytesIO(data), "rb") as w:
            sr = w.getframerate()
            ch = w.getnchannels()
            n = w.getnframes()
            width = w.getsampwidth()
            raw = w.readframes(n)
        if sr <= 0 or n == 0:
            raise ValueError("空 wav")
        if width == 1:
            samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif width == 2:
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif width == 3:
            packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
            values = packed[:, 0] | (packed[:, 1] << 8) | (packed[:, 2] << 16)
            values = np.where(values & 0x800000, values - 0x1000000, values)
            samples = values.astype(np.float32) / 8388608.0
        elif width == 4:
            samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"不支持的 WAV 位深：{width * 8} bit")
        samples = samples.reshape(-1, ch)
        if ch > 1:
            samples = samples.mean(axis=1)
        samples = samples.reshape(-1)
        return samples.astype(np.float32), int(sr), "wave-fallback"
    except Exception as e:  # noqa: BLE001
        errs.append(f"wave: {e}")

    raise ValueError(f"无法解码该音频。{SUPPORTED_HINT}。\n详情: {' | '.join(errs)}")


def wav_bytes(samples: np.ndarray, sr: int) -> bytes:
    """样本 -> WAV (PCM 16bit) 字节。"""
    buf = io.BytesIO()
    sf.write(buf, np.asarray(samples, dtype=np.float32), int(sr), format="WAV", subtype="PCM_16")
    return buf.getvalue()


def to_data_url(data: bytes, mime: str = "audio/wav") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def bytes_hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


# 画布 iframe 内嵌 WAV data URL 的上限（约 47s / 16 kHz / 16-bit 单声道）。
# 更大的音频只在主页「试听对比」播放，避免 Streamlit postMessage 被撑爆。
COMPONENT_AUDIO_MAX_BYTES = 1_500_000


def component_audio_payload(
    orig_wav: bytes,
    edit_wav: bytes,
    prev_orig_hash: str | None = None,
    prev_edit_hash: str | None = None,
    remount: bool = False,
    max_bytes: int = COMPONENT_AUDIO_MAX_BYTES,
) -> dict:
    """决定本次渲染要传给音高组件的音频字段。

    返回 dict：
      url_orig / url_edit:
        - data URL：写入组件
        - \"same\"：edit 与 orig 相同（仅 url_edit）
        - \"\"：清除组件内音频
        - None：保持组件内上一次的值（避免重复发送数 MB 的 data URL）
      orig_hash / edit_hash: 供会话记住上次已发送的内容
      embedded: 是否在组件内提供播放
    """
    too_big = len(orig_wav) > max_bytes or len(edit_wav) > max_bytes
    if too_big:
        return {
            "url_orig": "",
            "url_edit": "",
            "orig_hash": None,
            "edit_hash": None,
            "embedded": False,
        }
    orig_hash = bytes_hash(orig_wav)
    edit_hash = bytes_hash(edit_wav)
    url_orig: str | None
    if remount or prev_orig_hash != orig_hash:
        url_orig = to_data_url(orig_wav)
    else:
        url_orig = None
    url_edit: str | None
    if remount or prev_edit_hash != edit_hash:
        url_edit = "same" if edit_hash == orig_hash else to_data_url(edit_wav)
    else:
        url_edit = None
    return {
        "url_orig": url_orig,
        "url_edit": url_edit,
        "orig_hash": orig_hash,
        "edit_hash": edit_hash,
        "embedded": True,
    }


# ---------------------------------------------------------------------------
# 基频分析（归一化自相关法，分块 FFT 分帧实现）
# ---------------------------------------------------------------------------
def _extend_voicing(
    f0: np.ndarray,
    f0_cand: np.ndarray,
    voiced: np.ndarray,
    energy: np.ndarray,
    rmax: np.ndarray,
    max_run: int = 5,
    min_rmax: float = 0.22,
) -> np.ndarray:
    """仅向浊音段**尾部**作很短的延伸（约 50ms），并只填 1–2 帧的掉点。

    不向前延伸、不跨过下一个浊音段，避免把相邻音节粘成一个。
    """
    n = len(f0)
    voiced = voiced.copy()
    f0 = f0.copy()

    def accept(i: int, ref_f0: float, ref_e: float) -> bool:
        if energy[i] < max(1e-7, 0.12 * ref_e):
            return False
        if rmax[i] < min_rmax:
            return False
        cand = float(f0_cand[i])
        if not (cand > 0 and ref_f0 > 0):
            return False
        semis = abs(12.0 * np.log2(cand / ref_f0))
        return bool(semis <= 5.0)

    i = 0
    while i < n:
        if voiced[i]:
            i += 1
            continue
        j = i
        while j < n and not voiced[j]:
            j += 1
        left, right = i - 1, j if j < n else -1
        if left >= 0 and right >= 0 and (j - i) <= 2:
            ref_f = float(f0[left])
            ref_e = float(max(energy[left], energy[right]))
            if all(accept(k, ref_f, ref_e) for k in range(i, j)):
                for k in range(i, j):
                    f0[k] = float(f0_cand[k])
                    voiced[k] = True
        i = j

    runs: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if not voiced[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and voiced[j + 1]:
            j += 1
        runs.append((i, j))
        i = j + 1
    for run_i, (a, b) in enumerate(runs):
        next_a = runs[run_i + 1][0] if run_i + 1 < len(runs) else n
        ref_f, ref_e = float(f0[b]), float(energy[b])
        k, steps = b + 1, 0
        while k < next_a and not voiced[k] and steps < max_run:
            if not accept(k, ref_f, ref_e):
                break
            if energy[k] > energy[k - 1] * 1.15:
                break
            f0[k] = float(f0_cand[k])
            voiced[k] = True
            ref_f = f0[k]
            ref_e = float(energy[k])
            k += 1
            steps += 1
    return np.where(voiced, f0, 0.0)


def analyze_pitch(
    samples: np.ndarray,
    sr: int,
    floor: float = 75.0,
    ceiling: float = 500.0,
    frame_period: float = 10.0,
    win_len: float = 0.04,
    chunk_frames: int = 1024,
) -> tuple[np.ndarray, np.ndarray]:
    """归一化自相关基频提取 -> (times, f0)。f0 中 0 表示清音/无音高。

    frame_period 单位为毫秒（帧移）。chunk_frames 限制一次 FFT 的帧数，
    避免长音频一次构造数 GB 的帧矩阵。
    """
    sr = float(sr)
    floor = float(floor)
    ceiling = float(ceiling)
    if not np.isfinite(sr) or sr <= 0:
        raise ValueError("采样率必须为正数")
    if not np.isfinite(floor) or not np.isfinite(ceiling) or floor <= 0 or ceiling <= floor:
        raise ValueError("基频上下限无效：需要 0 < floor < ceiling")
    frame = max(64, int(round(win_len * sr)))
    hop = max(1, int(round(frame_period / 1000.0 * sr)))
    x = samples.astype(np.float64)
    n = len(x)
    n_frames = max(1, (n - frame) // hop + 1)
    # F0 属于分析窗中心，而不是窗起点；短音频使用实际样本中点。
    center = min(frame, n) / 2.0
    times = (np.arange(n_frames, dtype=np.float64) * hop + center) / sr
    f0 = np.zeros(n_frames, dtype=np.float64)

    if n < 64 or np.max(np.abs(x)) < 1e-9:
        return times, f0

    # ---- FFT 参数与滞后范围 ----
    nfft = 1
    while nfft < frame * 2:
        nfft *= 2
    lo = max(1, int(sr / ceiling))
    hi = min(frame - 1, int(sr / floor))
    if hi < lo:
        raise ValueError("分析窗过短，无法覆盖所选基频范围")
    lags = np.arange(lo, hi + 1, dtype=np.float64)
    voiced = np.zeros(n_frames, dtype=bool)
    energy_all = np.zeros(n_frames, dtype=np.float64)
    rmax_all = np.zeros(n_frames, dtype=np.float64)
    f0_cand = np.zeros(n_frames, dtype=np.float64)
    padded = np.pad(x, (0, max(0, frame - n)))
    chunk_frames = max(1, int(chunk_frames))

    # ---- 按块分帧、FFT 自相关和峰值选择 ----
    for begin in range(0, n_frames, chunk_frames):
        end = min(n_frames, begin + chunk_frames)
        starts = np.arange(begin, end) * hop
        idx = starts[:, None] + np.arange(frame)[None, :]
        seg = padded[idx]
        seg = seg - seg.mean(axis=1, keepdims=True)
        energy = np.einsum("ij,ij->i", seg, seg)

        spectrum = np.fft.rfft(seg, nfft, axis=1)
        autocorr = np.fft.irfft(spectrum * np.conj(spectrum), nfft, axis=1)[:, :frame]
        corr = autocorr / np.maximum(autocorr[:, 0:1], 1e-12)
        rsub = corr[:, lo:hi + 1]
        rmax = rsub.max(axis=1)
        chunk_voiced = (rmax > 0.35) & (energy > 1e-8)

        if rsub.shape[1] == 1:
            chosen = np.zeros(end - begin, dtype=int)
        else:
            is_peak = ((rsub >= np.roll(rsub, 1, axis=1))
                       & (rsub >= np.roll(rsub, -1, axis=1)))
            is_peak[:, 0] = rsub[:, 0] >= rsub[:, 1]
            is_peak[:, -1] = rsub[:, -1] >= rsub[:, -2]
            strong = is_peak & (rsub >= 0.75 * rmax[:, None])
            first_idx = np.argmax(strong, axis=1)
            chosen = np.where(strong.any(axis=1), first_idx, np.argmax(rsub, axis=1))

        tau = lags[chosen]
        rows = np.arange(end - begin)
        tau_i = tau.astype(int)
        r_prev = corr[rows, np.maximum(tau_i - 1, lo)]
        r_cur = corr[rows, tau_i]
        r_next = corr[rows, np.minimum(tau_i + 1, hi)]
        denom = r_prev - 2.0 * r_cur + r_next
        delta = np.zeros_like(denom)
        ok = np.abs(denom) > 1e-12
        delta[ok] = 0.5 * (r_prev[ok] - r_next[ok]) / denom[ok]
        tau_f = tau + np.clip(delta, -1.0, 1.0)

        cand = np.clip(sr / np.maximum(tau_f, 1e-9), floor, ceiling)
        f0_cand[begin:end] = cand
        energy_all[begin:end] = energy
        rmax_all[begin:end] = rmax
        chunk_f0 = np.zeros(end - begin, dtype=np.float64)
        chunk_f0[chunk_voiced] = cand[chunk_voiced]
        f0[begin:end] = chunk_f0
        voiced[begin:end] = chunk_voiced

    # 时间域中值滤波（窗口 3）平滑毛刺；邻帧若是清音则不参与，避免去声尾被 0 拉垮。
    f0_med = f0.copy()
    if n_frames >= 3:
        for i in range(1, n_frames - 1):
            if not voiced[i]:
                continue
            vals = [f0[i]]
            if voiced[i - 1]:
                vals.append(f0[i - 1])
            if voiced[i + 1]:
                vals.append(f0[i + 1])
            f0_med[i] = float(np.median(vals))
    f0 = np.where(voiced, f0_med, 0.0)
    f0 = _extend_voicing(f0, f0_cand, voiced, energy_all, rmax_all)
    return times, f0


def make_edit_points(
    times: np.ndarray, f0: np.ndarray, step: float = 0.05, max_points: int = 1500
) -> list[list[float]]:
    """把分析网格抽稀为可拖拽编辑点。

    仅保留浊音段；段内按 step 秒取样（首尾必取），清音段不产生编辑点。
    若点过多则自动加大步长重抽。
    """
    pts: list[list[float]] = []
    n = len(times)
    i = 0
    while i < n:
        if f0[i] <= 0:
            i += 1
            continue
        j = i
        while j + 1 < n and f0[j + 1] > 0:
            j += 1
        last_t: float | None = None
        for k in range(i, j + 1):
            if last_t is None or times[k] - last_t >= step - 1e-9:
                pts.append([round(float(times[k]), 4), round(float(f0[k]), 3)])
                last_t = float(times[k])
        if pts and abs(float(times[j]) - pts[-1][0]) > 1e-9:
            pts.append([round(float(times[j]), 4), round(float(f0[j]), 3)])
        i = j + 1
    if len(pts) > max_points and step < 2.0:
        return make_edit_points(times, f0, step * (len(pts) / max_points) + 0.001, max_points)
    return pts


def reference_curve(times: np.ndarray, f0: np.ndarray, step: float = 0.02) -> list[list[float]]:
    """抽稀的参考曲线（前端“显示原始”用），步长略小于编辑点。"""
    return make_edit_points(times, f0, step=step, max_points=4000)


# ---------------------------------------------------------------------------
# 重合成（TD-PSOLA）
# ---------------------------------------------------------------------------
def build_f0_tier(
    edit_points: list[list[float]],
    times: np.ndarray,
    f0_orig: np.ndarray,
    floor: float = 75.0,
    ceiling: float = 500.0,
) -> np.ndarray:
    """把编辑点在半音域线性插值回分析帧网格。

    原始浊音帧始终覆盖；另外，用户折线所覆盖的时间（含把末点拖进
    未检出浊音的尾段、或在空白处新加点）也会写入 F0，这样去声尾才听得到。
    折线按 0.3s 间隙分段，避免把音节之间的停顿填成浊音。
    """
    f0_new = np.zeros(len(f0_orig), dtype=np.float64)
    if not edit_points:
        return f0_new
    ts = np.array([p[0] for p in edit_points], dtype=np.float64)
    fs = np.array([p[1] for p in edit_points], dtype=np.float64)
    order = np.argsort(ts, kind="stable")
    ts = ts[order]
    fs = fs[order]
    valid = np.isfinite(ts) & np.isfinite(fs) & (fs > 0)
    ts, fs = ts[valid], fs[valid]
    if len(ts) == 0:
        return f0_new
    keep = np.r_[np.diff(ts) > 1e-12, True]
    ts, fs = ts[keep], fs[keep]
    cover = f0_orig > 0
    dt = float(times[1] - times[0]) if len(times) > 1 else 0.01
    pad = max(dt / 2.0, 0.015)
    for t in ts:
        cover |= np.abs(times - t) <= pad
    orig_segs = _voiced_segments(f0_orig, times, min_gap_frames=1)
    for i, (_ta, tb) in enumerate(orig_segs):
        tc = orig_segs[i + 1][0] if i + 1 < len(orig_segs) else float(times[-1]) + 1.0
        later = ts[(ts > tb) & (ts < tc)]
        if later.size:
            cover |= (times >= tb - pad) & (times <= float(later.max()) + pad)
        ta = orig_segs[i][0]
        tp = orig_segs[i - 1][1] if i > 0 else float(times[0]) - 1.0
        earlier = ts[(ts < ta) & (ts > tp)]
        if earlier.size:
            cover |= (times >= float(earlier.min()) - pad) & (times <= ta + pad)
    pts = [[float(t), float(f)] for t, f in zip(ts, fs)]
    for seg in _point_segments(pts, gap=0.3):
        t0, t1 = float(seg[0][0]), float(seg[-1][0])
        local = (times >= t0 - pad) & (times <= t1 + pad)
        if local.any() and not np.any((f0_orig > 0) & local):
            cover |= local
    if not cover.any():
        return f0_new
    log_fs = np.log2(np.clip(fs, float(floor), float(ceiling)))
    f0_new[cover] = np.exp2(np.interp(times[cover], ts, log_fs))
    f0_new[cover] = np.clip(f0_new[cover], float(floor), float(ceiling))
    return f0_new


def _voiced_segments(f0: np.ndarray, times: np.ndarray, min_gap_frames: int = 3) -> list[tuple[float, float]]:
    """把连续浊音帧聚合成 (t0, t1) 时间段；间隔不足 min_gap_frames 的段合并。"""
    segs: list[tuple[float, float]] = []
    n = len(f0)
    frame_step = float(times[1] - times[0]) if len(times) > 1 else 0.01
    i = 0
    while i < n:
        if f0[i] <= 0:
            i += 1
            continue
        j = i
        while j + 1 < n and f0[j + 1] > 0:
            j += 1
        segs.append((max(0.0, float(times[i]) - frame_step / 2.0),
                     float(times[j]) + frame_step / 2.0))
        i = j + 1
    merged: list[tuple[float, float]] = []
    for s in segs:
        if merged and s[0] - merged[-1][1] <= min_gap_frames * frame_step:
            merged[-1] = (merged[-1][0], s[1])
        else:
            merged.append(s)
    return merged


def _interp_f0_at(f0: np.ndarray, times: np.ndarray, t: float) -> float:
    """在分析网格上插值得到 t 时刻的 f0（t 越界时取边界值）。"""
    if t <= times[0]:
        return float(f0[0])
    if t >= times[-1]:
        return float(f0[-1])
    return float(np.interp(t, times, f0))


def _find_pitch_marks(x: np.ndarray, sr: float, t0: float, t1: float, f0_src: np.ndarray, times: np.ndarray) -> list[float]:
    """在浊音段内按源基频周期定位基音标记（局部峰值）。"""
    marks: list[float] = []
    t = t0
    guard = 0
    max_marks = 200000
    while t < t1 and guard < max_marks:
        f = _interp_f0_at(f0_src, times, t)
        if not (f > 0):
            t += 0.005
            guard += 1
            continue
        T = 1.0 / f
        half = max(2, int(round(0.5 * T * sr)))
        i0 = max(0, int(round(t * sr)) - half)
        i1 = min(len(x), int(round(t * sr)) + half + 1)
        if i1 - i0 < 2:
            break
        seg = x[i0:i1]
        k = i0 + int(np.argmax(seg))
        m = k / sr
        marks.append(m)
        fm = _interp_f0_at(f0_src, times, m)
        Tm = 1.0 / fm if fm > 0 else T
        t = m + Tm
        guard += 1
    return marks


def _local_rms(x: np.ndarray, sr: float, win_s: float = 0.02) -> np.ndarray:
    """短时 RMS 包络（汉宁平滑）。"""
    n = len(x)
    win = max(8, int(round(win_s * sr)))
    if win % 2 == 0:
        win += 1
    w = np.hanning(win)
    w = w / max(float(np.sum(w)), 1e-12)
    return np.sqrt(np.clip(np.convolve(np.asarray(x, dtype=np.float64) ** 2, w, mode="same"), 0.0, None))


def _instantaneous_f0(f0: np.ndarray, times: np.ndarray, n: int, sr: float) -> np.ndarray:
    """把帧级 F0 铺到样本；只填 f0>0 的浊音段，不跨越段间零值。"""
    inst = np.zeros(n, dtype=np.float64)
    for t0, t1 in _voiced_segments(f0, times, min_gap_frames=1):
        i0 = max(0, int(round(t0 * sr)))
        i1 = min(n, int(round(t1 * sr)) + 1)
        if i1 <= i0:
            continue
        tt = np.arange(i0, i1, dtype=np.float64) / sr
        inst[i0:i1] = np.interp(tt, times, f0)
        inst[i0:i1] = np.where(inst[i0:i1] > 0, inst[i0:i1], 0.0)
    return inst


def _unit_buzz(f_inst: np.ndarray, sr: float) -> np.ndarray:
    """按逐样本 F0 生成峰值约 1 的谐波源（无 F0 处为 0）。"""
    n = len(f_inst)
    phase = np.cumsum(2.0 * np.pi * np.maximum(f_inst, 0.0) / sr)
    y = np.zeros(n, dtype=np.float64)
    for k, a in enumerate([1.0, 0.40, 0.22, 0.13, 0.08]):
        y += a * np.sin((k + 1) * phase)
    y[f_inst <= 0] = 0.0
    peak = float(np.max(np.abs(y))) if n else 0.0
    if peak > 1e-12:
        y /= peak
    return y


def _smooth_mask(mask: np.ndarray, sr: float, fade_s: float = 0.008) -> np.ndarray:
    n = max(2, int(round(fade_s * sr)))
    w = np.hanning(n * 2 + 1)
    w = w / max(float(np.sum(w)), 1e-12)
    return np.clip(np.convolve(mask.astype(np.float64), w, mode="same"), 0.0, 1.0)


def _ola_window(out: np.ndarray, wsum: np.ndarray, x: np.ndarray, s: float, a: float, L: int, sr: float) -> None:
    """把源标记 a 处的窗叠加到合成时刻 s；靠近文件头/尾时裁窗，不整窗丢弃。"""
    n = len(x)
    half = L // 2
    o0 = int(round(s * sr)) - half
    a0 = int(round(a * sr)) - half
    k0 = max(0, -o0, -a0)
    k1 = min(L, n - o0, n - a0)
    if k1 <= k0:
        return
    win = np.hanning(L)[k0:k1]
    out[o0 + k0:o0 + k1] += x[a0 + k0:a0 + k1] * win
    wsum[o0 + k0:o0 + k1] += win


def synthesize_with_f0(
    samples: np.ndarray,
    sr: int,
    f0_new: np.ndarray,
    f0_orig: np.ndarray,
    times: np.ndarray,
    frame_period: float = 10.0,
) -> np.ndarray:
    """TD-PSOLA：用编辑后的 F0 重合成音频。

    原浊音区只做周期重排并整段替换，不与原声混合。
    用户画进原清音区时，沿用最后一个有效周期；仍无能量则补谐波，
    并先清掉该处原声，避免叠音。
    """
    x = np.asarray(samples, dtype=np.float64)
    n = len(x)
    sr = float(sr)

    if not f0_new.any():
        return x.astype(np.float32)
    if np.array_equal(f0_new, f0_orig):
        return x.astype(np.float32)

    if not (f0_new > 0).any():
        return x.astype(np.float32)

    peak_in = float(np.max(np.abs(x))) if n else 0.0
    energy_floor = max(0.04 * peak_in, 1e-4)

    # 原浊音处用原周期找标记；用户新覆盖的尾段用目标 F0 在波形上找峰。
    f0_src = np.where(f0_orig > 0, f0_orig, f0_new)

    out = np.zeros(n, dtype=np.float64)
    wsum = np.zeros(n, dtype=np.float64)

    for t0, t1 in _voiced_segments(f0_new, times):
        marks = _find_pitch_marks(x, sr, t0, t1, f0_src, times)
        if not marks:
            continue
        s = t0
        j = 0
        guard = 0
        last_good_a = None
        last_good_fa = None
        while s <= t1 and guard < len(marks) * 8 + 200:
            while j + 1 < len(marks) and abs(marks[j + 1] - s) < abs(marks[j] - s):
                j += 1
            a = marks[j]
            fa = _interp_f0_at(f0_src, times, a)
            orig_here = _interp_f0_at(f0_orig, times, s) > 0
            a_i = int(round(a * sr))
            local_e = 0.0
            if 0 <= a_i < n:
                w0 = max(0, a_i - 8)
                w1 = min(n, a_i + 9)
                local_e = float(np.max(np.abs(x[w0:w1])))
            if local_e >= energy_floor:
                last_good_a = a
                last_good_fa = fa
            elif (not orig_here) and last_good_a is not None:
                a = last_good_a
                fa = last_good_fa if last_good_fa and last_good_fa > 0 else fa
            Ta = 1.0 / fa if fa > 0 else 0.01
            L = max(8, int(round(2.0 * Ta * sr)))
            if L % 2 == 1:
                L += 1
            _ola_window(out, wsum, x, s, a, L, sr)
            ft = _interp_f0_at(f0_new, times, s)
            Tt = 1.0 / ft if ft > 0 else 0.01
            if Tt <= 0:
                break
            s += Tt
            guard += 1

    orig_s = _sample_voiced_mask(f0_orig, times, n, sr)
    new_s = _sample_voiced_mask(f0_new, times, n, sr)
    psola_ok = wsum > 1e-6
    mixed = x.copy()
    mixed[new_s & psola_ok] = out[new_s & psola_ok] / wsum[new_s & psola_ok]
    # 用户画进原清音区：不保留原波形，避免和补声叠音。
    painted = new_s & ~orig_s
    mixed[painted & ~psola_ok] = 0.0

    inst = _instantaneous_f0(f0_new, times, n, sr)
    if painted.any() and peak_in > 1e-9:
        rms_mix = _local_rms(mixed, sr)
        still_empty = painted & (rms_mix < 0.03 * peak_in)
        if still_empty.any():
            fade = _smooth_mask(still_empty, sr, 0.006) * painted.astype(np.float64)
            buzz = _unit_buzz(inst, sr)
            mixed = mixed * (1.0 - fade) + (0.10 * peak_in * buzz) * fade

    synthesized = (new_s & psola_ok) | painted
    out = mixed
    peak_synth = float(np.max(np.abs(out[synthesized]))) if synthesized.any() else 0.0
    if peak_in > 1e-9 and peak_synth > peak_in:
        out[synthesized] *= peak_in / peak_synth
    return out.astype(np.float32)


def _sample_voiced_mask(f0: np.ndarray, times: np.ndarray, n: int, sr: float) -> np.ndarray:
    """帧级浊音 -> 样本掩码（不额外外扩，避免原声在段缘漏进来）。"""
    mask = np.zeros(n, dtype=bool)
    for t0, t1 in _voiced_segments(f0, times, min_gap_frames=1):
        i0 = max(0, int(round(t0 * sr)))
        i1 = min(n, int(round(t1 * sr)) + 1)
        mask[i0:i1] = True
    return mask


def voiced_mask_continuous(x: np.ndarray, f0: np.ndarray, times: np.ndarray, sr: float) -> np.ndarray:
    """按帧级浊音掩码生成样本级掩码（分段边界做小扩展，避免窗口边缘裂化）。"""
    n = len(x)
    mask = np.zeros(n, dtype=bool)
    for t0, t1 in _voiced_segments(f0, times):
        pad = int(round(0.01 * sr))  # 10ms 扩展
        i0 = max(0, int(round(t0 * sr)) - pad)
        i1 = min(n, int(round(t1 * sr)) + 1 + pad)
        mask[i0:i1] = True
    return mask


# ---------------------------------------------------------------------------
# 编辑点后处理
# ---------------------------------------------------------------------------
def smooth_points(points: list[list[float]], window: int = 5) -> list[list[float]]:
    """按浊音段在半音域做滑动平均（跨段不混合）。"""
    if not points:
        return points
    segs: list[list[list[float]]] = []
    cur: list[list[float]] = []
    for p in points:
        if cur and p[0] - cur[-1][0] > 0.3:
            segs.append(cur)
            cur = []
        cur.append(p)
    if cur:
        segs.append(cur)

    out: list[list[float]] = []
    w = max(3, int(window))
    if w % 2 == 0:
        w += 1
    half = w // 2
    for seg in segs:
        if len(seg) <= w:
            out.extend(seg)
            continue
        fs = np.array([p[1] for p in seg], dtype=np.float64)
        log_fs = np.log2(np.maximum(fs, 1e-9))
        log_fs_p = np.pad(log_fs, (half, half), mode="edge")
        fs_s = np.exp2(np.convolve(log_fs_p, np.ones(w) / w, mode="valid"))
        for (t, _), f in zip(seg, fs_s):
            out.append([t, round(float(f), 3)])
    return out


def shift_semitones(
    points: list[list[float]],
    n_semitones: float,
    floor: float | None = None,
    ceiling: float | None = None,
) -> list[list[float]]:
    """整体平移 n 个半音。"""
    if not points:
        return points
    r = 2.0 ** (n_semitones / 12.0)
    out: list[list[float]] = []
    for time, frequency in points:
        shifted = frequency * r
        if floor is not None:
            shifted = max(float(floor), shifted)
        if ceiling is not None:
            shifted = min(float(ceiling), shifted)
        out.append([time, round(shifted, 3)])
    return out


# ---------------------------------------------------------------------------
# 按音节声调提取特征点（最高点/最低点）
# ---------------------------------------------------------------------------
import re as _re

_TONE_RE = _re.compile(r"([0-5])\s*$")
_FULLWIDE = str.maketrans("０１２３４５", "012345")

# 拼音音节：字母串（含 ü / u: 记法），可带声调数字 0-5（0/5 = 轻声）
_PINYIN_SYL_RE = _re.compile(r"(?:u:|[a-zA-ZüÜ])+[0-5]?")
_PUNCT = set("，。、；：！？·…～（）()【】[]「」『』“”\"'《》<>　 —–-_")
# 声调数字（半角/全角 0-5）
_DIGIT_CHARS = set("012345０１２３４５")


def split_syllable_text(text: str) -> tuple[list[str], str]:
    """把汉字或拼音文本切分为音节序列，用于对齐到音节框。

    - **拼音格式**（文本含英文字母）：以**声调数字（0-5）作为音节边界**切分，
      例如 `wo3men0shi4yi1shi4ba0` -> [wo3, men0, shi4, yi1, shi4, ba0]（6 个）；
      空格/标点自动跳过；连续字母串后没有数字时整体视为一个音节
      （因此拼音必须写全声调数字才能精确切分）。
    - **汉字格式**（纯汉字）：每个汉字一个音节；紧跟的**声调数字（半角/全角
      0-5）并入该汉字**（如 `好3你0在吗` -> [好3, 你0, 在, 吗]），便于后续
      按声调提取特征点；忽略空白与常见标点。

    返回 (音节列表, 格式说明："拼音" / "汉字" / "")。
    """
    text = (text or "").strip()
    if not text:
        return [], ""
    if _re.search(r"[A-Za-züÜ]", text):
        syls = [s for s in _PINYIN_SYL_RE.findall(text) if s]
        return syls, "拼音"
    syls: list[str] = []
    for ch in text:
        if ch in _PUNCT or not ch.strip():
            continue
        if ch in _DIGIT_CHARS:
            # 声调数字并入前一汉字（如 “好3”）；无前一音节或前一音节已带数字则忽略
            if syls and syls[-1][-1] not in _DIGIT_CHARS:
                syls[-1] += ch
            continue
        syls.append(ch)
    return syls, "汉字"


def parse_tone(text: str) -> int | None:
    """从音节文本解析声调号。末尾数字 1-4 -> 该声调；0 或 5 -> 0（轻声）；
    支持全角数字；无数字返回 None。例：'liu4' -> 4，'ma0'/'ma5' -> 0，'好3' -> 3。"""
    if not text:
        return None
    m = _TONE_RE.search(text.strip().translate(_FULLWIDE))
    if not m:
        return None
    d = int(m.group(1))
    return 0 if d in (0, 5) else d


def _detect_tone(st: np.ndarray) -> int | None:
    """从音节内音高轮廓（半音序列）自动推断声调，供无数字标注（如纯汉字）使用。

    判据（半音域，保守阈值）：
    - 整体接近水平（跨度 < 2 半音）→ 1 声（阴平，高平）；
    - 起点附近为最低、终点明显高于起点 → 2 声（阳平，升）；
    - 起点附近为最高、终点明显低于起点 → 4 声（去声，降）；
    - 谷点出现在中部且明显低于两端 → 3 声（上声，降-升/半三）；
    - 其余无法可靠判断 → None（退回通用：端点 + 最高 + 最低）。
    """
    n = len(st)
    if n < 4:
        return None
    i_min = int(np.argmin(st))
    i_max = int(np.argmax(st))
    rng = float(np.max(st) - np.min(st))
    start, end = float(st[0]), float(st[-1])
    if rng < 2.0:
        return 1
    if i_min <= 0.25 * n and end - start > 1.2:
        return 2
    if i_max <= 0.25 * n and start - end > 1.2:
        return 4
    if 0.15 * n < i_min < 0.9 * n:
        dip = float(np.min(st))
        if (start - dip) > 0.8 and (end - dip) > 0.8:
            return 3
    if i_min >= 0.6 * n and start - end > 0.8:
        return 4  # 整体下行且低点在尾部
    return None


def _tone_subset_features(subset: list[list[float]], tone: int | None) -> list[list[float]]:
    """对单个音节内的点序列按声调提取特征点（半音域，删除其间的平滑过渡点）。

    tone 取值：
    - 1/2/3/4：相应声调规则（见下）；
    - 5：只保留**最低点**（轻声，前接 1/2/4 声）；
    - 6：只保留**最高点**（轻声，前接 3 声）；
    - None：兜底保留端点 + 段内部最高/最低点。

    声调规则：
    - **1 声（阴平）**：稳定段两端点；
    - **2 声（阳平，升）**：前半段最低点 + 后半段最高点；
    - **3 声（上声）**：两端点 + 最低点（谷/低点）；
    - **4 声（去声，降）**：前半段最高点 + 后半段最低点。
    """
    n = len(subset)
    if n <= 2:
        return [list(p) for p in subset]
    fs = np.array([p[1] for p in subset], dtype=np.float64)
    st = 12.0 * np.log2(np.maximum(fs, 1e-9))
    h = n // 2  # 前后半段分界
    if tone == 1:
        keep = {0, n - 1}
    elif tone == 2:  # 前半段低点 + 后半段高点
        keep = {int(np.argmin(st[:h])), h + int(np.argmax(st[h:]))}
    elif tone == 4:  # 前半段高点 + 后半段低点
        keep = {int(np.argmax(st[:h])), h + int(np.argmin(st[h:]))}
    elif tone == 3:  # 两端点 + 最低点（谷/低点）
        keep = {0, n - 1, int(np.argmin(st))}
    elif tone == 5:  # 轻声·前接 1/2/4 声：最低点
        keep = {int(np.argmin(st))}
    elif tone == 6:  # 轻声·前接 3 声：最高点
        keep = {int(np.argmax(st))}
    else:  # None 兜底：端点 + 段内部最高/最低点
        keep = {0, n - 1}
        for i in (int(np.argmin(st)), int(np.argmax(st))):
            if 2 <= i <= n - 3:
                keep.add(i)
    idx = sorted(keep)
    return [[round(float(subset[i][0]), 4), round(float(subset[i][1]), 3)] for i in idx]


def extract_tone_feature_points(
    points: list[list[float]],
    syllables: list[dict],
    pad: float = 0.02,
) -> list[list[float]]:
    """按音节声调自动提取音高特征点。

    每个编辑点按时间**归属到唯一一个音节框**（连续铺满时 pad 为 0，避免
    相邻音节轮廓互相污染），在框内按声调保留端点 + 最高点 + 最低点，
    删除之间的平滑过渡点（框内跨清音间隔时按浊音段分别处理）；
    不属于任何框的点原样保留。返回按时间排序的去重点集。

    声调来源：音节文本末尾数字（1-4，汉字/拼音均可，如 `liu4` / `好3`）；
    无数字（如纯汉字对齐）时自动按框内轮廓推断声调。
    """
    if not points:
        return []
    if not syllables:
        return [list(p) for p in points]

    boxes = sorted(syllables, key=lambda s: float(s.get("t0", 0.0)))
    margin = max(0.0, float(pad))
    # 连续铺满时邻框共享边界，pad 必须为 0，否则后一音节开头的点会被前一框抢走。
    # 有空隙时每侧最多吃到间隙的一半。
    windows: list[tuple[float, float]] = []
    for i, s in enumerate(boxes):
        t0 = float(s.get("t0", 0.0))
        t1 = float(s.get("t1", 0.0))
        if i == 0:
            lo = t0 - margin
        else:
            gap = t0 - float(boxes[i - 1].get("t1", t0))
            lo = t0 - min(margin, max(0.0, gap / 2.0))
        if i == len(boxes) - 1:
            hi = t1 + margin
        else:
            gap = float(boxes[i + 1].get("t0", t1)) - t1
            hi = t1 + min(margin, max(0.0, gap / 2.0))
        windows.append((lo, hi))

    # ---- 归属：每个点至多属于一个音节框（按序取第一个包含它的框） ----
    owned: list[list[list[float]]] = [[] for _ in boxes]
    assigned = [False] * len(points)
    for point_index, p in enumerate(points):
        for i, (lo, hi) in enumerate(windows):
            if lo - 1e-9 <= p[0] <= hi + 1e-9:
                owned[i].append(p)
                assigned[point_index] = True
                break

    out: list[list[float]] = []
    prev_eff: int | None = None  # 前一音节的有效声调（供轻声参考：1/2/4 -> 低，3 -> 高）
    for i, s in enumerate(boxes):
        subset = owned[i]
        if not subset:
            continue
        base = parse_tone(str(s.get("text", "")))  # 0(轻声)/1-4 或 None
        segs = _point_segments(subset, gap=0.12)
        # 无数字标注：从轮廓自动推断声调（供规则与轻声参考）
        detected = None
        if base is None and segs:
            fs = np.array([p[1] for p in segs[0]], dtype=np.float64)
            st = 12.0 * np.log2(np.maximum(fs, 1e-9))
            detected = _detect_tone(st)
        eff = base if base not in (None, 0) else detected  # 轻声不提供调号，用自动推断（若有）

        for seg in segs:
            rule: int | None
            if base == 0:
                # 轻声：参考前一音节声调（1/2/4 -> 取最低点；3 -> 取最高点）
                if prev_eff in (1, 2, 4):
                    rule = 5
                elif prev_eff == 3:
                    rule = 6
                else:
                    rule = None  # 无前音参考 -> 兜底
            elif base is not None:
                rule = base
            else:
                rule = detected
            out.extend(_tone_subset_features(seg, rule))

        if base == 0:
            prev_eff = None  # 轻声不向后传递声调参考（保持审慎）
        else:
            prev_eff = eff

    # 音节框外的曲线不参与声调简化，但必须原样保留。
    out.extend([list(p) for i, p in enumerate(points) if not assigned[i]])

    # 排序 + 去除同时间重复点
    out.sort(key=lambda p: p[0])
    dedup: list[list[float]] = []
    for p in out:
        if not dedup or abs(p[0] - dedup[-1][0]) > 1e-9:
            dedup.append(p)
    return dedup


# ---------------------------------------------------------------------------
# 自动音节切分
# ---------------------------------------------------------------------------
def auto_segment_syllables(
    samples: np.ndarray,
    sr: int,
    times: np.ndarray | None = None,
    f0: np.ndarray | None = None,
    min_syl_dur: float = 0.10,
    max_syl_dur: float = 0.65,
    min_gap: float = 0.03,
    ext_max: float = 0.15,
    contiguous: bool = True,
) -> list[dict]:
    """自动切分音节边界。

    依据：
    1. 浊音段（F0 > 0）作为音节核（韵母），相邻间隔小于 min_gap 的段合并；
    2. 边界向两侧按能量包络（RMS）扩展，以纳入声母/韵尾（最多 ext_max）；
    3. 过长的浊音段（> max_syl_dur）在中间 60% 区域的最深能量谷处拆分；
    4. contiguous=True 时把音节框**连续铺满**整条时间轴：首框起点为 0、
       末框终点为音频时长，段间边界取两框间隙内 RMS 最低的自然切分点
       （间隙平坦时取中点），保证两两之间无空隙。

    返回 [{"id": ..., "text": "音N", "t0": ..., "t1": ...}, ...]，
    可直接作为音节标注使用（再手动改名/加声调数字即可）。
    """
    if times is None or f0 is None or len(times) == 0:
        return []

    dur = len(samples) / sr
    x = samples.astype(np.float64)

    # ---- 能量包络（RMS，10ms 窗 / 5ms 步进） ----
    win = max(4, int(0.01 * sr))
    hop = max(2, int(0.005 * sr))
    n = len(x)
    n_env = max(1, (n - win) // hop + 1)
    rms_t = np.arange(n_env, dtype=np.float64) * (hop / sr)
    rms_v = np.zeros(n_env, dtype=np.float64)
    for i in range(n_env):
        seg = x[i * hop:i * hop + win]
        rms_v[i] = float(np.sqrt(np.mean(seg * seg)))
    peak_rms = float(np.max(rms_v)) if n_env else 1.0
    thr = max(0.08 * peak_rms, 1e-6)  # 有声/无声阈值

    def rms_at(t: float) -> float:
        i = int(np.clip(t / (hop / sr), 0, n_env - 1))
        return float(rms_v[i])

    # ---- 浊音段 ----
    frame_gap = (times[1] - times[0]) if len(times) > 1 else 0.01
    runs = _voiced_segments(f0, times, min_gap_frames=max(1, int(round(min_gap / frame_gap))))

    # ---- 边界扩展 ----
    boxes: list[list[float]] = []
    for t0, t1 in runs:
        ext_l = 0.0
        while ext_l < ext_max and t0 - ext_l - 0.005 > 0 and rms_at(t0 - ext_l - 0.005) > thr:
            ext_l += 0.005
        ext_r = 0.0
        while ext_r < ext_max and t1 + ext_r + 0.005 < dur and rms_at(t1 + ext_r + 0.005) > thr:
            ext_r += 0.005
        boxes.append([max(0.0, t0 - ext_l), min(dur, t1 + ext_r)])

    boxes.sort()
    # 夹紧不重叠
    for i in range(1, len(boxes)):
        if boxes[i][0] < boxes[i - 1][1] + min_gap:
            boxes[i][0] = min(boxes[i][1] - min_syl_dur, boxes[i - 1][1] + min_gap)
            if boxes[i][0] < boxes[i - 1][1]:
                boxes[i][0] = boxes[i - 1][1] + 0.005

    # ---- 超长段在能量谷拆分 ----
    final: list[list[float]] = []
    for a, b in boxes:
        if b - a <= max_syl_dur:
            final.append([a, b])
            continue
        seg_idx = np.where((rms_t >= a + 0.2 * (b - a)) & (rms_t <= a + 0.8 * (b - a)))[0]
        if len(seg_idx) < 2:
            final.append([a, b])
            continue
        mid = int(np.argmin(rms_v[seg_idx]))
        dip_t = float(rms_t[seg_idx[mid]])
        dip_v = float(rms_v[seg_idx[mid]])
        mean_v = float(np.mean(rms_v[seg_idx]))
        if dip_v < 0.7 * mean_v and (dip_t - a) >= min_syl_dur and (b - dip_t) >= min_syl_dur:
            final.append([a, dip_t])
            final.append([dip_t, b])
        else:
            final.append([a, b])

    # 去除过短段
    final = [s for s in final if s[1] - s[0] >= min_syl_dur * 0.7]

    # ---- 连续铺满（默认）：无空隙、首尾贴 [0, dur] ----
    if contiguous and final:
        final.sort()
        final[0][0] = 0.0
        final[-1][1] = dur
        for i in range(len(final) - 1):
            a, b = final[i], final[i + 1]
            if b[0] <= a[1]:  # 已相接/重叠：取中点保证有序
                m = (a[1] + b[0]) / 2.0
            else:
                seg_idx = np.where((rms_t >= a[1]) & (rms_t <= b[0]))[0]
                if len(seg_idx) >= 2:
                    rms_seg = rms_v[seg_idx]
                    if float(np.max(rms_seg) - np.min(rms_seg)) > 0.05 * peak_rms:
                        m = float(rms_t[seg_idx[int(np.argmin(rms_seg))]])
                    else:  # 间隙平坦（如停顿）：取中点
                        m = (a[1] + b[0]) / 2.0
                else:
                    m = (a[1] + b[0]) / 2.0
            a[1] = m
            b[0] = m

    out: list[dict] = []
    for i, (a, b) in enumerate(final):
        if b - a < min_syl_dur * 0.7:
            continue
        out.append(
            {
                "id": f"auto-{i + 1}",
                "text": f"音{i + 1}",
                "t0": round(float(a), 4),
                "t1": round(float(b), 4),
            }
        )
    return out


# ---------------------------------------------------------------------------
# 特征点提取（仿 Praat "Stylize pitch"）
# ---------------------------------------------------------------------------
def _point_segments(points: list[list[float]], gap: float = 0.3) -> list[list[list[float]]]:
    """按时间间隔把点列切分为浊音段（间隔 > gap 秒视为不同段）。"""
    segs: list[list[list[float]]] = []
    cur: list[list[float]] = []
    for p in points:
        if cur and p[0] - cur[-1][0] > gap:
            segs.append(cur)
            cur = []
        cur.append(p)
    if cur:
        segs.append(cur)
    return segs


def _rdp_indices(ts: np.ndarray, st: np.ndarray, tol: float) -> set[int]:
    """Ramer–Douglas–Peucker 折线简化（迭代栈实现）。

    在半音域上，若某点到两端点连线的偏差超过 tol 半音则保留该点并递归细分；
    否则删除 —— 即"去除中间连续性好的点，保留趋势变化的特征点"。
    返回保留的索引集合（含两端点）。
    """
    keep = {0, len(ts) - 1}
    stack = [(0, len(ts) - 1)]
    n = len(ts)
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        span = ts[b] - ts[a]
        if span <= 1e-12:
            continue
        best_k = -1
        best_dev = -1.0
        base = st[a]
        slope = (st[b] - st[a]) / span
        for i in range(a + 1, b):
            dev = abs(st[i] - (base + slope * (ts[i] - ts[a])))
            if dev > best_dev:
                best_dev = dev
                best_k = i
        if best_k >= 0 and best_dev > tol:
            keep.add(best_k)
            stack.append((a, best_k))
            stack.append((best_k, b))
    return keep


def stylize_points(
    points: list[list[float]],
    max_change_semitones: float = 2.0,
    min_interval: float = 0.04,
) -> list[list[float]]:
    """Praat 式音高风格化：提取反映音高变化趋势的特征点。

    - 按浊音段独立处理（段端点必保）；
    - RDP 折线简化（半音域）：删除与相邻保留点连线偏差小于容差的
      “连续性好的”中间点；
    - 额外保留“显著转折点”（相邻三点构成 V/Λ 形且落差超过容差），
      防止快速拐弯被直线化；
    - 清理时间间隔过近的冗余点（非关键点优先移除）。

    返回仍按时间排序的 [[t, f0], ...]，f0 值取自原曲线，
    可直接用于拖拽微调并重合成（相邻保留点间按直线插值）。
    """
    tol = max(0.05, float(max_change_semitones))
    out: list[list[float]] = []
    for seg in _point_segments(points):
        n = len(seg)
        if n <= 4:
            out.extend(seg)
            continue
        ts = np.array([p[0] for p in seg], dtype=np.float64)
        st = 12.0 * np.log2(np.array([p[1] for p in seg], dtype=np.float64))

        keep = _rdp_indices(ts, st, tol)
        # 端点和显著转折不可删；普通 RDP 点可在过密时择优清理。
        critical = {0, n - 1}

        # 显著转折点补保：V/Λ 形且相邻落差超过容差（即使 RDP 未保留）
        for i in range(1, n - 1):
            d1 = st[i] - st[i - 1]
            d2 = st[i + 1] - st[i]
            if ((d1 > 1e-9) != (d2 > 1e-9)
                    and min(abs(d1), abs(d2)) > tol):
                keep.add(i)
                critical.add(i)

        # 最小间隔去冗余（非关键点优先移除）
        changed = True
        while changed:
            changed = False
            ks = sorted(keep)
            if len(ks) <= 2:
                break
            for i in range(1, len(ks) - 1):
                if ks[i] in critical:
                    continue
                if (
                    ts[ks[i]] - ts[ks[i - 1]] < min_interval
                    or ts[ks[i + 1]] - ts[ks[i]] < min_interval
                ):
                    keep.discard(ks[i])
                    changed = True
                    break

        idx = sorted(keep)
        out.extend([[round(float(ts[i]), 4), round(float(seg[i][1]), 3)] for i in idx])
    return out


# ---------------------------------------------------------------------------
# 波形显示
# ---------------------------------------------------------------------------
def decimate_waveform(samples: np.ndarray, sr: int, n_bins: int = 900) -> list[list[float]]:
    """按包络峰值抽稀波形 -> [[t, amp], ...]（amp 带符号，-1..1）。"""
    if len(samples) == 0:
        return []
    edges = np.unique(np.linspace(0, len(samples), n_bins + 1).astype(int))
    out: list[list[float]] = []
    dur = len(samples) / sr
    for i in range(len(edges) - 1):
        seg = samples[edges[i]:edges[i + 1]]
        if len(seg) == 0:
            continue
        k = int(np.argmax(np.abs(seg)))
        out.append([round(((edges[i] + k) / len(samples)) * dur, 4), round(float(seg[k]), 5)])
    return out


# ---------------------------------------------------------------------------
# 示例音频
# ---------------------------------------------------------------------------
def generate_sample_audio(sr: int = 16000) -> bytes:
    """生成约 3.6 秒哼鸣示例：三音节（降调、升调、再降调），中间含停顿，
    便于直接体验拖拽调音高与重合成。"""
    rng = np.random.default_rng(20240501)

    def syllable(dur, f_start, f_end, vibrato=5.0, amp=0.5, phase0=0.0):
        n = int(dur * sr)
        t = np.arange(n) / sr
        f = np.linspace(f_start, f_end, n) * (1 + 0.015 * np.sin(2 * np.pi * vibrato * t))
        phase = phase0 + 2 * np.pi * np.cumsum(f) / sr
        env = np.minimum(1.0, t / 0.045) * np.minimum(1.0, (dur - t) / 0.09)
        y = np.zeros(n)
        for k, a in enumerate([1.0, 0.40, 0.22, 0.13, 0.08]):
            y += a * np.sin((k + 1) * phase)
        y *= env * amp
        return y, phase[-1]

    s1, ph = syllable(0.9, 165, 105)
    gap = np.zeros(int(0.20 * sr))
    s2, ph2 = syllable(0.95, 165, 240, phase0=ph + 0.5)
    s3, _ = syllable(0.8, 205, 125, phase0=ph2 + 0.5)

    y = np.concatenate([s1, gap, s2, gap, s3])
    y = y + rng.normal(0, 0.004, len(y))  # 轻微噪声底
    y = y / max(1e-9, float(np.max(np.abs(y)))) * 0.9
    return wav_bytes(y.astype(np.float32), sr)


# ---------------------------------------------------------------------------
# Praat TextGrid 多层导出 / 解析（区间层 IntervalTier + 点层 TextTier）
# ---------------------------------------------------------------------------
def _tg_escape(value) -> str:
    """按 Praat 规则转义字符串：内嵌双引号写成两个双引号。"""
    return str(value or "").replace("\r", " ").replace("\n", " ").replace('"', '""')


def _tg_unescape(value: str) -> str:
    return value.replace('""', '"')


def _tg_num(value: float) -> str:
    """足够往返双精度时间且不制造无意义尾零。"""
    return format(float(value), ".17g")


def _textgrid_xmax(tiers: list[dict], duration: float) -> float:
    try:
        xmax = float(duration)
    except (TypeError, ValueError):
        xmax = float("nan")
    if np.isfinite(xmax) and xmax > 0:
        return xmax

    values: list[float] = []
    for tier in tiers:
        for item in tier.get("items", []):
            for key in ("t", "t0", "t1"):
                try:
                    value = float(item[key])
                except (KeyError, TypeError, ValueError):
                    continue
                if np.isfinite(value):
                    values.append(value)
    xmax = max(values, default=1.0)
    return xmax if xmax > 0 else 1.0


def _clean_point_tier(items: list[dict], xmax: float) -> list[dict]:
    points: list[dict] = []
    for item in items:
        try:
            time = float(item["t"])
        except (KeyError, TypeError, ValueError):
            continue
        if not np.isfinite(time):
            continue
        points.append({
            "t": min(max(time, 0.0), xmax),
            "text": str(item.get("text", "")),
        })
    points.sort(key=lambda point: point["t"])

    # TextTier 要求时间严格递增；同一时刻保留最后一项（通常是最近编辑值）。
    deduped: list[dict] = []
    for point in points:
        if deduped and abs(point["t"] - deduped[-1]["t"]) <= 1e-12:
            deduped[-1] = point
        else:
            deduped.append(point)
    return deduped


def _heal_interval_tier(items: list[dict], xmax: float) -> list[dict]:
    """把区间项整理为 Praat 严格合法的 IntervalTier：
    排序、裁到 [0,xmax]、去重叠，并**连续铺满** [0,xmax]（空隙补空区间、
    首尾贴齐、无项时生成一个整段空区间），保证 Praat 可读。
    """
    out: list[dict] = []
    for it in items:
        try:
            t0 = min(max(float(it.get("t0", 0)), 0.0), xmax)
            t1 = min(max(float(it.get("t1", t0)), 0.0), xmax)
        except (TypeError, ValueError):
            continue
        if np.isfinite(t0) and np.isfinite(t1) and t1 > t0:
            out.append({"t0": t0, "t1": t1, "text": str(it.get("text", ""))})
    out.sort(key=lambda x: x["t0"])
    # 去除重叠；所有相邻边界最终使用同一个 float，保证严格相接。
    merged: list[dict] = []
    for it in out:
        if merged and it["t0"] < merged[-1]["t1"]:
            it = dict(it)
            it["t0"] = merged[-1]["t1"]
            if it["t1"] <= it["t0"]:
                continue
        merged.append(it)
    # 连续铺满
    if not merged:
        merged.append({"t0": 0.0, "t1": xmax, "text": ""})
    elif merged[0]["t0"] > 0.0:
        merged.insert(0, {"t0": 0.0, "t1": merged[0]["t0"], "text": ""})
    filled: list[dict] = []
    for it in merged:
        if filled:
            previous_end = filled[-1]["t1"]
            if it["t0"] > previous_end:
                filled.append({"t0": previous_end, "t1": it["t0"], "text": ""})
            elif it["t0"] != previous_end:
                it = dict(it)
                it["t0"] = previous_end
        filled.append(it)
    if filled[-1]["t1"] < xmax:
        filled.append({"t0": filled[-1]["t1"], "t1": xmax, "text": ""})
    elif filled[-1]["t1"] != xmax:
        filled[-1]["t1"] = xmax
    return filled


def textgrid_export_tiers(tiers: list[dict], duration: float) -> str:
    """把多层标注导出为 Praat 可直接读取的 TextGrid（长格式 ooTextFile）。

    tiers: [{"name": str, "kind": "interval"|"point", "items": [...]}]
      - interval 项: {"t0": .., "t1": .., "text": ..}（导出时自动连续铺满 [0,xmax]）
      - point    项: {"t": .., "text": ..}
    区间层保证 Praat 结构合法（首贴 0、尾贴 xmax、无缝隙、每层 >= 1 个区间），
    空点层也合法（points: size = 0）。返回 UTF-8 文本内容（无 BOM，含结尾换行）。
    """
    tiers = [t for t in tiers if t.get("kind") in ("point", "interval")]
    xmax = _textgrid_xmax(tiers, duration)

    parts = [
        "File type = \"ooTextFile\"",
        'Object class = "TextGrid"',
        "",
        "xmin = 0",
        f"xmax = {_tg_num(xmax)}",
        "tiers? <exists>",
        f"size = {len(tiers)}",
        "item []:",
    ]
    for k, t in enumerate(tiers, start=1):
        name = _tg_escape(t.get("name", f"layer{k}"))
        parts.append(f"    item [{k}]:")
        if t.get("kind") == "point":
            parts.append('        class = "TextTier"')
            parts.append(f'        name = "{name}"')
            parts.append("        xmin = 0")
            parts.append(f"        xmax = {_tg_num(xmax)}")
            pts = _clean_point_tier(list(t.get("items", [])), xmax)
            parts.append(f"        points: size = {len(pts)}")
            for j, it in enumerate(pts, start=1):
                parts.append(f"        points [{j}]:")
                parts.append(f"            number = {_tg_num(it['t'])}")
                parts.append(f'            mark = "{_tg_escape(it.get("text", ""))}"')
        else:
            parts.append('        class = "IntervalTier"')
            parts.append(f'        name = "{name}"')
            parts.append("        xmin = 0")
            parts.append(f"        xmax = {_tg_num(xmax)}")
            healed = _heal_interval_tier(list(t.get("items", [])), xmax)
            parts.append(f"        intervals: size = {len(healed)}")
            for j, it in enumerate(healed, start=1):
                parts.append(f"        intervals [{j}]:")
                parts.append(f"            xmin = {_tg_num(it['t0'])}")
                parts.append(f"            xmax = {_tg_num(it['t1'])}")
                parts.append(f'            text = "{_tg_escape(it.get("text", ""))}"')
    return "\n".join(parts) + "\n"


def textgrid_export(syllables: list[dict], duration: float, tier_name: str = "音节") -> str:
    """（兼容）把单个音节区间层导出为 TextGrid。"""
    return textgrid_export_tiers([{"name": tier_name, "kind": "interval", "items": syllables}], duration)


def textgrid_parse(content: bytes | str) -> tuple[list[dict], float]:
    """解析 Praat TextGrid（长格式/短格式，含区间层与点层）。

    返回 (tiers, xmax)：
      tiers: [{"name": .., "kind": "interval"|"point",
               "items": [{"t0","t1","text"} | {"t","text"}]}]
    解析失败抛 ValueError。
    """
    if isinstance(content, bytes):
        try:
            if content.startswith((b"\xff\xfe", b"\xfe\xff")):
                text = content.decode("utf-16")
            else:
                text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            # 兼容少量 Unicode 之前的 Windows TextGrid；无法可靠区分 MacRoman。
            text = content.decode("latin-1")
    else:
        text = content.lstrip("\ufeff")

    parsed = _textgrid_parse_long(text)
    if parsed is None:
        parsed = _textgrid_parse_short(text)
    if parsed is None or not parsed[0]:
        raise ValueError("未能解析 TextGrid（需要包含 IntervalTier / TextTier 标注层）。")
    return parsed


def _textgrid_parse_long(text: str) -> tuple[list[dict], float] | None:
    """解析带 key=value 注释的 TextGrid 长格式。"""
    item_re = r"^\s*item\s*\[\s*\d+\s*\]\s*:"
    if not _re.search(item_re, text, _re.MULTILINE) or not _re.search(r"class\s*=", text):
        return None
    object_match = _re.search(r'Object\s+class\s*=\s*"((?:""|[^"])*)"', text)
    if object_match and _tg_unescape(object_match.group(1)).lower() != "textgrid":
        raise ValueError("文件对象类型不是 TextGrid")

    header = _re.split(item_re, text, maxsplit=1, flags=_re.MULTILINE)[0]
    xmax_matches = _re.findall(r"^\s*xmax\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)",
                               header, _re.MULTILINE)
    xmax = float(xmax_matches[0]) if xmax_matches else 0.0
    tiers: list[dict] = []
    cur: dict | None = None
    cur_item: dict | None = None

    def flush():
        nonlocal cur, cur_item
        if cur is not None and cur.get("_class"):
            kind = cur["kind"]
            if kind == "point":
                cur["items"] = [item for item in cur["items"] if "t" in item]
            else:
                cur["items"] = [item for item in cur["items"] if "t0" in item and "t1" in item]
            cur.pop("_class", None)
            tiers.append(cur)
        cur, cur_item = None, None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _re.match(r"item\s*\[\s*\d+\s*\]\s*:", line):
            flush()
            cur = {"name": "", "kind": "interval", "items": []}
            continue
        if cur is None:
            continue
        m = _re.match(r'class\s*=\s*"((?:""|[^"])*)"\s*$', line)
        if m:
            cls = _tg_unescape(m.group(1)).strip().lower()
            if cls == "intervaltier":
                cur["kind"] = "interval"
            elif cls in ("texttier", "pointtier"):
                # PointTier 是本项目旧版本写出的非标准名称，仅为向后兼容而接受。
                cur["kind"] = "point"
            else:
                raise ValueError(f"不支持的 TextGrid 层类型：{cls or '空'}")
            cur["_class"] = cls
            continue
        m = _re.match(r'name\s*=\s*"((?:""|[^"])*)"\s*$', line)
        if m:
            cur["name"] = _tg_unescape(m.group(1))
            continue
        if cur_item is not None:
            m = _re.match(r"(xmin|number|time)\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)", line)
            if m:
                if m.group(1) == "xmin":
                    cur_item["t0"] = float(m.group(2))
                else:
                    cur_item["t"] = float(m.group(2))
                continue
            m = _re.match(r"xmax\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)", line)
            if m:
                cur_item["t1"] = float(m.group(1))
                continue
            m = _re.match(r'(text|mark)\s*=\s*"((?:""|[^"])*)"\s*$', line)
            if not m:
                m = _re.match(r"(text|mark)\s*=\s*(.*)$", line)
            if m:
                cur_item["text"] = _tg_unescape(m.group(2))
                cur_item = None
            continue
        m = _re.match(r"(intervals|points)\s*\[\s*(\d+)\s*\]\s*:", line)
        if m:
            cur_item = {}
            cur["items"].append(cur_item)
    flush()
    return tiers, xmax


def _textgrid_short_tokens(text: str) -> list[tuple[str, str]]:
    """提取 Praat 认为是数据的独立字符串、数字和 flag，忽略标签与 ! 注释。"""
    tokens: list[tuple[str, str]] = []
    number_re = _re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
    for raw in text.splitlines():
        i = 0
        while i < len(raw):
            ch = raw[i]
            if ch == "!":
                break
            if ch == '"':
                i += 1
                value: list[str] = []
                while i < len(raw):
                    if raw[i] == '"':
                        if i + 1 < len(raw) and raw[i + 1] == '"':
                            value.append('"')
                            i += 2
                            continue
                        i += 1
                        break
                    value.append(raw[i])
                    i += 1
                tokens.append(("string", "".join(value)))
                continue
            if ch == "<":
                end = raw.find(">", i + 1)
                if end >= 0:
                    tokens.append(("flag", raw[i:end + 1].lower()))
                    i = end + 1
                    continue
            match = number_re.match(raw, i)
            if match:
                before = raw[i - 1] if i > 0 else " "
                after = raw[match.end()] if match.end() < len(raw) else " "
                if before not in "[_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" and after not in "]_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
                    tokens.append(("number", match.group(0)))
                    i = match.end()
                    continue
            i += 1
    return tokens


def _textgrid_parse_short(text: str) -> tuple[list[dict], float] | None:
    """解析最短格式及 Praat 允许的多数据同行/带注释变体。"""
    tokens = _textgrid_short_tokens(text)
    try:
        i = 0
        if len(tokens) < 6 or tokens[0] != ("string", "ooTextFile") or tokens[1] != ("string", "TextGrid"):
            return None
        i = 2

        def take(kind: str) -> str:
            nonlocal i
            if i >= len(tokens) or tokens[i][0] != kind:
                raise ValueError
            value = tokens[i][1]
            i += 1
            return value

        _xmin = float(take("number"))
        xmax = float(take("number"))
        exists = take("flag")
        if exists == "<absent>":
            return [], xmax
        if exists != "<exists>":
            raise ValueError
        tier_count = int(float(take("number")))
        tiers: list[dict] = []
        for _ in range(tier_count):
            cls = take("string").strip().lower()
            name = take("string")
            _tier_xmin = float(take("number"))
            _tier_xmax = float(take("number"))
            count = int(float(take("number")))
            items: list[dict] = []
            if cls == "intervaltier":
                for _ in range(count):
                    t0 = float(take("number"))
                    t1 = float(take("number"))
                    txt = take("string")
                    items.append({"t0": t0, "t1": t1, "text": txt})
                kind = "interval"
            elif cls in ("texttier", "pointtier"):
                for _ in range(count):
                    t = float(take("number"))
                    txt = take("string")
                    items.append({"t": t, "text": txt})
                kind = "point"
            else:
                raise ValueError
            tiers.append({"name": name, "kind": kind, "items": items})
        return tiers, xmax
    except (ValueError, IndexError, TypeError):
        return None


def textgrid_export_tiers_short(tiers: list[dict], duration: float) -> str:
    """Praat **经典短格式**（数值/引号布局）导出——所有 Praat 版本均可读取。

    与 textgrid_export_tiers（ooTextFile 长格式）内容一致：
    区间层自动连续铺满 [0, xmax]（结构自愈），点层按时间排序。
    返回 UTF-8 文本（无 BOM）。
    """
    tiers = [t for t in tiers if t.get("kind") in ("point", "interval")]
    xmax = _textgrid_xmax(tiers, duration)

    # 经典短格式：头部必须是带引号的 "ooTextFile"/"TextGrid"，
    # 否则 Praat 会按“长格式(ooTextFile key=value)”解析而报错
    lines = [
        '"ooTextFile"',
        '"TextGrid"',
        "",
        "0",
        _tg_num(xmax),
        "<exists>",
        str(len(tiers)),
    ]
    for t in tiers:
        name = _tg_escape(t.get("name", "layer"))
        if t.get("kind") == "point":
            pts = _clean_point_tier(list(t.get("items", [])), xmax)
            lines += ['"TextTier"', f'"{name}"', "0", _tg_num(xmax), str(len(pts))]
            for it in pts:
                lines += [_tg_num(it["t"]), f'"{_tg_escape(it.get("text", ""))}"']
        else:
            healed = _heal_interval_tier(list(t.get("items", [])), xmax)
            lines += ['"IntervalTier"', f'"{name}"', "0", _tg_num(xmax), str(len(healed))]
            for it in healed:
                lines += [_tg_num(it["t0"]), _tg_num(it["t1"]), f'"{_tg_escape(it.get("text", ""))}"']
    return "\n".join(lines) + "\n"


def pack_results(
    orig_wav: bytes,
    edited_wav: bytes,
    textgrid: str,
    base: str = "result",
    textgrid_legacy: str | None = None,
) -> bytes:
    """一键打包全部结果：原始音频 + 编辑后音频 + TextGrid 文本
    （应用侧传入短格式；如提供 textgrid_legacy 则额外附带一份变体）-> ZIP 字节。"""
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base}_original.wav", orig_wav)
        zf.writestr(f"{base}_edited.wav", edited_wav)
        zf.writestr(f"{base}_tiers.TextGrid", textgrid.encode("utf-8"))
        if textgrid_legacy is not None:
            zf.writestr(f"{base}_tiers_legacy.TextGrid", textgrid_legacy.encode("utf-8"))
    return buf.getvalue()
