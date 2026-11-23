#!/usr/bin/env python3
"""Offline PCAP study: discovery statistics, selected app bytes, and schema-free fields.
Outputs may contain private data. No sockets, live capture, game or process access.
Uses the published runtime's transport helpers; it is not a version-independent decoder.
"""
import argparse
import collections
import hashlib
import json
import os
import struct
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))


def same_path(a, b):
    return a.resolve() == b.resolve() or (a.exists() and b.exists() and os.path.samefile(a, b))


def fresh_output(path, inputs):
    if path is None:
        return
    if path.exists() or path.is_symlink() or any(same_path(path, p) for p in inputs):
        raise ValueError('output must be a new path, distinct from every input')


def write_json(path, value):
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as out:
            out.write(json.dumps(value, ensure_ascii=True, indent=2) + '\n')
    print(json.dumps(value, ensure_ascii=True, indent=2))


def local_ports(value):
    result = {int(x) for x in value.split(',')}
    if not result or not all(0 < x < 65536 for x in result):
        raise ValueError('ports must be confirmed LOCAL ports in 1..65535')
    return result


def applications(args):
    from protocol import Decoder, PcapTail, ProtocolError, UnsupportedIPFragment, transport_checksum, transport_segments, udp
    from replay_pcap import inspect_pcap
    ports = local_ports(args.ports)
    if not args.pcap.is_file():
        raise ValueError('PCAP input not found')
    report_path = args.summary
    selected = getattr(args, 'output', None)
    for path in (report_path, selected):
        fresh_output(path, [args.pcap])
    if report_path and selected and same_path(report_path, selected):
        raise ValueError('summary and selected app outputs must be distinct')
    shape = inspect_pcap(args.pcap)
    if not shape['input_complete']:
        raise ValueError(shape['input_error'])
    reader, transport = PcapTail(args.pcap), Decoder(ports)
    counts, commands, flows = collections.Counter(), collections.Counter(), collections.Counter()
    matches = 0
    saved = False
    last_error_type = None
    wanted = tuple(map(int, args.message.split('/'))) if args.command == 'extract' else None
    if wanted is not None and (len(wanted) != 2 or not all(0 <= n < 65536 for n in wanted)):
        raise ValueError('--message must be module/command, two UInt16 values')
    try:
        while True:
            records = list(reader.poll(2000))
            if not records:
                break
            for timestamp, ordinal, link, frame in records:
                counts['pcap_records'] += 1
                try:
                    packet = udp(link, frame)
                    if packet is None:
                        counts['non_udp_or_unsupported_ip_extensions'] += 1
                        continue
                    src, sp, dst, dp, packet_type, body = packet
                    if dp in ports and sp not in ports and packet_type != 4:
                        direction, local = 'in', dp
                    elif sp in ports and dp not in ports:
                        direction, local = 'out', sp
                    else:
                        counts['other_or_ambiguous_ports'] += 1
                        continue
                    flows[(direction, local)] += 1
                    if args.direction != 'both' and direction != args.direction:
                        continue
                    counts[direction + '_udp'] += 1
                    transport.expire_fragments(timestamp)
                    # The fixed upstream sample uses a 14-byte envelope, sequence at 6.
                    # Only inbound coalescing/reassembly is supported by runtime helpers.
                    pieces = transport_segments(body) if direction == 'in' else [body]

                    if len(pieces) > 1:
                        counts['coalesced_datagrams'] += 1
                        counts['coalesced_segments'] += len(pieces)
                    for piece in pieces:
                        if len(piece) < 2:
                            raise ProtocolError('short transport')
                        flag = piece[1]
                        if flag & 15 not in (4, 5) or (flag & 15 == 4 and flag & 16):
                            counts['control_or_ack'] += 1
                            continue
                        if direction == 'out' and flag & (32 | 64):
                            counts['unsupported_outgoing_fragment_flags'] += 1
                            continue
                        if len(piece) < (14 if direction == 'out' else 8 if flag & 32 else 10) or not transport_checksum(piece):
                            raise ProtocolError('transport checksum/header mismatch')
                        sequence = int.from_bytes(piece[6:8] if direction == 'out' else piece[2:4], 'little')
                        flow = (src, sp, dst, dp, flag & 15)
                        signature = flow + (sequence, hashlib.sha256(piece).digest())
                        if signature in transport.seen:
                            counts['exact_duplicate'] += 1
                            continue
                        transport.seen[signature] = None
                        if len(transport.seen) > 8192:
                            transport.seen.popitem(last=False)
                        assembled = (flag, piece[14:]) if direction == 'out' else transport.assemble(flow, timestamp, sequence, piece)
                        if assembled is None:
                            continue
                        app_flag, app = assembled
                        if app_flag & 128:
                            app = transport.zstd.unpack(app)
                            counts['zstd'] += 1
                        if len(app) < 4:
                            raise ProtocolError('short app')
                        module, command = struct.unpack_from('!HH', app)
                        counts[direction + '_applications'] += 1
                        commands[(direction, module, command)] += 1
                        if wanted == (module, command) and (args.packet is None or ordinal == args.packet):
                            matches += 1
                            if matches == args.occurrence:
                                selected.parent.mkdir(parents=True, exist_ok=True)
                                with selected.open('xb') as out:
                                    out.write(app)
                                saved = True
                                extraction = {'packet': ordinal, 'sequence': sequence, 'direction': direction, 'module': module, 'command': command, 'app_bytes': len(app), 'app_sha256': hashlib.sha256(app).hexdigest()}
                except UnsupportedIPFragment:
                    counts['unsupported_ip_fragments'] += 1
                except (ValueError, OverflowError, struct.error) as exc:
                    counts['decode_errors'] += 1
                    last_error_type = type(exc).__name__
    finally:
        reader.close()
    unhandled = {k: v for k, v in transport.stats.items() if v and k not in ('fragment_parts', 'fragments_reassembled')}
    report = {'scope': 'offline fixed-version transport study; counts include only selected local ports/directions', 'pcap_sha256': shape['pcap_sha256'], 'capture_truncated_records': shape['capture_truncated_records'], 'counts': dict(counts), 'flows_by_local_port': [{'direction': d, 'local_port': p, 'records': n} for (d, p), n in sorted(flows.items())], 'commands': [{'direction': d, 'module': m, 'command': c, 'applications': n} for (d, m, c), n in sorted(commands.items())], 'transport_stats': dict(transport.stats), 'pending_transport_streams': len(transport.fragments), 'last_error_type': last_error_type, 'outgoing_envelope': 'fixed-sample offset14/sequence6; no outgoing fragment/coalesced recovery', 'live_operations': False}
    if args.command == 'extract':
        report['matched_messages'] = matches
        report['extracted'] = extraction if saved else None
    any_apps = any(k.endswith('_applications') and n for k, n in counts.items())
    partial = shape['capture_truncated_records'] or counts['unsupported_ip_fragments'] or counts['unsupported_outgoing_fragment_flags'] or unhandled or transport.fragments
    code = 2 if counts['decode_errors'] else 3 if (partial or not any_apps or (args.command == 'extract' and not saved)) else 0
    report['status'] = 'errors' if code == 2 else 'partial_or_no_match' if code == 3 else 'decoded'
    report['exit_code'] = code
    write_json(report_path, report)
    return code


def fields(args):
    if not args.input.is_file() or args.input.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('input missing or larger than 8 MiB')
    fresh_output(args.output, [args.input])
    data = args.input.read_bytes()
    end = len(data) if args.length is None else args.offset + args.length
    if args.offset < 0 or end < args.offset or end > len(data):
        raise ValueError('field input slice outside file')
    def scan(begin, stop):
        pos = begin
        output = []
        def varint():
            nonlocal pos
            result = 0
            for shift in range(0, 70, 7):
                if pos >= stop:
                    raise ValueError('truncated varint')
                b = data[pos]
                pos += 1
                if shift == 63 and b > 1:
                    raise ValueError('uint64 overflow')
                result |= (b & 127) << shift
                if b < 128:
                    return result
            raise ValueError('overlong varint')
        while pos < stop:
            if len(output) >= 100000:
                raise ValueError('field limit exceeded')
            start = pos
            tag = varint()
            number, wire = tag >> 3, tag & 7
            if number == 0:
                raise ValueError('zero field number')
            item = {'tag_offset': start, 'field': number, 'wire': wire}
            if wire == 0:
                item['value_offset'] = pos
                item['unsigned_varint'] = varint()
            elif wire in (1, 2, 5):
                if wire in (1, 5) and not args.standard_fixed:
                    raise ValueError('wire 1/5 requires explicit --standard-fixed after verifying the actual reader; custom wire-5 varint exists in this game')
                length = varint() if wire == 2 else 8 if wire == 1 else 4
                item.update(value_offset=pos, length=length)
                if pos + length > stop:
                    raise ValueError('length-delimited/fixed field exceeds selected slice')
                item['prefix_hex'] = data[pos:pos + min(length, 16)].hex()
                pos += length
            else:
                raise ValueError('unsupported wire type')
            item['end_offset'] = pos
            output.append(item)
        return output
    begin = args.offset
    for part in args.path.split('/') if args.path else []:
        number, occurrence = map(int, part.split(':'))
        if number < 1 or occurrence < 1:
            raise ValueError('field path requires positive field:occurrence entries')
        matches = [x for x in scan(begin, end) if x['field'] == number]
        if occurrence > len(matches) or matches[occurrence - 1]['wire'] != 2:
            raise ValueError('selected field occurrence absent or not a length-delimited block')
        item = matches[occurrence - 1]
        begin, end = item['value_offset'], item['end_offset']
    report = {'scope': 'byte structure only; no inferred coordinates or identity; offsets are absolute within this app file', 'input_sha256': hashlib.sha256(data).hexdigest(), 'path': args.path, 'slice_offset': begin, 'slice_length': end - begin, 'fields': scan(begin, end), 'live_operations': False}
    write_json(args.output, report)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('survey', 'extract'):
        p = commands.add_parser(name, help='count both directions' if name == 'survey' else 'save one complete app message, including its four-byte header')
        p.add_argument('pcap', type=Path)
        p.add_argument('--ports', required=True)
        p.add_argument('--direction', choices=('in', 'out', 'both'), default='both')
        p.add_argument('--summary', type=Path)
        if name == 'extract':
            p.add_argument('--message', required=True, help='for example 3/852')
            p.add_argument('--packet', type=int, help='optional 1-based PCAP record ordinal, not the transport sequence')
            p.add_argument('--occurrence', type=int, default=1)
            p.add_argument('--output', required=True, type=Path)
    p = commands.add_parser('fields', help='inspect only one explicitly selected Protobuf-style slice')
    p.add_argument('input', type=Path)
    p.add_argument('--offset', type=int, default=4, help='absolute byte offset; 4 skips the app module/command')
    p.add_argument('--length', type=int)
    p.add_argument('--path', default='', help='nested length-delimited field:occurrence entries, for example 6:1/4:1; occurrences are 1-based')
    p.add_argument('--standard-fixed', action='store_true')
    p.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if getattr(args, 'occurrence', 1) < 1:
            raise ValueError('occurrence must be positive')
        return fields(args) if args.command == 'fields' else applications(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print('pcap study failed: ' + type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())