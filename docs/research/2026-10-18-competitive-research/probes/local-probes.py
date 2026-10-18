"""Research-only synthetic probes. No services, indexes, or product data modified."""
import json,hashlib
from pathlib import Path
from api.ingestion.python import parse_file,build_graph
from api.search.retrieval import interpret
cases={
'direct_python':{'m.py':'def normalize(x):\n    return x\ndef checkout(x):\n    return normalize(x)\n'},
'local_import':{'m.py':'def normalize(x):\n    return x\n','service.py':'def checkout(x):\n    from m import normalize\n    return normalize(x)\n'},
'parameter_dispatch':{'m.py':'class Normalizer:\n    def normalize(self,x):\n        return x\ndef checkout(n: Normalizer,x):\n    return n.normalize(x)\n'},
'non_python':{'service.ts':'export function normalize(x: number) { return x; }\nexport function checkout(x: number) { return normalize(x); }\n'},
'inherited_dispatch':{'m.py':'class Base:\n    def normalize(self,x):\n        return x\nclass Child(Base):\n    def checkout(self,x):\n        return self.normalize(x)\n'},
'static_test_relation':{'m.py':'def normalize(x):\n    return x\ndef helper(x):\n    return normalize(x)\ndef test_checkout():\n    return helper(1)\n'}
}
results=[]
for label,sources in cases.items():
 files={p:{'hash':hashlib.sha256(s.encode()).hexdigest(),'lines':len(s.splitlines()),'parsed':parse_file(p,s)} for p,s in sources.items()}
 nodes,edges,stats=build_graph('research-only','main','synthetic','probe',files)
 by_id={n['id']:n.get('original_id',n.get('name')) for n in nodes}
 results.append({'case':label,'stats':stats,'symbols':[n['original_id'] for n in nodes if n['type'] in {'Function','Class','TestCase'}],'calls':[{'source':by_id[e['source']],'target':by_id[e['target']],'line':e.get('line')} for e in edges if e['type']=='CALLS'],'tests':[{'source':by_id[e['source']],'target':by_id[e['target']]} for e in edges if e['type']=='TESTS']})
queries=['Where is X-CSRF-Token validated?','How is payment failure handled?','Trace checkout to normalize','Find callers of normalize','Which tests cover normalize?','Find service.ts','Explain the architecture']
output={'scope':'Synthetic parser/graph-builder and question interpreter only; no database or vendor runtime benchmark','parser_cases':results,'questions':[{'question':q,'interpretation':interpret(q)} for q in queries]}
Path('/tmp/graphpilot-research-20261018/local-probes.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output,indent=2))
