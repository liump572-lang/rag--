# 计算机学科知识点智能问答系统部署说明

本文档说明如何部署基于 RAG 的计算机学科知识点智能问答系统。系统由 Vue 3 前端、FastAPI 后端、Celery 异步任务、MySQL、Redis、Neo4j、ChromaDB 和 Nginx 组成，推荐使用 Docker Compose 一键部署。

## 1. 环境要求

### 1.1 推荐环境

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Linux、Windows 10/11、Windows Server、macOS 均可 |
| Docker | 20.10 或以上 |
| Docker Compose | v2.0 或以上 |
| CPU | 4 核以上，推荐 8 核 |
| 内存 | 16GB 以上，推荐 32GB |
| 磁盘 | 100GB SSD 以上 |
| 网络 | 可访问 DeepSeek API |

### 1.2 本地开发环境

如果不使用 Docker 完整部署，需要本地安装：

| 组件 | 版本建议 |
| --- | --- |
| Python | 3.10 或以上 |
| Node.js | 18 或以上 |
| MySQL | 8.0 |
| Redis | 7 |
| Neo4j | 4.4.x |
| ChromaDB | 0.5.5 |

## 2. 项目结构说明

```text
.
├── app/                         # FastAPI 后端服务
│   ├── main.py                  # 应用入口
│   ├── config.py                # 环境配置
│   ├── database.py              # MySQL 数据库连接
│   ├── common/                  # LLM、向量库、图数据库、解析器等公共能力
│   ├── modules/                 # auth、kb、qa、kg、notes、wrong_q 等业务模块
│   └── tasks/                   # Celery 异步任务
├── frontend/                    # Vue 3 前端项目
├── docker/                      # Docker Compose、Nginx、初始化 SQL
├── tests/                       # 自动化测试
├── requirements.txt             # Python 依赖
└── README.md                    # 项目说明
```

## 3. Docker Compose 一键部署

### 3.1 克隆项目

```bash
git clone https://github.com/liump572-lang/rag--.git
cd rag--
```

如果仓库目录名称不同，请进入实际项目根目录。

### 3.2 配置环境变量

进入 `docker` 目录，复制环境变量模板：

```bash
cd docker
cp .env.example .env
```

Windows PowerShell 可使用：

```powershell
Copy-Item .env.example .env
```

编辑 `docker/.env`，至少修改以下配置：

```env
MYSQL_ROOT_PASSWORD=change-this-root-password
MYSQL_DATABASE=knowledge_qa_system
MYSQL_USER=qa_app
MYSQL_PASSWORD=change-this-db-password

NEO4J_AUTH=neo4j/change-this-neo4j-password
NEO4J_USER=neo4j
NEO4J_PASSWORD=change-this-neo4j-password

DEEPSEEK_API_KEY=your-deepseek-api-key-here
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-flash
EMBEDDING_MODEL=deepseek-embedding

JWT_SECRET_KEY=generate-a-random-secret-key
```

注意：

- `DEEPSEEK_API_KEY` 必须填写，否则智能问答、Embedding 和知识抽取能力无法正常调用。
- `JWT_SECRET_KEY` 生产环境必须替换为随机长字符串。
- `NEO4J_AUTH` 中的密码要和 `NEO4J_PASSWORD` 保持一致。
- `.env` 和 `docker/.env` 已被 `.gitignore` 忽略，不要提交真实密钥。

### 3.3 构建并启动服务

在 `docker` 目录执行：

```bash
docker compose up -d --build
```

首次启动会拉取 MySQL、Redis、Neo4j、ChromaDB 等镜像，并构建后端、前端和 Celery 镜像，耗时取决于网络环境。

### 3.4 查看服务状态

```bash
docker compose ps
```

正常情况下应看到以下服务处于 `running` 或 `healthy` 状态：

| 服务 | 容器名 | 说明 |
| --- | --- | --- |
| mysql | kqa-mysql | 业务关系数据库 |
| redis | kqa-redis | 缓存与 Celery 消息队列 |
| neo4j | kqa-neo4j | 知识图谱数据库 |
| chromadb | kqa-chromadb | 向量数据库 |
| backend | kqa-backend | FastAPI 后端 |
| celery-worker | kqa-celery-worker | 文档解析任务 Worker |
| celery-kg-worker | kqa-celery-kg-worker | 知识图谱抽取任务 Worker |
| frontend | kqa-frontend | Nginx 前端服务 |

### 3.5 访问地址

| 服务 | 地址 | 用途 |
| --- | --- | --- |
| 前端页面 | http://localhost | 用户端和管理端页面 |
| 后端 API 文档 | http://localhost:8000/docs | Swagger / OpenAPI 调试 |
| 后端健康检查 | http://localhost:8000/api/v1/health | 服务健康状态 |
| Neo4j 控制台 | http://localhost:7474 | 图数据库管理 |
| ChromaDB | http://localhost:8001 | 向量数据库服务 |

Neo4j 登录用户名默认为 `neo4j`，密码为 `docker/.env` 中配置的 `NEO4J_PASSWORD`。

## 4. 初始化与验证

### 4.1 检查后端健康状态

```bash
curl http://localhost:8000/api/v1/health
```

如果返回正常 JSON，说明后端服务已经启动。

### 4.2 查看日志

查看后端日志：

```bash
docker compose logs -f backend
```

查看文档解析任务日志：

```bash
docker compose logs -f celery-worker
```

查看知识图谱抽取任务日志：

```bash
docker compose logs -f celery-kg-worker
```

### 4.3 基本使用流程

1. 打开 `http://localhost`。
2. 注册或登录用户。
3. 管理员进入知识库管理页面，上传 PDF、DOCX、PPTX、TXT 或 Markdown 文档。
4. 等待文档状态变为解析成功。
5. 进入知识图谱页面，查看抽取出的知识点关系。
6. 在问答页面输入问题，系统会结合 ChromaDB 向量检索和 Neo4j 图谱检索生成回答。

## 5. 本地开发部署

本地开发时可以只用 Docker 启动基础设施，然后在宿主机运行后端和前端。

### 5.1 启动基础设施

```bash
cd docker
docker compose up -d mysql redis neo4j chromadb
```

### 5.2 后端开发

回到项目根目录：

```bash
cd ..
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux / macOS：

```bash
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

复制环境变量：

```bash
cp docker/.env.example .env
```

Windows PowerShell：

```powershell
Copy-Item docker/.env.example .env
```

本地运行后端时，需要把 `.env` 中的服务地址改为本机端口：

```env
DATABASE_URL=mysql+pymysql://qa_app:change-this-db-password@localhost:3307/knowledge_qa_system?charset=utf8mb4
REDIS_HOST=localhost
REDIS_PORT=6379
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/1
NEO4J_URI=bolt://localhost:7687
CHROMA_HOST=localhost
CHROMA_PORT=8001
UPLOAD_DIR=uploads
```

启动后端：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5.3 启动 Celery Worker

文档解析 Worker：

```bash
celery -A app.tasks.celery_app worker -l info -Q parse_queue --concurrency=4
```

知识图谱抽取 Worker：

```bash
celery -A app.tasks.celery_app worker -l info -Q kg_queue --concurrency=4
```

Windows 本地开发如果 Celery 多进程模式异常，可临时加 `--pool=solo`：

```bash
celery -A app.tasks.celery_app worker -l info -Q parse_queue --pool=solo
```

### 5.4 前端开发

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器默认地址：

```text
http://localhost:5173
```

## 6. 生产部署建议

### 6.1 安全配置

- 使用强密码替换 MySQL、Neo4j、JWT 等默认配置。
- 不要将 `.env`、`docker/.env`、API Key、数据库密码提交到仓库。
- 生产环境建议启用 HTTPS。
- 生产环境建议将 CORS 来源限制为实际域名。
- DeepSeek API Key 建议使用独立密钥，并设置额度监控。

### 6.2 数据持久化

Docker Compose 使用以下 volume 保存数据：

| Volume | 内容 |
| --- | --- |
| mysql_data | MySQL 数据 |
| redis_data | Redis 数据 |
| neo4j_data | Neo4j 图数据 |
| neo4j_logs | Neo4j 日志 |
| chromadb_data | ChromaDB 向量数据 |
| uploads_data | 用户上传文档 |

备份时至少需要备份 MySQL、Neo4j、ChromaDB 和 uploads 数据。

### 6.3 更新部署

拉取新代码：

```bash
git pull
```

重新构建并启动：

```bash
cd docker
docker compose up -d --build
```

查看是否启动成功：

```bash
docker compose ps
docker compose logs -f backend
```

## 7. 常见问题

### 7.1 后端无法连接 MySQL

检查：

- `docker compose ps mysql` 是否 healthy。
- `MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE` 是否和 `DATABASE_URL` 一致。
- 本地开发时 MySQL 端口应使用 `localhost:3307`。

### 7.2 Neo4j 登录失败

检查：

- `NEO4J_AUTH` 是否为 `neo4j/密码` 格式。
- `NEO4J_PASSWORD` 是否和 `NEO4J_AUTH` 中的密码一致。
- 如果修改了 Neo4j 密码但 volume 已初始化，旧密码可能仍然生效；开发环境可删除 volume 后重建。

### 7.3 问答无法生成或 Embedding 失败

检查：

- `DEEPSEEK_API_KEY` 是否配置。
- 服务器是否能访问 `DEEPSEEK_API_BASE`。
- 后端日志中是否有模型名称、额度或网络错误。

### 7.4 文档上传后一直解析中

检查：

- `celery-worker` 是否运行。
- Redis 是否 healthy。
- 文档格式是否支持。
- 查看日志：`docker compose logs -f celery-worker`。

### 7.5 知识图谱没有数据

检查：

- 文档是否解析成功。
- `celery-kg-worker` 是否运行。
- DeepSeek API Key 是否可用。
- 候选关系是否需要管理员审核后才写入 Neo4j。

### 7.6 前端页面打不开

检查：

- `frontend` 容器是否运行。
- 80 端口是否被其他程序占用。
- 开发模式下应访问 `http://localhost:5173`。

## 8. 停止与清理

停止服务但保留数据：

```bash
cd docker
docker compose down
```

停止服务并删除 volume 数据：

```bash
docker compose down -v
```

注意：`docker compose down -v` 会删除数据库、向量库、图数据库和上传文件数据，只建议在开发环境重置时使用。
