from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

W, H = 1800, 1280
OUT = Path("system_architecture.png")
FONT = r"C:\Windows\Fonts\simhei.ttf"

font_title = ImageFont.truetype(FONT, 52)
font_layer = ImageFont.truetype(FONT, 34)
font_text = ImageFont.truetype(FONT, 25)
font_small = ImageFont.truetype(FONT, 22)
font_tiny = ImageFont.truetype(FONT, 19)

img = Image.new("RGB", (W, H), "#f6f8fb")
d = ImageDraw.Draw(img)

ink = "#172033"
muted = "#536273"
blue = "#2f6fed"
green = "#1f9d74"
orange = "#d9822b"
purple = "#7c4dff"
red = "#c94040"
line = "#5d6f85"
border = "#c9d4e2"


def rr(box, fill, outline=border, width=2, radius=22):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center(text, box, font=font_small, fill=ink, gap=8):
    x1, y1, x2, y2 = box
    lines = text.split("\n")
    sizes = [d.textbbox((0, 0), line, font=font) for line in lines]
    widths = [b[2] - b[0] for b in sizes]
    heights = [b[3] - b[1] for b in sizes]
    total_h = sum(heights) + gap * (len(lines) - 1)
    y = y1 + (y2 - y1 - total_h) / 2
    for line, width, height in zip(lines, widths, heights):
        d.text((x1 + (x2 - x1 - width) / 2, y), line, font=font, fill=fill)
        y += height + gap


def arrow(a, b, color=line, width=4, head=16):
    x1, y1 = a
    x2, y2 = b
    d.line((x1, y1, x2, y2), fill=color, width=width)
    angle = math.atan2(y2 - y1, x2 - x1)
    for delta in (math.pi * 0.85, -math.pi * 0.85):
        d.line(
            (x2, y2, x2 + head * math.cos(angle + delta), y2 + head * math.sin(angle + delta)),
            fill=color,
            width=width,
        )


def tag(text, x, y):
    b = d.textbbox((0, 0), text, font=font_tiny)
    pad = 8
    d.rounded_rectangle((x - pad, y - pad, x + b[2] + pad, y + b[3] + pad), radius=8, fill="#ffffff", outline="#dbe3ee")
    d.text((x, y), text, font=font_tiny, fill=muted)


def box(box, fill, outline, text):
    rr(box, fill, outline, 3 if outline != border else 2)
    center(text, box)


title = "系统技术架构图"
subtitle = "基于 RAG 的计算机学科知识点智能问答系统"
d.text((W / 2 - d.textbbox((0, 0), title, font=font_title)[2] / 2, 38), title, font=font_title, fill=ink)
d.text((W / 2 - d.textbbox((0, 0), subtitle, font=font_text)[2] / 2, 108), subtitle, font=font_text, fill=muted)

for band in [
    (80, 160, 1720, 290, "#eef4ff", "表示层"),
    (80, 325, 1720, 560, "#f7fbff", "应用层"),
    (80, 600, 1720, 840, "#fffaf3", "智能服务层"),
    (80, 880, 1720, 1125, "#f3fbf7", "数据与任务层"),
]:
    x1, y1, x2, y2, fill, name = band
    d.rounded_rectangle((x1, y1, x2, y2), radius=28, fill=fill, outline="#d9e2ef", width=2)
    d.text((x1 + 24, y1 + 18), name, font=font_layer, fill=muted)

# 表示层
user = (170, 190, 410, 260)
frontend = (600, 180, 1020, 270)
nginx = (1210, 180, 1550, 270)
box(user, "#ffffff", border, "用户 / 管理员")
box(frontend, "#e8f0ff", blue, "前端表示层\nVue 3 + Element Plus\nMarkdown / KaTeX / 图谱可视化")
box(nginx, "#ffffff", border, "Nginx 反向代理\nHTTP / SSE")
arrow((410, 225), (600, 225), blue)
tag("浏览器访问", 455, 198)
arrow((1020, 225), (1210, 225), blue)
tag("REST API / SSE", 1065, 198)

# 应用层
backend = (140, 375, 430, 520)
qa = (520, 365, 800, 535)
kb = (850, 365, 1130, 535)
kg = (1180, 365, 1480, 535)
config = (1510, 390, 1680, 510)
box(backend, "#ffffff", border, "后端应用层\nFastAPI\nJWT / SQLAlchemy")
box(qa, "#eaf7ff", "#2d8ecf", "智能问答模块\n意图识别 / 混合检索\nPrompt 构造 / 流式输出")
box(kb, "#fff8e8", orange, "知识库管理模块\n上传 / 解析 / 清洗\n分块 / 向量化")
box(kg, "#f0ecff", purple, "知识图谱模块\n实体关系抽取\n审核 / 子图查询")
box(config, "#ffffff", border, "系统配置\n模型参数\n检索参数")
arrow((1380, 270), (1380, 365), blue)
arrow((1380, 365), (430, 445), blue)
arrow((430, 445), (520, 445), blue)
arrow((800, 445), (850, 445))
arrow((1130, 445), (1180, 445))
arrow((1480, 445), (1510, 445))

# 智能服务层
llm = (180, 650, 520, 800)
chat = (620, 640, 960, 815)
embed = (1010, 640, 1320, 815)
extract = (1370, 640, 1680, 815)
box(llm, "#ffffff", "#9aa9ba", "统一 LLM 服务接口\n封装模型调用、异常处理\n对话 / Embedding / 抽取")
box(chat, "#e8f0ff", blue, "DeepSeek 对话生成\ndeepseek-v4-flash\n结构化消息列表\nTemperature 0.3-0.5")
box(embed, "#e8f8f1", green, "DeepSeek 向量嵌入\ndeepseek-embedding\n1024维稠密向量\n文档与问题同空间")
box(extract, "#fff3e6", orange, "实体关系抽取\nPrompt 模板引导\n六种语义关系\n置信度 0-1")
arrow((660, 535), (350, 650), "#7a8797")
arrow((990, 535), (350, 650), "#7a8797")
arrow((1330, 535), (350, 650), "#7a8797")
arrow((520, 725), (620, 725), blue)
arrow((520, 725), (1010, 725), green)
arrow((520, 725), (1370, 725), orange)
tag("system prompt + 检索上下文 + 对话历史 + 用户问题", 616, 596)

# 数据与任务层
mysql = (140, 930, 390, 1065)
redis = (450, 930, 700, 1065)
chroma = (760, 930, 1030, 1065)
neo4j = (1090, 930, 1360, 1065)
celery = (1420, 930, 1680, 1065)
box(mysql, "#ffffff", border, "MySQL\n用户 / 文档 / 消息\n错题 / 心得 / 配置")
box(redis, "#fff0f0", red, "Redis\n缓存 / 消息队列\nCelery Broker")
box(chroma, "#e8f8f1", green, "ChromaDB\n文档分块向量\nTop-K 语义检索")
box(neo4j, "#f0ecff", purple, "Neo4j\n知识点实体\n关系子图检索")
box(celery, "#fff3e6", orange, "Celery Worker\n文档解析\nKG 批量抽取")

arrow((790, 815), (895, 930), blue)
arrow((1165, 815), (895, 930), green)
arrow((1525, 815), (1225, 930), orange)
arrow((990, 535), (1550, 930), orange)
arrow((1550, 930), (575, 930), red)
arrow((270, 520), (265, 930), line)
arrow((660, 535), (895, 930), line)
arrow((660, 535), (1225, 930), line)
arrow((1550, 1065), (990, 535), orange)
tag("异步解析 / 抽取", 1395, 865)
tag("业务数据持久化", 172, 850)
tag("RAG 检索", 826, 865)
tag("图谱增强", 1125, 865)

note = (150, 1150, 1680, 1235)
d.rounded_rectangle(note, radius=18, fill="#ffffff", outline="#dbe3ee", width=2)
center(
    "知识图谱关系类型：PREREQUISITE 前置、NEXT 后继、RELATED 相关、CONTAINS 包含、CONTRAST 对比、EXAMINED_IN 考察于",
    note,
    font_small,
    muted,
)

img.save(OUT, quality=95)
print(OUT.resolve())
