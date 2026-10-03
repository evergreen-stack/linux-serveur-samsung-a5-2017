#!/usr/bin/env python3
"""Vérifier le ZIP, ses ajouts et l'absence des secrets de l'installation source."""
import argparse,gzip,hashlib,json,re,struct,subprocess,tarfile,zipfile
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('zip',type=Path);parser.add_argument('--report',type=Path);a=parser.parse_args()
    files={};names=set();apkcount=0
    needed=['etc/shadow','etc/inittab','etc/locale.conf','etc/timezone','etc/conf.d/wpa_supplicant',
            'etc/modules-load.d/telephone-home.conf','usr/local/bin/telephone-dashboard',
            'usr/local/lib/telephone-dashboard/dashboard-grand.py','usr/local/lib/telephone-dashboard/arret-mode.py',
            'boot/boot.img','boot/vmlinuz','boot/initramfs','usr/lib/modules/3.18.140/kernel/drivers/input/evdev.ko',
            'etc/ssh/sshd_config.d/50-serveur-a5.conf','etc/passwd','usr/lib/apk/db/installed']
    with zipfile.ZipFile(a.zip) as z:
        assert z.testzip() is None,'CRC ZIP'
        update=z.read('META-INF/com/google/android/update-binary')
        assert b'getprop ro.product.device' in update and b'mmcblk0p10' in update and b'mmcblk0p19' in update
        assert "DEVICE='samsung-a5y17lte'" in z.read('chroot/install_options').decode()
        assert "ISOREC='false'" in z.read('chroot/install_options').decode()
        with z.open('rootfs.tar.gz') as stream,tarfile.open(fileobj=stream,mode='r|gz') as t:
            for m in t:
                n=m.name.removeprefix('./');names.add(n)
                content=None
                if n in needed:content=t.extractfile(m).read();files[n]=content
                if n.startswith('opt/linux-serveur-samsung-a5-2017/apk-wifi/') and n.endswith('.apk'):apkcount+=1
                assert not(n.startswith(('home/','root/','var/backups/','var/log/','var/lib/chrony/','etc/credstore/','etc/credstore.encrypted/')) and m.isfile()),'Données privées dans '+n
                assert not(n.startswith('etc/NetworkManager/system-connections/') and m.isfile()),'Profil Wi-Fi'
                assert not n.startswith('etc/ssh/ssh_host_'),'Clé SSH hôte'
                assert not n.endswith('authorized_keys'),'Clé SSH autorisée'
                assert not(n.endswith(('.bash_history','.ash_history'))),'Historique'
                if m.isfile() and n.startswith(('etc/','usr/local/')) and m.size<2**20:
                    content=content if content is not None else t.extractfile(m).read()
                    assert not re.search(rb'(?mi)^(?:psk|password)\s*=\s*[^#\r\n]+',content),'Secret en clair dans '+n
                    assert b'-----BEGIN OPENSSH PRIVATE KEY-----' not in content,'Clé privée SSH'
    assert set(needed)<=files.keys(),str(set(needed)-files.keys())
    shadow=files['etc/shadow'].decode().splitlines()
    assert all(s.split(':')[1].startswith(('!','*')) for s in shadow),'Compte avec secret / accès vide'
    assert any(s.startswith('user:!:') for s in shadow) and any(s.startswith('root:!:') for s in shadow)
    assert 'user:x:10000:10000:' in files['etc/passwd'].decode()
    assert b'tty1::respawn:/usr/local/bin/telephone-dashboard' in files['etc/inittab']
    assert b'fr_FR.UTF-8' in files['etc/locale.conf'] and files['etc/timezone'].strip()==b'Europe/Paris'
    assert b'"-u"' in files['etc/conf.d/wpa_supplicant'] and files['etc/modules-load.d/telephone-home.conf'].strip()==b'evdev'
    for name in ('sshd','networkmanager','wpa_supplicant','chronyd'):assert 'etc/runlevels/default/'+name in names
    for phrase in ('Mode secours','Recovery (TWRP)','Download mode','SCREEN_TIMEOUT=300'):assert phrase.encode() in files['usr/local/lib/telephone-dashboard/dashboard-grand.py']
    assert 'P:linux-samsung-a5y17lte\nV:3.18.140-r3\n' in files['usr/lib/apk/db/installed'].decode()
    img=files['boot/boot.img'];assert img[:8]==b'ANDROID!'
    k,_,r,_,_,_,_,page,_,_=struct.unpack_from('<10I',img,8)
    offset=page+((k+page-1)//page*page);ram=img[offset:offset+r]
    assert img[page:page+k]==files['boot/vmlinuz'] and ram==files['boot/initramfs']
    raw=gzip.decompress(ram)
    assert b'--direct-io=off' in raw and b'--direct-io=on' not in raw
    assert b'console=tty0' in img[:page]
    assert apkcount>=6,'APK hors ligne absents'
    report={'zip':a.zip.name,'taille_octets':a.zip.stat().st_size,'sha256':hashlib.file_digest(a.zip.open('rb'),'sha256').hexdigest(),
            'cible':'samsung-a5y17lte','noyau':'3.18.140-r3','crc_zip':'OK','installer':'postmarketOS recovery installer 1.0.7 + garde modèle/partitions',
            'ajouts':'tableau, menu, Home, evdev, veille 300 s, Wi-Fi/D-Bus, SSH, français, Europe/Paris, chrony',
            'apk_wifi_hors_ligne':apkcount,'comptes':'user et root verrouillés, choisir son mot de passe dans TWRP',
            'secrets':'Aucun profil Wi-Fi, mot de passe de compte, clé SSH personnelle/hôte, historique, journal ou sauvegarde dans le rootfs',
            'boot_sha256':hashlib.sha256(img).hexdigest(),'validation_materielle':'Base/correctifs essayés sur A5 ; ZIP de distribution à réinstaller pour validation matérielle complète'}
    if a.report:a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
