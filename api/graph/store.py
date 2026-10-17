"""FalkorDB access: fixed labels, parameterized properties, bounded read templates."""

import hashlib
import json
import time
from functools import lru_cache

from falkordb import FalkorDB
from redis.exceptions import ResponseError

from api.config import settings
from api.graph.limits import MAX_EDGES, MAX_NODES, check_graph_budget
from api.services.telemetry import record_graph_read

NODE_TYPES = {
    "Repository",
    "Branch",
    "File",
    "Function",
    "Class",
    "Commit",
    "PullRequest",
    "Issue",
    "WorkflowRun",
    "TestCase",
    "LogArtifact",
    "Decision",
}
EDGE_TYPES = {
    "HAS_FILE",
    "DEFINES",
    "CALLS",
    "IMPORTS",
    "CONTAINS_COMMIT",
    "MODIFIES",
    "REFERENCES",
    "ADDRESSES",
    "TRIGGERED_BY",
    "TESTS",
    "PRODUCES",
    "RELATED_TO",
    "SUPERSEDES",
}


@lru_cache
def client():
    cfg = settings()
    if cfg.falkor_socket:
        return FalkorDB(unix_socket_path=cfg.falkor_socket, socket_timeout=10)
    return FalkorDB(
        host=cfg.falkor_host,
        port=cfg.falkor_port,
        password=cfg.falkor_password or None,
        socket_timeout=10,
    )


def graph_name(repo_id, branch, revision):
    suffix = hashlib.sha256(f"{branch}\0{revision}".encode()).hexdigest()[:24]
    return f"gp_{repo_id.replace('-', '')}_{suffix}"


def query(name, cypher, params=None, readonly=True):
    graph = client().select_graph(name)
    method = graph.ro_query if readonly else graph.query
    started = time.perf_counter()
    success = False
    try:
        result = method(cypher, params=params or {}, timeout=3000).result_set
        success = True
        return result
    finally:
        if readonly:
            record_graph_read((time.perf_counter() - started) * 1000, success)


def encode_node(node):
    return dict(node.properties)


def edge_dict(edge):
    return dict(edge.properties)


def create_graph(name: str, nodes: list[dict], edges: list[dict]):
    check_graph_budget(nodes, edges)
    graph = client().select_graph(name)
    for key in ["id", "name", "path"]:
        graph.query(f"CREATE INDEX FOR (n:Entity) ON (n.{key})")
    for kind in sorted(NODE_TYPES):
        batch = [dict(n) for n in nodes if n["type"] == kind]
        for start in range(0, len(batch), 200):
            graph.query(
                f"UNWIND $rows AS row CREATE (n:Entity:{kind}) SET n = row",
                {"rows": batch[start : start + 200]},
            )
    for kind in sorted(EDGE_TYPES):
        rows = []
        for edge in edges:
            if edge["type"] != kind:
                continue
            key = json.dumps([edge["source"], edge["target"], kind, edge.get("line", 0)])
            rows.append({**edge, "id": hashlib.sha256(key.encode()).hexdigest()[:32]})
        for start in range(0, len(rows), 200):
            graph.query(
                f"UNWIND $rows AS row MATCH (a:Entity {{id:row.source}}),(b:Entity {{id:row.target}}) CREATE (a)-[r:{kind}]->(b) SET r = row",
                {"rows": rows[start : start + 200]},
            )
    actual = query(name, "MATCH (n:Entity) RETURN count(n)")[0][0]
    if actual != len(nodes):
        raise RuntimeError("Graph node validation failed")


def delete_graph(name):
    if name in client().list_graphs():
        client().select_graph(name).delete()


def subgraph(name: str, limit=100, kind=None, term="", relation=""):
    rows = query(
        name,
        "MATCH (n:Entity) WHERE ($kind = '' OR n.type = $kind) AND ($term = '' OR toLower(n.name) CONTAINS $term OR toLower(n.path) CONTAINS $term) RETURN n ORDER BY n.type,n.name LIMIT $limit",
        {"kind": kind or "", "term": term.lower(), "limit": limit},
    )
    nodes = [encode_node(row[0]) for row in rows]
    ids = [n["id"] for n in nodes]
    edges = (
        query(
            name,
            "MATCH (a:Entity)-[r]->(b:Entity) WHERE a.id IN $ids AND b.id IN $ids AND ($relation = '' OR type(r) = $relation) RETURN r LIMIT 500",
            {"ids": ids, "relation": relation},
        )
        if ids
        else []
    )
    return {
        "nodes": nodes,
        "edges": [edge_dict(row[0]) for row in edges],
        "limit": limit,
        "bounded": True,
    }


def find_node(name, node_id):
    rows = query(name, "MATCH (n:Entity {id:$id}) RETURN n LIMIT 1", {"id": node_id})
    return encode_node(rows[0][0]) if rows else None


def neighbors(name, node_id, limit=50, relation=None):
    if relation and relation not in EDGE_TYPES:
        raise ValueError("Unsupported relationship filter")
    rel = f":{relation}" if relation else ""
    rows = query(
        name,
        f"MATCH (a:Entity {{id:$id}})-[r{rel}]-(b:Entity) RETURN a,r,b LIMIT $limit",
        {"id": node_id, "limit": limit},
    )
    nodes, edges = {}, {}
    for a, r, b in rows:
        for n in [a, b]:
            nodes[n.properties["id"]] = encode_node(n)
        edge = edge_dict(r)
        edges[edge["id"]] = edge
    return {
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "bounded": True,
        "limit": limit,
    }


def search(name, term, limit=20, kind="", status=""):
    term = term.strip().lower()
    if kind and kind not in NODE_TYPES:
        raise ValueError("Unsupported entity type")
    if not term and not status:
        return []
    rows = query(
        name,
        "MATCH (n:Entity) WHERE ($kind = '' OR n.type = $kind) "
        "AND ($status = '' OR n.status = $status) "
        "AND ($term = '' OR toLower(n.name) CONTAINS $term "
        "OR toLower(n.path) CONTAINS $term OR toLower(n.original_id) CONTAINS $term "
        "OR toString(n.number) = $number OR toLower(n.sha) STARTS WITH $term "
        "OR toLower(n.body) CONTAINS $term OR toLower(n.summary) CONTAINS $term) "
        "WITH n, CASE WHEN $term <> '' AND (toLower(n.name) = $term "
        "OR toLower(n.path) = $term OR toLower(n.original_id) = $term "
        "OR toString(n.number) = $number) THEN 1.0 "
        "WHEN $term <> '' AND toLower(n.sha) STARTS WITH $term THEN 0.95 "
        "WHEN $term <> '' AND toLower(n.name) STARTS WITH $term THEN 0.8 "
        "WHEN $term = '' OR toLower(n.name) CONTAINS $term "
        "OR toLower(n.path) CONTAINS $term OR toLower(n.original_id) CONTAINS $term "
        "THEN 0.55 ELSE 0.4 END AS relevance "
        "RETURN n,relevance ORDER BY relevance DESC,n.id LIMIT $limit",
        {
            "term": term,
            "number": term.lstrip("#"),
            "kind": kind,
            "status": status,
            "limit": max(1, min(limit, 50)),
        },
    )
    meanings = {
        1.0: "exact identifier/path match",
        0.95: "commit SHA prefix",
        0.8: "name prefix",
        0.55: "name/path/status match",
        0.4: "metadata text match",
    }
    return [
        {
            **encode_node(row[0]),
            "score": row[1],
            "score_meaning": meanings[row[1]],
            "uncertainty": "Recorded/static evidence does not prove runtime behavior or an issue fix.",
        }
        for row in rows
    ]


def impact(name, node_id, depth=2):
    # Depth is a validated integer, never arbitrary query text.
    depth = max(1, min(int(depth), 3))
    rows = query(
        name,
        f"MATCH p=(caller:Entity)-[:CALLS|IMPORTS*1..{depth}]->(target:Entity {{id:$id}}) RETURN nodes(p),relationships(p) LIMIT 100",
        {"id": node_id},
    )
    results = {}
    for path_nodes, path_edges in rows:
        origin = encode_node(path_nodes[0])
        distance = len(path_edges)
        if origin["id"] == node_id:
            continue
        row = {
            "node": origin,
            "distance": distance,
            "classification": "verified static direct dependency"
            if distance == 1
            else "possible indirect impact",
            "path": [encode_node(n) for n in path_nodes],
            "relationships": [edge_dict(e) for e in path_edges],
        }
        if origin["id"] not in results or distance < results[origin["id"]]["distance"]:
            results[origin["id"]] = row
    return {
        "results": sorted(results.values(), key=lambda r: (r["distance"], r["node"]["id"])),
        "unknown": "Dynamic dispatch, external packages and unsupported languages are unverified.",
        "max_depth": depth,
    }


def find_path(name, source, target, depth=3):
    depth = max(1, min(int(depth), 4))
    rows = query(
        name,
        f"MATCH p=(a:Entity {{id:$source}})-[:CALLS|IMPORTS|DEFINES|REFERENCES|MODIFIES*1..{depth}]-(b:Entity {{id:$target}}) RETURN nodes(p),relationships(p) LIMIT 3",
        {"source": source, "target": target},
    )
    return [
        {"nodes": [encode_node(n) for n in ns], "edges": [edge_dict(e) for e in es]}
        for ns, es in rows
    ]


def edge_id(edge):
    key = json.dumps([edge["source"], edge["target"], edge["type"], edge.get("line", 0)])
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def copy_snapshot(previous, name):
    # GRAPH.COPY is blocking but can explicitly reject its fork while another
    # background operation is active. Only this known pre-copy failure is safe
    # to retry. Connection errors and all other write failures remain errors.
    # https://github.com/FalkorDB/FalkorDB-rs#waiting-for-background-operations
    for attempt in range(7):
        try:
            client().select_graph(previous).copy(name)
            return
        except ResponseError as exc:
            if str(exc) != "GRAPH.COPY failed, could not fork" or attempt == 6:
                raise
            time.sleep(0.05 * 2**attempt)


def update_snapshot(previous, name, old_nodes, old_edges, new_nodes, new_edges):
    """Copy an immutable snapshot and apply a semantic diff. Unchanged entities are not rewritten."""
    check_graph_budget(new_nodes, new_edges)
    copy_snapshot(previous, name)
    graph = client().select_graph(name)
    old = {n["id"]: n for n in old_nodes}
    new = {n["id"]: n for n in new_nodes}
    removed = list(old.keys() - new.keys())
    if removed:
        graph.query("MATCH (n:Entity) WHERE n.id IN $ids DETACH DELETE n", {"ids": removed})
    old_e, new_e = {edge_id(e): e for e in old_edges}, {edge_id(e): e for e in new_edges}
    gone = list(old_e.keys() - new_e.keys())
    if gone:
        graph.query("MATCH ()-[r]->() WHERE r.id IN $ids DELETE r", {"ids": gone})
    changed_nodes = []
    for nid, node in new.items():

        def compare(n):
            return {k: v for k, v in n.items() if k != "commit"}

        if nid not in old or compare(old[nid]) != compare(node):
            changed_nodes.append(node)
    for node in changed_nodes:
        kind = node["type"]
        if kind not in NODE_TYPES:
            raise ValueError("Unknown entity type")
        graph.query(
            f"MERGE (n:Entity:{kind} {{id:$id}}) SET n = $props", {"id": node["id"], "props": node}
        )
    added = new_e.keys() - old_e.keys()
    for eid in added:
        edge = new_e[eid]
        kind = edge["type"]
        if kind not in EDGE_TYPES:
            raise ValueError("Unknown relationship type")
        graph.query(
            f"MATCH (a:Entity {{id:$source}}),(b:Entity {{id:$target}}) CREATE (a)-[r:{kind}]->(b) SET r = $props",
            {"source": edge["source"], "target": edge["target"], "props": {**edge, "id": eid}},
        )
    return {
        "nodes_written": len(changed_nodes),
        "nodes_deleted": len(removed),
        "edges_written": len(added),
        "edges_deleted": len(gone),
    }


def manifest(name):
    """Internal worker diff input: actual published data, with a hard safety cap."""
    nodes = [encode_node(row[0]) for row in query(name, "MATCH (n:Entity) RETURN n LIMIT 50001")]
    edges = [edge_dict(row[0]) for row in query(name, "MATCH ()-[r]->() RETURN r LIMIT 200001")]
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise ValueError("Snapshot exceeds worker diff budget")
    return nodes, edges
