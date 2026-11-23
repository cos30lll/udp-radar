#!/usr/bin/env python3
"""Fixed-version offline restoration. IL2CPP requires a prior metadata restore report."""
import argparse, ast, hashlib, json, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
EXPECTED={'metadata':'8bbd886ba5c332bff9bdd236457cc1bc06e86271831901c04a96bb1d0aed02d5','il2cpp':'9da0a892e2630254a54cb09867b4edba55782f49673122a761903e30512ea2a6'}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('kind',choices=EXPECTED);p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--metadata-report',type=Path,help='required for il2cpp: prior metadata restore-report.json');a=p.parse_args()
 source=a.input.resolve(strict=True);out=a.output.resolve()
 if not source.is_file() or source.is_relative_to(out): p.error('input must be a file outside output')
 if hashlib.sha256(source.read_bytes()).hexdigest()!=EXPECTED[a.kind]: p.error('different game input SHA256; fixed offsets cannot be reused')
 if out.exists() and (not out.is_dir() or any(out.iterdir())): p.error('output must be an empty/new directory')
 dependency=None
 if a.kind=='il2cpp':
  if a.metadata_report is None: p.error('il2cpp requires --metadata-report from the prior metadata restoration')
  dependency=a.metadata_report.resolve(strict=True)
  if dependency.is_relative_to(out): p.error('metadata report must be outside output')
  report=json.loads(dependency.read_text(encoding='utf-8'))
  if report.get('source_sha256')!=EXPECTED['metadata'] or not isinstance(report.get('images'),list) or not report['images']: p.error('metadata report does not describe the fixed input/images')
 elif a.metadata_report is not None: p.error('--metadata-report applies only to il2cpp')
 sys.dont_write_bytecode=True
 f=HERE/'original-scripts'/('restore_metadata.py' if a.kind=='metadata' else 'restore_il2cpp.py')
 tree=ast.parse(f.read_text(encoding='utf-8'));values={'ROOT':str(out),'SOURCE':str(source),'OUT':str(out)}
 for node in tree.body:
  if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in values:
   node.value=ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(values[node.targets[0].id])],keywords=[])
 if dependency:
  matches=0
  for node in ast.walk(tree):
   if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='read_text' and isinstance(node.func.value,ast.BinOp) and isinstance(node.func.value.left,ast.Name) and node.func.value.left.id=='ROOT' and isinstance(node.func.value.right,ast.Constant) and node.func.value.right.value=='成品/metadata-restored/restore-report.json':
    node.func.value=ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(dependency))],keywords=[]);matches+=1
  if matches!=1: raise RuntimeError('restore source dependency pattern changed; do not guess')
 out.mkdir(parents=True,exist_ok=True);ast.fix_missing_locations(tree);exec(compile(tree,str(f),'exec'),{'__name__':'__main__'})
 return 0
if __name__=='__main__': raise SystemExit(main())
