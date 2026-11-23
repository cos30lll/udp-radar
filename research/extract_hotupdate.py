#!/usr/bin/env python3
import argparse, hashlib, json, os, sys
from pathlib import Path
def main():
    p=argparse.ArgumentParser(description='Extract TextAssets from your own UnityFS update bundle; original game files are not redistributed.')
    p.add_argument('--bundle',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if a.bundle.resolve().is_relative_to(out):p.error('bundle cannot be inside output')
    tmp=out/'tmp';tmp.mkdir(exist_ok=True);os.environ['TMPDIR']=str(tmp);sys.dont_write_bytecode=True
    import UnityPy
    rows=[]
    for obj in UnityPy.load(str(a.bundle)).objects:
        if obj.type.name!='TextAsset':continue
        v=obj.read();raw=v.m_Script;raw=raw.encode('utf-8','surrogateescape') if isinstance(raw,str) else bytes(raw)
        name=Path(v.m_Name.replace(chr(92),'/')).name
        if not name or name in ('.','..'):name='asset-'+str(obj.path_id)
        if raw.startswith(b'MZ') and not name.lower().endswith('.dll'):name+='.dll'
        target=out/name
        if target.exists() and target.read_bytes()!=raw:p.error('conflicting extraction name '+name)
        if not target.exists():target.write_bytes(raw)
        rows.append({'path_id':obj.path_id,'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'managed_pe_candidate':raw.startswith(b'MZ')})
    (out/'asset-manifest.json').write_text(json.dumps({'bundle_sha256':hashlib.sha256(a.bundle.read_bytes()).hexdigest(),'text_assets':rows},ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'text_assets':len(rows),'managed_pe_candidates':[x['name'] for x in rows if x['managed_pe_candidate']]}))
if __name__=='__main__':main()
