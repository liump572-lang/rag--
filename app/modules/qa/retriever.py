import re
from typing import List, Optional

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.common.graph_store import run_query, search_nodes as neo4j_search_nodes
from app.common.vector_store import search_chunks as chroma_search


def _extract_keywords(query: str) -> List[str]:
    """Extract potential search keywords from query."""
    keywords = []
    eng_words = re.findall(r'[A-Za-z][A-Za-z+./_#-]{1,}', query)
    keywords.extend(w.strip('./_#-') for w in eng_words)
    cn_terms = re.findall(r'[一-鿿]{2,}', query)
    keywords.extend(cn_terms)
    if not keywords:
        keywords = [query]
    return keywords


def _extract_entity_names(db: Session, query: str, subject_id: Optional[int] = None) -> set:
    """Extract entity names from query by matching against known knowledge points."""
    keywords = _extract_keywords(query)
    if not keywords:
        return set()

    entity_names = set()
    for kw in keywords:
        q = db.query(
            sql_text("""
                SELECT name FROM knowledge_points
                WHERE name LIKE :kw
            """)
        ).params(kw=f"%{kw}%")
        if subject_id:
            q = q.params(subject_id=subject_id)

    # Use ORM query instead for compatibility
    from app.models import KnowledgePoint
    for kw in keywords:
        kq = db.query(KnowledgePoint.name)
        if subject_id:
            kq = kq.filter(KnowledgePoint.subject_id == subject_id)
        rows = kq.filter(KnowledgePoint.name.like(f"%{kw}%")).limit(10).all()
        for row in rows:
            entity_names.add(row.name)

    return entity_names


def _boost_by_entity_hits(results: List[dict], entity_names: set) -> List[dict]:
    """Boost scores for chunks that contain recognized entity names."""
    if not entity_names:
        return results

    for r in results:
        content = r.get("content", "")
        hit_count = sum(1 for name in entity_names if name in content)
        if hit_count > 0:
            boost = 1.0 + min(hit_count * 0.1, 0.5)
            r["score"] = round(r.get("score", 0.5) * boost, 4)
            r["entity_hits"] = hit_count

    return results


def search_knowledge(
    db: Session,
    query: str,
    subject_id: Optional[int] = None,
    top_k: int = 10,
) -> List[dict]:
    """Search knowledge base with entity-aware boosting."""
    # Primary: vector search
    chroma_results = chroma_search(query, top_k=top_k, db=db)

    # Extract entities from query for boosting
    entity_names = _extract_entity_names(db, query, subject_id)
    chroma_results = _boost_by_entity_hits(chroma_results, entity_names)

    # Supplement with full-text search from DB
    if subject_id:
        sql_results = db.execute(
            sql_text("""
                SELECT dc.id, dc.content, dc.chunk_index, d.title as doc_title
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.subject_id = :sid AND d.parse_status = 'success'
                ORDER BY dc.chunk_index
                LIMIT :limit
            """),
            {"sid": subject_id, "limit": top_k},
        ).fetchall()

        seen_ids = {r["id"] for r in chroma_results}
        for row in sql_results:
            if row.id not in seen_ids:
                chroma_results.append({
                    "id": row.id,
                    "content": row.content,
                    "metadata": {"document_id": None, "chunk_index": row.chunk_index},
                    "score": 0.45,
                    "doc_title": row.doc_title,
                })

    # Enrich with document titles
    for r in chroma_results:
        if "doc_title" not in r:
            doc = db.execute(
                sql_text("SELECT title FROM documents WHERE id = :did"),
                {"did": r["metadata"].get("document_id")},
            ).fetchone()
            r["doc_title"] = doc.title if doc else ""

    # Boost by entity hits again for the merged results
    if entity_names:
        chroma_results = _boost_by_entity_hits(chroma_results, entity_names)

    return chroma_results


def search_exam(
    db: Session,
    query: str,
    subject_id: Optional[int] = None,
    top_k: int = 5,
) -> List[dict]:
    conditions: list[str] = ["1=1"]
    params = {"limit": top_k, "query": f"%{query}%"}

    if subject_id:
        conditions.append("ep.subject_id = :sid")
        params["sid"] = subject_id

    where_clause = " AND ".join(conditions)
    rows = db.execute(
        sql_text(f"""
            SELECT eq.id, eq.content, eq.answer, eq.analysis, eq.question_type,
                   eq.difficulty, eq.knowledge_points, ep.year, ep.title as paper_title
            FROM exam_questions eq
            JOIN exam_papers ep ON eq.exam_paper_id = ep.id
            WHERE {where_clause} AND (eq.content LIKE :query OR eq.analysis LIKE :query2)
            ORDER BY eq.difficulty
            LIMIT :limit
        """),
        {**params, "query2": f"%{query}%"},
    ).fetchall()

    return [dict(row._mapping) for row in rows]


def search_notes(
    db: Session,
    query: str,
    subject_id: Optional[int] = None,
    top_k: int = 5,
    current_user_id: Optional[int] = None,
) -> List[dict]:
    conditions = []
    params = {"limit": top_k, "query": f"%{query}%"}

    if current_user_id:
        conditions.append("(sn.status = 'published' OR sn.user_id = :uid)")
        params["uid"] = current_user_id
    else:
        conditions.append("sn.status = 'published'")

    if subject_id:
        conditions.append("sn.subject_id = :sid")
        params["sid"] = subject_id

    where_clause = " AND ".join(conditions)
    rows = db.execute(
        sql_text(f"""
            SELECT sn.id, sn.title, sn.content, sn.tags, sn.like_count,
                   sn.favorite_count, sn.user_id, sn.status, sn.reject_reason, u.username
            FROM study_notes sn
            JOIN users u ON sn.user_id = u.id
            WHERE {where_clause} AND (sn.title LIKE :query OR sn.content LIKE :query2)
            ORDER BY sn.like_count DESC
            LIMIT :limit
        """),
        {**params, "query2": f"%{query}%"},
    ).fetchall()

    return [dict(row._mapping) for row in rows]


def search_graph(
    query: str,
    subject_id: Optional[int] = None,
    top_k: int = 5,
) -> List[dict]:
    """Search knowledge graph with neighborhood context."""
    results = []
    seen_ids = set()
    keywords = _extract_keywords(query)

    try:
        matched_nodes = []
        for kw in keywords:
            nodes = neo4j_search_nodes(kw, subject_id)
            for node in nodes:
                nid = node["id"]
                if nid not in seen_ids:
                    seen_ids.add(nid)
                    matched_nodes.append(node)
            if len(matched_nodes) >= top_k * 2:
                break

        if not matched_nodes:
            return []

        # Batch query for neighbors
        node_ids = [n["id"] for n in matched_nodes[:top_k * 2]]
        all_neighbors = run_query(
            """
            MATCH (n:KnowledgePoint)-[r]-(m:KnowledgePoint)
            WHERE n.id IN $ids
            RETURN n.id as node_id,
                   n.name as node_name,
                   m.id as neighbor_id,
                   m.name as neighbor_name,
                   r.type as relation_type,
                   coalesce(r.description, '') as description,
                   startNode(r).id as source_id,
                   startNode(r).name as source_name,
                   endNode(r).id as target_id,
                   endNode(r).name as target_name
            LIMIT 50
            """,
            {"ids": node_ids},
        )

        neighbor_map = {}
        relation_map = {}
        for row in all_neighbors:
            nid = row["node_id"]
            if nid not in neighbor_map:
                neighbor_map[nid] = []
                relation_map[nid] = []
            neighbor_map[nid].append(f"{row['neighbor_name']}({row['relation_type']})")
            relation_map[nid].append({
                "source_id": row.get("source_id"),
                "source_name": row.get("source_name", ""),
                "target_id": row.get("target_id"),
                "target_name": row.get("target_name", ""),
                "relation_type": row.get("relation_type", ""),
                "description": row.get("description", ""),
            })

        for node in matched_nodes[:top_k]:
            nid = node["id"]
            node_name = node["name"]
            neighbors = neighbor_map.get(nid, [])
            relations = relation_map.get(nid, [])
            context = f"知识点：{node_name}"
            if neighbors:
                context += f"；关联知识点：{', '.join(neighbors[:8])}"
            if relations:
                relation_text = "；".join(
                    f"{rel['source_name']} -[{rel['relation_type']}]-> {rel['target_name']}"
                    for rel in relations[:5]
                )
                context += f"；参考关系：{relation_text}"

            results.append({
                "type": "graph",
                "content": context,
                "node_id": nid,
                "node_name": node_name,
                "neighbors": neighbors,
                "relations": relations[:8],
                "score": 0.55,
            })

    except Exception:
        pass

    return results[:top_k]


def fusion_rank(
    knowledge_results: List[dict],
    exam_results: List[dict],
    note_results: List[dict],
    graph_results: List[dict],
    intent: str,
    subject_id: Optional[int] = None,
) -> List[dict]:
    """Fuse and rank results from multiple sources with entity-aware scoring."""
    results = []

    # Knowledge results (primary)
    for r in knowledge_results:
        score = r.get("score", 0.5)
        if score < 0.30:
            continue
        # Extra boost for entity hits
        entity_hits = r.get("entity_hits", 0)
        if entity_hits:
            score *= (1.0 + min(entity_hits * 0.08, 0.4))

        content = r.get("content", "")
        if not content or len(content) < 5:
            continue

        results.append({
            "type": "knowledge",
            "content": content,
            "source": r.get("doc_title", ""),
            "score": round(score, 4),
        })

    # Graph results - boost if we have entity matches
    for r in graph_results:
        score = r.get("score", 0.55) * 0.7
        if score < 0.25:
            continue
        # Graph results with direct entity matches are more valuable
        results.append({
            "type": "graph",
            "content": r["content"],
            "node_id": r.get("node_id"),
            "node_name": r.get("node_name", ""),
            "neighbors": r.get("neighbors", []),
            "relations": r.get("relations", []),
            "score": round(score, 4),
        })

    # Exam results
    if intent == "exam":
        for r in exam_results:
            score = 0.30
            if r.get("difficulty"):
                score += (6 - r["difficulty"]) * 0.02
            results.append({
                "type": "exam",
                "content": r.get("content", ""),
                "answer": r.get("answer", ""),
                "analysis": r.get("analysis", ""),
                "score": round(score, 4),
                "question_type": r.get("question_type", ""),
            })

    # Note results
    if intent == "note":
        for r in note_results:
            score = 0.30
            if r.get("like_count"):
                score += min(r["like_count"] * 0.01, 0.05)
            results.append({
                "type": "note",
                "content": r.get("content", ""),
                "title": r.get("title", ""),
                "author": r.get("username", ""),
                "user_id": r.get("user_id"),
                "status": r.get("status", "published"),
                "reject_reason": r.get("reject_reason", ""),
                "score": round(score, 4),
            })

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)

    # Deduplicate by content prefix
    seen = set()
    unique_results = []
    for r in results:
        key = r["content"][:120]
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    return unique_results[:15]
