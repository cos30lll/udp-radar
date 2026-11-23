'use strict';
const $ = id => document.getElementById(id);
const canvas = $('radar'), ctx = canvas.getContext('2d');
let data = null, fetched = 0, connected = false, paused = false, frozenNow = 0;
let center = [0, 0], initialized = false, anchorKey = '', pointHits = [], drag = null;
const fmt = n => Number.isFinite(n) ? n.toFixed(3) : '—';
function clock() { return paused ? frozenNow : (data ? data.now + (performance.now() - fetched) / 1000 : Date.now() / 1000); }
function age(e) { return Math.max(0, clock() - e.timestamp); }
function axes() { return $('plane').value.split(''); }
function color(key) { let h = 0; for (const c of key) h = (h * 31 + c.charCodeAt(0)) | 0; return `hsl(${Math.abs(h) % 360} 80% 68%)`; }
function entities() { return (data?.entities || []).filter(e => age(e) <= 30 && ($('category').value === 'all' || String(e.category) === $('category').value)); }
function anchor() { const a = (data?.entities || []).find(e => e.key === anchorKey); return a && age(a) <= 3 ? a : null; }
function select(key) { $('autoSelf').checked=false; anchorKey = key; $('anchor').value = key; renderTable(); draw(); }
function syncSelf() {
  if (!$('autoSelf').checked) return;
  const candidates=(data?.entities||[]).filter(e=>e.is_local===true&&age(e)<=3);
  candidates.sort((a,b)=>b.timestamp-a.timestamp);
  anchorKey=candidates[0]?.key||'';
}
function fit() {
  const es = entities(), [u,v] = axes(); if (!es.length) return;
  const xs = es.map(e => e[u]), ys = es.map(e => e[v]);
  const left = Math.min(...xs), right = Math.max(...xs), lo = Math.min(...ys), hi = Math.max(...ys);
  center = [(left + right) / 2, (lo + hi) / 2];
  const a = $('follow').checked ? anchor() : null; if (a) center = [a[u], a[v]];
  const dx = Math.max(...xs.map(x => Math.abs(x-center[0])))*2;
  const dy = Math.max(...ys.map(y => Math.abs(y-center[1])))*2;
  const r = canvas.getBoundingClientRect();
  $('span').value = Math.ceil(Math.max(20, dx*1.25, dy*1.25*r.width/Math.max(1,r.height)));
  initialized = true; draw();
}
function updateOptions() {
  const sel = $('anchor'), es = data?.entities || [];
  syncSelf();
  const wanted = new Map(es.map(e => [e.key, `${e.is_local===true?'[自己] ':''}${typeof e.name==='string'?e.name+' · ':''}${e.id1} / ${e.id2} · 类${e.category}`]));
  if (anchorKey && !wanted.has(anchorKey)) wanted.set(anchorKey, '参考实体已失联');
  const signature = JSON.stringify([...wanted.entries()]);
  if (sel.dataset.signature === signature) { sel.value = anchorKey; return; }
  sel.replaceChildren(new Option('无（世界坐标）',''));
  for (const [key,name] of wanted) sel.add(new Option(name,key));
  sel.value = anchorKey; sel.dataset.signature = signature;
}
function renderStatus() {
  const cap = data?.capture || {}, s = data?.stats || {};
  const delta = data?.last_position ? Math.max(0, clock()-data.last_position) : null;
  const fresh = connected && cap.running && delta !== null && delta < 3;
  $('health').textContent = paused ? '画面已暂停' : !connected ? '后端未连接' : fresh ? '坐标更新中' : cap.running ? '等待有效坐标' : '抓包未运行';
  $('health').className = 'badge ' + (fresh && !paused ? 'ok' : 'warn');
  $('status').textContent = `游戏 PID：${cap.game_pid || '—'} · UDP：${(cap.ports || []).join(', ') || '等待识别'} · ${cap.reason || '等待状态'}${cap.capture_scope==='device_udp'?' · 全机UDP限时缓存，仅解码游戏端口':''}`;
  const states=Object.values(data?.identity||{}), local=(data?.entities||[]).find(e=>e.is_local===true&&age(e)<=3);
  const own=local?(local.name||String(local.id1)):states.some(v=>v.local_uid||v.local_entity_id)?'身份已收，等待自身坐标':'等待进场初始化';
  const entries = [['自己',own],['身份消息',s.identity_messages||0],['姓名映射',states.reduce((a,v)=>a+v.players,0)],['血量更新',s.hp_actions||0],['包数',s.packets || 0],['场景帧',s.scene_frames || 0],['位置更新',s.position_actions || 0],['压缩包',s.zstd || 0],['解码错误',s.decode_errors || 0],['传输重组',s.fragments_reassembled||0],['合包拆分',s.coalesced_datagrams||0],['未支持IP分片',(s.unsupported_ip_fragments||0)+(s.capture_ip_fragments_unsupported||0)],['分片未完成',(s.fragment_orphan||0)+(s.fragment_sequence_gap||0)+(s.fragment_expired||0)+(s.fragment_interrupted||0)+(s.fragment_limited||0)],['最后坐标',delta === null ? '未收到' : delta.toFixed(1)+' 秒前'],['自动停止',cap.remaining_seconds === undefined ? '—' : cap.remaining_seconds+' 秒后']];
  const dl = $('metrics'); dl.replaceChildren();
  for (const [k,v] of entries) { const dt=document.createElement('dt'), dd=document.createElement('dd'); dt.textContent=k; dd.textContent=String(v); dl.append(dt,dd); }
  const dg=data?.diagnostics||{};
  for(const [k,v] of [['端口补解析',s.buffer_replayed_records||0],['待归属缓冲',dg.pending_records||0],['初始化观测',dg.identity==='received'?'已收到':'未观测到'],['HP31观测',dg.hp31==='received'?'已收到':'未观测到']]){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=k;dd.textContent=String(v);dl.append(dt,dd); }
  const errors = [...(data?.decoder_last_errors || []),...(data?.errors || []).map(x=>x.message)];
  $('error').textContent = errors.length ? '最近诊断：'+errors.at(-1) : '';
}
function renderTable() {
  updateOptions(); const ref=anchor(), tbody=$('rows'); tbody.replaceChildren();
  for (const e of entities().sort((a,b)=>a.id1-b.id1)) {
    const tr=document.createElement('tr'); if(age(e)>3) tr.classList.add('stale'); if(e.key===anchorKey) tr.classList.add('selected');
    const values=[e.key===anchorKey?'●':'○',e.category,e.id1,e.id2,typeof e.name==='string'?e.name:'未收到',e.uid||'未收到',Number.isInteger(e.hp)?String(e.hp):'未收到',Number.isFinite(e.hp_timestamp)?Math.max(0,clock()-e.hp_timestamp).toFixed(1)+'s':'—',e.is_local===true?'自己':e.is_local===false?'非本地':'未识别',fmt(e.x),fmt(e.y),fmt(e.z),ref?fmt(e.y-ref.y):'—',ref?fmt(Math.hypot(e.x-ref.x,e.z-ref.z)):'—',age(e).toFixed(1)+'s'];
    for(const val of values){const td=document.createElement('td');td.textContent=String(val);tr.append(td);}
    tr.addEventListener('click',()=>select(e.key)); tbody.append(tr);
  }
}
function draw() {
  const bounds=canvas.getBoundingClientRect(), w=bounds.width, h=bounds.height, dpr=Math.min(window.devicePixelRatio||1,3);
  if(!w||!h)return; if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#111b28';ctx.fillRect(0,0,w,h);
  const es=entities(), [u,v]=axes(), ref=anchor();
  if($('follow').checked&&ref)center=[ref[u],ref[v]];
  const span=Math.max(5,Math.min(100000,Number($('span').value)||160)), scale=w/span, sign=$('flip').checked?1:-1;
  const project=(a,b)=>[w/2+(a-center[0])*scale,h/2+sign*(b-center[1])*scale];
  const unit=Math.pow(10,Math.floor(Math.log10(80/scale)));const step=[1,2,5,10].map(x=>x*unit).find(x=>x*scale>=55)||10*unit;
  ctx.strokeStyle='#243346';ctx.lineWidth=1;ctx.font='11px system-ui';ctx.fillStyle='#7b8da4';
  for(let x=Math.floor((center[0]-span/2)/step)*step;x<center[0]+span/2;x+=step){const [px]=project(x,0);ctx.beginPath();ctx.moveTo(px,0);ctx.lineTo(px,h);ctx.stroke();ctx.fillText(x.toFixed(step<1?2:0),px+3,h-8);}
  const halfH=h/(2*scale);
  for(let y=Math.floor((center[1]-halfH)/step)*step;y<center[1]+halfH;y+=step){const [,py]=project(0,y);ctx.beginPath();ctx.moveTo(0,py);ctx.lineTo(w,py);ctx.stroke();ctx.fillText(y.toFixed(step<1?2:0),5,py-4);}
  ctx.strokeStyle='#56708d';ctx.setLineDash([4,5]);ctx.beginPath();ctx.moveTo(w/2,0);ctx.lineTo(w/2,h);ctx.moveTo(0,h/2);ctx.lineTo(w,h/2);ctx.stroke();ctx.setLineDash([]);pointHits=[];
  for(const e of es){const old=age(e)>3,c=old?'#67717f':e.is_local===true?'#46e3a3':color(e.key);ctx.strokeStyle=c;ctx.fillStyle=c;ctx.globalAlpha=old?0.45:0.85;
    if($('tracks').checked&&e.track?.length>1){ctx.beginPath();let started=false;for(const t of e.track){if(clock()-t[0]>30)continue;const p={x:t[1],y:t[2],z:t[3]},[x,y]=project(p[u],p[v]);if(!started){ctx.moveTo(x,y);started=true;}else ctx.lineTo(x,y);}ctx.lineWidth=1.5;ctx.stroke();}
    const [x,y]=project(e[u],e[v]);if(x<0||x>w||y<0||y>h)continue;ctx.beginPath();ctx.arc(x,y,e.key===anchorKey?7:5,0,Math.PI*2);ctx.fill();if(e.key===anchorKey){ctx.strokeStyle='#fff';ctx.lineWidth=2;ctx.stroke();}
    if($('labels').checked){ctx.font='12px system-ui';ctx.fillText((e.is_local===true?'[自己] ':'')+(e.name||String(e.id1))+(Number.isInteger(e.hp)?' HP:'+e.hp:'')+(old?' 旧':''),x+9,y-6);}pointHits.push({x,y,key:e.key});
  }
  ctx.globalAlpha=1;ctx.fillStyle='#a9bbd1';ctx.font='12px system-ui';ctx.fillText(`${u.toUpperCase()} → / ${v.toUpperCase()} ${sign<0?'↑':'↓'}`,12,20);
  let msg=`${es.length} 个可见实体 · 网格 ${step.toFixed(step<1?2:0)} 世界单位 · 拖动平移/滚轮缩放`;
  if(anchorKey&&!ref)msg+=' · 参考实体过期，已停止跟随';if(paused)msg+=' · 暂停仅冻结画面，不停止后台抓包';
  $('plotinfo').textContent=msg;
}
$('anchor').addEventListener('change',()=>select($('anchor').value));
$('autoSelf').addEventListener('change',()=>{syncSelf();renderTable();draw();});
$('fit').addEventListener('click',fit);
$('freeze').addEventListener('click',()=>{if(!paused)frozenNow=clock();paused=!paused;$('freeze').textContent=paused?'恢复画面':'暂停画面';renderStatus();draw();});
for(const id of ['plane','category','follow','tracks','labels','flip','span'])$(id).addEventListener('change',()=>{if(id==='plane')fit();renderTable();draw();});
canvas.addEventListener('pointerdown',ev=>{drag={x:ev.clientX,y:ev.clientY,center:[...center],moved:false};canvas.setPointerCapture(ev.pointerId);});
canvas.addEventListener('pointermove',ev=>{if(!drag)return;const dx=ev.clientX-drag.x,dy=ev.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>6){drag.moved=true;$('follow').checked=false;}if(drag.moved){const scale=canvas.clientWidth/(Number($('span').value)||160);center=[drag.center[0]-dx/scale,drag.center[1]-dy/(scale*($('flip').checked?1:-1))];draw();}});
canvas.addEventListener('pointerup',ev=>{if(drag&&!drag.moved){const r=canvas.getBoundingClientRect(),x=ev.clientX-r.left,y=ev.clientY-r.top;const hit=pointHits.find(p=>Math.hypot(p.x-x,p.y-y)<14);if(hit)select(hit.key);}drag=null;});
canvas.addEventListener('pointercancel',()=>{drag=null;});
canvas.addEventListener('wheel',ev=>{ev.preventDefault();$('span').value=Math.max(5,Math.min(100000,(Number($('span').value)||160)*(ev.deltaY>0?1.2:1/1.2))).toFixed(1);draw();},{passive:false});
window.addEventListener('resize',draw);
async function poll(){const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),2500);try{const r=await fetch('/api/state',{cache:'no-store',signal:abort.signal});if(!r.ok)throw new Error('HTTP '+r.status);const next=await r.json();connected=true;if(!paused){data=next;fetched=performance.now();syncSelf();if(!initialized&&entities().length)fit();renderTable();}renderStatus();draw();}catch(err){connected=false;$('health').textContent='后端未连接';$('health').className='badge warn';$('error').textContent='无法读取本地后端：'+err.message;}finally{clearTimeout(timer);setTimeout(poll,400);}}
setInterval(()=>{if(!paused&&data){renderStatus();draw();}},600);
poll();
