from pathlib import Path
import hashlib, json, os

p = Path('/storage/emulated/0/Download/超自然行动')
os.environ['TMPDIR'] = str(p / '临时/sidecar-export-v1')
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import UnityPy

src = next((p / '文件/assets/android/data/code').glob('updatescript*'))
out = p / '成品/hotupdate-static'
out.mkdir(parents=True, exist_ok=True)
env = UnityPy.load(str(src))
rows = []
for obj in env.objects:
    row = {'path_id': obj.path_id, 'type': obj.type.name}
    if obj.type.name == 'TextAsset':
        data = obj.read()
        row['name'] = data.m_Name
        raw = data.m_Script
        if isinstance(raw, str):
            raw = raw.encode('utf-8', 'surrogateescape')
        else:
            raw = bytes(raw)
        row.update(size=len(raw), magic_hex=raw[:16].hex(), sha256=hashlib.sha256(raw).hexdigest())
        name = Path(data.m_Name.replace('\\', '/')).name
        if not name or name in ('.', '..'):
            name = 'asset-' + str(obj.path_id)
        if raw.startswith(b'MZ') and not name.lower().endswith('.dll'):
            name += '.dll'
        dest = out / name
        if dest.exists():
            assert dest.read_bytes() == raw, str(dest)
        else:
            with dest.open('xb') as f:
                f.write(raw)
        row['output'] = str(dest.relative_to(p))
    rows.append(row)
manifest = out / 'asset-manifest.json'
text = json.dumps({'source': str(src.relative_to(p)), 'objects': rows}, ensure_ascii=False, indent=2) + '\n'
manifest.write_text(text, encoding='utf-8')
print(json.dumps({'object_count': len(rows), 'text_assets': [x for x in rows if x['type'] == 'TextAsset']}, ensure_ascii=False))
