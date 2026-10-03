#!/bin/sh
# A executer sur le PC juste apres le sideload, dans TWRP (hors mode sideload).
# Aucun mot de passe n'est stocke ; passwd reste interactif sur le telephone.
set -eu
command -v adb >/dev/null
exec adb shell -t '
ROOTFS=/tmp/postmarketos/chroot/mnt/pmOS
mountpoint -q "$ROOTFS" || { echo "Rootfs non monte : garder TWRP ouvert apres le sideload."; exit 1; }
[ -f "$ROOTFS/etc/passwd" ] || exit 1
mkdir -p "$ROOTFS/dev" || exit 1
mount -o bind /dev "$ROOTFS/dev" || exit 1
chroot "$ROOTFS" /usr/bin/passwd user
result=$?
umount "$ROOTFS/dev"
exit "$result"
'
