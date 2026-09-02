# -*- coding: utf-8 -*-
"""生成 README 中的架构示意图 docs/architecture.png（纯 PIL，无外部依赖）。"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 980, 540
BG = (24, 27, 34)
CARD = (38, 42, 52)
ACCENT = (255, 75, 75)
BLUE = (96, 130, 255)
GREEN = (0, 180, 120)
TEXT = (235, 238, 245)
SUB = (168, 175, 188)

font_path = r"C:\Windows\Fonts\msyh.ttc"  # 微软雅黑
F_TITLE = ImageFont.truetype(font_path, 30)
F_BOX = ImageFont.truetype(font_path, 19)
F_SUB = ImageFont.truetype(font_path, 15)
F_SMALL = ImageFont.truetype(font_path, 13)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def box(x, y, w, h, title, sub, fill=CARD, title_color=TEXT, sub_color=SUB, radius=14):
    d.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill, outline=(70, 76, 90), width=1)
    tw = d.textlength(title, font=F_BOX)
    d.text((x + (w - tw) / 2, y + 12), title, font=F_BOX, fill=title_color)
    if sub:
        lines = sub.split("\n")
        lh = 22
        total = len(lines) * lh
        cy = y + h - 22 - total
        for i, ln in enumerate(lines):
            sw = d.textlength(ln, font=F_SUB)
            d.text((x + (w - sw) / 2, cy + i * lh), ln, font=F_SUB, fill=sub_color)


def arrow(x1, y1, x2, y2, color=BLUE, width=4):
    d.line([x1, y1, x2, y2], fill=color, width=width)
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    for da in (0.35, -0.35):
        px = x2 - 16 * math.cos(ang + da)
        py = y2 - 16 * math.sin(ang + da)
        d.line([x2, y2, px, py], fill=color, width=width)


# 标题
tw = d.textlength("语调调试实验室 —— 架构", font=F_TITLE)
d.text(((W - tw) / 2, 18), "语调调试实验室 —— 架构", font=F_TITLE, fill=TEXT)

# 输入
box(60, 90, 250, 84, "音频输入", "导入文件 · 麦克风录音 · 示例", fill=CARD)
# 解码
box(365, 90, 250, 84, "音频解码", "soundfile (libsndfile)", fill=CARD)
# 基频分析
box(670, 90, 250, 84, "基频分析", "FFT 自相关 + 首峰选基频", fill=CARD)

arrow(310, 132, 365, 132)
arrow(615, 132, 670, 132)

# 曲线编辑（主色强调，横贯中部）
box(60, 260, 470, 150, "音高曲线编辑器（浏览器 Canvas 组件）",
    "拖拽调音高 · 双击加点 · Shift+点击删点\n↑↓ 半音微调 · 滚轮缩放 · 播放游标",
    fill=(50, 44, 44), title_color=ACCENT)
# Python 侧
box(600, 260, 320, 150, "Python 会话（Streamlit）",
    "编辑点抽稀 50ms · 重合成缓存\n指标 · 试听 · 导出 WAV", fill=CARD)

arrow(330, 174, 250, 260, color=BLUE)  # 分析 -> 编辑器
arrow(295, 335, 600, 335, color=ACCENT, width=5)  # 组件 -> Python（postMessage）
# 回程箭头（下侧）
arrow(760, 410, 620, 335, color=ACCENT, width=5)  # Python -> 组件（新曲线+音频）

# TD-PSOLA 重合成
box(60, 440, 250, 70, "TD-PSOLA 重合成", "时长/清浊结构保持不变", fill=CARD)
arrow(250, 335, 185, 440, color=GREEN, width=5)

# 输出
box(365, 440, 250, 70, "编辑后音频", "即时试听 · 对比 · 导出 WAV", fill=GREEN, title_color=(0, 60, 40))
arrow(310, 475, 365, 475, color=GREEN, width=5)

img.save(Path(__file__).with_name("architecture.png"))
print("architecture.png saved")
