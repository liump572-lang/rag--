import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.common.llm_client import chat_stream
from app.common.runtime_config import get_llm_config
from app.common.utils import sanitize_markdown
from app.database import SessionLocal
from app.models import Conversation, Message
from app.modules.qa.intent import detect_intent, is_meta_question, is_model_identity_question
from app.modules.qa.prompt import build_prompt
from app.modules.qa.retriever import fusion_rank, search_exam, search_graph, search_knowledge, search_notes

logger = logging.getLogger(__name__)


class QaService:
    HISTORY_LIMIT = 12

    @staticmethod
    def _build_reference_sources(contexts: list) -> list:
        safe_sources = []
        seen_documents = set()
        seen_entities = set()
        seen_relations = set()

        for s in (contexts or [])[:15]:
            source_type = s.get("type", "")
            if source_type == "knowledge":
                name = s.get("source", "") or "知识库文档"
                key = ("knowledge", name, s.get("content", "")[:80])
                if key in seen_documents:
                    continue
                seen_documents.add(key)
                safe_sources.append({
                    "type": "knowledge",
                    "content": s.get("content", "")[:220],
                    "source": name,
                    "score": s.get("score", 0),
                })
            elif source_type == "exam":
                key = ("exam", s.get("content", "")[:120])
                if key in seen_documents:
                    continue
                seen_documents.add(key)
                safe_sources.append({
                    "type": "exam",
                    "content": s.get("content", "")[:220],
                    "answer": s.get("answer", "")[:120],
                    "analysis": s.get("analysis", "")[:160],
                    "score": s.get("score", 0),
                    "question_type": s.get("question_type", ""),
                })
            elif source_type == "note":
                key = ("note", s.get("title", ""), s.get("user_id"))
                if key in seen_documents:
                    continue
                seen_documents.add(key)
                safe_sources.append({
                    "type": "note",
                    "content": s.get("content", "")[:220],
                    "title": s.get("title", ""),
                    "author": s.get("author", ""),
                    "user_id": s.get("user_id"),
                    "status": s.get("status", "published"),
                    "reject_reason": s.get("reject_reason", ""),
                    "score": s.get("score", 0),
                })
            elif source_type == "graph":
                node_id = s.get("node_id")
                node_name = s.get("node_name", "")
                if node_name:
                    key = node_id or node_name
                    if key not in seen_entities:
                        seen_entities.add(key)
                        safe_sources.append({
                            "type": "entity",
                            "node_id": node_id,
                            "node_name": node_name,
                            "content": s.get("content", "")[:220],
                            "score": s.get("score", 0),
                        })

                for rel in s.get("relations", [])[:5]:
                    rel_key = (
                        rel.get("source_id") or rel.get("source_name", ""),
                        rel.get("target_id") or rel.get("target_name", ""),
                        rel.get("relation_type", ""),
                    )
                    if rel_key in seen_relations:
                        continue
                    seen_relations.add(rel_key)
                    safe_sources.append({
                        "type": "relation",
                        "source_id": rel.get("source_id"),
                        "source_name": rel.get("source_name", ""),
                        "target_id": rel.get("target_id"),
                        "target_name": rel.get("target_name", ""),
                        "relation_type": rel.get("relation_type", ""),
                        "description": rel.get("description", ""),
                        "score": s.get("score", 0),
                    })

        return safe_sources[:20]

    @staticmethod
    def get_or_create_conversation(
        db: Session,
        user_id: int,
        conversation_id: Optional[int] = None,
        subject_id: Optional[int] = None,
    ) -> Conversation:
        if conversation_id:
            conv = db.query(Conversation).filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            ).first()
            if conv:
                return conv

        conv = Conversation(
            user_id=user_id,
            subject_id=subject_id,
            title="新对话",
            message_count=0,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv

    @staticmethod
    def save_message(db: Session, conversation_id: int, role: str, content: str, **kwargs) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources=kwargs.get("sources"),
            question_type=kwargs.get("question_type"),
            intent_confidence=kwargs.get("intent_confidence"),
            token_count=kwargs.get("token_count", 0),
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conv:
            conv.message_count = db.query(Message).filter(
                Message.conversation_id == conversation_id
            ).count()
            if role == "user" and (conv.title == "新对话" or conv.title == ""):
                conv.title = content[:50] if content else "新对话"
            conv.updated_at = datetime.now()
            db.commit()

        return msg

    @staticmethod
    def ask_stream(db: Session, user_id: int, question: str, conversation_id: Optional[int] = None, subject_id: Optional[int] = None):
        # Wrap setup in try/except so errors are reported via SSE, not as 500
        try:
            conv = QaService.get_or_create_conversation(db, user_id, conversation_id, subject_id)
            user_msg = QaService.save_message(db, conv.id, "user", question, question_type="knowledge")
        except Exception as e:
            logger.error("Failed to create conversation or save user message: %s", e)

            def error_gen():
                yield {"data": json.dumps({"type": "error", "content": "创建对话失败: " + str(e)}, ensure_ascii=False)}
                yield {"data": "[DONE]"}
            return error_gen, 0

        intent = detect_intent(question)

        # For meta-questions about the AI/system itself, skip RAG and answer directly
        if is_meta_question(question):
            contexts = []
        else:
            try:
                knowledge_results = search_knowledge(db, question, subject_id=subject_id)
                exam_results = search_exam(db, question, subject_id=subject_id) if intent in ("exam", "knowledge") else []
                note_results = search_notes(db, question, subject_id=subject_id, current_user_id=user_id) if intent in ("note",) else []
                graph_results = search_graph(question, subject_id=subject_id)
                contexts = fusion_rank(knowledge_results, exam_results, note_results, graph_results, intent, subject_id)
            except Exception as e:
                logger.warning("Search failed, falling back to direct answer: %s", e)
                contexts = []

        history_rows = db.query(Message).filter(
            Message.conversation_id == conv.id,
            Message.id < user_msg.id,
            Message.role.in_(("user", "assistant")),
        ).order_by(Message.id.desc()).limit(QaService.HISTORY_LIMIT).all()
        history = [
            {"role": row.role, "content": row.content}
            for row in reversed(history_rows)
        ]
        messages = build_prompt(intent, question, contexts, history=history)

        # 从 system_configs（DB）解析一次 LLM 运行时配置（此刻请求 db 仍打开），env 兜底；
        # 流式生成时直接复用解析结果，避免会话关闭后再查库。
        llm_cfg = get_llm_config(db)
        model_name = llm_cfg.model
        identity_answer = None
        if is_model_identity_question(question):
            identity_answer = (
                f"当前问答服务配置的 API 模型是 **{model_name}**。\n\n"
                "该名称来自系统控制页面保存的服务端配置，并会作为下一次提问请求中的 "
                "`model` 参数发送给所配置的大模型 API。模型自行生成的版本描述可能受训练语料限制，"
                "不应作为实际运行配置的判断依据。"
            )

        def generate():
            collected_content = ""
            collected_reasoning = ""
            stream_error = None

            try:
                if identity_answer:
                    collected_content = identity_answer
                    yield {"data": json.dumps({"type": "token", "content": identity_answer}, ensure_ascii=False)}
                else:
                    stream = chat_stream(
                        messages,
                        model=llm_cfg.model,
                        api_key=llm_cfg.api_key,
                        api_base=llm_cfg.api_url,
                    )
                    for chunk in stream:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            collected_content += delta.content
                            yield {"data": json.dumps({"type": "token", "content": delta.content}, ensure_ascii=False)}
                        elif hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                            collected_reasoning += delta.reasoning_content

            except Exception as e:
                stream_error = str(e)
                yield {"data": json.dumps({"type": "error", "content": stream_error}, ensure_ascii=False)}

            # Always save assistant message — use a fresh DB session because the
            # dependency-injected session may have been closed during long streaming.
            save_db = SessionLocal()
            try:
                if not collected_content and collected_reasoning:
                    collected_content = collected_reasoning

                cleaned = sanitize_markdown(collected_content) if collected_content else ""
                if stream_error:
                    cleaned += "\n\n> [回答中断：" + stream_error + "]"
                final_content = cleaned.strip() or "(模型未返回有效回答)"

                safe_sources = QaService._build_reference_sources(contexts)

                assistant_msg = QaService.save_message(
                    save_db, conv.id, "assistant", final_content,
                    sources=safe_sources,
                    question_type=intent,
                )

                yield {"data": json.dumps({"type": "done", "conversation_id": conv.id, "message_id": assistant_msg.id, "subject_id": conv.subject_id, "sources": safe_sources, "question_type": intent}, ensure_ascii=False)}

            except Exception as save_err:
                logger.error("Failed to save assistant message for conv %s: %s", conv.id, save_err)
                yield {"data": json.dumps({"type": "error", "content": "保存消息失败: " + str(save_err)}, ensure_ascii=False)}
            finally:
                save_db.close()

            yield {"data": "[DONE]"}

        return generate, conv.id

    @staticmethod
    def list_conversations(db: Session, user_id: int, page: int = 1, size: int = 20):
        query = db.query(Conversation).filter(Conversation.user_id == user_id)
        total = query.count()
        items = query.order_by(Conversation.updated_at.desc()).offset((page - 1) * size).limit(size).all()
        return items, total

    @staticmethod
    def get_messages(db: Session, conversation_id: int, user_id: int):
        conv = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if not conv:
            return None, []
        msgs = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at).all()
        return conv, msgs

    @staticmethod
    def delete_conversation(db: Session, conversation_id: int, user_id: int) -> bool:
        conv = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if not conv:
            return False
        db.query(Message).filter(Message.conversation_id == conversation_id).delete()
        db.delete(conv)
        db.commit()
        return True

    @staticmethod
    def submit_feedback(db: Session, message_id: int, user_id: int, score: int):
        msg = db.query(Message).filter(
            Message.id == message_id,
            Message.role == "assistant",
        ).join(Conversation, Message.conversation_id == Conversation.id).filter(
            Conversation.user_id == user_id,
        ).first()
        if not msg:
            return None
        msg.feedback_score = score
        db.commit()
        db.refresh(msg)
        return msg
