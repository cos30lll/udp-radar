#!/usr/bin/env python3
import argparse, ast, hashlib, os, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
EXPECTED={'metadata':'8bbd886ba5c332bff9bdd236457cc1bc06e86271831901c04a96bb1d0aed02d5','il2cpp':'9da0a892e2630254a54cb09867b4edba55782f49673122a761903e30512ea2a6'}
def main():
    p=argparse.ArgumentParser(description='Run the fixed-version restoration source against an explicit local file; no game modification.')
    p.add_argument('kind',choices=EXPECTED);p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();source=a.input.resolve(strict=True);out=a.output.resolve()
    if source.is_relative_to(out):p.error('input cannot be inside output directory')
    h=hashlib.sha256(source.read_bytes()).hexdigest()
    if h!=EXPECTED[a.kind]:p.error('different game input SHA256; do not reuse fixed offsets on other builds')
    if out.exists() and any(out.iterdir()):p.error('output must be empty to preserve existing artifacts')
    out.mkdir(parents=True,exist_ok=True);os.environ['PYTHONDONTWRITEBYTECODE']='1';sys.dont_write_bytecode=True
    f=HERE/'original-scripts'/('restore_metadata.py' if a.kind=='metadata' else 'restore_il2cpp.py')
    tree=ast.parse(f.read_text(encoding='utf-8'));values={'ROOT':str(out),'SOURCE':str(source),'OUT':str(out)}
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in values:
            node.value=ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(values[node.targets[0].id])],keywords=[])
    ast.fix_missing_locations(tree);exec(compile(tree,str(f),'exec'),{'__name__':'__main__'})
if __name__=='__main__':main()
