#!/usr/bin/env python3
"""Construire une distribution assainie dans un rootfs isole, sans flash.
Prend comme entree le ZIP recovery genere par pmbootstrap et les correctifs
BOOT/evdev de la meme compilation. Requiert Linux, root, QEMU user statique.
"""
import argparse,gzip,hashlib,json,os,re,shutil,struct,subprocess,tarfile,time,zipfile
from pathlib import Path

def run(*args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def write(root,name,value,mode=0o644):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value);p.chmod(mode)
def remove(p):
    if p.is_symlink() or p.is_file():p.unlink()
    elif p.exists():shutil.rmtree(p)
def main():
    parser=argparse.ArgumentParser()
    for name in ('base-zip','boot-image','kernel-apk','evdev','qemu','work','output'):parser.add_argument('--'+name,required=True,type=Path)
    a=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('Utiliser sudo ; aucun flash execute.')
    repo=Path(__file__).resolve().parents[1];root=a.work.resolve()/'rootfs'
    if root.exists():raise SystemExit('Le rootfs de travail existe deja ; choisir un nouveau --work.')
    root.mkdir(parents=True)
    with zipfile.ZipFile(a.base_zip) as z:
        with z.open('rootfs.tar.gz') as packed:
            with tarfile.open(fileobj=packed,mode='r|gz') as t:t.extractall(root,filter='fully_trusted')
    # Retirer les donnees privees AVANT toute installation de paquet.
    sanitize(root)
    qemutarget=root/'usr/bin/qemu-aarch64-static';shutil.copyfile(a.qemu,qemutarget);qemutarget.chmod(0o755)
    entry=Path('/proc/sys/fs/binfmt_misc/a5-rom-build')
    if entry.exists():raise SystemExit('Une registration a5-rom-build existe deja.')
    magic=bytes.fromhex('7f454c460201010000000000000000000200b700')
    mask=bytes.fromhex('ffffffffffffff00fffffffffffffffffeffffff')
    escape=lambda data: ''.join('\\x%02x'%b for b in data).encode()
    code=b':a5-rom-build:M::'+escape(magic)+b':'+escape(mask)+b':'+str(qemutarget).encode()+b':F'
    Path('/proc/sys/fs/binfmt_misc/register').write_bytes(code)
    mounted=[]
    try:
        for mount in ('dev','proc'):
            target=root/mount;target.mkdir(exist_ok=True)
            run('mount','--bind','/'+mount,str(target));mounted.append(target)
        shutil.copyfile('/etc/resolv.conf',root/'etc/resolv.conf')
        ch=lambda *cmd,**kw:run('chroot',str(root),*cmd,**kw)
        ch('/sbin/apk','update')
        packages=['python3','networkmanager-cli','networkmanager-wifi','wpa_supplicant','wpa_supplicant-openrc','musl-locales','lang','tzdata','chrony','chrony-openrc','openssh']
        ch('/sbin/apk','add',*packages,input='y\n',text=True)
        shutil.copyfile(a.kernel_apk,root/'tmp/linux-samsung-a5y17lte.apk')
        ch('/sbin/apk','add','--allow-untrusted','/tmp/linux-samsung-a5y17lte.apk',input='y\n',text=True)
        offline=root/'opt/linux-serveur-samsung-a5-2017/apk-wifi';offline.mkdir(parents=True)
        ch('/sbin/apk','fetch','--recursive','--output','/opt/linux-serveur-samsung-a5-2017/apk-wifi','networkmanager-cli','networkmanager-wifi','wpa_supplicant','wpa_supplicant-openrc')
        apkdest=repo/'apk-wifi';apkdest.mkdir(exist_ok=True)
        for p in offline.glob('*.apk'):shutil.copyfile(p,apkdest/p.name)
        manifest=ch('/sbin/apk','info','-v',capture_output=True,text=True).stdout
        (repo/'release/paquets-installes.txt').write_text(manifest)
        write(root,'etc/conf.d/wpa_supplicant','wpa_supplicant_args="-u"\n')
        write(root,'etc/locale.conf','export LANG=fr_FR.UTF-8\nexport LANGUAGE=fr_FR:fr\n')
        write(root,'etc/profile.d/99-francais.sh','export LANG=fr_FR.UTF-8\nexport LANGUAGE=fr_FR:fr\nunset LC_ALL\n')
        remove(root/'etc/localtime');(root/'etc/localtime').symlink_to('/usr/share/zoneinfo/Europe/Paris')
        write(root,'etc/timezone','Europe/Paris\n')
        write(root,'etc/hostname','samsung-a5y17lte\n')
        write(root,'etc/modules-load.d/telephone-home.conf','evdev\n')
        module=root/'lib/modules/3.18.140/kernel/drivers/input/evdev.ko';module.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a.evdev,module)
        ch('/sbin/depmod','-a','3.18.140')
        for service,level in [('modules','boot'),('sshd','default'),('networkmanager','default'),('wpa_supplicant','default'),('chronyd','default')]:ch('/sbin/rc-update','add',service,level)
        dashboard=root/'usr/local/lib/telephone-dashboard';dashboard.mkdir(parents=True,exist_ok=True)
        for name in ('dashboard-grand.py','arret-mode.py'):shutil.copyfile(repo/'src/dashboard'/name,dashboard/name)
        write(root,'usr/local/bin/telephone-dashboard',LAUNCHER,0o755)
        tab=(root/'etc/inittab').read_text()
        tab=re.sub(r'^tty1::respawn:.*$', 'tty1::respawn:/usr/local/bin/telephone-dashboard',tab,flags=re.M)
        tab=tab.replace('::shutdown:/sbin/openrc shutdown','::shutdown:/usr/bin/python3 /usr/local/lib/telephone-dashboard/arret-mode.py')
        write(root,'etc/inittab',tab)
        # Le BOOT fourni est celui teste : noyau r3, console et direct-io=off.
        install_boot(root,a.boot_image)
        write(root,'etc/motd','Linux serveur - Samsung Galaxy A5 (2017)\nBase Nura / postmarketOS / Alpine Linux.\nGestion des paquets : apk.\n')
        write(root,'etc/ssh/sshd_config.d/50-serveur-a5.conf','PermitRootLogin no\nPasswordAuthentication yes\nPermitEmptyPasswords no\n')
        # Le compte reste verrouille. Chaque utilisateur choisit son propre secret via TWRP.
        ch('/bin/sh','-c','id user >/dev/null && command -v passwd && python3 -c "import ast;ast.parse(open(\'/usr/local/lib/telephone-dashboard/dashboard-grand.py\').read())"')
    finally:
        for target in reversed(mounted):run('umount',str(target))
        entry.write_text('-1')
        remove(qemutarget)
    sanitize(root)
    # Installer officiel cree /home depuis /etc/skel : ne pas inclure /home.
    remove(root/'home')
    pack(root,a)

def install_boot(root,path):
    image=path.read_bytes()
    if image[:8]!=b'ANDROID!':raise ValueError('BOOT Android attendu')
    k,_,r,_,second,_,_,page,dt,_=struct.unpack_from('<10I',image,8)
    align=lambda n:(n+page-1)//page*page
    ramstart=page+align(k);dtstart=ramstart+align(r)+align(second)
    (root/'boot/boot.img').write_bytes(image)
    (root/'boot/vmlinuz').write_bytes(image[page:page+k])
    (root/'boot/initramfs').write_bytes(image[ramstart:ramstart+r])
    (root/'boot/dt.img').write_bytes(image[dtstart:dtstart+dt])

def pack(root,a):
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.base_zip) as original,zipfile.ZipFile(a.output,'w') as out:
        for info in original.infolist():
            if info.filename!='rootfs.tar.gz':
                data=original.read(info.filename)
                if info.filename=='META-INF/com/google/android/update-binary' and b'getprop ro.product.device' not in data:
                    data=data.replace(b'export ZIP="$3"\n',b'export ZIP="$3"\n'+DEVICE_GUARD.encode())
                out.writestr(info,data)
        with out.open('rootfs.tar.gz','w',force_zip64=True) as packed:
            with gzip.GzipFile(fileobj=packed,mode='wb',mtime=0) as gz:
                with tarfile.open(fileobj=gz,mode='w|') as t:
                    for path in sorted(root.iterdir()):t.add(path,arcname=path.name)
    print('ZIP construit :',a.output,flush=True)

def sanitize(root):
    for name in ('home','root','var/backups','var/log','var/cache/apk','run','tmp','var/tmp',
                 'etc/NetworkManager/system-connections','var/lib/NetworkManager','var/lib/chrony',
                 'etc/wpa_supplicant/wpa_supplicant.conf','var/lib/telephone-dashboard',
                 'etc/machine-id','var/lib/dbus/machine-id','etc/resolv.conf','etc/credstore','etc/credstore.encrypted'):
        remove(root/name)
    for name in ('root','var/log','var/cache/apk','run','tmp','var/tmp','etc/NetworkManager/system-connections','var/lib/NetworkManager','var/lib/chrony','var/lib/telephone-dashboard'):
        (root/name).mkdir(parents=True,exist_ok=True)
    (root/'tmp').chmod(0o1777);(root/'var/tmp').chmod(0o1777)
    (root/'root').chmod(0o700);(root/'etc/NetworkManager/system-connections').chmod(0o700)
    write(root,'etc/resolv.conf','')
    for pattern in ('etc/ssh/ssh_host_*','etc/shadow-','etc/passwd-','etc/group-','etc/gshadow-','etc/dropbear/dropbear_*_host_key','var/lib/*/random-seed','etc/apk/keys/*fra*'):
        for path in root.glob(pattern):remove(path)
    shadow=root/'etc/shadow'
    if shadow.exists():
        lines=[]
        for line in shadow.read_text().splitlines():
            fields=line.split(':')
            if len(fields)>1:fields[1]='!'
            lines.append(':'.join(fields))
        write(root,'etc/shadow','\n'.join(lines)+'\n',0o640)
    gshadow=root/'etc/gshadow'
    if gshadow.exists():
        lines=[]
        for line in gshadow.read_text().splitlines():
            fields=line.split(':')
            if len(fields)>1:fields[1]='!'
            lines.append(':'.join(fields))
        write(root,'etc/gshadow','\n'.join(lines)+'\n',0o640)
    skel=root/'etc/skel'
    for pattern in ('**/authorized_keys','**/id_*','**/*history*'):
        for path in skel.glob(pattern):remove(path)

DEVICE_GUARD='''
# Refuser tout appareil / agencement different avant l'installation.
if [ "$(getprop ro.product.device)" != a5y17lte ] ||
   [ "$(readlink -f /dev/block/platform/13540000.dwmmc0/by-name/BOOT)" != /dev/block/mmcblk0p10 ] ||
   [ "$(readlink -f /dev/block/platform/13540000.dwmmc0/by-name/SYSTEM)" != /dev/block/mmcblk0p19 ]; then
    echo "ui_print ERREUR : ce ZIP cible exclusivement samsung-a5y17lte (BOOT p10 / SYSTEM p19)." > /proc/self/fd/"$OUTFD"
    echo ui_print > /proc/self/fd/"$OUTFD"
    exit 1
fi
'''

LAUNCHER='''#!/bin/sh
if [ -e /var/lib/telephone-dashboard/rescue-next-boot ] && [ "$(cat /var/lib/telephone-dashboard/rescue-next-boot)" != "$(cat /proc/sys/kernel/random/boot_id)" ]; then
    rm -f /var/lib/telephone-dashboard/rescue-next-boot
    touch /run/telephone-dashboard-rescue-active
fi
if [ -e /run/telephone-dashboard-rescue-active ]; then
    /usr/bin/python3 /usr/local/lib/telephone-dashboard/dashboard-grand.py --console
    exec /sbin/getty 38400 tty1
fi
exec /usr/bin/python3 /usr/local/lib/telephone-dashboard/dashboard-grand.py >> /run/telephone-dashboard-grand.log 2>&1
'''
if __name__=='__main__':main()
