"""Synthetic source is parsed as data only; fixture functions are never executed."""
import hashlib,json
from pathlib import Path
from api.ingestion.python import parse_file,build_graph
cases={
'rebound_self':{'m.py':'''class Other:
    def target(self):
        return "other"
class Caller:
    def target(self):
        return "caller"
    def run(self):
        self = Other()
        return self.target()
'''},
'module_rebound_function':{'m.py':'''def target():
    return "old"
target = lambda: "replacement"
target()
'''},
'function_local_rebound_control':{'m.py':'''def target():
    return "old"
def run():
    target = lambda: "replacement"
    return target()
'''},
'missing_import_unique_name_control':{'unrelated.py':'''def target():
    return "unrelated"
''','caller.py':'''from missing_package import target
def run():
    return target()
'''},
'escaped_relative_import':{'target.py':'''def target():
    return "top-level"
''','caller.py':'''from ...target import target
def run():
    return target()
'''}
}
rows=[]
for name,sources in cases.items():
 files={p:{'hash':hashlib.sha256(s.encode()).hexdigest(),'lines':len(s.splitlines()),'parsed':parse_file(p,s)} for p,s in sources.items()}
 nodes,edges,stats=build_graph('research-adversarial','main','synthetic','probe',files);names={n['id']:n['original_id'] for n in nodes}
 rows.append({'case':name,'sources':sources,'calls':[{'source':names[e['source']],'target':names[e['target']],'line':e.get('line'),'provenance':e.get('provenance')} for e in edges if e['type']=='CALLS'],'resolved_calls':stats['resolved_calls'],'unresolved_calls':stats['unresolved_calls'],'parse_errors':stats['parse_errors']})
out={'scope':'Synthetic parser/graph-builder probes, no source execution and no database. Assess expected static binding behavior manually; no corpus-wide accuracy claim.','cases':rows}
Path('/tmp/graphpilot-research-20261018/adversarial-probes.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
