import json,time,contextlib
from pathlib import Path
from redislite.falkordb_client import FalkorDB
root=Path('/tmp/graphpilot-research-20261018/fts-check');root.mkdir(exist_ok=True)
db=FalkorDB(str(root/'check.rdb'),serverconfig={'port':'0','bind':'127.0.0.1','dir':str(root),'save':''})
out={'scope':'Isolated fulltext readiness/syntax check. No product database.'}
try:
 g=db.select_graph('research_fulltext')
 g.query("CREATE (:Entity {id:'snake',name:'normalize_url',terms:'normalize url'}),(:Entity {id:'camel',name:'normalizeUrl',terms:'normalize url'})")
 out['create']=g.query("CALL db.idx.fulltext.createNodeIndex({label:'Entity',stopwords:[]},'name','terms')").result_set
 out['indexes_initial']=g.query('CALL db.indexes()').result_set
 for _ in range(30):
  r=g.query("CALL db.idx.fulltext.queryNodes('Entity','normalize') YIELD node RETURN node.id").result_set
  if r:break
  time.sleep(0.1)
 out['indexes_after']=g.query('CALL db.indexes()').result_set
 out['queries']=[]
 for q in ['normalize','url','normalize_url','normalizeUrl','@terms:(normalize)','@name:(normalize_url)']:
  try:rows=g.query("CALL db.idx.fulltext.queryNodes('Entity',$q) YIELD node RETURN node.id",{'q':q}).result_set;out['queries'].append({'query':q,'rows':rows})
  except Exception as e:out['queries'].append({'query':q,'error':str(e)[:200]})
 p=Path('/tmp/graphpilot-research-20261018/fulltext-check.json');p.write_text(json.dumps(out,indent=2,default=str)+'\n');print(json.dumps(out,indent=2,default=str),flush=True)
finally:
 with contextlib.suppress(Exception):db.select_graph('research_fulltext').delete()
 db.close()
