from pathlib import Path
import hashlib, json, struct

ROOT = Path('/storage/emulated/0/Download/超自然行动')
SOURCE = ROOT / '文件/assets/bin/Data/Managed/Metadata/global-metadata.dat'
OUT = ROOT / '成品/metadata-restored'
NAMES = 'stringLiterals stringLiteralData strings events properties methods parameterDefaults fieldDefaults defaultData fieldMarshaledSizes parameters fields genericParameters genericConstraints genericContainers nestedTypes interfaces vtableMethods interfaceOffsets typeDefinitions images assemblies fieldRefs referencedAssemblies attributeData attributeDataRanges unresolvedCallTypes unresolvedCallRanges windowsRuntimeTypes windowsRuntimeStrings exportedTypes'.split()
XOR_TABLES = {0, 1, 9, 11, 14, 15, 22, 23, 24, 25, 27, 30}
STRIDES = {0:8,3:24,4:20,5:36,6:12,7:12,9:12,10:12,11:12,12:16,13:4,14:16,15:4,16:4,17:4,18:8,19:88,20:40,21:64,22:8,23:4,25:8,26:4,27:8,28:8,30:4}

def main():
    raw = SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '8bbd886ba5c332bff9bdd236457cc1bc06e86271831901c04a96bb1d0aed02d5', 'Source differs from inspected metadata'
    restored = bytearray(raw)
    # Observed file-level encoding: first 0x1000 bytes, then [0x1000,0x5000) in every 0x10000-byte block.
    intervals = [(0, min(0x1000, len(raw)))]
    intervals += [(base + 0x1000, min(base + 0x5000, len(raw))) for base in range(0, len(raw), 0x10000) if base + 0x1000 < len(raw)]
    for begin, end in intervals:
        restored[begin:end] = bytes(v ^ 0x66 for v in raw[begin:end])
    pairs = list(struct.iter_unpack('<II', restored[8:256]))
    assert len(pairs) == len(NAMES) == 31
    last = 256
    report = {'source':str(SOURCE), 'source_sha256':hashlib.sha256(raw).hexdigest(), 'version_candidate':31, 'version_basis':'Method records have returnParameterToken and 36-byte stride; 256-byte header; Unity 2022.3.62f3 marker', 'tables':[]}
    for i, (start, size) in enumerate(pairs):
        assert start >= last and start + size <= len(raw), ('Bad table boundary', i)
        if i in STRIDES:
            assert size % STRIDES[i] == 0, ('Bad table stride', i, size, STRIDES[i])
        last = start + size
        encoded_bytes = sum(max(0, min(start+size, end)-max(start, begin)) for begin, end in intervals)
        report['tables'].append({'index':i,'name':NAMES[i],'offset':start,'bytes':size,'xor66_bytes':encoded_bytes,'records':size//STRIDES[i] if i in STRIDES else None})
    assert last == len(raw)
    struct.pack_into('<II', restored, 0, 0xFAB11BAF, 31)
    sa, ss = pairs[2]
    strings = restored[sa:sa+ss]
    def string(i):
        assert 0 <= i < ss, ('String index', i)
        end = strings.find(0, i)
        assert end >= i
        return strings[i:end].decode('utf-8', errors='strict')
    for idx, stride, name_indices, token_at, prefix in [(3,24,[0],20,0x14),(4,20,[0],16,0x17),(5,36,[0],24,0x06),(10,12,[0],4,0x08),(11,12,[0],8,0x04),(19,88,[0,4],84,0x02),(20,40,[0],28,None)]:
        start,size = pairs[idx]
        for offset in range(start, start+size, stride):
            for ni in name_indices:
                string(struct.unpack_from('<I', restored, offset+ni)[0])
            token = struct.unpack_from('<I',restored,offset+token_at)[0]
            assert prefix is None or token >> 24 == prefix, ('Token',idx,(offset-start)//stride,hex(token))
    type_count = pairs[19][1]//88
    method_count = pairs[5][1]//36
    field_count = pairs[11][1]//12
    parameter_count = pairs[10][1]//12
    for ti in range(type_count):
        offset = pairs[19][0]+ti*88
        starts = struct.unpack_from('<8i',restored,offset+32)
        counts = struct.unpack_from('<8H',restored,offset+64)
        for start,count,table,stride in [(starts[0],counts[2],11,12),(starts[1],counts[0],5,36),(starts[2],counts[3],3,24),(starts[3],counts[1],4,20),(starts[4],counts[4],15,4),(starts[5],counts[6],16,4),(starts[6],counts[5],17,4),(starts[7],counts[7],18,8)]:
            assert count == 0 or 0 <= start <= start+count <= pairs[table][1]//stride, ('Member range',ti,table,start,count)
        if counts[0]:
            for mi in range(starts[1],starts[1]+counts[0]):
                mo = pairs[5][0]+mi*36
                assert struct.unpack_from('<i',restored,mo+4)[0] == ti, ('Method owner',ti,mi)
    for mi in range(method_count):
        offset=pairs[5][0]+mi*36
        ps=struct.unpack_from('<i',restored,offset+16)[0]
        pc=struct.unpack_from('<H',restored,offset+34)[0]
        assert pc == 0 or 0 <= ps <= ps+pc <= parameter_count, ('Parameters',mi,ps,pc)
    images=[]
    for offset in range(pairs[20][0],sum(pairs[20]),40):
        v=struct.unpack_from('<10I',restored,offset)
        assert v[2]+v[3] <= type_count
        images.append({'name':string(v[0]),'type_start':v[2],'type_count':v[3]})
    report.update({'types':type_count,'methods':method_count,'fields':field_count,'parameters':parameter_count,'images':images,'restored_sha256':hashlib.sha256(restored).hexdigest(),'validation':'All header boundaries, declared table strides, member names and token prefixes, type-member ownership and parameter ranges checked. Binary registration and code addresses still require dumper validation.'})
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'global-metadata.dat'
    target.write_bytes(restored)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == report['restored_sha256']
    (OUT/'restore-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'restored':str(target),'types':type_count,'methods':method_count,'fields':field_count,'parameters':parameter_count,'images':len(images),'main_image':next((i for i in images if i['name']=='Assembly-CSharp.dll'),None),'restored_sha256':report['restored_sha256']},ensure_ascii=False))

if __name__ == '__main__':
    main()