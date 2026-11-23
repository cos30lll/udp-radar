#!/system/bin/sh
# Read-only checks. Run in the native Android root shell, not proot.
OPERIT=${1:-/data/user/0/com.ai.assistance.operit/files}
FAILED=0
if [ ! -x /system/bin/sh ]; then
    echo 'FAIL: native Android shell/filesystem not visible; do not run this inside desktop Ubuntu/proot.'
    exit 2
fi
UID_NOW=$(id -u 2>/dev/null)
if [ "$UID_NOW" = 0 ]; then echo 'OK: caller reports uid 0; run only from native Android root shell.'
else echo 'FAIL: run this manually from native Android root shell; no su escalation is performed.'; FAILED=1; fi
for NAME in ss pidof su awk sort du grep date sleep cat mkdir rm mv sed cut nohup dirname tr head wc kill id; do
    if command -v "$NAME" >/dev/null 2>&1; then echo "OK: command $NAME"
    else echo "FAIL: missing command $NAME"; FAILED=1; fi
done
for FILE in /system/bin/tcpdump "$OPERIT/usr/bin/proot" "$OPERIT/usr/bin/loader" "$OPERIT/usr/var/lib/proot-distro/installed-rootfs/ubuntu/usr/bin/python3"; do
    if [ -x "$FILE" ]; then echo "OK: executable $FILE"
    else echo "FAIL: executable unavailable $FILE"; FAILED=1; fi
done
echo 'Scope: listed native prerequisites only; Python/libzstd must be checked separately inside Operit Ubuntu.'
echo 'No game, capture, proot, server, su or deployment process was started. Runtime behavior remains user-verified.'
[ "$FAILED" = 0 ] || exit 2
exit 0