"""Isolated real FalkorDBLite research probes; product services and data untouched."""
import json,hashlib,contextlib
from pathlib import Path
from redislite.falkordb_client import FalkorDB
from api.graph import store
from api.ingestion.python import parse_file,build_graph
root=Path('/tmp/graphpilot-research-20261018/isolated-falkor');root.mkdir(exist_ok=True)
db=FalkorDB(str(root/'probe.rdb'),serverconfig={'port':'0','bind':'127.0.0.1','dir':str(root),'save':''})
original=store.client
store.client=lambda:db
out={'scope':'Disposable isolated FalkorDBLite, UNIX socket only. Does not connect to application databases. Search capability probe, not a competitor performance benchmark.'}
try:
 files={};sources={}
 for folder in ['api','scripts','app/src']:
  for p in sorted(Path(folder).rglob('*')):
   if p.suffix not in {'.py','.ts','.tsx','.js','.jsx'} or '__pycache__' in p.parts or not p.is_file():continue
   source=p.read_text();rel=p.as_posix();sources[rel]=source
   files[rel]={'hash':hashlib.sha256(source.encode()).hexdigest(),'lines':len(source.splitlines()),'parsed':parse_file(rel,source)}
 nodes,edges,stats=build_graph('research-only','main','working-tree','GraphPilot',files)
 name='research_source_search';store.create_graph(name,nodes,edges)
 out['source_search']=[]
 for term in ['synthesize','authenticate_token','api/routes/context.py','X-CSRF-Token','Request origin is not allowed','python-ast-3','graph_queries']:
  hits=store.search(name,term,limit=50,include_docs=True)
  out['source_search'].append({'query':term,'graph_result_count':len(hits),'graph_results':[{'name':n.get('name'),'path':n.get('path')} for n in hits[:8]],'literal_source_files':[p for p,s in sources.items() if term.lower() in s.lower()]})
 out['substring_plan']=str(db.select_graph(name).explain("MATCH (n:Entity) WHERE toLower(n.name) CONTAINS 'token' RETURN n LIMIT 20"))
 out['exact_plan']=str(db.select_graph(name).explain("MATCH (n:Entity {id:'none'}) RETURN n LIMIT 1"))
 impact_name='research_impact_cap';g=db.select_graph(impact_name)
 fixtures=[{'id':'target','name':'target'}]+[{'id':f'caller{i}','name':f'caller{i}'} for i in range(105)]
 g.query('UNWIND $rows AS row CREATE (n:Entity:Function) SET n = row',{'rows':fixtures})
 g.query("MATCH (a:Entity),(b:Entity {id:'target'}) WHERE a.id <> 'target' CREATE (a)-[:CALLS]->(b)")
 impact=store.impact(impact_name,'target',1)
 out['impact_cap']={'known_direct_callers':105,'returned_callers':len(impact['results']),'response_keys':list(impact),'has_truncation_indicator':any(k in impact for k in ['truncated','has_more','complete','coverage','bounded']),'unknown':impact['unknown']}
 Path('/tmp/graphpilot-research-20261018/graph-probes.json').write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps(out,indent=2),flush=True)
finally:
 for name in ['research_source_search','research_impact_cap']:
  with contextlib.suppress(Exception):db.select_graph(name).delete()
 store.client=original
 db.close()
 print('Isolated graphs removed; embedded service closed.',flush=True)
