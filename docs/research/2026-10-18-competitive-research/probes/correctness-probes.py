"""Research-only fixtures. No application database or repository fixture executes."""
import contextlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api.graph import store
from redislite.falkordb_client import FalkorDB

root = Path('/tmp/graphpilot-research-20261018/correctness-isolated')
root.mkdir(exist_ok=True)
out = {'scope': 'Synthetic route fixture with persistence/model/retrieval mocked; isolated UNIX-socket FalkorDBLite for graph queries. No product data or services.'}
mod = importlib.import_module('api.routes.context')
source = ''.join(f'line {i:03d} ' + 'x' * 30 + '\n' for i in range(1, 201))
evidence = {'content': source, 'start_line': 1, 'end_line': 200, 'truncated': False,
            'commit': 'synthetic-commit', 'url': 'https://example.invalid/source'}
retrieved = {'results': [{'id': 'fixture', 'name': 'fixture', 'type': 'Function', 'path': 'fixture.py'}],
             'relationships': [], 'warnings': [], 'diagnostics': {'graph_queries': 0}}
class FakeDB:
    def scalars(self, *args): return []
    def add(self, row): self.row = row
    def commit(self): pass
fake = FakeDB()
repo = SimpleNamespace(id='research', branch='main', snapshot_id='synthetic', historical=False)
with patch.object(mod, 'indexed'), patch.object(mod, 'retrieve', return_value=retrieved), \
     patch.object(mod, 'read_evidence', return_value=evidence), \
     patch.object(mod, 'for_synthesis', return_value=None), \
     patch.object(mod, 'synthesize', return_value={'mode': 'graph', 'answer': None}):
    response = mod.context('research', mod.Question(question='fixture'), user=SimpleNamespace(id='fake'), db=fake, repo=repo)
cit = response['evidence'][0]
out['citation_range'] = {'input_characters': len(source), 'input_lines': 200,
    'returned_characters': len(cit['content']), 'returned_lines_including_partial': len(cit['content'].splitlines()),
    'reported_start_line': cit['start_line'], 'reported_end_line': cit['end_line'],
    'has_truncated_field': 'truncated' in cit, 'persistence': 'FakeDB, no actual database'}

db = FalkorDB(str(root/'research.rdb'), serverconfig={'port':'0','bind':'127.0.0.1','dir':str(root),'save':''})
original = store.client
store.client = lambda: db
out['impact_order_trials'] = []
names = []
try:
    for mode in ['direct_first', 'direct_last']:
        name = 'research_cap_order_' + mode
        names.append(name)
        g = db.select_graph(name)
        g.query("CREATE (:Entity:Function {id:'target',name:'target'}),(:Entity:Function {id:'caller',name:'caller'})")
        g.query('UNWIND $rows AS row CREATE (n:Entity:Function) SET n=row', {'rows':[{'id':f'relay{i}','name':f'relay{i}'} for i in range(110)]})
        direct = "MATCH (c:Entity {id:'caller'}),(t:Entity {id:'target'}) CREATE (c)-[:CALLS]->(t)"
        if mode == 'direct_first': g.query(direct)
        g.query("MATCH (c:Entity {id:'caller'}),(r:Entity) WHERE r.id STARTS WITH 'relay' CREATE (c)-[:CALLS]->(r)")
        g.query("MATCH (r:Entity),(t:Entity {id:'target'}) WHERE r.id STARTS WITH 'relay' CREATE (r)-[:CALLS]->(t)")
        if mode == 'direct_last': g.query(direct)
        result = store.impact(name, 'target', 2)
        caller = next((x for x in result['results'] if x['node']['id']=='caller'), None)
        out['impact_order_trials'].append({'mode':mode,'known_direct_callers':111,
            'returned_unique_origins':len(result['results']),
            'caller_returned': caller is not None,
            'caller_distance': caller['distance'] if caller else None,
            'caller_classification': caller['classification'] if caller else None})
finally:
    for name in names:
        with contextlib.suppress(Exception): db.select_graph(name).delete()
    store.client = original
    db.close()
out['impact_interpretation'] = 'Two order variants only. Lack of a misclassification in these fixtures would not prove capped path enumeration preserves global minimum distance.'
Path('/tmp/graphpilot-research-20261018/correctness-probes.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2),flush=True)
