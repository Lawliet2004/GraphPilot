"""Bound historical material before it is combined with a source graph."""

from sqlalchemy import select

from api.graph.limits import MAX_EDGES, MAX_NODES
from api.ingestion.sources import SourceError
from api.models import HistoryRecord


def records_graph(db, repo):
    nodes, edges = [], []
    rows = db.scalars(
        select(HistoryRecord)
        .where(HistoryRecord.repository_id == repo.id, HistoryRecord.branch == repo.branch)
        .limit(MAX_NODES + 1)
        .execution_options(yield_per=100)
    )
    for row in rows:
        if len(nodes) >= MAX_NODES or len(edges) + len(row.relationships) > MAX_EDGES:
            raise SourceError("Historical evidence exceeds the graph indexing capacity")
        nodes.append(row.data)
        edges.extend(row.relationships)
    return nodes, edges
