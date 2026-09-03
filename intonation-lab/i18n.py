"""中英文界面文案。

用法：
    from i18n import tr, trf, set_lang
    set_lang("en")            # 或 "zh"
    tr("撤销")                # zh 原样返回；en 查表翻译
    trf("已导出 {0} 层标注", 3)  # 带占位符的模板（{0},{1},...）
"""

from __future__ import annotations

_LANG = "zh"

# key = 中文文案（与 app.py 中传入 tr/trf 的字面量完全一致）
# value = 英文文案（模板保留 {0} {1} ... 占位符，索引顺序与调用参数一致）
EN: dict[str, str] = {
    # ---- 全局 ----
    "语调实验室": "Intonation Lab",
    "🎵 语调实验室": "🎵 Intonation Lab",
    "❓ 帮助": "❓ Help",
    "🔧 分析详情": "🔧 Analysis details",
    "音高曲线": "Pitch curve",
    "未命名": "unnamed",
    "未知": "unknown",
    "（暂无）": "(none)",
    "拼音": "Pinyin",
    "汉字": "Han characters",

    # ---- 侧边栏：语言 ----
    "界面语言 / Language": "Language",

    # ---- 侧边栏：音频输入 ----
    "🎛️ 音频输入": "🎛️ Audio input",
    "音频来源": "Source",
    "📁 导入文件": "📁 Import file",
    "🎙️ 麦克风录音": "🎙️ Microphone",
    "✨ 示例音频": "✨ Sample audio",
    "选择音频文件": "Choose audio file",
    "支持 wav / mp3 / flac / ogg（具体压缩编码取决于 libsndfile）": "Supports wav / mp3 / flac / ogg (codec support depends on libsndfile)",
    "点击开始录音，再次点击结束": "Click to start recording; click again to stop",
    "录音在浏览器本地进行，仅上传到本应用处理": "Recording stays in your browser; it is only uploaded to this app for processing",
    "麦克风录音": "Microphone recording",
    "🎵 生成示例哼鸣（降-升-降 语调）": "🎵 Generate sample hum (fall-rise-fall)",
    "示例音频": "Sample audio",
    "当前音频：**{0}**（{1} KB）": "Current audio: **{0}** ({1} KB)",
    "🗑️ 清除当前音频": "🗑️ Clear current audio",
    "📂 载入此前标注（多层 TextGrid）": "📂 Load previous annotation (multi-tier TextGrid)",
    "标注文件 (TextGrid)": "Annotation file (TextGrid)",
    "载入与当前音频配套的 Praat TextGrid（含 IntervalTier / TextTier 各层），自动恢复为多层标注（可撤销）；可与上方音频先后上传。": "Load a Praat TextGrid that matches the current audio (IntervalTier / TextTier tiers); it is restored as multi-tier annotation (undoable) and may be uploaded before or after the audio.",
    "TextGrid 中未解析出任何层。": "No tiers could be parsed from the TextGrid.",
    "已暂存 TextGrid（{0} 层），载入音频后自动应用。": "TextGrid staged ({0} tiers); it will be applied automatically once audio is loaded.",
    "TextGrid 已暂存，载入音频后会自动应用。": "TextGrid staged; it will be applied automatically once audio is loaded.",
    "TextGrid 解析失败：{0}": "TextGrid parse failed: {0}",

    # ---- 侧边栏：分析参数 ----
    "🔬 分析参数": "🔬 Analysis",
    "基频下限 (Hz)": "F0 floor (Hz)",
    "低于此频率视为清音": "frames below this are treated as unvoiced",
    "低于此频率视为清音；去声/嘎裂声可降到 40–60 Hz": "frames below this are treated as unvoiced; for falling/creaky tails try 40–60 Hz",
    "去声/儿化尾段若没有曲线：把最后一个点拖到更晚，或在空白处双击加点。": "If a falling/erhua tail has no curve: drag the last point later, or double-click in the blank to add a point.",
    "基频上限 (Hz)": "F0 ceiling (Hz)",
    "高于此频率视为清音": "frames above this are treated as unvoiced",
    "分析帧移 (ms)": "Frame period (ms)",
    "修改分析参数将重置音高编辑（重新提取曲线）": "Changing analysis parameters resets pitch editing (the curve is re-extracted)",

    # ---- 侧边栏：自动切分 / 标注层 ----
    "🎬 音节自动切分": "🎬 Syllable auto-segmentation",
    "自动切分音节": "Auto-segment syllables",
    "基于浊音段 + 能量包络自动检测音节边界并生成连续音节框（可再手动微调/改名）": "Automatically detects syllable boundaries from voiced runs + energy envelope and creates contiguous syllable boxes (fine-tune / rename later)",
    "写入第 0 层「PY」（拼音）；切分后可在图上微调边界、填入拼音（如 liu4 / 好3）。": "Writes into tier 0 “PY” (pinyin); after segmentation fine-tune boundaries and type pinyin (e.g. liu4 / hao3).",
    "📚 标注层（多层，仿 Praat）": "📚 Tiers (multi-tier, Praat-like)",
    "区间": "interval",
    "点": "point",
    "层{0}": "Layer {0}",
    "**{0}**：{1} 项": "**{0}**: {1} item(s)",
    "*(主层)*": "*(main)*",
    "删除该层": "Delete this tier",
    "第 0 层「PY」承载自动切分/文本对齐/声调提取；在 PY 轨点选某条边界后按 **B**：区间层加边界、点层(TextTier)加一个点。": "Tier 0 “PY” hosts segmentation / text alignment / tone extraction; click a PY boundary and press **B**: interval tiers get a boundary, point tiers (TextTier) get a point.",
    "新层名称": "New tier name",
    "如：词 / 字 / 重音": "e.g. word / char / stress",
    "类型": "Type",
    "区间 IntervalTier": "Interval IntervalTier",
    "点 TextTier": "Point TextTier",
    "➕ 添加标注层": "➕ Add tier",
    "请先填写新层名称。": "Please enter a tier name first.",

    # ---- 侧边栏：音高编辑 / 特征点 / 声调 ----
    "✏️ 音高编辑操作": "✏️ Pitch editing",
    "♭ 降 1 半音": "♭ Down 1 semitone",
    "整体降低 1 个半音": "Lower the whole curve by 1 semitone",
    "♯ 升 1 半音": "♯ Up 1 semitone",
    "整体升高 1 个半音": "Raise the whole curve by 1 semitone",
    "🌀 平滑曲线": "🌀 Smooth curve",
    "对编辑点做滑动平均，去掉锯齿": "Moving-average smoothing of the edit points to remove jitter",
    "以上为整体操作，可随时在图上“↩️ 撤销”。": "These are global operations — undo them anytime with “↩️ Undo”.",
    "🎯 特征点（仿 Praat Stylize）": "🎯 Feature points (Praat Stylize-like)",
    "容差（半音）": "Tolerance (semitones)",
    "容差越大保留的特征点越少。提取后相邻保留点之间按直线插值，与原曲线偏差不超过容差。": "A larger tolerance keeps fewer feature points; the kept points are joined by straight lines staying within that tolerance of the original curve.",
    "✂️ 提取特征点": "✂️ Extract feature points",
    "根据音高变化趋势保留转折点/端点，去除中间连续性好的点，便于手动微调语调": "Keeps the turning/edge points of the pitch contour and removes smooth runs in between, for manual fine-tuning of intonation",
    "提取后用鼠标拖拽特征点微调语调，曲线在相邻点间按直线插值。": "Drag the feature points to shape the intonation; between neighbouring points the curve is straight-line interpolated.",
    "🎵 按声调提取特征点": "🎵 Extract by tone number",
    "🎶 应用声调特征点": "🎶 Apply tone features",
    "对每个标注音节按声调提取特征点，删除其间的平滑过渡点": "Extracts tone-based feature points for every annotated syllable, removing the smooth transitions between them",
    "第0层已标注 {0} 个音节。规则（末尾数字=声调，如 liu4/好3）：\n1 声·稳定段两端；2 声·前半段低点+后半段高点；3 声·两端+低点；4 声·前半段高点+后半段低点；0(轻声)·前接1/2/4声取最低点、前接3声取最高点；无数字时自动按轮廓推断声调。": "{0} syllable(s) annotated on tier 0. Rule (trailing digit = tone, e.g. liu4 / hao3):\ntone 1·both ends of the level stretch; tone 2·min of first half + max of second half; tone 3·both ends + minimum; tone 4·max of first half + min of second half; 0 (neutral)·lowest point if previous tone is 1/2/4, highest if previous is 3; without a digit the tone is inferred from the contour.",
    "先在图上开启“📝 标注音节”或自动切分（文本如 liu4 / 好3 / 我）。": "First enable “📝 Annotate syllables” on the chart or auto-segment (text like liu4 / hao3 / wo).",

    # ---- 主体 ----
    "导入或录制一段语音 → 自动提取音高曲线 → 用鼠标**拖拽**调节音高 → TD-PSOLA 重合成即时试听。": "Import or record speech → the F0 curve is extracted automatically → **drag** the handles to adjust pitch → TD-PSOLA resynthesis for instant preview.",
    "图表内播放已关闭（音频较大）。请使用下方「试听对比」。": "In-chart playback is off (audio is large). Use “Compare” below.",
    "👈 请先在左侧选择音频来源：**导入文件**、**麦克风录音**或**示例音频**。\n\n示例音频是一段合成的哼鸣（降调→升调→降调），可以直接体验拖拽调音高。": "👈 First pick an audio source on the left: **Import file**, **Microphone** or **Sample audio**.\n\nThe sample is a synthetic hum (fall → rise → fall) so you can try pitch-dragging right away.",
    "❌ 音频解码失败：{0}": "❌ Audio decode failed: {0}",
    "⚠️ 音频较长（>4 分钟），重合成所需内存与时间会增加。": "⚠️ Audio is long (>4 min); resynthesis may need more memory and time.",
    "🔬 提取音高曲线中（自相关法）...": "🔬 Extracting pitch curve (autocorrelation)...",
    "⚠️ 未检测到浊音（音高）。请检查音频是否为语音/哼唱，或调整“基频上下限”参数。": "⚠️ No voicing (pitch) detected. Check that the audio is speech or humming, or adjust the “F0 floor / ceiling” parameters.",
    "⚠️ 未检测到可靠音高，已提供 150 Hz 基准线供手工编辑；重合成会自动尝试弱脉冲检测，仍可改变音高。": "⚠️ No reliable pitch was detected. A 150 Hz baseline is available for manual editing; resynthesis will retry weak-pulse detection so pitch changes still take effect.",
    "⚠️ TextGrid 时长为 {0}s，音频时长为 {1}s；超出音频范围的标注已裁剪。请确认文件是否配套。": "⚠️ TextGrid duration is {0}s while the audio is {1}s; annotations outside the audio were clipped. Please confirm the files match.",
    "✅ 已从 TextGrid 载入 {0} 层标注：{1}（可撤销）": "✅ Loaded {0} tier(s) from TextGrid: {1} (undoable)",
    "TextGrid 载入失败：{0}": "TextGrid load failed: {0}",

    # ---- 工具行 ----
    "撤销": "Undo",
    "撤销上一步操作（拖拽/加点/音节/升降调/提取特征点等），可多次点击逐级撤销": "Undo the last real action (drag / add point / syllables / semitone shift / feature extraction, etc.); click repeatedly to step back",
    "恢复": "Redo",
    "恢复被撤销的操作，可多次点击逐级恢复": "Redo the undone actions; click repeatedly — a new action clears the redo history",
    "重置为原始曲线": "Reset to original",
    "恢复由音频直接提取的原始音高曲线（可撤销）": "Restore the original pitch curve extracted from the audio (undoable)",
    "音节文本（对齐用）": "Syllable text (for alignment)",
    "汉字每字一音节 / 拼音按声调数字切分，如：好1你2在4 或 wo3shi4shei2": "One Hanzi per syllable, or pinyin split by tone digit, e.g. hao1 ni3 zai4 or wo3shi4shei2",
    "自动切分/手工定好音节边界后，把整段文本按顺序填入各音节框（数量须一致，可撤销）": "After auto-segmentation or manual boundaries, fill the whole text into the boxes in order (counts must match; undoable)",
    "对齐": "Align",
    "把文本切分为音节并逐框填入（数量须一致，操作可撤销）": "Splits the text into syllables and fills the boxes one by one (counts must match; undoable)",
    "还没有音节框：请先用侧边栏“🧩 自动切分音节”或手动标注。": "No syllable boxes yet: use “🧩 Auto-segment” in the sidebar, or annotate by hand.",
    "未能解析出音节。汉字直接输入；拼音需写全字母并带声调数字（如 wo3）。": "Could not parse syllables. Enter Hanzi directly, or pinyin with complete letters and a tone digit (e.g. wo3).",
    "音节数量不匹配：文本解析出 {0} 个（{1}），当前音节框 {2} 个。请调整文本或音节框数量后重试。": "Syllable count mismatch: the text gives {0} ({1}) but there are {2} boxes. Adjust the text or the number of boxes and retry.",
    "✅ 已按{0}对齐 {1} 个音节（可撤销）": "✅ Aligned {1} syllable(s) ({0}) (undoable)",
    "解析：{0} 个音节（{1}）· 音节框 {2} 个 —— ⚠️ 数量不一致，无法对齐": "Parsed {0} syllable(s) ({1}) · {2} box(es) — ⚠️ counts differ, cannot align",
    "解析：{0} 个音节（{1}）· 音节框 {2} 个，可直接点“🔤 对齐”": "Parsed {0} syllable(s) ({1}) · {2} box(es) — click “🔤 Align” to apply",
    "📄 导入": "📄 Import",
    "导入文本文件 (.txt)": "Import text file (.txt)",
    "选择 UTF-8 / GBK 编码的 .txt，自动填入左侧对齐输入框（可再编辑），点“🔤 对齐”应用。换行/空格/标点自动忽略。": "Pick a UTF-8 / GBK .txt file; it is auto-loaded into the alignment box on the left (still editable), then click “🔤 Align”. Line breaks / spaces / punctuation are ignored.",
    "无法识别文本编码，请使用 UTF-8 或 GBK。": "Could not detect the text encoding — please use UTF-8 or GBK.",
    "📄 已导入 {0} 个音节（{1}），与音节框一致，可直接点“🔤 对齐”。": "📄 Imported {0} syllable(s) ({1}) — matches the boxes, click “🔤 Align”.",
    "📄 已导入 {0} 个音节（{1}），音节框 {2} 个 —— ⚠️ 数量不一致，无法对齐。": "📄 Imported {0} syllable(s) ({1}) but there are {2} box(es) — ⚠️ counts differ, cannot align.",
    "⏱ 时长调节（仿 Praat manipulation）": "⏱ Duration (Praat-manipulation-like)",
    "在图下方「时长带」上下拖动各音节调音长（0.5×–2×），应用后按时长因子重合成（保持音高），生成的新音频自动载入、标注按时间映射迁移。": "Drag each syllable up/down in the “duration strip” below the chart (0.5×–2×); on apply, audio is resynthesized with those duration factors (pitch kept) and loaded as the current audio, with annotations mapped to the new timeline.",
    "在图下方「时长带」上下拖动各音节调音长（0.25×–3.0×），应用后按时长因子重合成（保持音高），生成的新音频自动载入、标注按时间映射迁移。": "Drag each syllable up/down in the “duration strip” below the chart (0.25×–3.0×); on apply, audio is resynthesized with those duration factors (pitch kept) and loaded as the current audio, with annotations mapped to the new timeline.",
    "🕐 应用时长（重合成）": "🕐 Apply durations (resynth.)",
    "按各音节时长因子重合成：总时长按因子变化、音高保持；结果作为新音频载入当前画布（原标注自动映射到新时间轴）。": "Resynthesize using each syllable's duration factor: total length changes accordingly while pitch is preserved; the result is loaded as the current audio (existing annotations are mapped onto the new timeline).",
    "因子重置 1×": "Reset factors to 1×",
    "把时长带中各音节因子恢复为 1×（不变速）": "Reset every syllable's duration factor in the strip back to 1× (no time change)",
    "（时长调整）": " (duration-adjusted)",
    "✅ 已应用时长：{0} s → {1} s（第{2}音节等已变速；标注已迁移，可用下方“应用时长前”对比试听）": "✅ Durations applied: {0} s → {1} s (syllable {2} was sped/slowed; annotations mapped — compare with “before applying” below)",
    "**应用时长前音频**（用于对比）": "**Audio before applying durations** (for comparison)",
    "对比提示：当前音频已按“时长调节”应用变速（{0}）。上面左为应用前、右为应用后。": "Compare: the current audio was time-adjusted via “Duration” ({0}). Left = before applying, right = after.",
    "时长因子未变化（都≈1×或与应用一致），无需重复应用。": "Duration factors are unchanged (all ≈1× or same as applied) — nothing to apply.",
    "🧪 自动演示：第 2 音节 1.5× 并应用": "🧪 Demo: set syllable 2 to 1.5× and apply",
    "把第 2 音节时长因子设为 1.5× 并立即应用——无需手动拖动即可看到效果": "Set syllable 2's duration factor to 1.5× and apply right away — see the effect without dragging manually",
    "📚 标注层": "📚 Tiers",
    "🎯 特征点": "🎯 Feature points",
    "⏱ 时长调节": "⏱ Duration",
    "按浊音段自动生成连续音节框（可再手动微调）": "Auto-generate contiguous syllable boxes from voiced runs (fine-tune manually later)",
    "容差越大保留的特征点越少": "Larger tolerance keeps fewer feature points",
    "保留转折点/端点，便于手动微调语调": "Keep turning/edge points of the contour for manual fine-tuning",
    "对每个标注音节按声调提取特征点": "Extract tone-based feature points for every annotated syllable",
    "按时长带因子重合成并载入新音频；因子未变则无需再点": "Resynthesize with the duration factors and load the new audio; no need to click again if factors are unchanged",
    "把各音节因子恢复为 1×（不变速）": "Reset every syllable's factor back to 1× (no time change)",
    "整体降 1 半音": "Lower the whole curve by 1 semitone",
    "整体升 1 半音": "Raise the whole curve by 1 semitone",
    "滑动平均去锯齿": "Moving-average smoothing to remove jitter",
    "💾 固化音高为新音频": "💾 Freeze pitch into new audio",
    "把当前编辑后的音高曲线重合成并保存为新音频载入（保留标注），类似 Praat 的 Publish resynthesis": "Resynthesize the currently edited pitch curve and load it as the new current audio (annotations kept) — like Praat’s Publish resynthesis",
    "（音高固化）": " (pitch-fixed)",
    "✅ 已固化编辑后的音高为新音频：{0} s（标注保留，可下载“编辑后 WAV”导出）": "✅ Edited pitch was frozen into the new audio: {0} s (annotations kept; export via “Edited WAV”)",
    "**处理前音频**（用于对比）": "**Audio before processing** (for comparison)",
    "对比提示：左为处理前、右为处理后（{0}）。": "Compare: left = before processing, right = after ({0}).",
    "⬇️ PitchTier": "⬇️ PitchTier",
    "把当前编辑过的音高控制点/特征点曲线保存为 Praat PitchTier 文本（可再读回/对照）": "Save the current edited pitch control / feature-point curve as a Praat PitchTier text file (for reuse or comparison)",
    "⚠️ 实验性：变速对自然语音可能产生轻微音色/边界变化；建议小幅调整并用「应用时长前」对比试听。": "⚠️ Experimental: time-stretching may slightly colour natural speech; keep adjustments modest and compare with “before applying”.",
    "❌ 应用时长失败：{0}": "❌ Applying durations failed: {0}",
    "在图下方「时长带」上下拖动各音节调音长（0.8×–1.5×），应用后按时长因子重合成（保持音高），生成的新音频自动载入、标注按时间映射迁移。": "Drag each syllable in the “duration strip” below the chart (0.8×–1.5×); on apply the audio is resynthesized with those factors (pitch kept) and loaded as the current audio, with annotations mapped to the new timeline.",
    "在图下方「时长带」上下拖动各音节调音长（0.25×–3×），应用后按时长因子重合成（保持音高），生成的新音频自动载入、标注按时间映射迁移。": "Drag each syllable in the “duration strip” below the chart (0.25×–3×); on apply the audio is resynthesized with those factors (pitch kept) and loaded as the current audio, with annotations mapped to the new timeline.",
    "按各音节时长因子重合成：总时长按因子变化、音高保持；结果作为新音频载入当前画布（原标注自动映射到新时间轴）。若因子未变化会给出提示。": "Resynthesize using each syllable's duration factor: total length changes accordingly while pitch is preserved; the result is loaded as the current audio (annotations are mapped onto the new timeline). If the factors are unchanged, a notice is shown.",

    # ---- 合成 / 指标 / 试听 ----
    "🎶 重合成编辑后音频中...": "🎶 Resynthesizing edited audio...",
    "时长": "Duration",
    "浊音占比": "Voiced ratio",
    "原始平均基频": "Orig. mean F0",
    "原始范围 {0}–{1} Hz": "original range {0}–{1} Hz",
    "当前平均基频": "Current mean F0",
    "编辑后范围 {0}–{1} Hz": "edited range {0}–{1} Hz",
    "编辑点数": "Edit points",
    "音节数": "Syllables",
    "🎧 试听对比": "🎧 Compare",
    "**解码后原始音频**": "**Decoded original audio**",
    "**编辑后音频**（TD-PSOLA 重合成）": "**Edited audio** (TD-PSOLA resynthesis)",

    # ---- 保存 ----
    "💾 保存结果": "💾 Save results",
    "⬇️ 原始 WAV": "⬇️ Original WAV",
    "⬇️ 编辑后 WAV": "⬇️ Edited WAV",
    "⬇️ TextGrid": "⬇️ TextGrid",
    "Praat 可直接读取的多层标注（区间层 IntervalTier + 点层 TextTier）": "Praat-readable multi-tier annotation (IntervalTier + TextTier)",
    "📦 一键保存全部": "📦 Save all (ZIP)",
    "ZIP：原始 WAV + 编辑后 WAV + 多层 TextGrid 标注": "ZIP: original WAV + edited WAV + multi-tier TextGrid",
    "ZIP：原始 WAV + 编辑后 WAV + 多层 TextGrid 标注 + PitchTier 音高编辑点": "ZIP: original WAV + edited WAV + multi-tier TextGrid + PitchTier pitch points",
    "已导出 {0} 层标注：{1}。左侧“📂 载入此前标注”可载入该 TextGrid（兼容长/短两种格式）恢复多层标注。": "Exported {0} tier(s): {1}. The sidebar “📂 Load previous annotation” can load this TextGrid (both long and short formats) to restore the tiers.",

    # ---- 分析详情 ----
    "采样率": "Sample rate",
    "解码方式": "Decoder",
    "样本数": "Samples",
    "帧移 (ms)": "Frame (ms)",
    "基频下限": "F0 floor",
    "基频上限": "F0 ceiling",
    "分析帧数": "Frames",
    "浊音帧数": "Voiced frames",
    "编辑点数量": "Edit point count",
    "平均基频 (Hz)": "Mean F0 (Hz)",
}


def set_lang(lang: str) -> None:
    global _LANG
    _LANG = "en" if lang == "en" else "zh"


def is_en() -> bool:
    return _LANG == "en"


def tr(text: str) -> str:
    """按当前语言返回文案：zh 原样；en 查 EN 表（缺失则回退中文）。"""
    if _LANG == "en":
        return EN.get(text, text)
    return text


def trf(template: str, *args) -> str:
    """模板化文案（含 {0} {1} ... 占位符），先翻译再格式化。"""
    if _LANG == "en":
        template = EN.get(template, template)
    if args:
        try:
            return template.format(*args)
        except (IndexError, KeyError):
            return template
    return template
