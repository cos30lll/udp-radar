#!/usr/bin/env python3
"""Check packaged sources without caches, or copy the nine interpreted runtime files."""
import argparse, ast, hashlib, json, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=('protocol.py','identity.py','server.py','app.js','index.html','style.css','runner.sh','启动.sh','停止.sh')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/runtime');p.add_argument('--check',action='store_true',help='read-only Python syntax and src/dist equality checks; no bytecode/cache');a=p.parse_args()
 if a.check:
  count=0
  for folder in ('src','tools','research'):
   for f in sorted((ROOT/folder).rglob('*.py')): ast.parse(f.read_text(encoding='utf-8'),filename=str(f));count+=1
  for n in FILES:
   if (ROOT/'src'/n).read_bytes()!=(ROOT/'dist/udp-radar-v2.2'/n).read_bytes(): p.error('src/dist mismatch: '+n)
  print(json.dumps({'python_syntax_files':count,'runtime_files':len(FILES),'src_dist_equal':True,'written':False}));return 0
 out=a.output.resolve()
 if out==ROOT or out in ROOT.parents: p.error('output cannot be repository root or its parent')
 for folder in ('src','dist','tools','research','docs'):
  protected=ROOT/folder
  if out==protected or out.is_relative_to(protected): p.error('output cannot overwrite tracked source/release directories')
 out.mkdir(parents=True,exist_ok=True)
 for n in FILES: shutil.copyfile(ROOT/'src'/n,out/n)
 hashes={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in FILES}
 (out/'runtime-manifest.json').write_text(json.dumps({'version':'v2.2-names-candidate','files':hashes},ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'output':str(out),'files':len(hashes),'started':False},ensure_ascii=True));return 0
if __name__=='__main__': raise SystemExit(main())
