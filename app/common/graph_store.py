from typing import Optional

from neo4j import GraphDatabase

from app.config import settings


_driver = None


def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


def run_query(query: str, params: dict = None):
    with get_driver().session() as session:
        result = session.run(query, params or {})
        return [r.data() for r in result]


def create_node(node_id: int, name: str, subject_id: int, labels: list = None) -> dict:
    results = run_query(
        """
        MERGE (n:KnowledgePoint {id: $id})
        SET n.name = $name, n.subject_id = $subject_id
        RETURN n.id as id, n.name as name, n.subject_id as subject_id
        """,
        {"id": node_id, "name": name, "subject_id": subject_id},
    )
    return results[0] if results else {}


def update_node(node_id: int, name: str = None, description: str = None) -> bool:
    sets = []
    params = {"id": node_id}
    if name is not None:
        sets.append("n.name = $name")
        params["name"] = name
    if description is not None:
        sets.append("n.description = $description")
        params["description"] = description
    if not sets:
        return False
    set_clause = ", ".join(sets)
    run_query(f"MATCH (n:KnowledgePoint {{id: $id}}) SET {set_clause} RETURN n", params)
    return True


def delete_node(node_id: int) -> bool:
    run_query(
        "MATCH (n:KnowledgePoint {id: $id}) DETACH DELETE n",
        {"id": node_id},
    )
    return True


def create_relation(
    source_id: int, target_id: int, rel_type: str,
    description: str = None,
) -> dict:
    results = run_query(
        """
        MATCH (a:KnowledgePoint {id: $source_id})
        MATCH (b:KnowledgePoint {id: $target_id})
        MERGE (a)-[r:RELATED {type: $rel_type}]->(b)
        SET r.type = $rel_type
        SET r.description = $description
        RETURN id(r) as rel_id, a.id as source_id, b.id as target_id, r.type as type
        """,
        {"source_id": source_id, "target_id": target_id, "rel_type": rel_type, "description": description or ""},
    )
    return results[0] if results else {}


def delete_relation(source_id: int, target_id: int, rel_type: str) -> bool:
    run_query(
        """
        MATCH (a:KnowledgePoint {id: $source_id})-[r:RELATED {type: $rel_type}]->(b:KnowledgePoint {id: $target_id})
        DELETE r
        """,
        {"source_id": source_id, "target_id": target_id, "rel_type": rel_type},
    )
    return True


def _node_payload(node: dict) -> dict:
    return {
        "id": node["id"],
        "label": node.get("name", ""),
        "subject_id": node.get("subject_id"),
        "group": str(node.get("subject_id", 0)),
    }


def _edge_payload(edge: dict) -> dict:
    payload = {
        "from": edge["source"],
        "to": edge["target"],
        "label": edge.get("type", ""),
        "title": edge.get("description", "") or edge.get("type", ""),
        "description": edge.get("description", ""),
    }
    edge_id = edge.get("id") or edge.get("rel_id")
    if edge_id is not None:
        payload["id"] = edge_id
    neo4j_rel_id = edge.get("neo4j_rel_id")
    if neo4j_rel_id is not None:
        payload["neo4j_rel_id"] = neo4j_rel_id
    return payload


def get_subgraph(subject_id: int = None, depth: int = 2) -> dict:
    node_query = "MATCH (n:KnowledgePoint)"
    params = {}
    if subject_id:
        node_query += " WHERE n.subject_id = $subject_id"
        params["subject_id"] = subject_id
    node_query += " RETURN n.id as id, n.name as name, n.subject_id as subject_id"

    edge_query = "MATCH (a:KnowledgePoint)-[r:RELATED]->(b:KnowledgePoint)"
    if subject_id:
        edge_query += " WHERE a.subject_id = $subject_id AND b.subject_id = $subject_id"
    edge_query += """
        RETURN id(r) as neo4j_rel_id,
               a.id as source, a.name as source_name, a.subject_id as source_subject_id,
               b.id as target, b.name as target_name, b.subject_id as target_subject_id,
               r.type as type, r.description as description
    """

    nodes = {_node["id"]: _node_payload(_node) for _node in run_query(node_query, params)}
    edges = []
    seen = set()
    for edge in run_query(edge_query, params):
        key = (edge.get("source"), edge.get("target"), edge.get("type", ""))
        if None not in key and key not in seen:
            seen.add(key)
            nodes[edge["source"]] = _node_payload({
                "id": edge["source"], "name": edge["source_name"], "subject_id": edge["source_subject_id"],
            })
            nodes[edge["target"]] = _node_payload({
                "id": edge["target"], "name": edge["target_name"], "subject_id": edge["target_subject_id"],
            })
            edges.append(_edge_payload(edge))
    return {"nodes": list(nodes.values()), "edges": edges}


def search_nodes(keyword: str, subject_id: int = None) -> list:
    keyword = keyword.strip()
    if not keyword:
        return []
    conditions = ["n.name CONTAINS $keyword"]
    params = {"keyword": keyword}
    if subject_id:
        conditions.append("n.subject_id = $subject_id")
        params["subject_id"] = subject_id

    where_clause = " AND ".join(conditions)
    query = f"""
        MATCH (n:KnowledgePoint)
        WHERE {where_clause}
        RETURN n.id as id, n.name as name, n.subject_id as subject_id
        LIMIT 20
    """
    return run_query(query, params)


def get_search_subgraph(keyword: str, subject_id: int = None, depth: int = 1) -> dict:
    keyword = keyword.strip()
    if not keyword:
        return {"nodes": [], "edges": []}

    params = {"keyword": keyword}
    node_conditions = ["n.name CONTAINS $keyword"]
    if subject_id:
        node_conditions.append("n.subject_id = $subject_id")
        params["subject_id"] = subject_id
    node_where = " AND ".join(node_conditions)

    matched_nodes = run_query(f"""
        MATCH (n:KnowledgePoint)
        WHERE {node_where}
        RETURN n.id as id, n.name as name, n.subject_id as subject_id
        LIMIT 50
    """, params)

    if matched_nodes:
        return {
            "nodes": [_node_payload(node) for node in matched_nodes],
            "edges": [],
        }

    relation_conditions = [
        "(r.type CONTAINS $keyword OR coalesce(r.description, '') CONTAINS $keyword)"
    ]
    if subject_id:
        relation_conditions.append("a.subject_id = $subject_id AND b.subject_id = $subject_id")
    relation_where = " AND ".join(relation_conditions)
    matched_edges = run_query(f"""
        MATCH (a:KnowledgePoint)-[r:RELATED]->(b:KnowledgePoint)
        WHERE {relation_where}
        RETURN DISTINCT a.id as source, a.name as source_name, a.subject_id as source_subject_id,
                        b.id as target, b.name as target_name, b.subject_id as target_subject_id,
                        r.type as type, r.description as description,
                        id(r) as neo4j_rel_id
        LIMIT 100
    """, params)

    nodes_map = {}
    for node in matched_nodes:
        nodes_map[node["id"]] = _node_payload(node)

    edges = []
    seen_edges = set()
    for edge in matched_edges:
        nodes_map[edge["source"]] = _node_payload({
            "id": edge["source"], "name": edge["source_name"], "subject_id": edge["source_subject_id"],
        })
        nodes_map[edge["target"]] = _node_payload({
            "id": edge["target"], "name": edge["target_name"], "subject_id": edge["target_subject_id"],
        })
        key = (edge.get("source"), edge.get("target"), edge.get("type", ""), edge.get("description", ""))
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append(_edge_payload(edge))

    return {
        "nodes": list(nodes_map.values()),
        "edges": edges,
    }


def close():
    global _driver
    if _driver:
        _driver.close()
        _driver = None
