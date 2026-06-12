from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.response import error_response, paginated_response, success_response
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import Subject, User
from app.common.llm_client import chat
from app.modules.notes.schemas import (
    AiReviewResponse,
    BatchReviewInput,
    CommentCreate,
    CommentResponse,
    NoteCreate,
    NoteResponse,
    NoteUpdate,
    ReviewInput,
)
from app.modules.notes.service import NotesService

router = APIRouter()


@router.get("")
def list_notes(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    subject_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    only_published = not (user_id and user_id == current_user.id)
    items, total = NotesService.list_notes(db, page, size, subject_id, keyword, only_published=only_published, user_id=user_id)
    data = [_format_note_row(r) for r in items]
    return paginated_response(data, total, page, size)


@router.get("/my-counts")
def get_my_counts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    counts = NotesService.get_my_counts(db, current_user.id)
    return success_response(data=counts)


@router.get("/{note_id}/status")
def get_note_status(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = NotesService.get_note(db, note_id)
    if not note:
        return error_response(404, "心得不存在")
    if note.user_id != current_user.id and current_user.role != "admin":
        return error_response(403, "无权查看")
    return success_response(data={
        "id": note.id,
        "status": note.status,
        "reject_reason": note.reject_reason,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    })


@router.get("/{note_id}")
def get_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = NotesService.get_note(db, note_id)
    if not note:
        return error_response(404, "心得不存在")
    if note.status != "published" and note.user_id != current_user.id and current_user.role != "admin":
        return error_response(403, "无权查看")
    return success_response(data=NoteResponse.model_validate(note).model_dump())


@router.post("")
def create_note(
    body: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "user":
        return error_response(403, "仅学生可发布心得")
    note = NotesService.create_note(db, current_user.id, body.subject_id, body.title, body.content, body.tags)
    return success_response(data=NoteResponse.model_validate(note).model_dump())


@router.put("/{note_id}")
def update_note(
    note_id: int,
    body: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = NotesService.update_note(db, note_id, current_user.id, body.title, body.content, body.tags)
    if not note:
        return error_response(404, "心得不存在或无权限")
    return success_response(data=NoteResponse.model_validate(note).model_dump())


@router.delete("/{note_id}")
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ok = NotesService.delete_note(db, note_id, current_user.id, current_user.role == "admin")
    if not ok:
        return error_response(404, "心得不存在")
    return success_response(message="已删除")


@router.post("/{note_id}/like")
def toggle_like(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    action, count = NotesService.toggle_field(db, note_id, current_user.id, "like")
    if action is None:
        return error_response(404, "心得不存在")
    return success_response(data={"liked": action == "added", "count": count})


@router.post("/{note_id}/favorite")
def toggle_favorite(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    action, count = NotesService.toggle_field(db, note_id, current_user.id, "favorite")
    if action is None:
        return error_response(404, "心得不存在")
    return success_response(data={"favorited": action == "added", "count": count})


@router.get("/{note_id}/comments")
def get_comments(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comments = NotesService.get_comments(db, note_id)
    data = [CommentResponse.model_validate(c).model_dump() for c in comments]
    return success_response(data=data)


@router.post("/{note_id}/comments")
def add_comment(
    note_id: int,
    body: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = NotesService.add_comment(db, note_id, current_user.id, body.content)
    if not comment:
        return error_response(404, "心得不存在")
    return success_response(data=CommentResponse.model_validate(comment).model_dump())


@router.get("/admin/review")
def list_review(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str = Query("pending"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    items, total = NotesService.list_notes(db, page, size, status=status, only_published=False)
    data = [_format_note_row(r) for r in items]
    return paginated_response(data, total, page, size)


@router.post("/admin/review/ai-all")
def ai_review_all_pending(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    try:
        results = NotesService.ai_review_all_pending(db)
        msg = f"AI审核完成：通过 {results['approved']} 篇，驳回 {results['rejected']} 篇"
        if results["failed"]:
            msg += f"，{results['failed']} 篇失败"
        return success_response(data=results, message=msg)
    except Exception as e:
        return error_response(500, f"AI批量审核出错：{str(e)}")


@router.post("/admin/review/batch")
def batch_review(
    body: BatchReviewInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    results = NotesService.batch_review(db, body.ids, body.action, body.reject_reason)
    return success_response(data=results)


@router.post("/admin/review/{note_id}")
def review_note(
    note_id: int,
    body: ReviewInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    note = NotesService.review_note(db, note_id, body.action, body.reject_reason)
    if not note:
        return error_response(404, "心得不存在")
    return success_response(data=NoteResponse.model_validate(note).model_dump())


@router.post("/admin/pin/{note_id}")
def toggle_pin(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")
    note = NotesService.toggle_pin(db, note_id)
    if not note:
        return error_response(404, "心得不存在")
    return success_response(data=NoteResponse.model_validate(note).model_dump())


@router.post("/admin/ai-review/{note_id}")
def ai_review_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        return error_response(403, "无权限")

    note = NotesService.get_note(db, note_id)
    if not note:
        return error_response(404, "心得不存在")

    subject = db.query(Subject).filter(Subject.id == note.subject_id).first()
    subject_name = subject.name if subject else "未知"

    prompt = f"""你是一个学习心得审核助手。请根据以下心得内容，判断是否应该通过审核。

审核标准：
1. 内容是否与学习相关，是否属于有效的学习心得
2. 内容质量是否合格（有实际学习内容，不是无意义文字）
3. 语言表达是否清晰、专业
4. 是否有违规内容（广告、政治敏感、人身攻击等）

心得标题：{note.title}
所属科目：{subject_name}
心得作者ID：{note.user_id}
心得内容：
{note.content[:3000]}

请给出审核建议，严格按照以下JSON格式返回：
{{
  "suggested_action": "approve" 或 "reject",
  "confidence": 0-1之间的小数,
  "reasons": ["理由1", "理由2"],
  "quality_score": 1-10之间的整数评分,
  "summary": "对心得的简要评价"
}}"""

    try:
        response = chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是一个严格但公平的心得审核助手，只返回纯JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1024,
        )

        import json, re
        match = re.search(r"\{.*\}", response, re.DOTALL)
        data = json.loads(match.group()) if match else None

        if not data:
            return error_response(500, "AI审核失败，无法解析结果")

        return success_response(data=AiReviewResponse(
            suggested_action=data.get("suggested_action", "reject"),
            confidence=data.get("confidence", 0.5),
            reasons=data.get("reasons", []),
            quality_score=data.get("quality_score", 5),
            summary=data.get("summary", ""),
        ).model_dump())

    except Exception as e:
        return error_response(500, f"AI审核出错：{str(e)}")


def _format_note_row(r):
    d = {
        "id": r.id, "user_id": r.user_id, "subject_id": r.subject_id,
        "title": r.title, "content": r.content, "tags": r.tags,
        "status": r.status, "is_pinned": bool(r.is_pinned),
        "like_count": r.like_count, "favorite_count": r.favorite_count,
        "comment_count": r.comment_count,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        "username": r.username,
    }
    return d
