from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

W, H = 1900, 1120
OUT = Path("kg_main_ui.png")
FONT = r"C:\Windows\Fonts\simhei.ttf"

font_title = ImageFont.truetype(FONT, 42)
font_h2 = ImageFont.truetype(FONT, 30)
font_text = ImageFont.truetype(FONT, 23)
font_small = ImageFont.truetype(FONT, 19)
font_tiny = ImageFont.truetype(FONT, 16)

img = Image.new("RGB", (W, H), "#f4f7fb")
d = ImageDraw.Draw(img)

ink = "#1f2937"
muted = "#64748b"
border = "#d9e2ef"
primary = "#4f46e5"
blue = "#38bdf8"
pink = "#f472b6"
purple = "#a78bfa"
green = "#4ade80"
gold = "#fbbf24"
orange = "#fb923c"
cyan = "#22d3ee"
red = "#f87171"


def rr(box, fill, outline=border, width=2, radius=18):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text_center(text, box, font=font_small, fill=ink, gap=5):
    x1, y1, x2, y2 = box
    lines = text.split("\n")
    bbs = [d.textbbox((0, 0), line, font=font) for line in lines]
    widths = [b[2] - b[0] for b in bbs]
    heights = [b[3] - b[1] for b in bbs]
    total = sum(heights) + gap * (len(lines) - 1)
    y = y1 + (y2 - y1 - total) / 2
    for line, width, height in zip(lines, widths, heights):
        d.text((x1 + (x2 - x1 - width) / 2, y), line, font=font, fill=fill)
        y += height + gap


def draw_button(box, label, fill="#ffffff", outline=border, color=ink):
    rr(box, fill, outline, 2, 10)
    text_center(label, box, font_small, color)


def draw_tag(box, label, fill, color):
    rr(box, fill, color, 1, 9)
    text_center(label, box, font_tiny, color)


def arrow(a, b, color, width=3, dashed=False):
    x1, y1 = a
    x2, y2 = b
    if dashed:
        segs = 18
        for i in range(segs):
            if i % 2 == 0:
                t1, t2 = i / segs, (i + 1) / segs
                d.line((x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1,
                        x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2), fill=color, width=width)
    else:
        d.line((x1, y1, x2, y2), fill=color, width=width)
    angle = math.atan2(y2 - y1, x2 - x1)
    head = 13
    for delta in (math.pi * 0.85, -math.pi * 0.85):
        d.line((x2, y2, x2 + head * math.cos(angle + delta), y2 + head * math.sin(angle + delta)), fill=color, width=width)


def node(cx, cy, r, label, fill, outline="#ffffff"):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=outline, width=5)
    text_center(label, (cx - r + 6, cy - 25, cx + r - 6, cy + 25), font_tiny, "#ffffff")


# Page shell
rr((55, 45, 1845, 1075), "#ffffff", "#e3eaf5", 2, 26)

# Header
rr((95, 80, 1805, 185), "#eef2ff", "#dbe3ff", 2, 22)
d.text((130, 108), "知识图谱可视化", font=font_title, fill=ink)
d.text((132, 155), "探索实体与关系的知识网络", font=font_text, fill=muted)

# Main areas
graph_card = (95, 215, 1405, 985)
side_card = (1430, 215, 1805, 985)
rr(graph_card, "#ffffff", "#dce6f2", 2, 20)
rr(side_card, "#ffffff", "#dce6f2", 2, 20)

# Toolbar
rr((130, 245, 1370, 330), "#f8fafc", "#e2e8f0", 2, 14)
draw_button((160, 265, 320, 310), "全部科目", "#ffffff")
draw_button((340, 265, 700, 310), "搜索实体或关系...", "#ffffff")
draw_button((720, 265, 815, 310), "刷新", "#ffffff")
draw_button((860, 265, 980, 310), "新增实体", "#eef2ff", primary, primary)
draw_button((1000, 265, 1120, 310), "新增关系", "#ecfdf5", "#16a34a", "#16a34a")
draw_button((1140, 265, 1260, 310), "生成文档", "#fffbeb", "#d97706", "#d97706")
draw_button((1280, 265, 1360, 310), "候选审核", "#ffffff")

# Graph canvas
canvas = (130, 355, 1370, 895)
rr(canvas, "#f8fbff", "#e2e8f0", 2, 18)

# Example graph
positions = {
    "计算机网络": (360, 520, 58, "#60a5fa"),
    "OSI七层模型": (610, 445, 52, "#a78bfa"),
    "TCP协议": (805, 585, 50, "#34d399"),
    "UDP协议": (1040, 585, 48, "#22d3ee"),
    "三次握手": (770, 760, 45, "#fb7185"),
    "滑动窗口": (1030, 760, 44, "#f59e0b"),
    "HTTP协议": (1120, 430, 47, "#818cf8"),
    "应用层": (555, 710, 42, "#4ade80"),
}

edges = [
    ("计算机网络", "OSI七层模型", purple, False, "包含"),
    ("OSI七层模型", "应用层", green, True, "包含"),
    ("应用层", "HTTP协议", blue, False, "后继"),
    ("计算机网络", "TCP协议", purple, False, "相关"),
    ("TCP协议", "UDP协议", gold, True, "对比"),
    ("TCP协议", "三次握手", pink, True, "前置"),
    ("TCP协议", "滑动窗口", orange, False, "相关"),
    ("HTTP协议", "TCP协议", green, False, "依赖"),
]

for a, b, color, dashed, label in edges:
    x1, y1, *_ = positions[a]
    x2, y2, *_ = positions[b]
    arrow((x1, y1), (x2, y2), color, 3, dashed)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    draw_tag((mx - 28, my - 14, mx + 28, my + 14), label, "#ffffff", color)

for label, (x, y, r, fill) in positions.items():
    node(x, y, r, label, fill)

# Canvas hint
rr((470, 920, 1020, 960), "#ffffff", "#dbe3ee", 1, 12)
text_center("滚轮缩放 · 拖动画布 · 双击重置视图 · Neo4j 风格布局", (470, 920, 1020, 960), font_small, muted)

# Side panel
d.text((1465, 250), "图例", font=font_h2, fill=ink)
legend_items = [
    ("前置条件", pink, "虚线"),
    ("后继", blue, "实线"),
    ("关联", purple, "实线"),
    ("包含", green, "点线"),
    ("对比", gold, "虚线"),
    ("考点", orange, "实线"),
]
y = 305
for name, color, style in legend_items:
    d.ellipse((1470, y + 7, 1490, y + 27), fill=color)
    d.text((1505, y), name, font=font_small, fill=ink)
    d.text((1665, y), style, font=font_small, fill=muted)
    y += 48

d.line((1460, 610, 1775, 610), fill="#e2e8f0", width=2)

def stat(y, num, label):
    rr((1465, y, 1775, y + 70), "#f8fafc", "#e2e8f0", 2, 14)
    d.text((1490, y + 16), num, font=font_h2, fill=primary)
    d.text((1590, y + 22), label, font=font_small, fill=muted)

stat(645, "128", "数据库总节点数")
stat(735, "8", "当前显示节点")
stat(825, "8", "关系数")

d.text((1465, 930), "点击节点查看详情 · 双击画布重置视图", font=font_tiny, fill="#94a3b8")

# Figure caption
text_center("图3-1 知识图谱可视化主界面", (0, 1010, W, 1060), font_text, muted)

img.save(OUT, quality=95)
print(OUT.resolve())
