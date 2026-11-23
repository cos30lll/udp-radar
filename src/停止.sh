#!/system/bin/sh
BASE='/storage/emulated/0/Download/超自然行动'
APP="$BASE/成品/udp-radar-v1"
ROOT="$BASE/日志/udp-radar-v1"
if [ "$(id -u)" != 0 ]; then
    exec /system/bin/su -c "/system/bin/sh '$APP/停止.sh'"
fi
[ -s "$ROOT/current.txt" ] || { echo '没有记录到雷达会话'; exit 0; }
RUN=$(cat "$ROOT/current.txt")
case "$RUN" in "$ROOT/"*) ;; *) echo '会话路径异常，未操作进程'; exit 2 ;; esac
case "$RUN" in *'/../'*|*'/./'*) echo '会话路径异常'; exit 2 ;; esac
[ -d "$RUN" ] || { echo '会话目录不存在'; exit 2; }
: > "$RUN/STOP"
owned_signal() {
    FILE="$1"; MODE="$2"; SIG="$3"
    [ -s "$RUN/$FILE" ] || return 0
    PID=$(cat "$RUN/$FILE")
    case "$PID" in ''|*[!0-9]*) return 0 ;; esac
    [ "$PID" -gt 1 ] || return 0
    CMD=$(tr '\000' ' ' < "/proc/$PID/cmdline" 2>/dev/null)
    case "$MODE:$CMD" in
        capture:*tcpdump*"$RUN/capture-"*) kill -"$SIG" "$PID" 2>/dev/null ;;
        supervisor:*runner.sh*"$RUN"*) kill -"$SIG" "$PID" 2>/dev/null ;;
        server:*server.py*"$RUN"*) kill -"$SIG" "$PID" 2>/dev/null ;;
        proot:*proot*server.py*"$RUN"*) kill -"$SIG" "$PID" 2>/dev/null ;;
    esac
}
# Stop only this session's capture immediately; never kill other tcpdump processes.
owned_signal tcpdump.pid capture INT
owned_signal supervisor.pid supervisor TERM
I=0
while [ ! -f "$RUN/finished.txt" ] && [ "$I" -lt 12 ]; do sleep 1; I=$((I+1)); done
if [ ! -f "$RUN/finished.txt" ]; then
    owned_signal tcpdump.pid capture TERM
    owned_signal server.pid server TERM
    owned_signal proot.pid proot TERM
    echo '已向本会话残留进程发送停止信号；请查看 launcher.log。'
else
    echo '本会话已结束，游戏进程不受影响。'
fi
echo "日志：$RUN"
