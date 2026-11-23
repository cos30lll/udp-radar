#!/usr/bin/env python3
import argparse, hashlib, json, struct, subprocess
from pathlib import Path
def main():
    p=argparse.ArgumentParser(description='Recreate selected native UDP evidence from your own arm64 libjelib.so.')
    p.add_argument('--so',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);raw=a.so.read_bytes()
    if raw[:6]!=bytes.fromhex('7f454c460201'):p.error('need ELF64 little-endian')
    if struct.unpack_from('<H',raw,18)[0]!=183:p.error('need AArch64 ELF')
    ph=struct.unpack_from('<Q',raw,32)[0];step,count=struct.unpack_from('<HH',raw,54);loads=[]
    for i in range(count):
        typ,flags,offset,va,pa,size,mem,align=struct.unpack_from('<IIQQQQQQ',raw,ph+i*step)
        if typ==1:loads.append((va,size,offset))
    def mapped(va,size):
        for base,limit,offset in loads:
            if base<=va and va+size<=base+limit:return raw[offset+va-base:offset+va-base+size]
        raise ValueError('unmapped VA '+hex(va))
    result=subprocess.run(['readelf','--dyn-syms','--wide',str(a.so)],check=True,capture_output=True,text=True)
    rows=[]
    for line in result.stdout.splitlines():
        values=line.split()
        if len(values)>=8 and values[3]=='FUNC' and values[6]!='UND':
            try:rows.append({'va':int(values[1],16),'size':int(values[2]),'name':values[7]})
            except ValueError:pass
    demangled=subprocess.run(['c++filt'],input='\n'.join(x['name'] for x in rows),check=True,capture_output=True,text=True).stdout.splitlines()
    for row,name in zip(rows,demangled):row['demangled']=name
    from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
    md=Cs(CS_ARCH_ARM64,CS_MODE_ARM);chosen=[]
    wanted=('JeUdpClient::Connect(','JeUdpClient::AsyncSend(','JeUdpClient::udpParse(','JeUdpClient::msgParse(','JeUdpClient::RecvLoop(','JeUdpClient::GetMsg(','JeMsgQueue::PushMsg(','JeUdpSocket::recvfrom(')
    for row in rows:
        if not row['demangled'].startswith(wanted) or not row['size']:continue
        name=f"{row['va']:08x}.asm.txt"
        lines=[row['demangled']]+[f'{v.address:08x}: {v.mnemonic:8s} {v.op_str}' for v in md.disasm(mapped(row['va'],row['size']),row['va'])]
        (out/name).write_text('\n'.join(lines)+'\n', encoding='utf-8');chosen.append(dict(row,output=name))
    (out/'manifest.json').write_text(json.dumps({'input_sha256':hashlib.sha256(raw).hexdigest(),'functions':chosen},indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'functions':len(chosen),'output':str(out)}))
if __name__=='__main__':main()
