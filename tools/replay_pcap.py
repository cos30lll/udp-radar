#!/usr/bin/env python3
"""Offline classic PCAP replay; outputs are private and never overwrite existing files."""
import argparse, csv, hashlib, json, math, os, struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'src'))
def same_path(a,b):
 if a.resolve()==b.resolve(): return True
 return a.exists() and b.exists() and os.path.samefile(a,b)
def inspect_pcap(path):
 h=hashlib.sha256();records=0;capture_truncated_records=0;error=None
 with path.open('rb') as f:
  header=f.read(24);h.update(header)
  formats={b'\xd4\xc3\xb2\xa1':'<',b'\x4d\x3c\xb2\xa1':'<',b'\xa1\xb2\xc3\xd4':'>',b'\xa1\xb2\x3c\x4d':'>'}
  endian=formats.get(header[:4])
  if len(header)!=24 or endian is None: error='invalid/truncated classic PCAP header (pcapng is unsupported)'
  elif struct.unpack_from(endian+'HH',header,4)!=(2,4): error='unsupported PCAP version'
  else:
   snaplen=struct.unpack_from(endian+'I',header,16)[0]
   link=struct.unpack_from(endian+'I',header,20)[0] & 0xffff
   if link not in (1,101,113,228,229,276): error='unsupported PCAP link type'
   while error is None:
    record=f.read(16);h.update(record)
    if not record: break
    if len(record)!=16: error='truncated PCAP record header';break
    _,_,size,original=struct.unpack(endian+'IIII',record)
    if size>262144 or size>original or (snaplen and size>snaplen): error='invalid/oversized PCAP record length';break
    data=f.read(size);h.update(data)
    if len(data)!=size: error='truncated PCAP record payload';break
    records+=1
    if size<original: capture_truncated_records+=1
  if error:
   for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
 return {'pcap_sha256':h.hexdigest(),'records':records,'capture_truncated_records':capture_truncated_records,'input_complete':error is None,'input_error':error}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('pcap',type=Path);p.add_argument('--ports',required=True,help='comma-separated confirmed local UDP ports');p.add_argument('--summary',type=Path);p.add_argument('--events',type=Path);p.add_argument('--expected-csv',type=Path);a=p.parse_args()
 try:
  ports=[int(x) for x in a.ports.split(',')]
  if not ports or not all(0<x<65536 for x in ports): raise ValueError()
 except ValueError: p.error('invalid local ports')
 inputs=[a.pcap]+([a.expected_csv] if a.expected_csv else []);outputs=[x for x in (a.summary,a.events) if x is not None]
 for source in inputs:
  if not source.is_file(): p.error('input file not found')
 for target in outputs:
  if any(same_path(target,source) for source in inputs): p.error('output must not overwrite any input')
  if target.exists(): p.error('output already exists; choose a fresh private output path')
 if len(outputs)==2 and same_path(*outputs): p.error('summary and events must be distinct files')
 structural=inspect_pcap(a.pcap)
 report=dict(structural,confirmed_local_ports=ports,events=0,positions=0,stats={},message_counts_inbound={},action_counts={},last_error=None,csv_match=None,live_operations=False)
 code=2 if not structural['input_complete'] else 0
 if code: report['status']='invalid_input'
 else:
  from protocol import Decoder,PcapTail
  reader=PcapTail(a.pcap);decoder=Decoder(ports);out=None;csvfile=None;expected=None
  try:
   if a.events: a.events.parent.mkdir(parents=True,exist_ok=True);out=a.events.open('x',encoding='utf-8')
   if a.expected_csv: csvfile=a.expected_csv.open(encoding='utf-8-sig',newline='');expected=iter(csv.DictReader(csvfile))
   while True:
    records=list(reader.poll(3000))
    if not records: break
    for record in records:
     for event in decoder.feed_many(*record):
      report['events']+=1
      if out: out.write(json.dumps(event,ensure_ascii=True)+'\n')
      for item in event['positions']:
       if expected is not None:
        row=next(expected,None)
        if row is None: raise ValueError('excess coordinates')
        actual=(event['packet'],item['category'],item['id1'],str(item['id2']),item['scale'],*item['raw'],event['frame4'],event['frame5'])
        wanted=(int(row['packet']),int(row['category']),int(row['entity_field1']),row['entity_field2'],int(row['scale']),int(row['raw_x']),int(row['raw_y']),int(row['raw_z']),int(row['frame_field4']),int(row['frame_field5']))
        if actual!=wanted: raise ValueError('raw coordinate/order mismatch')
        if any(not math.isclose(item[k],float(row[k]),rel_tol=0,abs_tol=1e-9) for k in ('x','y','z')): raise ValueError('XYZ mismatch')
        if abs(event['timestamp']-float(row['timestamp']))>1e-6: raise ValueError('timestamp mismatch')
       report['positions']+=1
   if expected is not None and next(expected,None) is not None: raise ValueError('missing coordinates')
   if expected is not None: report['csv_match']=True
  except (ValueError,RuntimeError,KeyError,OSError,UnicodeError,struct.error) as exc:
   report['last_error']=type(exc).__name__+': '+str(exc);report['csv_match']=False if a.expected_csv else None;code=2
  finally:
   reader.close()
   if out: out.close()
   if csvfile: csvfile.close()
  stats=dict(decoder.stats);pending=len(getattr(decoder,'fragments',{}))
  indicators=('unsupported','expired','evicted','orphan','dropped','discard','mismatch','missing','overflow','out_of_order','gap','limit','interrupted','replaced','invalid_')
  skipped={k:v for k,v in stats.items() if v and any(term in k.lower() for term in indicators)}
  report.update(stats=stats,message_counts_inbound=dict(decoder.message_counts),action_counts=dict(decoder.action_counts),last_error=report['last_error'] or decoder.last_error,pending_transport_streams=pending,unhandled_indicators=skipped)
  if code or stats.get('decode_errors',0): report['status']='decode_or_comparison_error';code=2
  elif not report['events']: report['status']='no_target_events';code=3
  elif skipped or pending or structural['capture_truncated_records']: report['status']='partial';code=3
  else: report['status']='decoded';code=0
 report['exit_code']=code
 if a.summary:
  a.summary.parent.mkdir(parents=True,exist_ok=True)
  with a.summary.open('x',encoding='utf-8') as f: f.write(json.dumps(report,ensure_ascii=True,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=True,indent=2));return code
if __name__=='__main__': raise SystemExit(main())