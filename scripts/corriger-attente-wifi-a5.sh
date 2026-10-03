#!/bin/sh
# Réduit uniquement le délai de secours du chargeur de firmware.
# Aucun flash, aucune suppression de firmware, aucun redémarrage.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Lancer avec sudo sh.' >&2; exit 1; }
[ "$(hostname)" = samsung-a5y17lte ] || { echo 'Ce script est réservé au A5 samsung-a5y17lte.' >&2; exit 1; }
parameter=/sys/class/firmware/timeout
[ -w "$parameter" ] || { echo 'Paramètre de délai firmware indisponible.' >&2; exit 1; }
service=/etc/init.d/a5-firmware-timeout
backup=/var/backups/a5-attente-wifi-$(date +%Y%m%d-%H%M%S)-$$
mkdir -p "$backup"
cat "$parameter" > "$backup/timeout-precedent"
if [ -e "$service" ]; then cp -p "$service" "$backup/service-precedent"; fi
if [ -e /etc/runlevels/sysinit/a5-firmware-timeout ]; then
    touch "$backup/deja-active"
fi
temporary=$(mktemp)
trap 'rm -f "$temporary"' EXIT HUP INT TERM
cat > "$temporary" <<'SERVICE'
#!/sbin/openrc-run
description="Réduit l'attente des firmwares absents sur le Samsung A5"
depend() {
    need sysfs
    before udev udev-trigger udev-settle
    keyword -containers
}
start() {
    ebegin "Délai de secours firmware : 5 secondes"
    if [ -w /sys/class/firmware/timeout ]; then
        printf '5\n' > /sys/class/firmware/timeout
        eend $?
    else
        eend 1 "Paramètre firmware indisponible"
        return 1
    fi
}
SERVICE
sh -n "$temporary"
cp "$temporary" "$service"
chmod 755 "$service"
rc-update add a5-firmware-timeout sysinit
rc-service a5-firmware-timeout restart
cat > "$backup/restaurer.sh" <<'RESTORE'
#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || exit 1
backup=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
rc-service a5-firmware-timeout stop || true
rc-update del a5-firmware-timeout sysinit || true
if [ -f "$backup/service-precedent" ]; then
    cp -p "$backup/service-precedent" /etc/init.d/a5-firmware-timeout
else
    rm -f /etc/init.d/a5-firmware-timeout
fi
if [ -e "$backup/deja-active" ]; then rc-update add a5-firmware-timeout sysinit; fi
cat "$backup/timeout-precedent" > /sys/class/firmware/timeout
echo 'Configuration précédente restaurée.'
RESTORE
chmod 700 "$backup/restaurer.sh"
printf 'Installé. Délai actuel : '
cat "$parameter"
printf 'Sauvegarde et restauration : %s/restaurer.sh\n' "$backup"
echo 'Le prochain démarrage permettra de mesurer le gain. Aucun redémarrage lancé.'
