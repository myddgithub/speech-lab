"""语调实验室 —— Streamlit 主应用。

功能：
1. 导入音频文件 / 麦克风录音 / 示例音频
2. 自相关法提取音高曲线（F0）
3. 自定义组件中鼠标拖拽调节音高（双击加点、Shift+点击删点、↑↓ 半音微调）
4. 用修改后的音高曲线重合成音频并即时试听、导出
"""

from __future__ import annotations

import re

import numpy as np
import streamlit as st

import core
from i18n import set_lang, tr, trf
from pitch_editor import pitch_editor

# --- 界面语言：默认中文；可用 ?lang=en 或在侧边栏顶部“中文/English”切换 ---
_q = st.query_params.get("lang") or "zh"
st.session_state.setdefault("ui_lang", _q if _q in ("zh", "en") else "zh")
set_lang(st.session_state["ui_lang"])

st.set_page_config(page_title=tr("语调实验室"), page_icon="🎵", layout="wide")

st.markdown(
    """
    <style>
    .block-container { padding-top: 3.3rem; padding-bottom: 2.2rem; }
    div[data-testid="stMetric"] {
        background: rgba(128,128,128,0.06);
        border-radius: 10px; padding: 8px 10px;
    }
    /* 隐藏右上角 Deploy 按钮（保留 ⋮ 菜单） */
    button[data-testid="stBaseButton-header"] { display: none !important; }
    /* 上传控件调小：压缩内边距、隐藏拖拽提示行 */
    section[data-testid="stFileUploaderDropzone"] {
        min-height: 0 !important;
        padding: 3px 10px !important;
        margin: 0 !important;
    }
    section[data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderDropzoneInstructions"] {
        display: none !important;
    }
    section[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {
        padding: 2px 10px !important;
        min-height: 30px !important;
    }
    /* 整体紧凑：主区元素间距略收紧 */
    div[data-testid="stVerticalBlock"] > div {
        gap: 0.35rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

SS = st.session_state
SS.setdefault("audio_bytes", None)
SS.setdefault("audio_name", "")
SS.setdefault("edit_points", [])
SS.setdefault("syllables", [])
SS.setdefault("layers", [])
SS.setdefault("edit_history", [])   # 撤销栈
SS.setdefault("redo_history", [])   # 恢复栈
SS.setdefault("analysis_key", None)
SS.setdefault("annotate_mode", False)
SS.setdefault("syl_draft", "")
SS.setdefault("textgrid_pending", None)
SS.setdefault("textgrid_seen_hash", None)
SS.setdefault("textgrid_notice", None)
SS.setdefault("audio_hash", None)
SS.setdefault("audio_uploader_epoch", 0)
SS.setdefault("audio_input_epoch", 0)
SS.setdefault("component_epoch", 0)
SS.setdefault("pitch_dirty", False)
SS.setdefault("last_seq", -1)
SS.setdefault("align_import_hash", None)
SS.setdefault("import_hint", None)
SS.setdefault("import_hint_text", None)
SS.setdefault("comp_orig_hash", None)
SS.setdefault("comp_edit_hash", None)
SS.setdefault("comp_audio_epoch", None)

# 从 .txt 导入的对齐文本：须在“对齐”输入框实例化之前写入（否则不能修改已实例化控件）
if SS.get("align_input_pending") is not None:
    SS["align_input"] = SS["align_input_pending"]
    SS["align_input_pending"] = None


def _snapshot() -> dict:
    """深拷贝当前（编辑点 + 全部标注层）作为历史快照。"""
    return {
        "points": [list(p) for p in SS["edit_points"]],
        "layers": _layers_deep(),
        "pitch_dirty": bool(SS.get("pitch_dirty", False)),
    }


def _layers_deep() -> list[dict]:
    """深拷贝标注层（含第 0 层 PY items）。"""
    return [
        {
            "name": str(l.get("name", f"层{i + 1}")),
            "kind": l.get("kind", "interval"),
            "def": str(l.get("def", "")),
            "items": [dict(it) for it in l.get("items", [])],
        }
        for i, l in enumerate(SS.get("layers", []))
    ]


def _sync_layers() -> None:
    """确保标注层存在且第 0 层为区间“PY”（拼音）层，SS['syllables'] 与其 items 同步。"""
    if not SS.get("layers"):
        SS["layers"] = [{"name": "PY", "kind": "interval", "def": "", "items": SS.get("syllables", [])}]
    lay0 = SS["layers"][0]
    if lay0.get("kind") != "interval":
        SS["layers"].insert(0, {"name": "PY", "kind": "interval", "def": "", "items": []})
        lay0 = SS["layers"][0]
    SS["syllables"] = lay0["items"]


def _set_syl(items) -> None:
    """替换第 0 层（PY 层）内容并同步。"""
    SS["syllables"] = items
    if SS.get("layers"):
        SS["layers"][0]["items"] = items


def _push_history() -> None:
    """把当前状态压入撤销栈，并清空恢复栈（新操作使恢复失效）。"""
    SS.setdefault("edit_history", []).append(_snapshot())
    SS["redo_history"] = []
    if len(SS["edit_history"]) > 30:
        SS["edit_history"].pop(0)


def _undo() -> None:
    """撤销一步：当前状态入恢复栈，弹出撤销栈恢复。"""
    if not SS["edit_history"]:
        return
    SS.setdefault("redo_history", []).append(_snapshot())
    if len(SS["redo_history"]) > 30:
        SS["redo_history"].pop(0)
    entry = SS["edit_history"].pop()
    SS["edit_points"] = entry.get("points", [])
    SS["layers"] = entry.get("layers", [])
    SS["pitch_dirty"] = bool(entry.get("pitch_dirty", False))
    _sync_layers()


def _redo() -> None:
    """恢复一步：当前状态入撤销栈，弹出恢复栈恢复。"""
    if not SS["redo_history"]:
        return
    SS.setdefault("edit_history", []).append(_snapshot())
    if len(SS["edit_history"]) > 30:
        SS["edit_history"].pop(0)
    entry = SS["redo_history"].pop()
    SS["edit_points"] = entry.get("points", [])
    SS["layers"] = entry.get("layers", [])
    SS["pitch_dirty"] = bool(entry.get("pitch_dirty", False))
    _sync_layers()


def _set_audio(data: bytes, name: str) -> bool:
    """切换音频并隔离其编辑状态；同一上传对象在重跑时不重复重置。"""
    new_hash = core.bytes_hash(data)
    if new_hash == SS.get("audio_hash"):
        SS["audio_name"] = name
        return False
    SS["audio_bytes"] = data
    SS["audio_name"] = name
    SS["audio_hash"] = new_hash
    SS["edit_points"] = []
    SS["syllables"] = []
    SS["layers"] = []
    SS["edit_history"] = []
    SS["redo_history"] = []
    SS["analysis_key"] = None
    SS["annotate_mode"] = False
    SS["syl_draft"] = ""
    SS["align_applied"] = None
    SS["align_msg"] = None
    SS["pitch_dirty"] = False
    SS["last_seq"] = -1
    SS["component_epoch"] = int(SS.get("component_epoch", 0)) + 1
    SS["comp_orig_hash"] = None
    SS["comp_edit_hash"] = None
    SS["comp_audio_epoch"] = None
    SS["textgrid_notice"] = None
    # 若上传控件仍保留着 TextGrid，新音频应有机会明确地重新应用一次。
    SS["textgrid_seen_hash"] = None
    return True


# 调试/演示：?demo=1 自动载入示例音频（便于快速体验与截图验证）
if st.query_params.get("demo") == "1" and SS.get("audio_bytes") is None:
    _set_audio(core.generate_sample_audio(), "示例音频")
if SS.get("audio_bytes") is not None:
    _sync_layers()  # 音频就绪后确保存在第 0 层（PY）


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, max_entries=8)
def _load_only(h: str, data: bytes):
    return core.load_audio_bytes(data)


@st.cache_data(show_spinner=False, max_entries=8)
def _analyze(h: str, data: bytes, floor: float, ceiling: float, fp: float):
    samples, sr, _fmt = _load_only(h, data)
    times, f0 = core.analyze_pitch(samples, sr, floor, ceiling, fp)
    return times, f0


@st.cache_data(show_spinner=False, max_entries=8)
def _orig_wav(h: str, data: bytes):
    samples, sr, _fmt = _load_only(h, data)
    return core.wav_bytes(samples, sr)


@st.cache_data(show_spinner=False, max_entries=12)
def _resynth(h: str, data: bytes, fp: float, floor: float, ceiling: float, pts: tuple):
    """按编辑点 TD-PSOLA 重合成 WAV 字节。pts 为 ((t, f0), ...) 元组。"""
    samples, sr, _fmt = _load_only(h, data)
    times, f0 = _analyze(h, data, floor, ceiling, fp)
    if not pts:
        return core.wav_bytes(samples, sr)
    tier = core.build_f0_tier([list(p) for p in pts], times, f0, floor, ceiling)
    if not tier.any():
        return core.wav_bytes(samples, sr)
    out = core.synthesize_with_f0(samples, sr, tier, f0, times, fp)
    return core.wav_bytes(out, sr)


# ---------------------------------------------------------------------------
# 标题 + 右上角语言切换（中 / English）
# ---------------------------------------------------------------------------
_head = st.columns([4.6, 1.15], vertical_alignment="center", gap="small")
# 语言钮先执行，标题文案才能用上新语言（列布局位置不变）
with _head[1]:
    _lang_ctl = st.segmented_control(
        "语言 / Language",
        options=["中文", "English"],
        default="中文" if SS["ui_lang"] == "zh" else "English",
        key="ui_lang_ctl",
        label_visibility="collapsed",
    )
    SS["ui_lang"] = "zh" if _lang_ctl == "中文" else "en"
    set_lang(SS["ui_lang"])
with _head[0]:
    st.title(tr("🎵 语调实验室"))


# ---------------------------------------------------------------------------
# 侧边栏（各功能区折叠，节省空间、便于快速选择）
# ---------------------------------------------------------------------------
with st.sidebar:
    with st.expander(tr("🎛️ 音频输入"), expanded=True):
        src_mode = st.radio(
            tr("音频来源"),
            ["file", "mic", "sample"],
            horizontal=False,
            label_visibility="collapsed",
            format_func=lambda v: {"file": tr("📁 导入文件"),
                                   "mic": tr("🎙️ 麦克风录音"),
                                   "sample": tr("✨ 示例音频")}[v],
        )
        if src_mode == "file":
            up = st.file_uploader(
                tr("选择音频文件"),
                type=list(core.SUPPORTED_EXTS),
                help=tr("支持 wav / mp3 / flac / ogg（具体压缩编码取决于 libsndfile）"),
                key=f"audio_file_{SS['audio_uploader_epoch']}",
            )
            if up is not None:
                _set_audio(up.getvalue(), up.name)
        elif src_mode == "mic":
            rec = st.audio_input(
                tr("点击开始录音，再次点击结束"),
                help=tr("录音在浏览器本地进行，仅上传到本应用处理"),
                key=f"audio_recording_{SS['audio_input_epoch']}",
            )
            if rec is not None:
                _set_audio(rec.getvalue(), tr("麦克风录音"))
        else:
            if st.button(tr("🎵 生成示例哼鸣（降-升-降 语调）"), use_container_width=True):
                _set_audio(core.generate_sample_audio(), tr("示例音频"))

        if SS["audio_bytes"] is not None:
            st.caption(trf("当前音频：**{0}**（{1} KB）",
                           SS["audio_name"] or tr("未知"), len(SS["audio_bytes"]) / 1024))
            if st.button(tr("🗑️ 清除当前音频"), use_container_width=True):
                SS["audio_bytes"] = None
                SS["audio_hash"] = None
                SS["edit_points"] = []
                SS["syllables"] = []
                SS["layers"] = []
                SS["edit_history"] = []
                SS["redo_history"] = []
                SS["analysis_key"] = None
                SS["annotate_mode"] = False
                SS["syl_draft"] = ""
                SS["align_applied"] = None
                SS["align_msg"] = None
                SS["textgrid_pending"] = None
                SS["textgrid_seen_hash"] = None
                SS["textgrid_notice"] = None
                SS["pitch_dirty"] = False
                SS["last_seq"] = -1
                SS["audio_uploader_epoch"] += 1
                SS["audio_input_epoch"] += 1
                SS["component_epoch"] += 1
                SS["comp_orig_hash"] = None
                SS["comp_edit_hash"] = None
                SS["comp_audio_epoch"] = None
                if st.query_params.get("demo") == "1":
                    del st.query_params["demo"]
                st.rerun()

        st.caption(tr("📂 载入此前标注（多层 TextGrid）"))
        tg_file = st.file_uploader(
            tr("标注文件 (TextGrid)"),
            type=["textgrid"],
            help=tr("载入与当前音频配套的 Praat TextGrid（含 IntervalTier / TextTier 各层），"
                    "自动恢复为多层标注（可撤销）；可与上方音频先后上传。"),
        )
        if tg_file is None:
            SS["textgrid_seen_hash"] = None
        else:
            try:
                tg_bytes = tg_file.getvalue()
                tg_hash = core.bytes_hash(tg_bytes)
                if tg_hash != SS.get("textgrid_seen_hash"):
                    # 新选择的文件必须取代旧暂存；若新文件解析失败，不能在稍后
                    # 载入音频时悄悄应用此前的 TextGrid。
                    SS["textgrid_pending"] = None
                    parsed_tiers, _ = core.textgrid_parse(tg_bytes)
                    if not parsed_tiers:
                        st.error(tr("TextGrid 中未解析出任何层。"))
                    else:
                        SS["textgrid_seen_hash"] = tg_hash
                        SS["textgrid_pending"] = tg_bytes
                        if SS.get("audio_bytes") is None:
                            st.info(trf("已暂存 TextGrid（{0} 层），载入音频后自动应用。", len(parsed_tiers)))
                elif SS.get("audio_bytes") is None and SS.get("textgrid_pending") is not None:
                    st.info(tr("TextGrid 已暂存，载入音频后会自动应用。"))
            except ValueError as e:
                st.error(trf("TextGrid 解析失败：{0}", e))

    with st.expander(tr("🔬 分析参数"), expanded=False):
        f0_floor = st.slider(tr("基频下限 (Hz)"), 40, 120, 75, help=tr("低于此频率视为清音；去声/嘎裂声可降到 40–60 Hz"))
        f0_ceil = st.slider(tr("基频上限 (Hz)"), 300, 1000, 500, step=50, help=tr("高于此频率视为清音"))
        frame_period = st.select_slider(tr("分析帧移 (ms)"), options=[1, 2, 3, 5, 10, 15, 20], value=10)
        st.caption(tr("修改分析参数将重置音高编辑（重新提取曲线）"))
        st.caption(tr("去声/儿化尾段若没有曲线：把最后一个点拖到更晚，或在空白处双击加点。"))

    if SS["audio_bytes"] is not None:
        with st.expander(tr("🎬 音节自动切分"), expanded=False):
            if st.button(
                "🧩 " + tr("自动切分音节"), use_container_width=True,
                help=tr("基于浊音段 + 能量包络自动检测音节边界并生成连续音节框（可再手动微调/改名）"),
            ):
                _push_history()
                hh = core.bytes_hash(SS["audio_bytes"])
                _s, _sr, _fmt = _load_only(hh, SS["audio_bytes"])
                _t, _f = _analyze(hh, SS["audio_bytes"], float(f0_floor), float(f0_ceil), float(frame_period))
                _set_syl(core.auto_segment_syllables(_s, _sr, _t, _f))
            st.caption(tr("写入第 0 层「PY」（拼音）；切分后可在图上微调边界、填入拼音（如 liu4 / 好3）。"))
        with st.expander(tr("📚 标注层（多层，仿 Praat）"), expanded=False):
            _sync_layers()
            for i, lyr in enumerate(SS["layers"]):
                n_it = len(lyr.get("items", []))
                kind_lbl = tr("区间") if lyr.get("kind") == "interval" else tr("点")
                lbl = f"{i + 1}. {lyr.get('name', trf('层{0}', i + 1))} · {kind_lbl}"
                c1, c2 = st.columns([4.2, 1])
                with c1:
                    st.markdown(trf("**{0}**：{1} 项", lbl, n_it))
                with c2:
                    if i == 0:
                        st.markdown(tr("*(主层)*"))
                    elif st.button("🗑", key=f"del_layer_{i}", help=tr("删除该层")):
                        _push_history()
                        del SS["layers"][i]
                        _sync_layers()
                        st.rerun()
            st.caption(tr("第 0 层「PY」承载自动切分/文本对齐/声调提取；"
                          "在 PY 轨点选某条边界后按 **B**：区间层加边界、点层(TextTier)加一个点。"))
            n_name = st.text_input(tr("新层名称"), placeholder=tr("如：词 / 字 / 重音"), key="new_layer_name")
            n_kind = st.radio(
                tr("类型"), ["interval", "point"], horizontal=True,
                key="new_layer_kind", label_visibility="collapsed",
                format_func=lambda v: tr("区间 IntervalTier") if v == "interval" else tr("点 TextTier"),
            )
            if st.button(tr("➕ 添加标注层"), use_container_width=True):
                if n_name.strip():
                    _push_history()
                    SS["layers"].append({
                        "name": n_name.strip(),
                        "kind": n_kind,
                        "def": "",
                        "items": [],
                    })
                    st.rerun()
                else:
                    st.warning(tr("请先填写新层名称。"))

        with st.expander(tr("✏️ 音高编辑操作"), expanded=False):
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button(tr("♭ 降 1 半音"), use_container_width=True, help=tr("整体降低 1 个半音")):
                    _push_history()
                    SS["edit_points"] = core.shift_semitones(
                        SS["edit_points"], -1, float(f0_floor), float(f0_ceil)
                    )
                    SS["pitch_dirty"] = True
            with col_b:
                if st.button(tr("♯ 升 1 半音"), use_container_width=True, help=tr("整体升高 1 个半音")):
                    _push_history()
                    SS["edit_points"] = core.shift_semitones(
                        SS["edit_points"], 1, float(f0_floor), float(f0_ceil)
                    )
                    SS["pitch_dirty"] = True
            if st.button(tr("🌀 平滑曲线"), use_container_width=True, help=tr("对编辑点做滑动平均，去掉锯齿")):
                _push_history()
                SS["edit_points"] = core.smooth_points(SS["edit_points"], window=5)
                SS["pitch_dirty"] = True
            st.caption(tr("以上为整体操作，可随时在图上“↩️ 撤销”。"))

        with st.expander(tr("🎯 特征点（仿 Praat Stylize）"), expanded=False):
            stylize_tol = st.select_slider(
                tr("容差（半音）"),
                options=[1.0, 1.5, 2.0, 3.0, 4.0],
                value=2.0,
                help=tr("容差越大保留的特征点越少。提取后相邻保留点之间按直线插值，与原曲线偏差不超过容差。"),
            )
            if st.button(
                tr("✂️ 提取特征点"), use_container_width=True,
                help=tr("根据音高变化趋势保留转折点/端点，去除中间连续性好的点，便于手动微调语调"),
            ):
                _push_history()
                SS["edit_points"] = core.stylize_points(SS["edit_points"], stylize_tol)
                SS["pitch_dirty"] = True
            st.caption(tr("提取后用鼠标拖拽特征点微调语调，曲线在相邻点间按直线插值。"))

        with st.expander(tr("🎵 按声调提取特征点"), expanded=False):
            n_syl = len(SS.get("syllables", []))
            if st.button(
                tr("🎶 应用声调特征点"), use_container_width=True,
                disabled=n_syl == 0,
                help=tr("对每个标注音节按声调提取特征点，删除其间的平滑过渡点"),
            ):
                _push_history()
                SS["edit_points"] = core.extract_tone_feature_points(SS["edit_points"], SS["syllables"])
                SS["pitch_dirty"] = True
            if n_syl:
                st.caption(
                    trf("第0层已标注 {0} 个音节。规则（末尾数字=声调，如 liu4/好3）：\n"
                        "1 声·稳定段两端；2 声·前半段低点+后半段高点；"
                        "3 声·两端+低点；4 声·前半段高点+后半段低点；"
                        "0(轻声)·前接1/2/4声取最低点、前接3声取最高点；"
                        "无数字时自动按轮廓推断声调。", n_syl)
                )
            else:
                st.caption(tr("先在图上开启“📝 标注音节”或自动切分（文本如 liu4 / 好3 / 我）。"))

        # 编辑后的音频与多层 TextGrid 统一在主区“💾 保存结果”下载（见下）

# ---------------------------------------------------------------------------
# 主体
# ---------------------------------------------------------------------------
st.caption(tr("导入或录制一段语音 → 自动提取音高曲线 → 用鼠标**拖拽**调节音高 → TD-PSOLA 重合成即时试听。"))

if SS["audio_bytes"] is None:
    st.info(
        tr("👈 请先在左侧选择音频来源：**导入文件**、**麦克风录音**或**示例音频**。\n\n"
           "示例音频是一段合成的哼鸣（降调→升调→降调），可以直接体验拖拽调音高。"),
        icon="🎧",
    )
    st.stop()

h = core.bytes_hash(SS["audio_bytes"])

# --- 加载与基频分析（首次较慢，之后走缓存） ---
try:
    samples, sr, fmt = _load_only(h, SS["audio_bytes"])
except ValueError as e:
    st.error(trf("❌ 音频解码失败：{0}", e))
    st.stop()

duration = len(samples) / sr
if duration > 240:
    st.warning(tr("⚠️ 音频较长（>4 分钟），重合成所需内存与时间会增加。"))

with st.spinner(tr("🔬 提取音高曲线中（自相关法）...")):
    times, f0 = _analyze(h, SS["audio_bytes"], float(f0_floor), float(f0_ceil), float(frame_period))

voiced = f0 > 0
if not voiced.any():
    st.warning(
        tr("⚠️ 未检测到可靠音高，已提供 150 Hz 基准线供手工编辑；重合成会自动尝试弱脉冲检测，仍可改变音高。"),
        icon="🤔",
    )

# 分析参数变化 -> 重置编辑点为原始曲线
analysis_key = (h, float(f0_floor), float(f0_ceil), float(frame_period))
if SS["analysis_key"] != analysis_key:
    if SS["analysis_key"] is not None:
        # 不允许撤销到另一套分析网格上的旧控制点。
        SS["edit_history"] = []
        SS["redo_history"] = []
    SS["edit_points"] = (
        core.make_edit_points(times, f0)
        or core.fallback_edit_points(times, float(f0_floor), float(f0_ceil))
    )
    SS["analysis_key"] = analysis_key
    SS["pitch_dirty"] = False

# --- 应用暂存的 TextGrid 多层标注（载入此前标注） ---
if SS.get("textgrid_pending") is not None:
    try:
        parsed_tiers, tg_xmax = core.textgrid_parse(SS["textgrid_pending"])
        if parsed_tiers:
            _push_history()
            tolerance = max(0.02, duration * 0.001)
            if tg_xmax > 0 and abs(tg_xmax - duration) > tolerance:
                SS["textgrid_notice"] = trf(
                    "⚠️ TextGrid 时长为 {0}s，音频时长为 {1}s；超出音频范围的标注已裁剪。请确认文件是否配套。",
                    round(tg_xmax, 6), round(duration, 6),
                )
            else:
                SS["textgrid_notice"] = None
            new_layers: list[dict] = []
            for t in parsed_tiers:
                kind = t.get("kind", "interval")
                items = []
                for it in t.get("items", []):
                    if kind == "point":
                        tt = max(0.0, min(float(it.get("t", 0)), duration))
                        items.append({"t": round(tt, 9), "text": str(it.get("text", ""))})
                    else:
                        t0 = max(0.0, min(float(it.get("t0", 0)), duration))
                        t1 = max(t0, min(float(it.get("t1", t0)), duration))
                        if t1 > t0:
                            items.append({"t0": round(t0, 9), "t1": round(t1, 9), "text": str(it.get("text", ""))})
                new_layers.append({"name": str(t.get("name", f"层{len(new_layers) + 1}")),
                                   "kind": kind, "def": "", "items": items})
            SS["layers"] = new_layers
            _sync_layers()
            names = "、".join(l.get("name", "?") for l in new_layers) or "?"
            st.success(trf("✅ 已从 TextGrid 载入 {0} 层标注：{1}（可撤销）", len(new_layers), names))
    except ValueError as e:
        st.error(trf("TextGrid 载入失败：{0}", e))
    finally:
        SS["textgrid_pending"] = None

if SS.get("textgrid_notice"):
    st.warning(SS["textgrid_notice"])

edit_points = SS["edit_points"]

# --- 重合成当前编辑结果（未改音高时严格返回解码后的音频） ---
orig_wav = _orig_wav(h, SS["audio_bytes"])
if SS.get("pitch_dirty", False):
    with st.spinner(tr("🎶 重合成编辑后音频中...")):
        edit_wav = _resynth(
            h, SS["audio_bytes"], float(frame_period), float(f0_floor), float(f0_ceil),
            tuple(tuple(p) for p in edit_points),
        )
else:
    edit_wav = orig_wav

epoch = int(SS.get("component_epoch", 0))
audio_payload = core.component_audio_payload(
    orig_wav,
    edit_wav,
    prev_orig_hash=SS.get("comp_orig_hash"),
    prev_edit_hash=SS.get("comp_edit_hash"),
    remount=SS.get("comp_audio_epoch") != epoch,
)
SS["comp_orig_hash"] = audio_payload["orig_hash"]
SS["comp_edit_hash"] = audio_payload["edit_hash"]
SS["comp_audio_epoch"] = epoch
url_edit = audio_payload["url_edit"]
url_orig = audio_payload["url_orig"]

# --- 音高编辑器（独占整宽；多层标注）置于工具行上方，曲线优先呈现 ---
last_seq = SS.get("last_seq", -1)
result = pitch_editor(
    points=edit_points,
    syllables=SS.get("syllables", []),
    layers=SS.get("layers", []),
    original=core.reference_curve(times, f0),
    waveform=core.decimate_waveform(samples, sr),
    duration=duration,
    min_f0=float(f0_floor),
    max_f0=float(f0_ceil),
    edited_audio_url=url_edit,
    original_audio_url=url_orig,
    label=f"{tr('音高曲线')} · {SS['audio_name'] or tr('未命名')}",
    seq=int(last_seq),
    annotate=SS.get("annotate_mode", False),
    draft=SS.get("syl_draft", ""),
    lang=st.session_state["ui_lang"],
    # 同一音频内保持组件身份稳定；切换音频时换代，隔离旧组件事件。
    key=f"pitch_editor_main_{SS['component_epoch']}",
)
if not audio_payload["embedded"]:
    st.caption(tr("图表内播放已关闭（音频较大）。请使用下方「试听对比」。"))
if result and result.get("event") != "none" and result.get("seq", -1) > last_seq:
    pts_changed = result.get("points") is not None and result.get("points") != SS["edit_points"]
    syl_changed = result.get("syllables") is not None and result.get("syllables") != SS.get("syllables", [])
    layers_changed = result.get("layers") is not None and result.get("layers") != SS.get("layers", [])
    if pts_changed or syl_changed or layers_changed:
        _push_history()  # 组件编辑入撤销栈，使“撤销”回退到上一次真实操作
    if pts_changed:
        SS["edit_points"] = result.get("points") or []
        SS["pitch_dirty"] = True
    if layers_changed:
        SS["layers"] = result.get("layers")
        _sync_layers()
    elif syl_changed:
        _sync_layers()
        _set_syl(result.get("syllables") or [])
    SS["annotate_mode"] = bool(result.get("annotate", SS.get("annotate_mode", False)))
    SS["syl_draft"] = str(result.get("draft", "") or "")
    SS["last_seq"] = int(result.get("seq", last_seq))
    st.rerun()

# --- 工具行（单行）：撤销 / 恢复 / 重置 + 音节文本输入 + 📄 导入 + 对齐 ---
# 不用 form：文本输入框失焦/回车即提交，按钮点击读到的是最新值；且“导入”
# 上传控件放在行内，选中文件即可立即自动填入（若在 form 内需先提交才生效）。
tb = st.columns([1.0, 1.0, 1.9, 4.6, 1.15, 2.3, 1.2], vertical_alignment="center", gap="small")
with tb[0]:
    clicked_undo = st.button(
        "↩️ " + tr("撤销"), type="secondary",
        disabled=not SS["edit_history"],
        help=tr("撤销上一步操作（拖拽/加点/音节/升降调/提取特征点等），可多次点击逐级撤销"),
    )
with tb[1]:
    clicked_redo = st.button(
        "↪️ " + tr("恢复"), type="secondary",
        disabled=not SS["redo_history"],
        help=tr("恢复被撤销的操作，可多次点击逐级恢复"),
    )
with tb[2]:
    clicked_reset = st.button(
        "🔄 " + tr("重置为原始曲线"), type="secondary",
        help=tr("恢复由音频直接提取的原始音高曲线（可撤销）"),
    )
with tb[3]:
    align_input = st.text_input(
        tr("音节文本（对齐用）"),
        key="align_input",
        placeholder=tr("汉字每字一音节 / 拼音按声调数字切分，如：好1你2在4 或 wo3shi4shei2"),
        label_visibility="collapsed",
        help=tr("自动切分/手工定好音节边界后，把整段文本按顺序填入各音节框（数量须一致，可撤销）"),
    )
with tb[4]:
    st.markdown(tr("📄 导入"))
with tb[5]:
    imp_file = st.file_uploader(
        tr("导入文本文件 (.txt)"), type=["txt"], key="align_txt_import",
        label_visibility="collapsed",
        help=tr("选择 UTF-8 / GBK 编码的 .txt，自动填入左侧对齐输入框（可再编辑），点“🔤 对齐”应用。"
                "换行/空格/标点自动忽略。"),
    )
with tb[6]:
    align_clicked = st.button(
        "🔤 " + tr("对齐"), type="primary",
        help=tr("把文本切分为音节并逐框填入（数量须一致，操作可撤销）"),
    )

n_box = len(SS.get("syllables", []))
align_err: str | None = None
if clicked_undo:
    _undo()
    SS["align_msg"] = None  # 撤销后旧的“已对齐”提示失效
elif clicked_redo:
    _redo()
    SS["align_msg"] = None
elif clicked_reset:
    _push_history()
    SS["edit_points"] = (
        core.make_edit_points(times, f0)
        or core.fallback_edit_points(times, float(f0_floor), float(f0_ceil))
    )
    SS["analysis_key"] = analysis_key  # 避免重置后再次自动重建
    SS["pitch_dirty"] = False
    SS["align_msg"] = None
elif align_clicked:
    syls, input_fmt = core.split_syllable_text(align_input)
    if n_box == 0:
        align_err = tr("还没有音节框：请先用侧边栏“🧩 自动切分音节”或手动标注。")
    elif not syls:
        align_err = tr("未能解析出音节。汉字直接输入；拼音需写全字母并带声调数字（如 wo3）。")
    elif len(syls) != n_box:
        align_err = trf(
            "音节数量不匹配：文本解析出 {0} 个（{1}），当前音节框 {2} 个。请调整文本或音节框数量后重试。",
            len(syls), tr(input_fmt), n_box,
        )
    else:
        _push_history()  # 对齐可撤销
        for box, s in zip(SS["syllables"], syls):
            box["text"] = s
        SS["align_applied"] = align_input
        SS["align_msg"] = trf("✅ 已按{0}对齐 {1} 个音节（可撤销）", tr(input_fmt), len(syls))
    if align_err:
        SS["align_msg"] = None
if clicked_undo or clicked_redo or clicked_reset or (align_clicked and not align_err):
    # 撤销/恢复/重置：让按钮可用状态与最新栈一致；对齐成功：让组件刷新新文本
    st.rerun()
edit_points = SS["edit_points"]

# --- 工具行下方的对齐提示 / 解析预览 ---
if align_err:
    st.warning(align_err)
elif SS.get("align_msg") and SS.get("align_applied") == align_input:
    st.success(SS["align_msg"])
else:
    SS["align_msg"] = None
    # 导入提示：输入框仍是导入内容时显示；手动改动/对齐成功后自动消失
    if SS.get("import_hint") and SS.get("import_hint_text") == align_input:
        st.info(SS["import_hint"])
    else:
        SS["import_hint"] = None
        SS["import_hint_text"] = None
    if align_input:
        ps, pf = core.split_syllable_text(align_input)
        if SS.get("import_hint") is None and ps and len(ps) != n_box:
            st.caption(
                trf("解析：{0} 个音节（{1}）· 音节框 {2} 个 —— ⚠️ 数量不一致，无法对齐",
                    len(ps), tr(pf), n_box)
            )
        elif SS.get("import_hint") is None and ps and n_box:
            st.caption(trf("解析：{0} 个音节（{1}）· 音节框 {2} 个，可直接点“🔤 对齐”",
                           len(ps), tr(pf), n_box))

# --- 对齐文本：.txt 自动导入（上传控件在工具行内；选中即填入上方输入框） ---
if imp_file is not None:
    imp_raw = imp_file.getvalue()
    if imp_raw != SS.get("align_import_hash"):
        SS["align_import_hash"] = imp_raw
        imp_text = None
        for _enc in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                imp_text = imp_raw.decode(_enc)
                break
            except UnicodeDecodeError:
                continue
        if imp_text is None:
            st.error(tr("无法识别文本编码，请使用 UTF-8 或 GBK。"))
        else:
            _imp_text = imp_text.strip()
            SS["align_input_pending"] = _imp_text
            _ps, _pf = core.split_syllable_text(_imp_text)
            _nbox = len(SS.get("syllables", []))
            if _ps:
                if len(_ps) == _nbox:
                    SS["import_hint"] = trf(
                        "📄 已导入 {0} 个音节（{1}），与音节框一致，可直接点“🔤 对齐”。",
                        len(_ps), tr(_pf),
                    )
                else:
                    SS["import_hint"] = trf(
                        "📄 已导入 {0} 个音节（{1}），音节框 {2} 个 —— ⚠️ 数量不一致，无法对齐。",
                        len(_ps), tr(_pf), _nbox,
                    )
                SS["import_hint_text"] = _imp_text
            st.rerun()

# --- 指标 ---
f0v = f0[voiced]
mean_f0 = float(np.mean(f0v)) if len(f0v) else float("nan")
min_f0d = float(np.min(f0v)) if len(f0v) else float("nan")
max_f0d = float(np.max(f0v)) if len(f0v) else float("nan")
if edit_points:
    edit_f0_frames = core.build_f0_tier(
        edit_points, times, f0, float(f0_floor), float(f0_ceil)
    )
    ef = edit_f0_frames[edit_f0_frames > 0]
    mean_edit = float(np.mean(ef))
    min_edit = float(np.min(ef))
    max_edit = float(np.max(ef))
else:
    mean_edit, min_edit, max_edit = mean_f0, min_f0d, max_f0d
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric(tr("时长"), f"{duration:.2f} s")
c2.metric(tr("浊音占比"), f"{voiced.mean() * 100:.0f} %")
c3.metric(tr("原始平均基频"), f"{mean_f0:.0f} Hz" if len(f0v) else "—",
          help=trf("原始范围 {0}–{1} Hz", min_f0d, max_f0d) if len(f0v) else None)
c4.metric(tr("当前平均基频"), f"{mean_edit:.0f} Hz",
          help=trf("编辑后范围 {0}–{1} Hz", min_edit, max_edit))
c5.metric(tr("编辑点数"), f"{len(edit_points)}")
c6.metric(tr("音节数"), f"{len(SS.get('syllables', []))}")

# --- 试听与导出 ---
st.subheader(tr("🎧 试听对比"))
a1, a2 = st.columns(2)
with a1:
    st.markdown(tr("**解码后原始音频**"))
    st.audio(orig_wav, format="audio/wav")
with a2:
    st.markdown(tr("**编辑后音频**（TD-PSOLA 重合成）"))
    st.audio(edit_wav, format="audio/wav")

# --- 保存结果（编辑前后音频 + 多层 TextGrid 标注） ---
st.subheader(tr("💾 保存结果"))
name_stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", (SS.get("audio_name") or "audio").rsplit(".", 1)[0]) or "audio"
n_layers = len(SS.get("layers", []))
layers_now = SS.get("layers", [])
tg_text = core.textgrid_export_tiers_short(layers_now, duration)
tg_bytes = tg_text.encode("utf-8")
zip_bytes = core.pack_results(orig_wav, edit_wav, tg_text, name_stem)
b1, b2, b3, b4 = st.columns(4)
with b1:
    st.download_button(
        tr("⬇️ 原始 WAV"), data=orig_wav,
        file_name=f"{name_stem}_original.wav", mime="audio/wav", use_container_width=True,
    )
with b2:
    st.download_button(
        tr("⬇️ 编辑后 WAV"), data=edit_wav,
        file_name=f"{name_stem}_edited.wav", mime="audio/wav", use_container_width=True,
    )
with b3:
    st.download_button(
        tr("⬇️ TextGrid"), data=tg_bytes,
        file_name=f"{name_stem}_tiers.TextGrid", mime="text/plain; charset=utf-8", use_container_width=True,
        help=tr("Praat 可直接读取的多层标注（区间层 IntervalTier + 点层 TextTier）"),
    )
with b4:
    st.download_button(
        tr("📦 一键保存全部"), data=zip_bytes,
        file_name=f"{name_stem}_results.zip", mime="application/zip", use_container_width=True,
        type="primary",
        help=tr("ZIP：原始 WAV + 编辑后 WAV + 多层 TextGrid 标注"),
    )
_names = "、".join(str(l.get("name", "?")) for l in layers_now) or tr("（暂无）")
st.caption(
    trf("已导出 {0} 层标注：{1}。左侧“📂 载入此前标注”可载入该 TextGrid（兼容长/短两种格式）恢复多层标注。",
        n_layers, _names)
)

# --- 帮助内容（中/英双语） ---
_HELP_HOW = {
    "zh": """**5 步上手**
1. **导入 / 录音 / 示例**（左侧 🎛️ 音频输入）→ 自动提取 F0 音高曲线；
2. **切分音节**：点「🧩 自动切分音节」把第 0 层 **PY** 铺满音节框，或开启 **📝 标注音节** 手动拖框；
3. **填拼音**：点选音节框后在右侧输入框填 `liu4`（末尾数字 = 声调）；整段文本可一次 **🔤 对齐** 填入；
4. **调语调**：拖拽圆点改音高；A/双击加点、Delete 删点；侧边栏可整体升降半音 / 平滑 / 提取特征点；
5. **保存**：💾 保存结果 下载 **原始 WAV / 编辑后 WAV / TextGrid**（📦 一键打包 ZIP）。

**常用技巧**
- **撤销 / 恢复** 在图上工具行左侧，拖拽、音节、对齐等所有操作都可逐级回退；
- 对齐文本可**从 .txt 文件导入**（工具行内“📄 导入”），UTF-8 / GBK 均可，
  换行 / 空格 / 标点自动忽略，导入后点 **🔤 对齐** 一次填入；
- 第 2..n 层以 PY 为参照：**点选 PY 层一条边界**（红色虚线）→ 按 **B**，区间层同步加边界、点层（TextTier）同步加点；
- **播放选中**：点选某个区间段（PY 音节框，或“词/字”等区间层）后，点工具栏 **▶ 播放选中·编辑后 / ·原始** 只听该段；
- 想逐字对齐：先**双击**音节框把它一分为二，再填文本；
- 界面语言：侧边栏顶部 **中文 / English** 随时切换；帮助内容随语言切换。""",
    "en": """**5 steps to start**
1. **Import / Record / Sample** (🎛️ Audio input on the left) → F0 curve is extracted automatically;
2. **Segment syllables**: click “🧩 Auto-segment” to fill the **PY** tier (layer 0) with syllable boxes, or enable **📝 Annotate** to draw boxes by hand;
3. **Fill pinyin**: select a box and type `liu4` (trailing digit = tone) in the text box; a whole sentence can be **🔤 Aligned** into the boxes at once;
4. **Adjust intonation**: drag the handles; A / double-click adds a point, Delete removes one; the sidebar can shift semitones / smooth / extract feature points globally;
5. **Save**: in “💾 Save results” download **Original WAV / Edited WAV / TextGrid** (📦 or pack all as ZIP).

**Tips**
- **Undo / Redo** sit at the left of the toolbar above the chart; every drag, syllable or align action can be stepped back;
- Alignment text can be **imported from a .txt file** (“📄 Import” in the toolbar); UTF-8 / GBK both work, line breaks / spaces / punctuation are ignored, then click **🔤 Align** to fill at once;
- For tiers 2..n use PY as a reference: **click a PY boundary** (red dashed line) → press **B** — interval tiers get a boundary, point tiers (TextTier) get a point at that instant;
- **Play selection**: click any interval segment (a PY box or a tier like “word”) then use **▶ Play selection (edited / original)** to audition just that span;
- To align word by word: **double-click** a syllable box to split it first;
- Language: switch **中文 / English** at the top of the sidebar at any time.""",
}
_HELP_KNOW = {
    "zh": """**音高 F0 与声调**
- **基频 F0** = 声带振动频率（Hz）。只有浊音段才有 F0；清音（如 s、f）显示为断开的无声区；
- 人耳对频率是**对数感知**：升高 12 个半音 = 频率翻倍（跨一个八度），所以本工具纵轴采用**半音（对数）刻度**；
- 普通话声调本质是 **F0 轮廓形状**：1 声高平、2 声上升、3 声低降升（或低平）、4 声下降、轻声短而弱并随前字变化；
- 拼音末尾数字 = 声调（`0` 与 `5` 都表示轻声），如 `liu4` = 第四声；没有数字时按轮廓自动推断声调。

**分析原理**
- **自相关法**：在短帧内寻找波形周期重复的滞后量来估计 F0，再做中值滤波去掉毛刺；
- **TD-PSOLA**：时域基音同步叠加——按目标 F0 调整基音周期的拼接间距，**只替换音高**，保持时长与清浊结构；
- **特征点（仿 Praat stylize）**：用 RDP 折线把密集曲线压缩为转折点/端点，便于整体整形；
- **按声调提取特征点**：把每个编辑点归属到音节框内，按声调规则保留高/低/两端关键点，删除中间平滑过渡点。

**多层标注（仿 Praat）**
- **IntervalTier 区间层**：带起止时间与文本的段（如 PY、词）；**TextTier 点层**：只含时刻的标记（如重音）；
- 第 0 层默认名 **PY**（拼音），承载切分/对齐/声调提取；导出为 Praat 可直接读取的短格式 TextGrid（UTF-8）。""",
    "en": """**F0 and tones**
- **Fundamental frequency (F0)** = vocal-fold vibration rate (Hz). Only voiced parts have F0; voiceless sounds (s, f…) show up as gaps;
- Human hearing is **logarithmic**: +12 semitones = doubled frequency (an octave), so the chart uses a **semitone (log) scale** on the vertical axis;
- Mandarin tones are basically **F0 contour shapes**: tone 1 high-level, 2 rising, 3 low-dipping (or low-level), 4 falling, neutral short & weak and dependent on the preceding syllable;
- A trailing digit in pinyin encodes the tone (`0`/`5` = neutral), e.g. `liu4` = 4th tone; undigitized syllables are auto-inferred from the contour.

**Analysis**
- **Autocorrelation**: within short frames it finds the lag where the waveform repeats itself to estimate F0, then a median filter removes outliers;
- **TD-PSOLA**: time-domain pitch-synchronous overlap-add — it resplices pitch periods at the target F0, replacing **only the pitch** while keeping duration and voicing;
- **Feature points (Praat-style stylize)**: RDP polyline simplification keeps turning/edge points for coarse editing;
- **Tone-based feature extraction**: assigns each point to its syllable and keeps the highs/lows/endpoints per tone rule, removing smooth transitions in between.

**Multi-tier annotation (Praat-like)**
- **IntervalTier**: segments with start/end time and text (PY, word…); **TextTier**: point markers with time only (stress etc.);
- Tier 0 is named **PY** (pinyin) by default and hosts segmentation / alignment / tone extraction; exports a Praat-readable short TextGrid (UTF-8).""",
}
_HELP_KEYS = {
    "zh": """| 键 / 操作 | 作用 |
|---|---|
| **A / Insert** | 在鼠标位置插入音高控制点 |
| **双击曲线** | 在鼠标处加点（无曲线的清音/尾段也可以） |
| **Delete / Backspace** | 删除选中点 / 音节 / 层项 |
| **Shift + 点击圆点** | 删除该控制点 |
| **↑ / ↓** | 选中点 ±1 半音 |
| **PageUp / PageDown** | 选中点 ±5 半音 |
| **滚轮** | 缩放时间轴（随光标） |
| **Shift + 滚轮** | 时间轴前后平移 |
| **Ctrl + 滚轮** | 缩放音高刻度 |
| **B** | 把选中的 PY 边界同步到下方区间层（加边界）/ 点层（加点） |
| **双击音节框内** | 把该音节一分为二 |
| **双击区间层框内** | 在该层同一时刻加边界 |""",
    "en": """| Key / action | Effect |
|---|---|
| **A / Insert** | insert a pitch point at the mouse |
| **double-click curve** | add a point at the mouse (also in unvoiced gaps / tails) |
| **Delete / Backspace** | delete the selected point / syllable / tier item |
| **Shift + click handle** | delete that point |
| **↑ / ↓** | selected point ±1 semitone |
| **PageUp / PageDown** | selected point ±5 semitones |
| **wheel** | zoom the time axis (at cursor) |
| **Shift + wheel** | pan the time axis |
| **Ctrl + wheel** | zoom the pitch scale |
| **B** | sync the selected PY boundary to lower interval tiers (boundary) / point tiers (point) |
| **double-click inside a syllable** | split that syllable into two |
| **double-click inside an interval-tier box** | add a boundary in that tier at that instant |""",
}
_lang = SS["ui_lang"]
with st.expander(tr("❓ 帮助"), expanded=False):
    _tabs = (["🛠️ 使用要领", "🎓 知识讲解", "⌨️ 快捷键"]
             if _lang == "zh" else ["🛠️ How-to", "🎓 Concepts", "⌨️ Shortcuts"])
    _t_how, _t_know, _t_keys = st.tabs(_tabs)
    with _t_how:
        st.markdown(_HELP_HOW[_lang])
    with _t_know:
        st.markdown(_HELP_KNOW[_lang])
    with _t_keys:
        st.markdown(_HELP_KEYS[_lang])

# 调试信息（可折叠）
with st.expander(tr("🔧 分析详情"), expanded=False):
    st.write(
        {
            tr("采样率"): sr,
            tr("解码方式"): fmt,
            tr("样本数"): len(samples),
            tr("帧移 (ms)"): frame_period,
            tr("基频下限"): f0_floor,
            tr("基频上限"): f0_ceil,
            tr("分析帧数"): int(len(times)),
            tr("浊音帧数"): int(voiced.sum()),
            tr("编辑点数量"): len(edit_points),
            tr("平均基频 (Hz)"): round(mean_f0, 1),
        }
    )
