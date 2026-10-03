#!/usr/bin/env python3
"""Relais shutdown BusyBox : OpenRC puis RESTART2 pour recovery/download.
Ne lancer que via l'action shutdown de /etc/inittab.
"""
import ctypes,os,platform,subprocess,sys
from pathlib import Path

def main():
    if os.geteuid()!=0:raise SystemExit('Root requis')
    marker=Path('/run/telephone-dashboard-reboot-mode')
    try:mode=marker.read_text().strip()
    except FileNotFoundError:mode=''
    marker.unlink(missing_ok=True)
    if mode not in ('','recovery','download'):raise SystemExit('Mode invalide')
    if mode and platform.machine()!='aarch64':raise SystemExit('Architecture inattendue')
    # Charger libc avant que shutdown ne demonte/remonte les systemes de fichiers.
    libc=ctypes.CDLL(None,use_errno=True);libc.syscall.restype=ctypes.c_long
    rc=subprocess.call(['/sbin/openrc','shutdown'])
    if rc:print('OpenRC shutdown : code',rc,flush=True)
    if not mode:return rc
    if rc:
        print('Mode special annule : arret OpenRC incomplet',flush=True);return rc
    os.sync()
    # SYS_reboot=142 sur aarch64 ; LINUX_REBOOT_CMD_RESTART2.
    result=libc.syscall(ctypes.c_long(142),ctypes.c_long(0xfee1dead),
                        ctypes.c_long(672274793),ctypes.c_long(0xa1b2c3d4),ctypes.c_char_p(mode.encode()))
    if result==-1:
        print('RESTART2 :',os.strerror(ctypes.get_errno()),flush=True);return 1
    return 0
if __name__=='__main__':sys.exit(main())
