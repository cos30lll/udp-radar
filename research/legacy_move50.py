#!/usr/bin/env python3
"""Offline only. No sockets, process attachment, packet sending or capture.
Input: application message (BE16 module + BE16 command + body), or a
verified movement body. This is NOT a generic Protocol Buffers decoder.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT = Path.cwd().resolve()
MAX_INPUT = 16 * 1024 * 1024
MAX_FIELDS = 200000
MAX_ITEMS = 20000

class DecodeError(ValueError):
    pass

class Reader:
    def __init__(self, data):
        self.data = memoryview(data)
        self.pos = 0
        self.fields = 0

    def varint(self):
        value = 0
        for shift in range(0, 70, 7):
            if self.pos >= len(self.data):
                raise DecodeError('truncated varint at byte %d' % self.pos)
            byte = self.data[self.pos]
            self.pos += 1
            if shift == 63 and byte > 1:
                raise DecodeError('varint exceeds uint64')
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise DecodeError('overlong varint')

    def tag(self):
        self.fields += 1
        if self.fields > MAX_FIELDS:
            raise DecodeError('field count limit exceeded')
        start = self.pos
        tag = self.varint()
        field, wire = tag >> 3, tag & 7
        if field == 0 or wire in (3, 4, 6, 7):
            raise DecodeError('unsupported field tag at byte %d: %d' % (start, tag))
        return start, field, wire

    def expect(self, actual, expected):
        if actual != expected:
            raise DecodeError('unexpected wire type %d; expected %d at byte %d' % (actual, expected, self.pos))

    def block(self):
        length = self.varint()
        if length > len(self.data) - self.pos:
            raise DecodeError('length-delimited field exceeds message boundary')
        start = self.pos
        self.pos += length
        return self.data[start:self.pos]

    def unknown(self, field, wire, start):
        # Deliberately do not guess unknown fixed32/fixed64 semantics.
        if wire == 0:
            value = self.varint()
            return {'field': field, 'wire': wire, 'offset': start, 'varint': value}
        if wire == 2:
            value = self.block()
            return {'field': field, 'wire': wire, 'offset': start, 'length': len(value), 'prefix_hex': bytes(value[:24]).hex()}
        raise DecodeError('unknown wire=%d field=%d; refusing to guess custom width' % (wire, field))

    def remaining(self):
        return self.pos < len(self.data)

def uint(value, bits):
    if value >= 1 << bits:
        raise DecodeError('integer exceeds uint%d' % bits)
    return value

def vector(data, existing=None):
    r = Reader(data)
    out = dict(existing) if existing is not None else {'x': 0.0, 'y': 0.0, 'z': 0.0}
    unknown = list(out.get('unknown_fields', []))
    while r.remaining():
        start, field, wire = r.tag()
        if field in (1, 2, 3):
            r.expect(wire, 5)
            n = uint(r.varint(), 32)  # Verified custom wire=5 VARINT, not fixed32.
            out[('x', 'y', 'z')[field - 1]] = ((n >> 1) ^ -(n & 1)) / 100.0
        else:
            unknown.append(r.unknown(field, wire, start))
    if unknown:
        out['unknown_fields'] = unknown
    return out

def move(data):
    r = Reader(data)
    out = {'lookup_id': 0, 'position': {'x': 0.0, 'y': 0.0, 'z': 0.0},
           'velocity': {'x': 0.0, 'y': 0.0, 'z': 0.0},
           'field4_uint16': 0, 'field5_bool': False, 'field6_bool': False,
           'present_fields': [], 'unknown_fields': []}
    seen = set()
    while r.remaining():
        start, field, wire = r.tag()
        seen.add(field)
        if field in (2, 3):
            r.expect(wire, 2)
            key = 'position' if field == 2 else 'velocity'
            out[key] = vector(r.block(), out[key])
        elif field in (1, 4, 5, 6):
            r.expect(wire, 0)
            value = r.varint()
            if field == 1:
                out['lookup_id'] = uint(value, 32)
            elif field == 4:
                out['field4_uint16'] = uint(value, 16)
            else:
                out['field%d_bool' % field] = bool(value)
        else:
            out['unknown_fields'].append(r.unknown(field, wire, start))
    out['present_fields'] = sorted(seen)
    return out

def batch(data):
    r = Reader(data)
    out = {'message_type': 'MNEHOHLMOCB', 'items': [], 'unknown_fields': []}
    while r.remaining():
        start, field, wire = r.tag()
        if field == 1:
            r.expect(wire, 2)
            if len(out['items']) >= MAX_ITEMS:
                raise DecodeError('movement item limit exceeded')
            out['items'].append(move(r.block()))
        else:
            out['unknown_fields'].append(r.unknown(field, wire, start))
    out['count'] = len(out['items'])
    return out

def application(data):
    if len(data) < 4:
        raise DecodeError('application header requires four bytes')
    module = int.from_bytes(data[:2], 'big')
    command = int.from_bytes(data[2:4], 'big')
    out = {'module': module, 'command': command, 'body_bytes': len(data) - 4}
    if (module, command) == (3, 50):
        out['decoded'] = batch(memoryview(data)[4:])
    else:
        out['decoded'] = None
        out['note'] = 'Not mapped by this decoder. Command names alone do not prove message structure.'
    return out

def bounded_file(path, binary=True):
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_relative_to(PROJECT):
        raise DecodeError('keep input files inside project directory: ' + str(PROJECT))
    if path.stat().st_size > (MAX_INPUT if binary else MAX_INPUT * 3):
        raise DecodeError('input exceeds size limit')
    return path, path.read_bytes()

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--input', help='binary file inside project directory')
    src.add_argument('--hex', help='one hexadecimal message, not a packet capture')
    src.add_argument('--hex-file', help='UTF-8 hexadecimal text file inside project directory')
    ap.add_argument('--kind', choices=('app', 'batch-body', 'move-body', 'vector-body'), default='app')
    ap.add_argument('--output', help='optional new JSON file inside project directory; never overwrites')
    ap.add_argument('--workspace', type=Path, default=Path.cwd(), help='local private input/output root, default current directory')
    args = ap.parse_args(argv)
    global PROJECT
    PROJECT = args.workspace.resolve()
    try:
        origin = 'command-line hexadecimal input'
        if args.input:
            path, raw = bounded_file(args.input)
            origin = str(path)
        else:
            if args.hex_file:
                path, text = bounded_file(args.hex_file, False)
                origin = str(path)
                text = text.decode('utf-8-sig')
            else:
                text = args.hex
            if len(text) > MAX_INPUT * 3:
                raise DecodeError('hexadecimal input exceeds size limit')
            raw = bytes.fromhex(text)
        if len(raw) > MAX_INPUT:
            raise DecodeError('input exceeds size limit')
        parse = {'app': application, 'batch-body': batch, 'move-body': move, 'vector-body': vector}[args.kind]
        result = {'source': origin, 'input_kind': args.kind, 'input_bytes': len(raw),
                  'sha256': hashlib.sha256(raw).hexdigest(), 'result': parse(raw),
                  'validation': 'static-code-derived; no real captured message validated in this project',
                  'scope': 'No UDP header removal, packet reassembly, Zstd decompression, key extraction or networking.'}
        text = json.dumps(result, ensure_ascii=True, indent=2) + chr(10)
        if args.output:
            target = Path(args.output).expanduser().resolve()
            if not target.is_relative_to(PROJECT):
                raise DecodeError('output must stay inside project directory')
            if not target.parent.is_dir():
                raise DecodeError('output parent directory does not exist')
            with target.open('x', encoding='utf-8') as f:
                f.write(text)
            print(str(target))
        else:
            print(text, end='')
        return 0
    except (DecodeError, ValueError, OSError, UnicodeError) as exc:
        print('decode error: ' + str(exc), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
