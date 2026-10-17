"""Hard worker budgets shared by graph construction, copy and publication."""

from api.ingestion.sources import SourceError

MAX_NODES = 50000
MAX_EDGES = 200000


def check_graph_budget(nodes, edges):
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise SourceError(
            "Graph exceeds the indexing capacity of 50,000 nodes or 200,000 relationships"
        )
