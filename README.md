# 计算机学科知识点智能问答系统

基于 **RAG（Retrieval-Augmented Generation）** 架构的计算机学科智能学习平台，支持多格式文档知识库构建、知识图谱可视化、流式智能问答、学习心得社区、错题本管理等核心功能。

## 快速入口

- [部署文档](./部署文档.md)：包含 Docker 部署步骤、每条命令的执行目录、服务验证、常见问题和项目文件作用说明。

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (Vue 3)                     │
│            Element Plus / ECharts / vis-network          │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP/SSE (Nginx Proxy)
┌─────────────────────▼───────────────────────────────────┐
│                  Backend (FastAPI)                       │
│  ┌──────────┬──────────┬──────────┬──────────────────┐  │
│  │ Auth     │ KB       │ Q&A      │ Knowledge Graph  │  │
│  │ (JWT)    │ (文档管理) │ (RAG问答) │ (Neo4j 知识图谱)   │  │
│  ├──────────┼──────────┼──────────┼──────────────────┤  │
│  │ Notes    │ Wrong Q  │ Notify   │ System / Admin   │  │
│  │ (学习心得) │ (错题本)   │ (消息通知) │ (系统管理)         │  │
│  └──────────┴──────────┴──────────┴──────────────────┘  │
└──────┬──────────┬──────────┬──────────┬─────────────────┘
       │          │          │          │
┌──────▼──┐ ┌─────▼───┐ ┌───▼────┐ ┌──▼──────────┐
│  MySQL  │ │  Redis  │ │ Neo4j  │ │  ChromaDB   │
│ (关系数据) │ │(缓存/队列)│ │(知识图谱)│ │ (向量检索)    │
└─────────┘ └─────────┘ └────────┘ └─────────────┘
                      │
              ┌───────▼────────┐
              │  Celery Worker │
              │ (文档解析/异步任务)│
              └───────┬────────┘
                      │
              ┌───────▼────────┐
              │  DeepSeek LLM  │
              │ (对话/Embedding)│
              └────────────────┘
```

## ✨ 核心功能

### 📚 知识库管理
- 支持 **PDF、DOCX、PPTX、TXT、Markdown** 等多种文档格式上传
- 文档自动解析、智能分块（Chunking）、向量化存储
- 按科目分类管理，支持教材、真题、笔记、补充材料四种文档类型
- 检索测试工具，可视化检索效果

### 🤖 智能问答（RAG）
- 基于 **DeepSeek LLM** 的流式对话（SSE）
- 多轮对话记忆，自动生成对话标题
- 意图识别（知识点问答 / 真题练习 / 学习心得）
- 自动关联引用来源，支持用户反馈与错题收录
- 可配置的检索策略（Top-K、相似度阈值、Temperature 等）

### 🧠 知识图谱
- 基于 **Neo4j** 的知识点关系网络
- 支持 PREREQUISITE（前置）、NEXT（后继）、RELATED（相关）、CONTAINS（包含）、CONTRAST（对比）、EXAMINED_IN（考察于）六种关系类型
- 图可视化探索、关键词搜索子图
- 支持从知识库自动生成知识点文档

### ✍️ 学习心得社区
- 学生可撰写 Markdown 格式学习心得
- 支持**点赞、收藏、评论**互动
- **AI 自动审核**：大模型自动评估心得质量，支持批量审核
- 管理员可人工审核、置顶、驳回
- 标签系统，按科目和知识点分类

### 📝 错题本
- 自动从问答反馈中收录错题
- 手动添加错题记录
- 错误原因分析（知识盲区 / 理解偏差 / 粗心 / 其他）
- 掌握状态追踪（待掌握 / 未掌握 / 已掌握）
- 智能组卷练习（按科目、掌握状态筛选）
- 复习统计与进度追踪

### 🔔 消息通知
- 心得审核结果通知（通过 / 驳回）
- 系统通知
- 已读/未读状态管理

### 📊 管理后台
- 系统仪表盘（用户数、文档数、对话数、知识点数统计）
- 按科目、文档类型的数据分布可视化
- 用户管理（CRUD、角色权限）
- 科目管理（内置科目 + 自定义科目）
- 系统配置（LLM 参数、检索参数动态调整）
- 第三方题库 API 配置

## 🛠️ 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **后端框架** | FastAPI 0.115 | Python 异步 Web 框架 |
| **ORM** | SQLAlchemy 2.0 | 数据库 ORM |
| **数据库** | MySQL 8.0 | 关系型数据存储 |
| **缓存/队列** | Redis 7 | 缓存 + Celery 消息队列 |
| **图数据库** | Neo4j 4.4 | 知识图谱存储 |
| **向量数据库** | ChromaDB 0.5.5 | 文档向量存储与语义检索 |
| **LLM** | DeepSeek (OpenAI SDK) | 对话生成 + Embedding |
| **异步任务** | Celery 5.4 | 文档解析等异步任务 |
| **前端框架** | Vue 3 + Vite | SPA 应用 |
| **UI 组件库** | Element Plus 2.4 | 桌面端 UI 组件 |
| **状态管理** | Pinia 2.1 | Vue 状态管理 |
| **可视化** | ECharts 5.5 / vis-network 7.5 | 图表 + 知识图谱渲染 |
| **数学公式** | KaTeX 0.16 | LaTeX 公式渲染 |
| **Markdown** | marked 11 | Markdown 渲染 |
| **容器化** | Docker Compose | 一键部署 |
| **反向代理** | Nginx | 前端静态资源 + API 代理 |

## 🚀 快速开始

### 环境要求

- **Docker** ≥ 20.10 且 **Docker Compose** ≥ 2.0
- 或本地安装：Python 3.10+、Node.js 18+、MySQL 8.0、Redis 7、Neo4j 4.4、ChromaDB 0.5.5

### Docker Compose 一键部署（推荐）

```bash
# 1. 克隆项目
git clone <repo-url>
cd 沛沛沛

# 2. 配置环境变量
cp docker/.env.example docker/.env
# 编辑 docker/.env，填入你的 DeepSeek API Key（必填）

# 3. 启动所有服务
cd docker
docker compose up -d

# 4. 查看服务状态
docker compose ps
```

服务启动后：
- **前端页面**：http://localhost
- **后端 API 文档（Swagger）**：http://localhost:8000/docs
- **Neo4j 控制台**：http://localhost:7474

### 本地开发部署

#### 1. 启动基础设施

```bash
# 仅启动数据库等中间件
cd docker
docker compose up -d mysql redis neo4j chromadb
```

#### 2. 后端

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 复制并配置环境变量
cp docker/.env.example .env
# 编辑 .env 文件，将服务地址改为 localhost

# 启动后端
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 3. Celery Worker

```bash
celery -A app.modules.kb.tasks worker --loglevel=info --concurrency=2
```

#### 4. 前端

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器默认运行在 `http://localhost:5173`。

## 📁 项目结构

```
├── app/                          # 后端应用
│   ├── main.py                   # FastAPI 入口，路由注册
│   ├── config.py                 # 配置管理（Pydantic Settings）
│   ├── database.py               # 数据库连接（SQLAlchemy）
│   ├── models.py                 # 数据模型定义
│   ├── common/                   # 通用模块
│   │   ├── llm_client.py         # DeepSeek LLM 客户端
│   │   ├── vector_store.py       # ChromaDB 向量存储
│   │   ├── graph_store.py        # Neo4j 图数据库操作
│   │   ├── response.py           # 统一响应格式
│   │   ├── utils.py              # 工具函数
│   │   └── parsers/              # 文档解析器
│   │       ├── pdf_parser.py     # PDF 解析
│   │       ├── docx_parser.py    # DOCX 解析
│   │       ├── pptx_parser.py    # PPTX 解析
│   │       ├── txt_parser.py     # TXT 解析
│   │       ├── md_parser.py      # Markdown 解析
│   │       ├── chunker.py        # 文档分块
│   │       └── cleaner.py        # 文本清洗
│   ├── middleware/               # 中间件
│   │   ├── auth.py               # JWT 认证
│   │   └── cors.py               # CORS 配置
│   └── modules/                  # 业务模块
│       ├── auth/                 # 认证模块
│       ├── user/                 # 用户管理
│       ├── kb/                   # 知识库模块
│       ├── qa/                   # 智能问答模块
│       │   ├── intent.py         # 意图识别
│       │   ├── retriever.py      # 检索器
│       │   ├── prompt.py         # Prompt 模板
│       │   └── service.py        # 问答服务
│       ├── kg/                   # 知识图谱模块
│       ├── notes/                # 学习心得模块
│       ├── wrong_q/              # 错题本模块
│       ├── notification/         # 消息通知模块
│       ├── dashboard/            # 仪表盘模块
│       └── system/               # 系统设置模块
├── frontend/                     # 前端应用
│   ├── src/
│   │   ├── views/                # 页面视图
│   │   │   ├── admin/            # 管理后台页面
│   │   │   │   ├── Dashboard.vue     # 仪表盘
│   │   │   │   ├── KnowledgeBase.vue # 知识库管理
│   │   │   │   ├── KnowledgeGraph.vue# 知识图谱
│   │   │   │   ├── NoteReview.vue    # 心得审核
│   │   │   │   ├── UserManage.vue    # 用户管理
│   │   │   │   ├── SubjectManage.vue # 科目管理
│   │   │   │   └── SystemConfig.vue  # 系统配置
│   │   │   └── user/             # 用户端页面
│   │   │       ├── QaChat.vue        # 智能问答
│   │   │       ├── StudyNotes.vue    # 学习心得广场
│   │   │       ├── NoteDetail.vue    # 心得详情
│   │   │       ├── NotePublish.vue   # 发布心得
│   │   │       ├── MyNotes.vue       # 我的心de
│   │   │       └── WrongQuestions.vue# 错题本
│   │   ├── api/                  # API 接口层
│   │   ├── router/               # 路由配置
│   │   ├── stores/               # Pinia 状态管理
│   │   ├── composables/          # 组合式函数
│   │   └── styles/               # 样式主题
│   └── vite.config.js            # Vite 配置
├── docker/                       # Docker 部署配置
│   ├── docker-compose.yml        # 服务编排
│   ├── Dockerfile.backend        # 后端镜像
│   ├── Dockerfile.celery         # Celery Worker 镜像
│   ├── Dockerfile.frontend       # 前端镜像
│   ├── nginx.conf                # Nginx 配置
│   ├── init.sql                  # 数据库初始化脚本
│   └── .env.example              # 环境变量模板
├── tests/                        # 测试用例
├── uploads/                      # 上传文件存储
├── requirements.txt              # Python 依赖
└── README.md                     # 项目文档
```

## 🔌 API 概览

| 模块 | 前缀 | 说明 |
|------|------|------|
| 认证 | `/api/v1/auth` | 注册、登录、Token 刷新 |
| 用户管理 | `/api/v1/admin/users` | 用户 CRUD（管理员） |
| 知识库 | `/api/v1/kb` | 文档上传、列表、删除、重新解析、检索测试 |
| 智能问答 | `/api/v1/qa` | 流式问答、对话管理、反馈提交 |
| 知识图谱 | `/api/v1/kg` | 知识点/关系 CRUD、子图查询、搜索 |
| 学习心得 | `/api/v1/notes` | 心得 CRUD、点赞收藏评论、AI 审核 |
| 错题本 | `/api/v1/wq` | 错题 CRUD、统计、组卷练习、复习 |
| 消息通知 | `/api/v1/notifications` | 通知列表、已读标记 |
| 系统管理 | `/api/v1/admin/system` | 系统配置 CRUD、日志查询 |
| 仪表盘 | `/api/v1/admin/dashboard` | 统计数据 |
| 科目管理 | `/api/v1/subjects` / `/api/v1/admin/subjects` | 科目列表、科目 CRUD |

> 启动后端后，访问 `http://localhost:8000/docs` 查看完整的 Swagger API 文档。

## ⚙️ 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（**必填**） | - |
| `DEEPSEEK_API_BASE` | DeepSeek API 地址 | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 对话模型名称 | `deepseek-v4-flash` |
| `EMBEDDING_MODEL` | Embedding 模型名称 | `deepseek-embedding` |
| `DATABASE_URL` | MySQL 连接字符串 | `mysql+pymysql://...` |
| `REDIS_HOST` | Redis 主机 | `redis` |
| `NEO4J_URI` | Neo4j Bolt 地址 | `bolt://neo4j:7687` |
| `NEO4J_USER` / `NEO4J_PASSWORD` | Neo4j 认证 | `neo4j` / `neo4j_password` |
| `CHROMA_HOST` / `CHROMA_PORT` | ChromaDB 地址 | `chromadb` / `8000` |
| `JWT_SECRET_KEY` | JWT 签名密钥 | 请修改为随机值 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token 过期时间（分钟） | `30` |

## 📊 数据库设计

核心数据实体：
- **users** — 用户（admin/user 角色）
- **subjects** — 科目（计算机网络、操作系统、数据库、机器学习等）
- **documents / document_chunks** — 文档与分块
- **exam_papers / exam_questions** — 真题试卷与题目
- **conversations / messages** — 对话与消息
- **wrong_questions** — 错题本
- **study_notes / note_comments / note_likes / note_favorites** — 学习心得社区
- **knowledge_points / knowledge_relations** — 知识点与关系
- **notifications** — 消息通知
- **system_configs / system_logs** — 系统配置与日志
- **third_party_apis** — 第三方题库 API

详见 `docker/init.sql` 完整建表脚本。

## 👥 角色与权限

| 功能 | 学生（user） | 管理员（admin） |
|------|:-----------:|:-------------:|
| 智能问答 | ✅ | ✅ |
| 浏览心得广场 | ✅ | ✅ |
| 发布/管理心得 | ✅ | ✅ |
| 错题本 | ✅ | ✅ |
| 查看通知 | ✅ | ✅ |
| 仪表盘统计 | ❌ | ✅ |
| 用户管理 | ❌ | ✅ |
| 知识库管理 | ❌ | ✅ |
| 心得审核（人工+AI） | ❌ | ✅ |
| 知识图谱管理 | ❌ | ✅ |
| 系统配置 | ❌ | ✅ |

## 🧪 开发说明

### 文档解析流程

1. 用户上传文件 → 保存至 `uploads/`
2. Celery Worker 异步解析文档（根据文件类型调用对应 Parser）
3. 文本清洗 → 智能分块（可配置大小和重叠量）
4. DeepSeek Embedding → 存入 ChromaDB
5. 解析状态回写 MySQL

### RAG 问答流程

1. 用户提问 → 意图识别（知识点 / 真题 / 心得）
2. 向量检索（ChromaDB）+ 知识图谱检索（Neo4j）
3. 构建 Prompt（System Prompt + 检索上下文 + 对话历史）
4. DeepSeek LLM 流式生成 → SSE 推送至前端
5. 记录对话历史，支持反馈收集

### 添加新的文档解析器

在 `app/common/parsers/` 中创建新的 `*_parser.py`，实现解析接口即可。现有的解析器可作为参考模板。

## 📄 License

MIT

---

**🤖 基于 DeepSeek 大模型 | 🐍 FastAPI + Vue 3 | 🐳 Docker 一键部署**
