#!/system/bin/sh
BASE='/storage/emulated/0/Download/超自然行动'
APP="$BASE/成品/udp-radar-v1"
DURATION=${1:-600}
HTTP_PORT=${2:-8765}
case "$DURATION" in ''|*[!0-9]*) echo '运行秒数须为数字'; exit 2 ;; esac
case "$HTTP_PORT" in ''|*[!0-9]*) echo '网页端口须为数字'; exit 2 ;; esac
[ "$DURATION" -ge 30 ] && [ "$DURATION" -le 3600 ] || { echo '运行时间须为30至3600秒'; exit 2; }
[ "$HTTP_PORT" -ge 1024 ] && [ "$HTTP_PORT" -le 65535 ] || { echo '端口须为1024至65535'; exit 2; }
DURATION=$(expr "$DURATION" + 0)
HTTP_PORT=$(expr "$HTTP_PORT" + 0)
if [ "$(id -u)" != 0 ]; then
    exec /system/bin/su -c "/system/bin/sh '$APP/启动.sh' '$DURATION' '$HTTP_PORT'"
fi
for F in runner.sh server.py protocol.py identity.py index.html app.js style.css; do
    [ -s "$APP/$F" ] || { echo "缺少成品文件：$F"; exit 3; }
done
LOGROOT="$BASE/日志/udp-radar-v1"
mkdir -p "$LOGROOT" || exit 3
LOCK="$LOGROOT/.start-lock"
if ! mkdir "$LOCK" 2>/dev/null; then
    echo "启动锁存在，请先确认无重复启动：$LOCK"
    exit 4
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
if [ -s "$LOGROOT/current.txt" ]; then
    OLD=$(cat "$LOGROOT/current.txt")
    case "$OLD" in "$LOGROOT/"*)
        if [ -s "$OLD/supervisor.pid" ]; then
            OLD_PID=$(cat "$OLD/supervisor.pid")
            case "$OLD_PID" in ''|*[!0-9]*) ;; *)
                CMD=$(tr '\000' ' ' < "/proc/$OLD_PID/cmdline" 2>/dev/null)
                case "$CMD" in *runner.sh*"$OLD"*) echo '已有雷达会话，请先运行停止.sh'; exit 4 ;; esac
            ;; esac
        fi
    ;; esac
fi
SESSION=$(/system/bin/date '+%Y%m%d-%H%M%S')-$$
RUN="$LOGROOT/$SESSION"
mkdir -p "$RUN/tmp" || exit 3
export TMPDIR="$RUN/tmp" PROOT_TMP_DIR="$RUN/tmp"
/system/bin/sh -n "$APP/runner.sh" || exit 3
nohup /system/bin/sh "$APP/runner.sh" "$RUN" "$DURATION" "$HTTP_PORT" > "$RUN/launcher.log" 2>&1 < /dev/null &
SUPERVISOR=$!
printf '%s\n' "$SUPERVISOR" > "$RUN/launcher.pid"
printf '%s\n' "$RUN" > "$LOGROOT/current.txt.new"
mv "$LOGROOT/current.txt.new" "$LOGROOT/current.txt"
I=0
while [ "$I" -lt 20 ] && kill -0 "$SUPERVISOR" 2>/dev/null && [ ! -s "$RUN/server-ready.json" ]; do sleep 1; I=$((I+1)); done
if [ -s "$RUN/server-ready.json" ] && kill -0 "$SUPERVISOR" 2>/dev/null; then
    echo "网页后端已就绪：http://127.0.0.1:$HTTP_PORT"
    echo "日志：$RUN"
    echo "最长运行 $DURATION 秒；用停止.sh结束。"
    echo '本次限时缓存全机UDP，仅解析已确认游戏端口；会话约64MiB时停止。'
    echo '请手动进入场景，查看网页包数、初始化/HP观测和坐标是否持续更新。'
    echo '本版需浏览器分屏/浮窗，不是游戏内叠加层。'
else
    : > "$RUN/STOP"
    kill -TERM "$SUPERVISOR" 2>/dev/null
    echo "启动未确认，已请求收尾；查看 $RUN/server.log 和 launcher.log"
    tail -12 "$RUN/server.log" "$RUN/launcher.log" 2>/dev/null
    exit 5
fi
