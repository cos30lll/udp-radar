#!/usr/bin/env python3
"""Local release integrity plus limited privacy heuristics; never uploads."""
import argparse
import hashlib
import json
import os
import re
import stat
import zipfile
from pathlib import Path
RUNTIME = ('protocol.py','identity.py','server.py','app.js','index.html','style.css','runner.sh','启动.sh','停止.sh')
TEXT_EXT = {'.py','.js','.css','.html','.md','.json','.txt','.sh','.cs','.csproj','.xml','.yml','.yaml'}
TEXT_NAMES = {'LICENSE','.gitignore','.gitattributes'}
PRIVATE_DIRS = {'input','private','work','logs','日志','临时','build','__pycache__','.venv','bin','obj','.pytest_cache'}
FORBIDDEN_EXT = {'.pcap','.pcapng','.apk','.aab','.so','.dll','.dat','.csv','.tsv','.jsonl','.ndjson','.log','.pyc','.pyo','.pem','.key','.pfx','.p12','.zip','.7z','.tar','.gz','.exe','.bin','.o','.a','.pdb','.db','.sqlite','.dmp'}
ALLOW_IPS = {'127.0.0.1','0.0.0.0','255.255.255.255','192.0.2.1','198.51.100.1','203.0.113.1','1.35.20.001'}
PUBLIC_PATH = '/storage/emulated/0/Download/超自然行动'
MAX_BYTES = 2 * 1024 * 1024
RULES = {
 'session-reference': re.compile(r'日志/udp-radar-v1/\d{8}-\d{6}-\d+'),
 'ipv4-review': re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])'),
 'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b'),
 'private-key': re.compile(r'BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY'),
 'json-uid': re.compile(r'"uid"\s*:\s*"?\d{5,}'),
 'json-name-review': re.compile(r'"name"\s*:\s*"[^"\n]{1,32}"'),
 'device-path-review': re.compile(r'/(?:storage/emulated/0|sdcard)/[A-Za-z0-9_\u4e00-\u9fff.-]+(?:/[A-Za-z0-9_\u4e00-\u9fff.-]+)*'),
}
def safe_name(name):
 return isinstance(name,str) and bool(name) and not name.startswith('/') and not any(c in name for c in ('\\',':')) and all(x not in ('','.','..') for x in name.split('/')) and all(ord(c)>=32 for c in name)
def digest(p):
 return hashlib.sha256(p.read_bytes()).hexdigest()
def load_json(p, errors):
 try: return json.loads(p.read_text(encoding='utf-8'))
 except (OSError,ValueError,UnicodeError):
  errors.append('missing/invalid JSON: '+p.name);return None
def check_zip(path, root, actual, errors):
 try:
  with zipfile.ZipFile(path) as z:
   infos=z.infolist();seen=set();found=set()
   if len(infos)>5000: errors.append('too many archive entries');return
   for i in infos:
    name=i.filename;trim=name[:-1] if i.is_dir() else name
    if name in seen: errors.append('duplicate ZIP entry: '+name);continue
    seen.add(name)
    if not safe_name(trim) or stat.S_ISLNK(i.external_attr>>16): errors.append('unsafe ZIP entry: '+name);continue
    if any(ord(c)>127 for c in name) and not (i.flag_bits & 0x800): errors.append('ZIP filename lacks UTF-8 flag: '+name)
    if i.is_dir() and trim==root.name: continue
    prefix=root.name+'/'
    if not name.startswith(prefix): errors.append('unexpected ZIP root: '+name);continue
    if i.is_dir(): continue
    rel=name[len(prefix):];found.add(rel)
    if rel not in actual: errors.append('unexpected ZIP file: '+rel);continue
    p=actual[rel]
    if i.file_size!=p.stat().st_size or i.file_size>MAX_BYTES: errors.append('ZIP size mismatch: '+rel);continue
    if z.read(i)!=p.read_bytes(): errors.append('ZIP content mismatch: '+rel)
   for rel in sorted(set(actual)-found): errors.append('missing ZIP file: '+rel)
 except (OSError,ValueError,RuntimeError,zipfile.BadZipFile,NotImplementedError) as exc:
  errors.append('cannot verify ZIP: '+type(exc).__name__)
def audit(root, archive=None):
 errors=[];warnings=[];actual={}
 if not root.is_dir(): return {'ok':False,'problems':['missing release root'],'warnings':[]}
 for directory,dirs,files in os.walk(root,followlinks=False):
  base=Path(directory)
  for name in list(dirs):
   path=base/name;rel=path.relative_to(root).as_posix()
   if path.is_symlink(): errors.append('symlink directory: '+rel);dirs.remove(name)
   elif name=='.git': dirs.remove(name)
   elif name in PRIVATE_DIRS: errors.append('private/generated directory in release: '+rel);dirs.remove(name)
  for name in files:
   path=base/name;rel=path.relative_to(root).as_posix()
   if rel=='.git': continue
   if path.is_symlink() or not path.is_file(): errors.append('non-regular release file: '+rel);continue
   actual[rel]=path
   if path.suffix.lower() in FORBIDDEN_EXT or re.search(r'\.pcap\d+$',name,re.I) or name=='.env' or name.startswith('.env.'):
    errors.append('forbidden artifact: '+rel);continue
   if path.suffix.lower() not in TEXT_EXT and name not in TEXT_NAMES: errors.append('unknown file type: '+rel);continue
   if path.stat().st_size>MAX_BYTES: errors.append('oversized release text: '+rel);continue
   try: text=path.read_text(encoding='utf-8')
   except (OSError,UnicodeError): errors.append('unreadable/non-UTF-8 text: '+rel);continue
   if '\x00' in text: errors.append('binary content in text: '+rel)
   for rule,pattern in RULES.items():
    for m in pattern.finditer(text):
     value=m.group(0)
     if rule=='ipv4-review' and value in ALLOW_IPS: continue
     if rule=='device-path-review' and (value==PUBLIC_PATH or value.startswith(PUBLIC_PATH+'/')): continue
     errors.append('{} at {}:{} (value redacted)'.format(rule,rel,text.count('\n',0,m.start())+1))
 for name in ('README.md','LICENSE','AGENTS.md','SOURCE_ORIGIN.json'):
  if name not in actual: errors.append('missing required file: '+name)
 m=load_json(root/'FILES_SHA256.json',errors);entries=m.get('files') if isinstance(m,dict) else None
 if not isinstance(entries,dict) or not entries: errors.append('invalid/empty release manifest')
 else:
  for rel,want in entries.items():
   if not safe_name(rel) or rel=='FILES_SHA256.json' or '.git' in rel.split('/'): errors.append('invalid manifest path');continue
   if not isinstance(want,str) or not re.fullmatch('[0-9a-f]{64}',want): errors.append('invalid manifest hash: '+rel)
   elif rel not in actual: errors.append('missing manifest file: '+rel)
   elif digest(actual[rel])!=want: errors.append('manifest hash mismatch: '+rel)
  for rel in sorted(set(actual)-set(entries)-{'FILES_SHA256.json'}): errors.append('file absent from manifest: '+rel)
 o=load_json(root/'SOURCE_ORIGIN.json',errors);origin=o.get('runtime_files_sha256') if isinstance(o,dict) else None
 if not isinstance(origin,dict): errors.append('missing original runtime hashes');origin={}
 for name in RUNTIME:
  a=root/'src'/name;b=root/'dist/udp-radar-v2.2'/name
  if not a.is_file() or not b.is_file() or a.is_symlink() or b.is_symlink(): errors.append('missing/unsafe runtime file: '+name);continue
  if a.read_bytes()!=b.read_bytes(): errors.append('src/dist mismatch: '+name)
  if digest(a)!=origin.get(name): errors.append('runtime origin mismatch: '+name)
 if archive is not None: check_zip(archive,root,actual,errors)
 warnings.append('Limited heuristics only; manually review privacy, Git index/history, licensing and actual device behavior.')
 return {'ok':not errors,'problems':sorted(set(errors)),'warnings':warnings,'files_checked':len(actual),'runtime_files':len(RUNTIME),'archive_checked':archive is not None,'git_history_checked':False}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',nargs='?',type=Path,default=Path('.'));p.add_argument('--archive',type=Path);p.add_argument('--json',action='store_true');a=p.parse_args()
 try: report=audit(a.root.resolve(),a.archive)
 except OSError as exc: report={'ok':False,'problems':['filesystem check failed: '+type(exc).__name__],'warnings':[]}
 if a.json: print(json.dumps(report,ensure_ascii=True,indent=2))
 else:
  print('OK' if report['ok'] else 'FAILED')
  for key in ('problems','warnings'):
   for item in report[key]: print(key.upper(),item)
 return 0 if report['ok'] else 1
if __name__=='__main__': raise SystemExit(main())
