from pathlib import Path
import hashlib, json, re, struct, subprocess
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

P = Path('/storage/emulated/0/Download/超自然行动')
A = P / '成品/hotupdate-static/network-analysis'
OUT = A / 'native-udp'
OUT.mkdir(parents=True, exist_ok=True)
src = P / '文件/lib/arm64-v8a/libjelib.so'
b = src.read_bytes()
assert b[:6] == bytes.fromhex('7f454c460201')
phoff = struct.unpack_from('<Q', b, 32)[0]
phentsize, phnum = struct.unpack_from('<HH', b, 54)
loads = []
for i in range(phnum):
    typ, flags, off, va, pa, size, memsize, align = struct.unpack_from('<IIQQQQQQ', b, phoff + i*phentsize)
    if typ == 1:
        loads.append((va, size, off))
def mapped(va, n):
    for base, size, off in loads:
        if base <= va and va+n <= base+size:
            return b[off+va-base:off+va-base+n]
    raise ValueError(hex(va))
raw = (A / 'libjelib-dynsyms.txt').read_text(encoding='utf-8')
rows=[]
for line in raw.splitlines():
    v=line.split()
    if len(v)>=8 and v[3]=='FUNC' and v[6]!='UND':
        rows.append(dict(va=int(v[1],16),size=int(v[2]),name=v[7]))
r=subprocess.run(['c++filt'],input='\n'.join(x['name'] for x in rows),text=True,capture_output=True,check=True)
for x,n in zip(rows,r.stdout.splitlines()): x['demangled']=n
by_va={}
for x in rows: by_va.setdefault(x['va'],x['demangled'])
(A/'libjelib-symbol-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
want=('JeUdpClient::Connect(', 'JeUdpClient::SendInitFlag(', 'JeUdpClient::SendCookieFlag(', 'JeUdpClient::udpParse(', 'JeUdpClient::AsyncSend(', 'JeUdpClient::msgParse(')
md=Cs(CS_ARCH_ARM64,CS_MODE_ARM)
selected=[]
for x in rows:
    if not x['demangled'].startswith(want): continue
    lines=[x['demangled'],f"ELF VA=0x{x['va']:x} SIZE={x['size']}"]
    for i in md.disasm(mapped(x['va'],x['size']),x['va']):
        note=''
        if i.mnemonic in ('bl','b') and i.op_str.startswith('#0x'):
            target=int(i.op_str[1:],16)
            note=' ; '+by_va.get(target,'unresolved_target')
        lines.append(f'{i.address:08x}: {i.mnemonic:8s} {i.op_str}{note}')
    dest=OUT/(f"{x['va']:08x}.asm.txt")
    dest.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    selected.append(dict(x,output=str(dest.relative_to(P))))
manifest=dict(source=str(src.relative_to(P)),sha256=hashlib.sha256(b).hexdigest(),functions=selected)
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'disassembled':[(hex(x['va']),x['size'],x['demangled']) for x in selected], 'message_symbols':[x['demangled'] for x in rows if re.search(r'cmdmsg::.*(?:[Vv]ector|[Pp]os|[Mm]ove|[Cc]ookie|[Kk]ey|[Ll]ogin)',x['demangled'])][:28]},ensure_ascii=False))
