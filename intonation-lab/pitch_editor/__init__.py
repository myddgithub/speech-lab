"""语调调试实验室 —— 音高曲线编辑器自定义组件。

使用 Streamlit 自定义组件 (st.components.v1) 封装一个无构建依赖的
前端 (纯 HTML/JS + Canvas)，实现：

- 波形与音高曲线联动显示
- 鼠标拖拽调节音高点（垂直移动）
- 双击 / 快捷键 A(Insert) 在曲线插入新点、Shift+点击 / Delete 删除点
- 键盘上下键按半音微调选中点
- 播放编辑后/解码后原始音频并显示播放游标
- 图下方音节标注轨：标注模式拖拽创建/移动/缩放音节框，输入音节文本（如 liu4）

组件输入 (args)：
    points          [[t, f0], ...]   当前可编辑音高点（秒, Hz）
    syllables       [{id,text,t0,t1}] 音节标注列表
    original        [[t, f0], ...]   原始提取曲线（参考显示）
    waveform        [[t, amp], ...]  波形（抽稀）
    duration        float            音频时长（秒）
    min_f0 / max_f0 float            初始纵轴及允许编辑范围（Hz）
    edited_audio_url str|None        编辑后音频 data URL（base64 wav）
    original_audio_url str|None      解码后原始音频 data URL
    label           str              标题
    seq             int              最后一次被接受的用户操作序号（防回退）

组件返回值 (value)：
    {"points": ..., "syllables": ..., "event": ..., "seq": ...}
    event 包含音高点、主音节层、额外标注层与标注模式的编辑事件；无事件为 "none"。
"""

from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_component_func = components.declare_component(
    "pitch_editor",
    path=str(Path(__file__).parent / "frontend"),
)


def pitch_editor(
    points,
    syllables=None,
    layers=None,
    original=None,
    waveform=None,
    duration=0.0,
    min_f0=60.0,
    max_f0=500.0,
    edited_audio_url=None,
    original_audio_url=None,
    label="音高曲线",
    seq=-1,
    annotate=False,
    draft="",
    lang="zh",
    key=None,
):
    """渲染音高编辑器组件，返回最新编辑点/多层标注 dict。"""
    syllables = syllables or []
    layers = layers or [{"name": "PY", "kind": "interval", "items": syllables}]
    original = original or []
    waveform = waveform or []
    return _component_func(
        points=points,
        syllables=syllables,
        layers=layers,
        original=original,
        waveform=waveform,
        duration=float(duration),
        min_f0=float(min_f0),
        max_f0=float(max_f0),
        url_edit=edited_audio_url or None,
        url_orig=original_audio_url or None,
        label=label,
        editable=True,
        seq=int(seq),
        annotate=bool(annotate),
        draft=str(draft or ""),
        lang=lang,
        key=key,
        default={
            "points": points,
            "syllables": syllables,
            "layers": layers,
            "event": "none",
            "seq": -1,
            "annotate": False,
            "draft": "",
        },
    )
