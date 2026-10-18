"""Research spike, isolated stores only. No product implementation changes."""
import contextlib,json,re,sqlite3,time,statistics
from pathlib import Path
from redislite.falkordb_client import FalkorDB
root=Path('/tmp/graphpilot-research-20261018/index-spike');root.mkdir(exist_ok=True)
db=FalkorDB(str(root/'probe.rdb'),serverconfig={'port':'0','bind':'127.0.0.1','dir':str(root),'save':''})
conn=sqlite3.connect(str(root/'source-search.sqlite'))
out={'scope':'Research-only isolated local indexes; named-query behavior and small synthetic timing observations, not a product benchmark or deployment recommendation.'}
try:
 corpus=[{'id':'snake','name':'normalize_url','path':'network/urls.py','doc':'Normalize a URL'},{'id':'camel','name':'normalizeUrl','path':'network/urls.ts','doc':'Normalize a URL'},{'id':'swapped','name':'url_normalize','path':'network/helpers.py','doc':''},{'id':'header','name':'validate_request','path':'api/auth.py','doc':'Validate incoming requests'}]
 def tokens(s):return ' '.join(re.sub(r'([a-z0-9])([A-Z])',r'\1 \2',s).replace('_',' ').replace('/',' ').split()).lower()
 for n in corpus:n['terms']=tokens(n['name']+' '+n['path'])
 g=db.select_graph('index_behavior');g.query('UNWIND $rows AS row CREATE (n:Entity) SET n = row',{'rows':corpus})
 g.query("CALL db.idx.fulltext.createNodeIndex({label:'Entity',stopwords:[]},'name','doc','terms')")
 out['falkor_fulltext_behavior']=[]
 for term in ['normalize_url','normalizeUrl','url','normalize','X-CSRF-Token']:
  rec={'query':term}
  try:rec['substring_ids']=[r[0] for r in g.query('MATCH (n:Entity) WHERE toLower(n.name) CONTAINS $term RETURN n.id ORDER BY n.id',{'term':term.lower()}).result_set]
  except Exception as e:rec['substring_error']=type(e).__name__
  for field in ['name','terms']:
   try:
    # Queries are parameters. Special punctuation is intentionally left intact to observe behavior.
    rec[field+'_fulltext_ids']=[r[0] for r in g.query("CALL db.idx.fulltext.queryNodes('Entity',$q) YIELD node RETURN node.id ORDER BY node.id",{'q':'@'+field+':('+term+')'}).result_set]
   except Exception as e:rec[field+'_fulltext_error']=str(e)[:180]
  out['falkor_fulltext_behavior'].append(rec)
 conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS source_fts USING fts5(path,content,tokenize="trigram")')
 conn.execute('DELETE FROM source_fts')
 sources=[]
 for folder in ['api','scripts','app/src']:
  for p in sorted(Path(folder).rglob('*')):
   if p.is_file() and p.suffix in {'.py','.ts','.tsx','.js','.jsx'} and '__pycache__' not in p.parts:sources.append((p.as_posix(),p.read_text()))
 conn.executemany('INSERT INTO source_fts(path,content) VALUES (?,?)',sources);conn.commit()
 out['sqlite_fts5_trigram']=[]
 for term in ['X-CSRF-Token','Request origin is not allowed','python-ast-3','graph_queries','xy']:
  phrase='"'+term.replace('"','""')+'"'
  expected={p for p,s in sources if term.lower() in s.lower()}
  try:
   hits=conn.execute('SELECT path,bm25(source_fts) FROM source_fts WHERE source_fts MATCH ? ORDER BY bm25(source_fts),path LIMIT 100',(phrase,)).fetchall()
   found={r[0] for r in hits}
   out['sqlite_fts5_trigram'].append({'query':term,'result_count':len(hits),'expected_literal_file_count':len(expected),'all_expected_returned':expected<=found,'returned_nonliteral_files':sorted(found-expected),'paths':[r[0] for r in hits]})
  except Exception as e:out['sqlite_fts5_trigram'].append({'query':term,'error':str(e)})
 out['sqlite_version']=sqlite3.sqlite_version
 # Equal-result exact-name lookup vs substring lookup, at explicitly synthetic sizes.
 timings=[]
 for count in [1000,10000,50000]:
  sg=db.select_graph('scaling_'+str(count));sg.query('CREATE INDEX FOR (n:Entity) ON (n.name)')
  for start in range(0,count,1000):
   sg.query('UNWIND $rows AS row CREATE (n:Entity) SET n = row',{'rows':[{'id':str(i),'name':f'unique_function_{i:07d}'} for i in range(start,min(start+1000,count))]})
  target=f'unique_function_{count-1:07d}'
  for mode,query in [('substring','MATCH (n:Entity) WHERE toLower(n.name) CONTAINS $q RETURN n.id LIMIT 20'),('exact','MATCH (n:Entity {name:$q}) RETURN n.id LIMIT 20')]:
   samples=[];last=[]
   for iteration in range(22):
    before=time.perf_counter();last=sg.query(query,{'q':target}).result_set;elapsed=(time.perf_counter()-before)*1000
    if iteration>=2:samples.append(elapsed)
   samples.sort();timings.append({'nodes':count,'mode':mode,'returned':len(last),'measured_repeats':len(samples),'warmups':2,'median_ms':round(statistics.median(samples),3),'p95_nearest_rank_ms':round(samples[18],3)})
 out['synthetic_lookup_timings']=timings
 Path('/tmp/graphpilot-research-20261018/search-index-probe.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2),flush=True)
finally:
 conn.close()
 for name in ['index_behavior','scaling_1000','scaling_10000','scaling_50000']:
  with contextlib.suppress(Exception):db.select_graph(name).delete()
 db.close();print('Research stores closed; graphs removed.',flush=True)
