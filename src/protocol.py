import collections
import ctypes
import ctypes.util
import hashlib
import socket
import struct
import time
from identity import decode_identity

MAX_RECORD = 262144
MAX_MESSAGE = 8 * 1024 * 1024

class ProtocolError(ValueError):
    pass

class UnsupportedIPFragment(ProtocolError):
    pass

class Reader:
    def __init__(self, data):
        self.data = memoryview(data)
        self.pos = 0
        self.fields = 0

    def varint(self):
        out = 0
        for shift in range(0, 70, 7):
            if self.pos >= len(self.data):
                raise ProtocolError('truncated varint')
            b = self.data[self.pos]
            self.pos += 1
            if shift == 63 and b > 1:
                raise ProtocolError('uint64 overflow')
            out |= (b & 127) << shift
            if b < 128:
                return out
        raise ProtocolError('overlong varint')

    def block(self):
        n = self.varint()
        if n > len(self.data) - self.pos:
            raise ProtocolError('invalid block length')
        start = self.pos
        self.pos += n
        return self.data[start:self.pos]

    def fields_iter(self):
        while self.pos < len(self.data):
            self.fields += 1
            if self.fields > 100000:
                raise ProtocolError('field limit')
            tag = self.varint()
            number, wire = tag >> 3, tag & 7
            if not number:
                raise ProtocolError('zero field')
            if wire == 0:
                value = self.varint()
            elif wire == 2:
                value = self.block()
            else:
                raise ProtocolError('unverified wire ' + str(wire))
            yield number, wire, value

def values64(data):
    r = Reader(data)
    result = []
    while r.pos < len(r.data):
        n = r.varint()
        result.append(n - (1 << 64) if n >= (1 << 63) else n)
        if len(result) > 32768:
            raise ProtocolError('value limit')
    return result

def action(data):
    out = {'kind': 0, 'scale': 0, 'values': []}
    for n, w, v in Reader(data).fields_iter():
        if n in (1, 2) and w == 0:
            out['kind' if n == 1 else 'scale'] = v
        elif n == 3 and w == 0:
            out['values'].append(v - (1 << 64) if v >= (1 << 63) else v)
        elif n == 3 and w == 2:
            out['values'].extend(values64(v))
        elif n == 4 and w == 2:
            pass
        else:
            raise ProtocolError('unverified action field')
    return out

def entity(data):
    out = {'id1': 0, 'id2': 0, 'category': 0, 'actions': []}
    for n, w, v in Reader(data).fields_iter():
        if n in (1, 2, 3) and w == 0:
            out[{1: 'id1', 2: 'id2', 3: 'category'}[n]] = v
        elif n == 4 and w == 2:
            out['actions'].append(action(v))
        else:
            raise ProtocolError('unverified entity field')
    return out

def scene(data):
    out = {'frame4': 0, 'frame5': 0, 'entities': [], 'removed': []}
    for n, w, v in Reader(data).fields_iter():
        if n in (4, 5) and w == 0:
            out['frame' + str(n)] = v
        elif n == 6 and w == 2:
            out['entities'].append(entity(v))
        elif n == 7 and w in (0, 2):
            removed = values64(v) if w == 2 else [v]
            if any(i < 0 or i > 0xffffffff for i in removed):
                raise ProtocolError('invalid removed entity id')
            out['removed'].extend(removed)
        else:
            raise ProtocolError('unverified scene field')
    return out

class Zstd:
    def __init__(self):
        name = ctypes.util.find_library('zstd')
        if not name:
            raise RuntimeError('libzstd is missing from the Ubuntu environment')
        self.lib = ctypes.CDLL(name)
        self.lib.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        self.lib.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
        self.lib.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
        self.lib.ZSTD_decompress.restype = ctypes.c_size_t
        self.lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
        self.lib.ZSTD_isError.restype = ctypes.c_uint

    def unpack(self, raw):
        src = ctypes.create_string_buffer(raw)
        size = self.lib.ZSTD_getFrameContentSize(src, len(raw))
        if not 0 < size <= MAX_MESSAGE:
            raise ProtocolError('unknown or excessive zstd output size')
        dst = ctypes.create_string_buffer(size)
        n = self.lib.ZSTD_decompress(dst, size, src, len(raw))
        if self.lib.ZSTD_isError(n) or n != size:
            raise ProtocolError('zstd decoding failed')
        return dst.raw[:n]

class PcapTail:
    def __init__(self, path):
        self.path = path
        self.file = None
        self.header = None
        self.ordinal = 0

    def close(self):
        if self.file:
            self.file.close()

    def poll(self, limit=2000):
        if self.file is None:
            if not self.path.exists():
                return
            self.file = self.path.open('rb')
        f = self.file
        if self.header is None:
            f.seek(0)
            h = f.read(24)
            if len(h) < 24:
                return
            magic = {bytes.fromhex('d4c3b2a1'): ('<', 1e6), bytes.fromhex('4d3cb2a1'): ('<', 1e9), bytes.fromhex('a1b2c3d4'): ('>', 1e6), bytes.fromhex('a1b23c4d'): ('>', 1e9)}
            if h[:4] not in magic:
                raise ProtocolError('not classic PCAP')
            self.endian, self.scale = magic[h[:4]]
            self.link = struct.unpack_from(self.endian + 'I', h, 20)[0] & 0xffff
            if self.link not in (1, 101, 113, 228, 229, 276):
                raise ProtocolError('unsupported PCAP link ' + str(self.link))
            self.header = h
        for _ in range(limit):
            start = f.tell()
            h = f.read(16)
            if len(h) < 16:
                f.seek(start)
                return
            sec, frac, cap, original = struct.unpack(self.endian + 'IIII', h)
            if cap > MAX_RECORD or cap > original:
                raise ProtocolError('invalid PCAP record length')
            frame = f.read(cap)
            if len(frame) < cap:
                f.seek(start)
                return
            self.ordinal += 1
            yield sec + frac / self.scale, self.ordinal, self.link, frame

def udp(link, data):
    pkt_type = None
    if link == 276:
        if len(data) < 20:
            raise ProtocolError('short SLL2')
        ethertype, pkt_type, data = int.from_bytes(data[:2], 'big'), data[10], data[20:]
    elif link == 113:
        if len(data) < 16:
            raise ProtocolError('short SLL')
        ethertype, pkt_type, data = int.from_bytes(data[14:16], 'big'), int.from_bytes(data[:2], 'big'), data[16:]
    elif link == 1:
        if len(data) < 14:
            raise ProtocolError('short Ethernet')
        ethertype, data = int.from_bytes(data[12:14], 'big'), data[14:]
        for _ in range(2):
            if ethertype not in (0x8100, 0x88a8):
                break
            if len(data) < 4:
                raise ProtocolError('short VLAN')
            ethertype, data = int.from_bytes(data[2:4], 'big'), data[4:]
    else:
        ethertype = 0x86dd if data and data[0] >> 4 == 6 else 0x800
    if ethertype == 0x800:
        if len(data) < 20:
            raise ProtocolError('short IPv4')
        ihl, total = (data[0] & 15) * 4, int.from_bytes(data[2:4], 'big')
        if ihl < 20 or total > len(data) or total < ihl:
            raise ProtocolError('bad IPv4 length')
        if int.from_bytes(data[6:8], 'big') & 0x3fff:
            raise UnsupportedIPFragment('IP fragments unsupported')
        proto = data[9]
        src, dst = socket.inet_ntop(socket.AF_INET, data[12:16]), socket.inet_ntop(socket.AF_INET, data[16:20])
        data = data[ihl:total]
    elif ethertype == 0x86dd:
        if len(data) < 40:
            raise ProtocolError('short IPv6')
        total = 40 + int.from_bytes(data[4:6], 'big')
        if total > len(data):
            raise ProtocolError('bad IPv6 length')
        proto = data[6]
        src, dst = socket.inet_ntop(socket.AF_INET6, data[8:24]), socket.inet_ntop(socket.AF_INET6, data[24:40])
        data = data[40:total]
    else:
        return None
    if proto != 17:
        return None
    if len(data) < 8:
        raise ProtocolError('short UDP')
    sport, dport, size, _ = struct.unpack_from('!HHHH', data)
    if size < 8 or size > len(data):
        raise ProtocolError('invalid UDP size')
    return src, sport, dst, dport, pkt_type, data[8:size]

def transport_checksum(data):
    # libjelib AsyncSend 0x5ab78..0x5abbc: length + flag + both sequence bytes.
    return len(data) >= 4 and data[0] == ((len(data) + sum(data[1:4])) & 255)

def transport_header(data):
    if len(data) < 8:
        return False
    flag = data[1]
    if (flag & 15) not in (4, 5) or flag & 16:
        return False
    header = 8 if flag & 32 else 10
    if len(data) < header:
        return False
    if flag & 32:
        return True
    payload = data[header:]
    if flag & 128:
        return payload.startswith(bytes.fromhex('28b52ffd'))
    return len(payload) >= 4 and payload[:2] == bytes((0, 3))

def transport_segments(body):
    # Conservative recovery for coalesced capture records. No nickname scanning.
    # Accept a split only when the complete checksum/header/sequence chain is unique.
    if transport_checksum(body):
        return [body]
    if not transport_header(body):
        return [body]
    paths = []
    budget = [0]
    def walk(offset, expected, parts):
        budget[0] += 1
        if budget[0] > 1024 or len(parts) >= 64 or len(paths) > 1:
            return
        data = body[offset:]
        if not transport_header(data):
            return
        sequence = int.from_bytes(data[2:4], 'little')
        if expected is not None and sequence != expected:
            return
        minimum = 8 if data[1] & 32 else 14
        residue = (data[0] - sum(data[1:4])) & 255
        length = residue
        while length < minimum:
            length += 256
        while length <= len(data):
            part = data[:length]
            if transport_header(part) and transport_checksum(part):
                if length == len(data):
                    paths.append(parts + [part])
                elif transport_header(data[length:]):
                    walk(offset + length, (sequence + 1) & 65535, parts + [part])
            length += 256
    walk(0, None, [])
    return paths[0] if len(paths) == 1 and len(paths[0]) > 1 and budget[0] <= 1024 else [body]

class Decoder:
    def __init__(self, ports):
        self.ports = set(ports)
        self.zstd = Zstd()
        self.stats = collections.Counter()
        self.seen = collections.OrderedDict()
        self.fragments = collections.OrderedDict()
        self.last_error = ''
        self.message_counts = collections.Counter()
        self.action_counts = collections.Counter()

    def feed(self, timestamp, ordinal, link, frame):
        # Legacy single-result reader; live backend uses feed_many at every call site.
        results = self.feed_many(timestamp, ordinal, link, frame)
        if len(results) > 1:
            self.stats['legacy_additional_results'] += len(results) - 1
        return results[0] if results else None

    def expire_fragments(self, timestamp):
        for key in list(self.fragments):
            if timestamp - self.fragments[key]['timestamp'] > 15:
                del self.fragments[key]
                self.stats['fragment_expired'] += 1
        while len(self.fragments) > 16:
            self.fragments.popitem(last=False)
            self.stats['fragment_limited'] += 1

    def assemble(self, flow, timestamp, sequence, body):
        flag = body[1]
        current = self.fragments.get(flow)
        if flag & 32:
            if current is None:
                self.stats['fragment_orphan'] += 1
                return None
            if sequence != current['next']:
                self.stats['fragment_sequence_gap'] += 1
                self.fragments.pop(flow, None)
                return None
            current['data'].extend(body[8:])
            current['next'] = (sequence + 1) & 65535
            current['timestamp'] = timestamp
            current['pieces'] += 1
            self.stats['fragment_parts'] += 1
            if len(current['data']) > MAX_MESSAGE or current['pieces'] > 512:
                self.fragments.pop(flow, None)
                self.stats['fragment_limited'] += 1
                return None
            if flag & 64:
                return None
            self.fragments.pop(flow, None)
            self.stats['fragments_reassembled'] += 1
            return current['flag'], bytes(current['data'])
        if flag & 64:
            if current is not None:
                self.stats['fragment_replaced'] += 1
            self.fragments[flow] = {'data': bytearray(body[10:]), 'flag': flag,
                                    'next': (sequence + 1) & 65535, 'timestamp': timestamp, 'pieces': 1}
            self.stats['fragment_parts'] += 1
            self.expire_fragments(timestamp)
            return None
        if current is not None:
            self.fragments.pop(flow, None)
            self.stats['fragment_interrupted'] += 1
        return flag, body[10:]

    def feed_many(self, timestamp, ordinal, link, frame):
        self.stats['packets'] += 1
        results = []
        try:
            packet = udp(link, frame)
            if packet is None:
                self.stats['non_udp'] += 1
                return results
            src, sp, dst, dp, pkt_type, body = packet
            if dp not in self.ports or sp in self.ports or pkt_type == 4:
                self.stats['outgoing_or_other'] += 1
                return results
            self.stats['incoming'] += 1
            self.expire_fragments(timestamp)
            chunks = transport_segments(body)
            if len(chunks) > 1:
                self.stats['coalesced_datagrams'] += 1
                self.stats['coalesced_segments'] += len(chunks)
            for chunk in chunks:
                try:
                    if len(chunk) < 2:
                        raise ProtocolError('short transport packet')
                    flag = chunk[1]
                    if (flag & 15) not in (4, 5) or (flag & 15 == 4 and flag & 16):
                        self.stats['control_or_ack'] += 1
                        continue
                    minimum = 8 if flag & 32 else 10
                    if len(chunk) < minimum:
                        raise ProtocolError('short application transport header')
                    if not transport_checksum(chunk):
                        self.stats['transport_checksum_mismatch'] += 1
                        raise ProtocolError('unresolved transport length/checksum')
                    sequence = int.from_bytes(chunk[2:4], 'little')
                    signature = (src, sp, dst, dp, flag & 15, sequence, hashlib.sha256(chunk).digest())
                    if signature in self.seen:
                        self.stats['exact_duplicate'] += 1
                        continue
                    self.seen[signature] = None
                    if len(self.seen) > 8192:
                        self.seen.popitem(last=False)
                    assembled = self.assemble((src, sp, dst, dp, flag & 15), timestamp, sequence, chunk)
                    if assembled is None:
                        continue
                    app_flag, app = assembled
                    if app_flag & 128:
                        app = self.zstd.unpack(app)
                        self.stats['zstd'] += 1
                    result = self._application(timestamp, ordinal, src, sp, dp, sequence, app_flag, app)
                    if result is not None:
                        results.append(result)
                except (ValueError, struct.error, OverflowError) as exc:
                    self.stats['decode_errors'] += 1
                    self.last_error = str(exc)
        except UnsupportedIPFragment:
            self.stats['unsupported_ip_fragments'] += 1
        except (ValueError, struct.error, OverflowError) as exc:
            self.stats['decode_errors'] += 1
            self.last_error = str(exc)
        return results

    def _application(self, timestamp, ordinal, src, sp, dp, sequence, flag, app):
        if len(app) < 4:
            raise ProtocolError('short decoded application')
        mod, cmd = struct.unpack_from('!HH', app)
        self.stats['applications'] += 1
        message_key = str(mod) + '/' + str(cmd)
        if message_key in self.message_counts or len(self.message_counts) < 512:
            self.message_counts[message_key] += 1
        else:
            self.message_counts['other'] += 1
        if mod == 3 and cmd in (1, 3, 6, 2005):
            event = decode_identity(cmd, app[4:])
            self.stats['identity_messages'] += 1
            self.stats['roster_players'] += len(event['players'])
            return {'type': 'identity', 'timestamp': timestamp, 'packet': ordinal,
                    'peer': src + ':' + str(sp), 'local_port': dp, 'sequence': sequence,
                    'transport_kind': flag & 15, 'identity': event, 'positions': []}
        if (mod, cmd) != (3, 852):
            self.stats['other_applications'] += 1
            return None
        parsed = scene(app[4:])
        self.stats['scene_frames'] += 1
        positions = []
        health_updates = []
        for ent in parsed['entities']:
            for ac in ent['actions']:
                self.stats['actions'] += 1
                action_key = str(ac['kind'])
                if action_key in self.action_counts or len(self.action_counts) < 256:
                    self.action_counts[action_key] += 1
                else:
                    self.action_counts['other'] += 1
                if ac['kind'] == 31:
                    if not ac['values']:
                        self.stats['invalid_hp_length'] += 1
                        continue
                    # HP action: values[0] -> conv.i4 -> GPJFBHCPDAB. No position scale.
                    hp = ((ac['values'][0] + (1 << 31)) % (1 << 32)) - (1 << 31)
                    health_updates.append({'id1': ent['id1'], 'id2': str(ent['id2']), 'category': ent['category'], 'hp': hp, 'hp_raw': list(ac['values'])})
                    self.stats['hp_actions'] += 1
                    continue
                if ac['kind'] != 1:
                    continue
                if len(ac['values']) != 3:
                    self.stats['invalid_position_length'] += 1
                    continue
                scale = ac['scale']
                xyz = [n / scale if scale > 0 else float(n) for n in ac['values']]
                positions.append({'id1': ent['id1'], 'id2': str(ent['id2']), 'category': ent['category'], 'raw': ac['values'], 'scale': scale, 'x': xyz[0], 'y': xyz[1], 'z': xyz[2]})
                self.stats['position_actions'] += 1
        return {'timestamp': timestamp, 'packet': ordinal, 'peer': src + ':' + str(sp), 'local_port': dp, 'sequence': sequence, 'frame4': parsed['frame4'], 'frame5': parsed['frame5'], 'positions': positions, 'health_updates': health_updates, 'removed': parsed['removed'], 'type': 'scene', 'transport_kind': flag & 15}
