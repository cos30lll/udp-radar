#!/usr/bin/env python3
import argparse
import collections
import json
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from protocol import Decoder, PcapTail, udp, UnsupportedIPFragment

PROJECT = Path('/storage/emulated/0/Download/超自然行动').resolve()
HERE = Path(__file__).resolve().parent

class State:
    def __init__(self, run):
        self.run = run
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.entities = {}
        self.health = {}
        self.identities = {}
        self.capture = {}
        self.readers = {}
        self.last_sequence = {}
        self.last_pid = None
        self.last_epoch = None
        self.epoch_start = 0
        self.message_counts = {}
        self.action_counts = {}
        self.pending = collections.deque()
        self.pending_bytes = 0
        self.last_diagnostic_write = 0
        self.decoder_totals = {}
        self.decoder_errors = []
        self.stats = collections.Counter()
        self.errors = collections.deque(maxlen=8)
        self.last_scene = None
        self.last_position = None
        self.log = (run / 'positions.jsonl').open('a', encoding='utf-8', buffering=1)
        self.log_bytes = self.log.tell()
        self.event_log = (run / 'metadata.jsonl').open('a', encoding='utf-8', buffering=1)
        self.event_bytes = self.event_log.tell()

    def error(self, message):
        with self.lock:
            self.errors.append({'time': time.time(), 'message': str(message)[:240]})

    def write_event(self, event):
        if self.event_bytes >= 8 * 1024 * 1024:
            return
        line = json.dumps(event, ensure_ascii=False) + chr(10)
        self.event_log.write(line)
        self.event_bytes += len(line.encode('utf-8'))

    def attach_identity(self, item):
        for field in ('name', 'uid', 'identity_timestamp', 'identity_packet', 'identity_source', 'is_local'):
            item.pop(field, None)
        if item['category'] != 4:
            return
        state = self.identities.get(item['stream'])
        if state is None:
            return
        player = state['players'].get(str(item['id1']))
        if player is not None:
            for field in ('name', 'uid', 'identity_timestamp', 'identity_packet', 'identity_source'):
                if field in player:
                    item[field] = player[field]
            uid = player.get('uid')
            local_uid = state.get('local_uid')
            if uid and uid != '0' and local_uid and local_uid != '0':
                item['is_local'] = uid == local_uid
                return
        # Login field 3 and roster field 1 use the same runtime entity namespace.
        entity_id = state.get('local_entity_id')
        if entity_id:
            item['is_local'] = item['id1'] == entity_id
            if item['is_local']:
                item['uid'] = state.get('local_uid', item.get('uid'))

    def apply_identity(self, result, stream):
        event = result['identity']
        if event['reset']:
            self.identities.pop(stream, None)
            for key in [k for k, v in self.entities.items() if v['stream'] == stream]:
                del self.entities[key]
            for key in [k for k in self.health if k.startswith(stream + '/')]:
                del self.health[key]
        state = self.identities.setdefault(stream, {'players': {}})
        for field in ('local_uid', 'local_entity_id'):
            if field in event:
                if field == 'local_uid' and state.get(field) != event[field]:
                    state.pop('local_entity_id', None)
                state[field] = event[field]
        state['timestamp'] = result['timestamp']
        state['command'] = event['command']
        for player in event['players']:
            entity_id = str(player['entity_id'])
            old = state['players'].get(entity_id, {})
            if player.get('uid') and old.get('uid') != player['uid']:
                old = {}
            current = dict(old, **player)
            current.update(identity_timestamp=result['timestamp'], identity_packet=result['packet'],
                           identity_source='3/' + str(event['command']))
            state['players'][entity_id] = current
        for entity_id in event['removed']:
            state['players'].pop(str(entity_id), None)
            for key in [k for k, v in self.entities.items()
                        if v['stream'] == stream and v['category'] == 4 and v['id1'] == entity_id]:
                self.entities.pop(key, None)
                self.health.pop(key, None)
        if len(state['players']) > 2048:
            keep = sorted(state['players'], key=lambda k: state['players'][k]['identity_timestamp'], reverse=True)[:2048]
            state['players'] = {k: state['players'][k] for k in keep}
        for item in self.entities.values():
            if item['stream'] == stream:
                self.attach_identity(item)
        self.stats['identity_updates_applied'] += 1
        self.write_event(dict(result, stream=stream))

    def apply(self, result):
        stream = str(result['local_port']) + '@' + result['peer']
        event_type = result.get('type', 'scene')
        # Reliable identity notifications and scene updates need separate ordering.
        order_key = stream + '/' + str(result.get('transport_kind', 0)) + '/' + event_type
        seq = result['sequence']
        old = self.last_sequence.get(order_key)
        if old is not None and ((seq - old) & 65535) > 32767:
            with self.lock:
                self.stats['out_of_order_not_displayed'] += 1
            return
        self.last_sequence[order_key] = seq
        now = time.time()
        with self.lock:
            if event_type == 'identity':
                self.apply_identity(result, stream)
                return
            self.last_scene = result['timestamp']
            health_events = result.get('health_updates', [])
            for h in health_events:
                key = stream + '/' + str(h['category']) + '/' + str(h['id1']) + '/' + h['id2']
                metadata = {'hp': h['hp'], 'hp_raw': h['hp_raw'], 'hp_timestamp': result['timestamp'], 'hp_packet': result['packet']}
                self.health[key] = metadata
                if key in self.entities:
                    self.entities[key].update(metadata)
                self.stats['hp_updates_received'] += 1
            if health_events:
                self.write_event({'type': 'health', 'stream': stream, 'timestamp': result['timestamp'],
                                  'packet': result['packet'], 'health_updates': health_events})
            for p in result['positions']:
                key = stream + '/' + str(p['category']) + '/' + str(p['id1']) + '/' + p['id2']
                previous = self.entities.get(key)
                track = collections.deque(previous['track'] if previous else [], maxlen=60)
                if not track or track[-1][1:] != [p['x'], p['y'], p['z']]:
                    track.append([result['timestamp'], p['x'], p['y'], p['z']])
                item = dict(p, key=key, stream=stream, timestamp=result['timestamp'], packet=result['packet'], frame4=result['frame4'], track=list(track))
                item.update(self.health.get(key, {}))
                self.attach_identity(item)
                self.entities[key] = item
                self.last_position = result['timestamp']
                self.stats['position_updates_displayed'] += 1
                if self.log_bytes < 16 * 1024 * 1024:
                    line = json.dumps(dict(p, stream=stream, timestamp=result['timestamp'], packet=result['packet']), ensure_ascii=False) + chr(10)
                    self.log.write(line)
                    self.log_bytes += len(line.encode('utf-8'))
            for entity_id in result.get('removed', []):
                for key in [k for k, v in self.entities.items() if v['stream'] == stream and v['id1'] == entity_id]:
                    self.entities.pop(key, None)
                    self.health.pop(key, None)
            stale = [k for k, v in self.entities.items() if now - v['timestamp'] > 300]
            for key in stale:
                del self.entities[key]
            if len(self.entities) > 512:
                for key in sorted(self.entities, key=lambda k: self.entities[k]['timestamp'])[:len(self.entities)-512]:
                    del self.entities[key]
            expired = [k for k, h in self.health.items() if now - h['hp_timestamp'] > 300]
            if len(self.health) - len(expired) > 512:
                expired += sorted((k for k in self.health if k not in expired),
                                  key=lambda k: self.health[k]['hp_timestamp'])[:len(self.health)-len(expired)-512]
            for key in expired:
                self.health.pop(key, None)
                if key in self.entities:
                    for field in ('hp', 'hp_raw', 'hp_timestamp', 'hp_packet'):
                        self.entities[key].pop(field, None)

    def buffer_record(self, key, record):
        # Bounded raw replay window; never infer game ownership from payload contents.
        self.pending.append((time.monotonic(), key, record))
        self.pending_bytes += len(record[3])
        self.trim_pending()

    def trim_pending(self):
        cutoff = time.monotonic() - 15
        while self.pending and (self.pending[0][0] < cutoff or len(self.pending) > 8192 or self.pending_bytes > 8 * 1024 * 1024):
            _, _, record = self.pending.popleft()
            self.pending_bytes -= len(record[3])
            self.stats['buffer_expired_or_limited'] += 1

    def replay_pending(self, key, decoder, new_ports):
        keep = collections.deque()
        while self.pending:
            entry = self.pending.popleft()
            _, record_key, record = entry
            matched = False
            if record_key == key:
                packet = udp(record[2], record[3])
                matched = packet is not None and (packet[1] in new_ports or packet[3] in new_ports)
            if matched:
                self.pending_bytes -= len(record[3])
                if record[0] >= self.epoch_start:
                    self.stats['buffer_replayed_records'] += 1
                    for result in decoder.feed_many(*record):
                        self.apply(result)
            else:
                keep.append(entry)
        self.pending = keep

    def refresh_capture(self):
        status_file = self.run / 'capture.json'
        if not status_file.exists():
            return
        status = json.loads(status_file.read_text())
        pid = status.get('game_pid', 0)
        epoch = status.get('game_epoch', pid)
        if self.last_epoch is not None and epoch != self.last_epoch:
            with self.lock:
                self.entities.clear()
                self.health.clear()
                self.identities.clear()
                self.last_scene = None
                self.last_position = None
            self.last_sequence.clear()
            for item in self.readers.values():
                item['decoder'].ports.clear()
                item['decoder'].seen.clear()
                item['decoder'].fragments.clear()
            self.stats['game_epoch_changes'] += 1
        self.last_epoch = epoch
        self.last_pid = pid
        # Ignore buffered traffic predating the current process when its start is known.
        self.epoch_start = float(status.get('game_started_at') or 0) if pid else float('inf')
        ports = {int(p) for p in status.get('ports', []) if 0 < int(p) < 65536} if pid else set()
        for key, item in self.readers.items():
            if not item['continuous']:
                continue
            decoder = item['decoder']
            new_ports = ports - decoder.ports
            decoder.ports = set(ports)
            if new_ports:
                self.replay_pending(key, decoder, new_ports)
        with self.lock:
            self.capture = status

    def collect_diagnostics(self):
        totals, messages, actions = collections.Counter(), collections.Counter(), collections.Counter()
        errors = []
        for item in self.readers.values():
            decoder = item['decoder']
            totals.update(decoder.stats)
            messages.update(decoder.message_counts)
            actions.update(decoder.action_counts)
            if decoder.last_error:
                errors.append(decoder.last_error)
        with self.lock:
            self.decoder_totals = dict(totals)
            self.decoder_errors = errors[-5:]
            self.message_counts = dict(messages)
            self.action_counts = dict(actions)

    def save_diagnostics(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_diagnostic_write < 2:
            return
        snapshot = self.snapshot()
        payload = {k: snapshot[k] for k in ('version', 'now', 'capture', 'stats', 'diagnostics', 'errors', 'decoder_last_errors')}
        target = self.run / 'diagnostics.json'
        temporary = target.with_suffix('.json.new')
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + chr(10))
        temporary.replace(target)
        self.last_diagnostic_write = now

    def consume(self):
        try:
            while not self.stop.is_set():
                try:
                    for meta in sorted(self.run.glob('capture-*.json')):
                        key = meta.stem
                        if key not in self.readers:
                            m = json.loads(meta.read_text())
                            continuous = m.get('mode') == 'continuous_udp'
                            self.readers[key] = {'tail': PcapTail(meta.with_suffix('.pcap')),
                                                 'decoder': Decoder([] if continuous else m['ports']), 'continuous': continuous}
                    self.trim_pending()
                    self.refresh_capture()
                    for key, item in list(self.readers.items()):
                        tail, decoder = item['tail'], item['decoder']
                        for record in tail.poll(3000):
                            if item['continuous']:
                                self.stats['capture_records_seen'] += 1
                                try:
                                    packet = udp(record[2], record[3])
                                except UnsupportedIPFragment:
                                    self.stats['capture_ip_fragments_unsupported'] += 1
                                    continue
                                except (ValueError, OverflowError) as exc:
                                    self.stats['capture_unparsed_records'] += 1
                                    self.error(exc)
                                    continue
                                if packet is None:
                                    self.stats['capture_non_udp'] += 1
                                    continue
                                if not (packet[1] in decoder.ports or packet[3] in decoder.ports):
                                    self.buffer_record(key, record)
                                    continue
                                if record[0] < self.epoch_start:
                                    self.stats['previous_game_records_ignored'] += 1
                                    continue
                            for result in decoder.feed_many(*record):
                                self.apply(result)
                    self.collect_diagnostics()
                    self.save_diagnostics()
                    self.stop.wait(0.12)
                except (OSError, ValueError, RuntimeError) as exc:
                    self.error(exc)
                    self.stop.wait(0.5)
        finally:
            self.collect_diagnostics()
            try:
                self.save_diagnostics(force=True)
            except (OSError, ValueError) as exc:
                self.error(exc)
            for item in self.readers.values():
                item['tail'].close()
            self.log.close()
            self.event_log.close()

    def snapshot(self):
        with self.lock:
            totals = collections.Counter(self.decoder_totals) + self.stats
            return {'version': 'v2.2-names-candidate', 'now': time.time(), 'capture': dict(self.capture), 'stats': dict(totals),
                    'last_scene': self.last_scene, 'last_position': self.last_position, 'entities': list(self.entities.values()),
                    'identity': {k: {'local_uid': v.get('local_uid'), 'local_entity_id': v.get('local_entity_id'),
                                     'players': len(v['players']), 'timestamp': v.get('timestamp')} for k, v in self.identities.items()},
                    'diagnostics': {'message_counts_inbound': dict(self.message_counts), 'action_counts': dict(self.action_counts),
                                    'identity': 'received' if totals['identity_messages'] else 'not_observed',
                                    'hp31': 'received' if totals['hp_actions'] else 'not_observed',
                                    'pending_records': len(self.pending), 'pending_bytes': self.pending_bytes,
                                    'buffer_seconds': 15, 'buffer_max_bytes': 8388608, 'buffer_max_records': 8192},
                    'errors': list(self.errors), 'decoder_last_errors': list(self.decoder_errors),
                    'warning': '限时全机UDP被动缓存，仅解码已确认游戏端口；姓名/HP/自身须收到对应消息。未收到不猜填；持续抓包改版待用户实测。'}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        host = self.headers.get('Host', '')
        allowed = {'127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)}
        if host not in allowed:
            self.send_error(403)
            return
        path = self.path.split('?', 1)[0]
        if path == '/api/state':
            body = json.dumps(self.server.state.snapshot(), ensure_ascii=False).encode('utf-8')
            kind = 'application/json; charset=utf-8'
        elif path in ('/', '/index.html', '/app.js', '/style.css'):
            name = {'/': 'index.html'}.get(path, path.lstrip('/'))
            try:
                body = (HERE / name).read_bytes()
            except OSError:
                self.send_error(404)
                return
            kind = {'index.html': 'text/html', 'app.js': 'text/javascript', 'style.css': 'text/css'}[name] + '; charset=utf-8'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

def main():
    parser = argparse.ArgumentParser(description='Local passive UDP coordinate viewer; capture is managed by Android shell.')
    parser.add_argument('--run', required=True)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    run = Path(args.run).resolve(strict=True)
    if not run.is_relative_to(PROJECT / '日志/udp-radar-v1'):
        parser.error('run directory must be under project 日志/udp-radar-v1')
    if not 1024 <= args.port <= 65535:
        parser.error('invalid local HTTP port')
    state = State(run)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.daemon_threads = True
    server.state = state
    (run / 'server.pid').write_text(str(os.getpid()) + chr(10))
    (run / 'server-ready.json').write_text(json.dumps({'pid': os.getpid(), 'port': args.port, 'url': 'http://127.0.0.1:' + str(args.port), 'time': time.time()}))
    worker = threading.Thread(target=state.consume, daemon=True)
    worker.start()
    def terminate(signum, frame):
        state.stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    print('Radar ready at http://127.0.0.1:' + str(args.port), flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        state.stop.set()
        server.server_close()
        worker.join(timeout=3)
        (run / 'server-finished.txt').write_text(str(time.time()))

if __name__ == '__main__':
    main()
