"""Research model only: cap semantics, not application/database implementation."""
from collections import defaultdict
import json
from pathlib import Path

def bounded_incoming(edges, target, cap, depth):
    incoming = defaultdict(set)
    for a, b in edges:
        incoming[b].add(a)
    seen = {target: 0}
    frontier = [target]
    results = {}
    stopped = False
    for distance in range(1, depth + 1):
        candidates = sorted(set().union(*(incoming[n] for n in frontier)) - set(seen))
        remaining = cap - len(results)
        selected = candidates[:remaining]
        for node in selected:
            seen[node] = distance
            results[node] = distance
        if len(candidates) > remaining:
            stopped = True
            break
        frontier = selected
        if not frontier:
            break
    return results, stopped

def floyd_warshall(edges, size):
    distances = [[0 if a == b else 100 for b in range(size)] for a in range(size)]
    for a, b in edges:
        distances[a][b] = 1
    for k in range(size):
        for a in range(size):
            for b in range(size):
                distances[a][b] = min(distances[a][b], distances[a][k] + distances[k][b])
    return distances

possible = [(a, b) for a in range(4) for b in range(4) if a != b]
checks = 0
for bits in range(1 << len(possible)):
    edges = [edge for i, edge in enumerate(possible) if bits & (1 << i)]
    matrix = floyd_warshall(edges, 4)
    truth = {a: matrix[a][0] for a in range(1, 4) if matrix[a][0] <= 3}
    for cap in [1, 2, 3]:
        got, partial = bounded_incoming(edges, 0, cap, 3)
        assert all(truth[node] == distance for node, distance in got.items())
        assert len(got) <= cap
        assert partial == (len(truth) > cap)
        checks += 1
out = {
    'scope': 'Exhaustive four-node simple directed graphs without self loops; research model of stop-on-partial-layer cap semantics. Not product code, database validation, resource bounds, or a release test. Parallel relationship rows and races are not modeled.',
    'directed_graphs': 1 << len(possible), 'cap_variants': [1, 2, 3], 'checks': checks,
    'reference': 'Independent Floyd-Warshall all-pairs shortest distances',
    'all_returned_distances_equal_full_reference': True,
    'disclosed_cap_matches_reference': True,
    'required_followup': 'Real FalkorDB incoming single-hop queries need edge/work budgets and timeout handling. Stop after an incomplete earlier layer, or explicitly label later distances provisional. Do not assume algo.BFS supports the required direction/type filters or a result LIMIT bounds its internal work.'
}
root = Path('/tmp/graphpilot-research-20261018')
root.mkdir(exist_ok=True)
(root/'traversal-contract-check.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2))
