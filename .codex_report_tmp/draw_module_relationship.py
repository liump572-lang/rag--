from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

W, H = 1800, 1260
OUT = Path("module_relationship.png")
FONT = r"C:\Windows\Fonts\simhei.ttf"

font_title = ImageFont.truetype(FONT, 52)
font_text = ImageFont.truetype(FONT, 25)
font_small = ImageFont.truetype(FONT, 22)
font_tiny = ImageFont.truetype(FONT, 19)

img = Image.new("RGB", (W, H), "#f7f9fc")
d = ImageDraw.Draw(img)

ink = "#172033"
muted = "#536273"
border = "#c9d4e2"
blue = "#2f6fed"
cyan = "#168aad"
green = "#1f9d74"
orange = "#d9822b"
purple = "#7c4dff"
red = "#c94040"
gray = "#5d6f85"


def rr(box, fill, outline=border, width=2, radius=24):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center(text, box, font=font_small, fill=ink, gap=8):
    x1, y1, x2, y2 = box
    lines = text.split("\n")
    boxes = [d.textbbox((0, 0), line, font=font) for line in lines]
    widths = [b[2] - b[0] for b in boxes]
    heights = [b[3] - b[1] for b in boxes]
    total_h = sum(heights) + gap * (len(lines) - 1)
    y = y1 + (y2 - y1 - total_h) / 2
    for line, width, height in zip(lines, widths, heights):
        d.text((x1 + (x2 - x1 - width) / 2, y), line, font=font, fill=fill)
        y += height + gap


def arrow(a, b, color=gray, width=4, head=16):
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


def poly_arrow(points, color=gray, width=4):
    for i in range(len(points) - 2):
        d.line((points[i], points[i + 1]), fill=color, width=width)
    arrow(points[-2], points[-1], color, width)


def tag(text, x, y, color=muted):
    b = d.textbbox((0, 0), text, font=font_tiny)
    pad = 8
    d.rounded_rectangle((x - pad, y - pad, x + b[2] + pad, y + b[3] + pad), radius=9, fill="#ffffff", outline="#dbe3ee")
    d.text((x, y), text, font=font_tiny, fill=color)


def box(title, body, xy, fill, outline):
    rr(xy, fill, outline, 3)
    x1, y1, x2, y2 = xy
    center(title, (x1 + 12, y1 + 18, x2 - 12, y1 + 58), font_text, ink)
    center(body, (x1 + 18, y1 + 76, x2 - 18, y2 - 14), font_small, muted)


title = "系统功能模块关系图"
subtitle = "用户认证统一支撑，知识库作为数据基础，智能问答融合向量检索与图谱检索"
d.text((W / 2 - d.textbbox((0, 0), title, font=font_title)[2] / 2, 38), title, font=font_title, fill=ink)
d.text((W / 2 - d.textbbox((0, 0), subtitle, font=font_text)[2] / 2, 108), subtitle, font=font_text, fill=muted)

# Bands
rr((90, 175, 1710, 330), "#eef4ff", "#cfe0ff", 2, 28)
rr((90, 370, 1710, 680), "#ffffff", "#dbe3ee", 2, 28)
rr((90, 720, 1710, 1005), "#f3fbf7", "#dbe3ee", 2, 28)
d.text((120, 196), "基础支撑层", font=font_text, fill=muted)
d.text((120, 392), "核心业务链路", font=font_text, fill=muted)
d.text((120, 742), "学习支持、后台管理与数据存储", font=font_text, fill=muted)

# Top support
auth = (235, 215, 565, 320)
api = (735, 215, 1065, 320)
redis = (1235, 215, 1565, 320)
box("用户认证模块", "JWT 双 Token\n身份验证 / 角色授权", auth, "#e8f0ff", blue)
box("RESTful API", "模块间同步调用\n路由依赖注入当前用户", api, "#ffffff", border)
box("Redis 消息队列", "异步任务解耦\nparse_queue / kg_queue", redis, "#fff0f0", red)
arrow((565, 268), (735, 268), blue)
tag("身份注入", 610, 238, blue)
arrow((1065, 268), (1235, 268), red)
tag("异步任务", 1110, 238, red)

# Main chain
kb = (165, 465, 465, 635)
kg = (565, 465, 865, 635)
qa = (965, 465, 1265, 635)
llm = (1365, 465, 1665, 635)
box("知识库管理模块", "文档导入\n解析 / 分块 / 向量化\n输出文档片段", kb, "#fff8e8", orange)
box("知识图谱模块", "实体关系抽取\nCandidateRelation 审核\nNeo4j 图谱构建", kg, "#f0ecff", purple)
box("智能问答模块", "ChromaDB Top-K 检索\nNeo4j 图检索\nSSE 流式回答", qa, "#eaf7ff", cyan)
box("LLM 服务", "Prompt 组装\nDeepSeek 回答生成\n实体关系抽取", llm, "#e8f8f1", green)

arrow((465, 530), (565, 530), orange)
tag("实体关系抽取输入", 475, 500, orange)
arrow((865, 530), (965, 530), purple)
tag("图谱检索能力", 875, 500, purple)
arrow((1265, 530), (1365, 530), green)
tag("提交上下文", 1285, 500, green)

poly_arrow([(315, 635), (315, 675), (1115, 675), (1115, 635)], orange)
tag("语义检索数据来源", 645, 646, orange)
poly_arrow([(1515, 465), (1515, 410), (715, 410), (715, 465)], green)
tag("LLM 抽取知识三元组", 895, 382, green)
poly_arrow([(1400, 310), (1400, 420), (715, 420), (715, 465)], red)
tag("Celery Worker 消费", 1190, 392, red)

# Lower modules and stores
notes = (165, 820, 445, 950)
wrong = (500, 820, 780, 950)
admin = (835, 810, 1145, 960)
mysql = (1220, 800, 1460, 960)
stores = (1500, 800, 1665, 960)
box("学习心得模块", "发布 / 审核\n点赞 / 收藏 / 评论\n通过 user_id 关联用户", notes, "#f7f5ff", purple)
box("错题本模块", "错题录入\n筛选 / 复习 / 组卷\n通过 user_id 关联用户", wrong, "#fff7e8", orange)
box("后台管理模块", "全局统计\n系统配置\n跨模块维护", admin, "#eef7ff", blue)
box("MySQL", "用户 / 文档 / 消息\n错题 / 心得 / 配置\n业务数据持久化", mysql, "#ffffff", border)
box("向量库 / 图数据库", "ChromaDB 向量\nNeo4j 图数据", stores, "#e8f8f1", green)

poly_arrow([(400, 310), (400, 365), (305, 365), (305, 465)], blue)
poly_arrow([(900, 310), (900, 365), (1115, 365), (1115, 465)], blue)
poly_arrow([(400, 310), (400, 785), (305, 785), (305, 820)], blue)
poly_arrow([(400, 310), (400, 785), (640, 785), (640, 820)], blue)
tag("认证支撑所有业务模块", 470, 345, blue)

poly_arrow([(990, 810), (990, 710), (315, 710), (315, 635)], blue)
poly_arrow([(990, 810), (990, 710), (715, 710), (715, 635)], blue)
poly_arrow([(990, 810), (990, 710), (1115, 710), (1115, 635)], blue)
tag("跨模块统计 / 配置 / 管理", 820, 690, blue)

tag("业务数据统一持久化", 1205, 770, gray)
tag("向量检索 / 图检索", 1450, 755, green)

# Legend
legend = (150, 1045, 1650, 1215)
rr(legend, "#ffffff", "#dbe3ee", 2, 18)
center(
    "关系说明：知识库模块为知识图谱抽取和智能问答检索提供数据基础；知识图谱模块为问答提供关联知识。\n学习心得和错题本通过 user_id 与认证模块关联；后台管理跨越全部业务模块。\nRedis 队列用于文档解析和知识图谱抽取等异步任务解耦。",
    legend,
    font_small,
    muted,
)

img.save(OUT, quality=95)
print(OUT.resolve())
