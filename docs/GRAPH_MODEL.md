# Graph data model and Cypher queries

GraphPilot stores every indexed repository revision in its own immutable FalkorDB
graph named `gp_<repository-uuid>_<sha256(branch, revision)[:24]>`
(`api/graph/store.py:graph_name`). Branches and snapshots never share a graph, so
reads are always scoped to one pinned revision.

## Nodes

Every node carries the shared label `Entity` plus one type label. Indexed
properties: `id`, `name`, `path`.

| Label | Meaning | Key properties |
|---|---|---|
| `Repository` | Connected repository | `id`, `name` |
| `Branch` | Indexed branch head | `name`, revision |
| `File` | Source file at that revision | `path`, language, hash |
| `Class` | Python class | `name`, `path`, line range |
| `Function` | Python function/method | `name`, `path`, line range |
| `TestCase` | Test function | `name`, `path` |
| `Commit` | Git commit | sha, message, author |
| `PullRequest` / `Issue` | GitHub history | number, state, title |
| `WorkflowRun` | CI run | status, conclusion |
| `LogArtifact` | Stored, redacted CI log | size, expiry |
| `Decision` | Recorded design decision (only with reliable evidence) | |

IDs are stable, scoped hashes, so an unchanged symbol keeps its ID across scans.

## Relationships

| Type | From → To |
|---|---|
| `HAS_FILE` | Branch → File |
| `DEFINES` | File/Class → Class/Function/TestCase |
| `CALLS` | Function → Function (static call sites) |
| `IMPORTS` | File → File/Entity |
| `TESTS` | TestCase → Function/Class |
| `CONTAINS_COMMIT` | Branch → Commit |
| `MODIFIES` | Commit → File |
| `REFERENCES` | PullRequest/Issue/Commit → Entity |
| `ADDRESSES` | PullRequest → Issue |
| `TRIGGERED_BY` | WorkflowRun → Commit |
| `PRODUCES` | WorkflowRun → LogArtifact |
| `RELATED_TO`, `SUPERSEDES` | Decision links |

Every relationship stores an `id` (hash of source, type, target) and the source
reference it was derived from, so every edge links to the code that produced it.

```
(Branch)-[:HAS_FILE]->(File)-[:DEFINES]->(Class)-[:DEFINES]->(Function)
(Function)-[:CALLS]->(Function)        (File)-[:IMPORTS]->(File)
(TestCase)-[:TESTS]->(Function)        (Commit)-[:MODIFIES]->(File)
(WorkflowRun)-[:TRIGGERED_BY]->(Commit) (WorkflowRun)-[:PRODUCES]->(LogArtifact)
```

## Cypher queries the product depends on

All are parameterized; labels/relationship types are interpolated only from the
fixed allow-lists above. Reads use `GRAPH.RO_QUERY`.

**Indexes (on publish)**
```cypher
CREATE INDEX FOR (n:Entity) ON (n.id)
CREATE INDEX FOR (n:Entity) ON (n.name)
CREATE INDEX FOR (n:Entity) ON (n.path)
```

**Bulk snapshot publication (batches of 200)**
```cypher
UNWIND $rows AS row CREATE (n:Entity:Function) SET n = row
UNWIND $rows AS row
MATCH (a:Entity {id: row.source}), (b:Entity {id: row.target})
CREATE (a)-[r:CALLS]->(b) SET r = row
MATCH (n:Entity) RETURN count(n)          // publication validation
```

**Incremental diff (changed files only)**
```cypher
MATCH (n:Entity) WHERE n.id IN $ids DETACH DELETE n
MATCH ()-[r]->() WHERE r.id IN $ids DELETE r
MERGE (n:Entity:Function {id: $id}) SET n = $props
MATCH (a:Entity {id: $source}), (b:Entity {id: $target})
CREATE (a)-[r:CALLS]->(b) SET r = $props
```

**Bounded graph view / search**
```cypher
MATCH (n:Entity)
WHERE ($kind = '' OR n.type = $kind)
  AND ($term = '' OR toLower(n.name) CONTAINS $term OR toLower(n.path) CONTAINS $term)
RETURN n ORDER BY n.type, n.name LIMIT $limit

MATCH (a:Entity)-[r]->(b:Entity)
WHERE a.id IN $ids AND b.id IN $ids AND ($relation = '' OR type(r) = $relation)
RETURN r LIMIT 500
```

**Node lookup and neighbor expansion**
```cypher
MATCH (n:Entity {id: $id}) RETURN n LIMIT 1
MATCH (n:File {path: $path}) RETURN n ORDER BY n.id LIMIT 1
MATCH (a:Entity {id: $id})-[r:CALLS]-(b:Entity) RETURN a, r, b LIMIT $limit
```

**Impact analysis — breadth-first traversal of incoming dependencies.**
Run once per hop over the current frontier; direct (hop 1) and indirect (hop ≥ 2)
dependents are reported separately, with the query count disclosed.
```cypher
MATCH (caller:Entity)-[r:CALLS|IMPORTS]->(n:Entity)
WHERE n.id IN $ids
RETURN n.id, caller, r LIMIT $limit
```

**Path between two symbols — bounded variable-length match (1–4 hops, default 3)**
```cypher
MATCH p = (a:Entity {id: $source})
          -[:CALLS|IMPORTS|DEFINES|REFERENCES|MODIFIES*1..3]-
          (b:Entity {id: $target})
RETURN nodes(p), relationships(p) LIMIT 3
```

**Context retrieval for Ask / MCP**
```cypher
MATCH (n:File) RETURN n ORDER BY n.path LIMIT 5000
```

Graph algorithms used: bounded BFS (impact), bounded variable-length path
matching (paths), 1-hop neighborhood expansion, and set-difference diffing of
node/edge IDs for incremental publication.
