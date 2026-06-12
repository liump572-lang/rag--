import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.config import settings
from app.database import engine, Base, get_db
from app.common.response import error_response, success_response
from sqlalchemy import func
from app.models import Conversation, Document, KnowledgePoint, Subject, StudyNote, User, WrongQuestion
from app.middleware.auth import get_current_user
from app.modules.auth.router import router as auth_router
from app.modules.user.router import router as user_router
from app.modules.kb.router import router as kb_router
from app.modules.qa.router import router as qa_router
from app.modules.kg.router import router as kg_router
from app.modules.notes.router import router as notes_router
from app.modules.wrong_q.router import router as wrong_q_router
from app.modules.notification.router import router as notification_router
from app.modules.system.router import router as system_router

# ==================== 应用初始化 ====================

# 创建 FastAPI 应用实例，配置 Swagger 文档地址
app = FastAPI(
    title="计算机学科知识点智能问答系统",
    description="基于 RAG 架构的智能问答系统 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 跨域中间件：开发环境允许所有来源，生产环境建议限制 allow_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 路由注册 ====================
# 所有业务模块按前缀分组，统一挂载到 /api/v1 下

app.include_router(auth_router, prefix="/api/v1/auth", tags=["认证"])              # 注册、登录、Token 刷新
app.include_router(user_router, prefix="/api/v1/admin/users", tags=["用户管理"])    # 管理员：用户 CRUD
app.include_router(kb_router, prefix="/api/v1/kb", tags=["知识库"])                # 文档上传、解析、检索
app.include_router(qa_router, prefix="/api/v1/qa", tags=["智能问答"])              # RAG 流式问答、对话管理
app.include_router(kg_router, prefix="/api/v1/kg", tags=["知识图谱"])              # 知识点/关系 CRUD、图查询
app.include_router(notes_router, prefix="/api/v1/notes", tags=["学习心得"])         # 心得发布、点赞、评论、AI审核
app.include_router(wrong_q_router, prefix="/api/v1/wq", tags=["错题本"])           # 错题收录、复习、组卷
app.include_router(system_router, prefix="/api/v1/admin/system", tags=["系统设置"]) # 系统配置、日志
app.include_router(notification_router, prefix="/api/v1/notifications", tags=["消息通知"])  # 通知列表、已读管理


# ==================== 启动事件 ====================

@app.on_event("startup")
def on_startup():
    """应用启动时执行：自动建表、知识图谱 schema 迁移、触发自动重建任务"""
    # 根据 ORM 模型自动创建尚不存在的数据表
    Base.metadata.create_all(bind=engine)
    from app.common.schema_migrations import ensure_kg_schema, enqueue_auto_rebuild
    ensure_kg_schema()       # 确保 Neo4j 中知识图谱的 schema 就绪
    enqueue_auto_rebuild()   # 将知识图谱自动重建任务加入队列


# ==================== 健康检查 ====================

@app.get("/api/v1/health")
def health_check():
    """健康检查接口，供 Docker/负载均衡器探活使用"""
    return success_response(data={"status": "ok", "version": "1.0.0"})


# ==================== 科目管理（公开接口） ====================

@app.get("/api/v1/subjects")
def list_subjects(db: Session = Depends(get_db)):
    """获取所有科目列表，按 sort_order 排序"""
    subjects = db.query(Subject).order_by(Subject.sort_order).all()
    data = [{"id": s.id, "name": s.name, "description": s.description, "is_built_in": bool(s.is_built_in)} for s in subjects]
    return success_response(data=data)


# ---------- 请求体模型 ----------

class SubjectCreate(BaseModel):
    """创建科目的请求体"""
    name: str
    description: str = ""


class SubjectUpdate(BaseModel):
    """更新科目的请求体（所有字段可选，仅更新传入的字段）"""
    name: str | None = None
    description: str | None = None
    sort_order: int | None = None


# ==================== 科目管理（管理员接口） ====================

@app.post("/api/v1/admin/subjects")
def create_subject(
    body: SubjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """管理员创建新科目，名称不可重复"""
    if current_user.role != "admin":
        return error_response(403, "无权限")
    existing = db.query(Subject).filter(Subject.name == body.name).first()
    if existing:
        return error_response(400, "该科目已存在")
    max_sort = db.query(func.max(Subject.sort_order)).scalar() or 0
    subject = Subject(name=body.name, description=body.description, sort_order=max_sort + 1)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return success_response(data={"id": subject.id, "name": subject.name, "description": subject.description, "is_built_in": False})


@app.put("/api/v1/admin/subjects/{subject_id}")
def update_subject(
    subject_id: int,
    body: SubjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """管理员更新科目信息（名称、描述、排序）"""
    if current_user.role != "admin":
        return error_response(403, "无权限")
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        return error_response(404, "科目不存在")
    if body.name is not None:
        dup = db.query(Subject).filter(Subject.name == body.name, Subject.id != subject_id).first()
        if dup:
            return error_response(400, "科目名称已存在")
        subject.name = body.name
    if body.description is not None:
        subject.description = body.description
    if body.sort_order is not None:
        subject.sort_order = body.sort_order
    db.commit()
    db.refresh(subject)
    return success_response(data={"id": subject.id, "name": subject.name, "description": subject.description, "is_built_in": bool(subject.is_built_in), "sort_order": subject.sort_order})


@app.delete("/api/v1/admin/subjects/{subject_id}")
def delete_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """管理员删除科目（内置科目不可删，有文档关联时也不可删）"""
    if current_user.role != "admin":
        return error_response(403, "无权限")
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        return error_response(404, "科目不存在")
    if subject.is_built_in:
        return error_response(400, "内置科目不可删除")
    doc_count = db.query(func.count(Document.id)).filter(Document.subject_id == subject_id).scalar()
    if doc_count > 0:
        return error_response(400, f"该科目下还有 {doc_count} 个文档，请先删除或迁移")
    db.delete(subject)
    db.commit()
    return success_response(data={"id": subject_id})


# ==================== 管理后台仪表盘 ====================

@app.get("/api/v1/admin/dashboard")
def dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """管理员仪表盘：返回用户数、文档数、对话数、知识点数等统计信息及近 7 天对话趋势"""
    if current_user.role != "admin":
        return error_response(403, "无权限")
    # 各实体总数统计
    total_users = db.query(func.count(User.id)).scalar()
    total_docs = db.query(func.count(Document.id)).scalar()
    total_convs = db.query(func.count(Conversation.id)).scalar()
    total_points = db.query(func.count(KnowledgePoint.id)).scalar()
    total_notes = db.query(func.count(StudyNote.id)).scalar()
    total_wrong = db.query(func.count(WrongQuestion.id)).scalar()

    # 按科目统计文档数量分布
    docs_by_subject = (
        db.query(Subject.id, Subject.name, func.count(Document.id))
        .outerjoin(Document, Subject.id == Document.subject_id)
        .group_by(Subject.id, Subject.name)
        .order_by(Subject.sort_order)
        .all()
    )

    # 按文档类型（教材/真题/笔记/补充材料）统计数量
    docs_by_type = (
        db.query(Document.doc_type, func.count(Document.id))
        .group_by(Document.doc_type)
        .all()
    )

    # 近 7 天每日对话数量趋势
    from datetime import datetime, timedelta
    week_ago = datetime.now() - timedelta(days=7)
    recent_convs = (
        db.query(func.date(Conversation.created_at), func.count(Conversation.id))
        .filter(Conversation.created_at >= week_ago)
        .group_by(func.date(Conversation.created_at))
        .order_by(func.date(Conversation.created_at))
        .all()
    )

    return success_response(data={
        "total_users": total_users,
        "total_documents": total_docs,
        "total_conversations": total_convs,
        "total_knowledge_points": total_points,
        "total_notes": total_notes,
        "total_wrong_questions": total_wrong,
        "docs_by_subject": [{"subject_id": r[0], "name": r[1], "count": r[2]} for r in docs_by_subject],
        "docs_by_type": [{"type": r[0], "count": r[1]} for r in docs_by_type],
        "recent_conversations": [{"date": str(r[0]), "count": r[1]} for r in recent_convs],
    })


# ==================== 根路由 ====================

@app.get("/")
def root():
    """根路由，返回系统名称和 API 文档地址"""
    return {"message": "计算机学科知识点智能问答系统 API", "docs": "/docs"}


# ==================== 启动入口 ====================

if __name__ == "__main__":
    # 直接运行此文件时启动 uvicorn 开发服务器，reload=True 支持热重载
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
