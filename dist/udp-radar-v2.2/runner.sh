#!/system/bin/sh
# Root Android supervisor; run explicitly by user. Does not launch game.
BASE='/storage/emulated/0/Download/超自然行动'
APP="$BASE/成品/udp-radar-v1"
RUN="$1"
DURATION="$2"
HTTP_PORT="$3"
case "$RUN" in "$BASE/日志/udp-radar-v1/"*) ;; *) exit 2 ;; esac
case "$DURATION" in ''|*[!0-9]*) exit 2 ;; esac
case "$HTTP_PORT" in ''|*[!0-9]*) exit 2 ;; esac
[ -d "$RUN" ] || exit 2
export TMPDIR="$RUN/tmp" PROOT_TMP_DIR="$RUN/tmp"
mkdir -p "$TMPDIR"
printf '%s\n' "$$" > "$RUN/supervisor.pid"
CAP_PID=''
BACK_PID=''
GAME_PID=0
PORTS=''
CHILD_START=0
EPOCH=0
GAME_START=0
ROUND=0
STOP=0
REASON='starting_continuous_udp'
START=$(/system/bin/date +%s)
END=$((START+DURATION))
cleanup_done=0
state() {
    NOW=$(/system/bin/date +%s)
    LEFT=$((END-NOW)); [ "$LEFT" -ge 0 ] || LEFT=0
    PORTJSON=$(printf '%s' "$PORTS" | tr ' ' ',')
    RUNNING=false
    if [ -n "$CAP_PID" ] && kill -0 "$CAP_PID" 2>/dev/null; then RUNNING=true; fi
    printf '{"running":%s,"game_pid":%s,"game_epoch":%s,"game_started_at":%s,"ports":[%s],"capture_scope":"device_udp","capture_processes":%s,"reason":"%s","remaining_seconds":%s,"time":%s}\n' "$RUNNING" "$GAME_PID" "$EPOCH" "$GAME_START" "$PORTJSON" "$ROUND" "$REASON" "$LEFT" "$NOW" > "$RUN/capture.json.new"
    mv "$RUN/capture.json.new" "$RUN/capture.json"
}
stop_capture() {
    if [ -n "$CAP_PID" ]; then
        kill -INT "$CAP_PID" 2>/dev/null
        I=0
        while kill -0 "$CAP_PID" 2>/dev/null && [ "$I" -lt 4 ]; do sleep 1; I=$((I+1)); done
        if kill -0 "$CAP_PID" 2>/dev/null; then kill -TERM "$CAP_PID" 2>/dev/null; fi
        wait "$CAP_PID" 2>/dev/null
        CAP_PID=''
        rm -f "$RUN/tcpdump.pid"
    fi
}
cleanup() {
    [ "$cleanup_done" -eq 0 ] || return
    cleanup_done=1
    stop_capture
    [ -f "$RUN/end-reason.txt" ] || printf '%s\n' "$REASON" > "$RUN/end-reason.txt"
    REASON='stopped'
    state
    if [ -s "$RUN/server.pid" ]; then
        PY_PID=$(cat "$RUN/server.pid")
        case "$PY_PID" in ''|*[!0-9]*) ;; *)
            CMD=$(tr '\000' ' ' < "/proc/$PY_PID/cmdline" 2>/dev/null)
            case "$CMD" in *server.py*"$RUN"*) kill -TERM "$PY_PID" 2>/dev/null ;; esac
        ;; esac
    fi
    if [ -n "$BACK_PID" ]; then
        I=0
        while kill -0 "$BACK_PID" 2>/dev/null && [ "$I" -lt 4 ]; do sleep 1; I=$((I+1)); done
        if kill -0 "$BACK_PID" 2>/dev/null; then kill -TERM "$BACK_PID" 2>/dev/null; fi
        wait "$BACK_PID" 2>/dev/null
    fi
    /system/bin/date '+%Y-%m-%dT%H:%M:%S%z' > "$RUN/finished.txt"
}
trap 'STOP=1' INT TERM HUP
trap cleanup EXIT
OPERIT='/data/user/0/com.ai.assistance.operit/files'
BIN="$OPERIT/usr/bin"
ROOTFS="$OPERIT/usr/var/lib/proot-distro/installed-rootfs/ubuntu"
[ -x "$BIN/proot" ] && [ -x "$ROOTFS/usr/bin/python3" ] || { echo 'Missing Operit Ubuntu Python runtime'; exit 3; }
[ -x /system/bin/tcpdump ] || { echo 'Missing /system/bin/tcpdump'; exit 3; }
export PROOT_LOADER="$BIN/loader"
unset LD_PRELOAD LD_LIBRARY_PATH
# Capture starts before backend readiness and never restarts on game/port changes.
# Scope is all device UDP, but only ss-confirmed game ports enter the decoder.
ROUND=1
STEM="$RUN/capture-0001"
printf '{"mode":"continuous_udp","ports":[],"game_pid":0}\n' > "$STEM.json"
printf '%s\n' 'udp' > "$RUN/filter.latest.txt"
/system/bin/tcpdump -p -i any -nn -s 0 -U -B 4096 -w "$STEM.pcap" udp > "$STEM.log" 2>&1 &
CAP_PID=$!
printf '%s\n' "$CAP_PID" > "$RUN/tcpdump.pid"
state
"$BIN/proot" -0 -r "$ROOTFS" --link2symlink -b /dev -b /proc -b /sys -b /storage/emulated/0 -w "$APP" /usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 HOME="$RUN/tmp" TMPDIR="$RUN/tmp" XDG_CACHE_HOME="$RUN/tmp" PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B "$APP/server.py" --run "$RUN" --port "$HTTP_PORT" > "$RUN/server.log" 2>&1 &
BACK_PID=$!
printf '%s\n' "$BACK_PID" > "$RUN/proot.pid"
I=0
while [ ! -f "$RUN/server-ready.json" ] && kill -0 "$BACK_PID" 2>/dev/null && [ "$I" -lt 15 ] && [ "$STOP" -eq 0 ]; do sleep 1; I=$((I+1)); done
if [ ! -f "$RUN/server-ready.json" ]; then echo 'Backend did not become ready; see server.log'; exit 4; fi
if ! kill -0 "$CAP_PID" 2>/dev/null; then REASON='tcpdump_failed'; exit 5; fi
state
while [ "$STOP" -eq 0 ]; do
    [ ! -f "$RUN/STOP" ] || break
    NOW=$(/system/bin/date +%s)
    [ "$NOW" -lt "$END" ] || { REASON='time_limit'; break; }
    kill -0 "$BACK_PID" 2>/dev/null || { REASON='backend_exited'; break; }
    USED=$(du -sk "$RUN" 2>/dev/null | awk '{print $1}')
    case "$USED" in ''|*[!0-9]*) REASON='disk_check_failed'; break ;; esac
    [ "$USED" -lt 65536 ] || { REASON='session_size_limit'; break; }
    PIDLIST=$(pidof com.pi.czrxdfirst 2>/dev/null)
    set -- $PIDLIST
    NEXT_PID=${1:-0}
    NEXT_PORTS=''
    if [ "$NEXT_PID" -gt 0 ]; then
        ss -H -u -a -n -p -e 2>/dev/null | grep "pid=$NEXT_PID," > "$RUN/sockets.latest.txt"
        NEXT_PORTS=$(awk '{n=split($4,a,":");p=a[n];if(p ~ /^[0-9]+$/ && p>0 && p<65536)print p}' "$RUN/sockets.latest.txt" | sort -nu | tr '\n' ' ' | sed 's/ *$//')
    fi
    if [ "$NEXT_PID" != "$GAME_PID" ]; then
        GAME_PID=$NEXT_PID
        PORTS=''
        EPOCH=$((EPOCH+1))
        GAME_START=0
        if [ "$GAME_PID" -gt 0 ]; then
            # Approximate process start from /proc so buffered old-PID traffic is not reused.
            GAME_START=$(awk -v now="$NOW" -v up="$(cut -d ' ' -f 1 /proc/uptime)" '{print int(now-up+$22/100)}' "/proc/$GAME_PID/stat" 2>/dev/null)
            case "$GAME_START" in ''|*[!0-9]*) GAME_START=$NOW ;; esac
        fi
    fi
    if [ "$GAME_PID" -gt 0 ]; then
        PORTS=$(printf '%s %s\n' "$PORTS" "$NEXT_PORTS" | tr ' ' '\n' | awk '/^[0-9]+$/ && $0>0 && $0<65536 {print $0}' | sort -nu | tr '\n' ' ' | sed 's/ *$//')
    fi
    if ! kill -0 "$CAP_PID" 2>/dev/null; then
        wait "$CAP_PID"; RC=$?
        printf '%s %s\n' "$ROUND" "$RC" >> "$RUN/capture-exits.txt"
        CAP_PID=''
        REASON='tcpdump_exited'
        break
    fi
    [ "$STOP" -eq 0 ] && [ ! -f "$RUN/STOP" ] || break
    if [ -n "$PORTS" ]; then REASON='continuous_game_udp'; else REASON='buffering_until_game_ports'; fi
    state
    sleep 1
done
printf '%s\n' "$REASON" > "$RUN/end-reason.txt"
exit 0
