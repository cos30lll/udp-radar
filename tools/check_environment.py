#!/usr/bin/env python3
"""Check this Python environment only; Android host readiness is a separate check."""
import argparse, ctypes, ctypes.util, json, platform, shutil, sys
from pathlib import Path
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--android',action='store_true',help='report static paths only; does not certify Android/root readiness');p.add_argument('--operit-files',default='/data/user/0/com.ai.assistance.operit/files');a=p.parse_args()
 lib=ctypes.util.find_library('zstd');loadable=False
 if lib:
  try: ctypes.CDLL(lib);loadable=True
  except OSError: pass
 result={'scope':'current Python environment','python':platform.python_version(),'python_min_3_9':sys.version_info>=(3,9),'libzstd':lib,'libzstd_loadable':loadable,'node_optional':shutil.which('node'),'dotnet_optional':shutil.which('dotnet'),'android_device_ready':'not established; run check_android.sh in native Android root shell'}
 ok=result['python_min_3_9'] and loadable
 if a.android:
  h=Path(a.operit_files);required_files=(Path('/system/bin/tcpdump'),h/'usr/bin/proot',h/'usr/bin/loader',h/'usr/var/lib/proot-distro/installed-rootfs/ubuntu/usr/bin/python3')
  result['static_file_visibility']={str(f):f.is_file() for f in required_files}
  result['current_path_commands']={n:shutil.which(n) for n in ('ss','pidof','su','awk','sort','du','grep','date','sleep')}
  result['root_permissions']='not probed; no su invocation; proot uid 0 is not proof of Android root'
  result['android_result']='INCOMPLETE: static visibility is not host/device validation'
  ok=False
 print(json.dumps(result,ensure_ascii=True,indent=2));return 0 if ok else 2
if __name__=='__main__': raise SystemExit(main())
