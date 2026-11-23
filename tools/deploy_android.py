#!/usr/bin/env python3
"""Copy runtime locally or stage it for manual transfer. No ADB, service or game launch."""
import argparse, hashlib, json
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
FILES=('protocol.py','identity.py','server.py','app.js','index.html','style.css','runner.sh','启动.sh','停止.sh')
ORIGINAL='/storage/emulated/0/Download/超自然行动'
OPERIT='/data/user/0/com.ai.assistance.operit/files'
def android_path(value, parser, shared=False):
 if not value.startswith('/') or any(c in value for c in ("'",'"','\\','\n','\r','\t','\x00','$','`')) or '..' in value.split('/'):
  parser.error('Android paths must be absolute and contain no shell quoting/expansion characters')
 value=str(PurePosixPath(value))
 if shared and not value.startswith('/storage/emulated/0/'):
  parser.error('runtime project must be under the shared-storage mount supported by runner.sh')
 return value
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--source',type=Path,default=ROOT/'dist/udp-radar-v2.2')
 p.add_argument('--project-root',default=ORIGINAL,help='final Android path embedded in files, not a remote transfer destination')
 p.add_argument('--operit-files',default=OPERIT)
 g=p.add_mutually_exclusive_group();g.add_argument('--stage',type=Path,help='local staging project root; manually transfer its contents later');g.add_argument('--android-local',action='store_true',help='explicitly confirm this filesystem maps the target phone shared storage')
 p.add_argument('--write',action='store_true');p.add_argument('--overwrite',action='store_true');a=p.parse_args()
 runtime=android_path(a.project_root,p,True);operit=android_path(a.operit_files,p)
 if a.write and a.stage is None and not a.android_local: p.error('--write requires --stage DIR or explicit --android-local; desktop execution does not transfer to a phone')
 base=a.stage.resolve() if a.stage is not None else Path(runtime);target=base/'成品/udp-radar-v1';source=a.source.resolve();payload={}
 if a.stage is not None and (base==ROOT or base in ROOT.parents): p.error('staging root cannot be the repository or its parent')
 for name in FILES:
  f=source/name
  if not f.is_file() or f.is_symlink(): p.error('missing/unsafe source '+name)
  text=f.read_bytes().decode('utf-8')
  if name in ('server.py','runner.sh','启动.sh','停止.sh'): text=text.replace(ORIGINAL,runtime)
  if name=='runner.sh': text=text.replace("OPERIT='"+OPERIT+"'","OPERIT='"+operit+"'")
  payload[name]=text.encode('utf-8')
 for path in (base,target):
  if path.is_symlink(): p.error('target must not be a symlink')
 for name in FILES:
  f=target/name
  if f.is_symlink() or (f.exists() and not f.is_file()): p.error('unsafe existing target '+name)
 differing=[n for n,b in payload.items() if (target/n).is_file() and (target/n).read_bytes()!=b]
 if differing and not a.overwrite: p.error('existing differing files: '+', '.join(differing)+'; stop old session before using --overwrite')
 print(json.dumps({'mode':'stage' if a.stage is not None else ('android-local' if a.android_local else 'preview-only'),'local_target':str(target),'android_project_root':runtime,'files':list(payload),'write':a.write,'transferred':False,'started':False},ensure_ascii=True))
 if not a.write: return 0
 target.mkdir(parents=True,exist_ok=True)
 for name,b in payload.items():
  f=target/name
  if not f.exists() or f.read_bytes()!=b: f.write_bytes(b)
 (base/'日志/udp-radar-v1').mkdir(parents=True,exist_ok=True)
 hashes={n:hashlib.sha256((target/n).read_bytes()).hexdigest() for n in FILES}
 record={'version':'v2.2-names-candidate','files':hashes,'path_adapted':runtime!=ORIGINAL or operit!=OPERIT,'android_project_root':runtime,'transferred':False,'started':False}
 (target/'deployment-manifest.json').write_text(json.dumps(record,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
 return 0
if __name__=='__main__': raise SystemExit(main())
