import collections,hashlib,json,subprocess,time
from pathlib import Path
from api.ingestion.python import parse_file,build_graph,PARSER_VERSION
root=Path.cwd()
paths=[]
for folder in ['api','scripts','app/src']:
 paths += [p for p in (root/folder).rglob('*') if p.suffix in {'.py','.ts','.tsx','.js','.jsx'} and '__pycache__' not in p.parts and p.is_file()]
files={};languages=collections.Counter();lines=collections.Counter();hashes={}
started=time.perf_counter()
for path in sorted(paths):
 rel=path.relative_to(root).as_posix();content=path.read_text();digest=hashlib.sha256(content.encode()).hexdigest()
 hashes[rel]=digest;languages[path.suffix]+=1;lines[path.suffix]+=len(content.splitlines())
 files[rel]={'hash':digest,'lines':len(content.splitlines()),'parsed':parse_file(rel,content)}
nodes,edges,stats=build_graph('research-self-analysis','working-tree','uncommitted-working-tree','GraphPilot',files)
result={'scope':'Current api/, scripts/, app/src/ source only, including preexisting uncommitted files. Pure parser and in-memory graph builder; no database/indexing service changed. Resolution counts include builtins, external and dynamic calls, and are NOT precision or recall metrics.','parser_version':PARSER_VERSION,'git_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'files_by_extension':dict(languages),'lines_by_extension':dict(lines),'node_types':dict(collections.Counter(n['type'] for n in nodes)),'edge_types':dict(collections.Counter(e['type'] for e in edges)),'stats':stats,'elapsed_seconds':round(time.perf_counter()-started,3),'source_hashes':hashes}
Path('/tmp/graphpilot-research-20261018/self-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='source_hashes'},indent=2))
