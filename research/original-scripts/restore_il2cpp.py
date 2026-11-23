from pathlib import Path
import struct, json, hashlib

ROOT = Path('/storage/emulated/0/Download/超自然行动')
SOURCE = ROOT / '文件/lib/arm64-v8a/libil2cpp.so'
OUT = ROOT / '成品/arm64-restored'

class Elf:
    def __init__(self, data):
        self.data = data
        h = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
        self.ph = [struct.unpack_from('<IIQQQQQQ', data, h[5]+i*h[9]) for i in range(h[10])]
        self.loads = [p for p in self.ph if p[0] == 1]
        self.dynamic = {}
        for p in self.ph:
            if p[0] == 2:
                for o in range(p[2], p[2]+p[5], 16):
                    t, v = struct.unpack_from('<qQ', data, o)
                    if t == 0: break
                    self.dynamic[t] = v
        d = self.dynamic
        self.rel = {}
        for o in range(self.off(d[7]), self.off(d[7])+d[8], 24):
            a, info, add = struct.unpack_from('<QQq', data, o)
            kind = info & 0xffffffff
            if kind == 1027:
                self.rel[a] = add
            elif kind == 257:
                so = self.off(d[6])+24*(info >> 32)
                self.rel[a] = add+struct.unpack_from('<Q', data, so+8)[0]
    def off(self, va):
        for p in self.loads:
            if p[3] <= va < p[3]+p[5]: return va-p[3]+p[2]
        raise ValueError('Unmapped VA '+hex(va))
    def q(self, va):
        return self.rel[va] if va in self.rel else struct.unpack_from('<Q', self.data, self.off(va))[0]
    def string(self, va):
        o = self.off(va)
        end = self.data.find(0, o, o+512)
        assert end >= o, ('Unterminated module name', hex(va))
        return self.data[o:end].decode('utf-8', errors='strict')

def main():
    raw = SOURCE.read_bytes()
    data = bytearray(raw)
    elf = Elf(data)
    config = elf.off(0x61e3900)
    assert raw[config:config+15] == b'#U#I#N#F#P#A#F#'
    entry = config+0x14
    sec_va, sec_file, sec_size = struct.unpack_from('<III', raw, entry+16)
    assert (sec_va, sec_file, sec_size) == (0xf74080, 0xf74080, 0x72a0bb)
    # libtprt 0x140058 -> 0x13e6f4 -> 0x1569e8.
    # Vector constants at 0x1900e0/0x190230 extract eight high-to-low nibbles.
    permutation_word = 0x74623015
    permutation = [(permutation_word >> shift) & 15 for shift in range(28, -1, -4)]
    assert sorted(permutation) == list(range(8))
    delta = 0x2000-(sec_va & 0xfff)
    first = sec_file+delta
    body = first+0x10000
    length = sec_size-delta-0x10000
    key = 0x7c
    trans = bytes.maketrans(bytes(range(256)), bytes(x ^ key for x in range(256)))
    full = length//0x10000
    for i in range(full):
        at = body+i*0x10000
        data[at:at+0x4000] = raw[at:at+0x4000].translate(trans)
    for group in range(full//8):
        base = body+group*0x80000
        blocks = [bytes(data[base+i*0x10000:base+i*0x10000+0x4000]) for i in range(8)]
        for i, dest in enumerate(permutation):
            at = base+dest*0x10000
            data[at:at+0x4000] = blocks[i]
    tail = body+full*0x10000
    end = sec_file+sec_size
    data[tail:end] = raw[tail:end].translate(trans)
    images = json.loads((ROOT/'成品/metadata-restored/restore-report.json').read_text(encoding='utf-8'))['images']
    expected = {im['name'] for im in images}
    names = []
    modules = []
    range_records = 0
    for i in range(96):
        m = elf.q(0x5ccd1b0+8*i)
        v = [elf.q(m+8*j) for j in range(17)]
        name = elf.string(v[0])
        assert name in expected, ('Module name mismatch', i, name)
        names.append(name)
        assert 0 <= v[1] < 200000 and 0 <= v[8] < 200000 and 0 <= v[10] < 2000000
        if v[8]:
            at = elf.off(v[9])
            for j in range(v[8]):
                token, start, count = struct.unpack_from('<Iii', data, at+12*j)
                assert token >> 24 in (2, 6), ('RGCTXData token', name, j, hex(token))
                assert 0 <= start <= start+count <= v[10], ('RGCTXData range',name,j,start,count,v[10])
                range_records += 1
        modules.append({'index':i,'name':name,'module_va':hex(m),'methods':v[1],'rgctx_ranges':v[8],'rgctx_entries':v[10]})
    assert len(names) == len(set(names)) == 96 and set(names) == expected
    generic_count = elf.q(0x5a97880)
    generic_at = elf.off(elf.q(0x5a97888))
    specs_count = elf.q(0x5a978a0)
    for i in range(generic_count):
        spec, method, invoker, adjustor = struct.unpack_from('<4i', data, generic_at+16*i)
        assert 0 <= spec < specs_count, ('Generic method spec',i,spec,specs_count)
        assert -1 <= method < elf.q(0x58886e8), ('Generic method pointer index',i,method)
        assert -1 <= invoker < elf.q(0x5888700), ('Invoker index',i,invoker)
    report = {'source':str(SOURCE),'source_sha256':hashlib.sha256(raw).hexdigest(),'scope':'Offline analysis copy: restores sparse XOR and permutation in .rodata body only. Initial AES window and native code sections are not restored. Not an installable or runnable library.','xor_key':hex(key),'xor_basis':'Known module-name ciphertext and strict validation of all 96 module names and RGCTX ranges','permutation':permutation,'permutation_source':'libtprt 0x1569e8 and global +0x60 value 0x74623015','restored_body_file_start':hex(body),'unrestored_initial_aes_file_range':[hex(first),hex(first+0x4000)],'validated_modules':len(names),'validated_rgctx_ranges':range_records,'validated_generic_method_records':generic_count,'modules':modules,'code_registration':'0x58886d8','metadata_registration':'0x5a97860','output_sha256':hashlib.sha256(data).hexdigest()}
    OUT.mkdir(parents=True,exist_ok=True)
    target = OUT/'libil2cpp-analysis.so'
    target.write_bytes(data)
    assert target.stat().st_size == len(raw)
    (OUT/'restore-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['validated_modules','validated_rgctx_ranges','validated_generic_method_records','unrestored_initial_aes_file_range','output_sha256']},ensure_ascii=False))
    print('OUTPUT',str(target))

if __name__ == '__main__':
    main()
