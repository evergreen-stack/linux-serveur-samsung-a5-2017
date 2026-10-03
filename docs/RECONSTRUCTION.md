# Reconstruction et provenance

## Base exacte

- pmbootstrap 3.11.1 ; pmaports `bbcd4e5b5f1d6feb37d22f240e70a0d9d9416315`.
- Packages officiels archivés `device/archived/device-samsung-a5y17lte` et `device/archived/linux-samsung-a5y17lte`.
- Port `aarch64`, UI `none`, OpenRC. Firmware officiel du port déjà inclus dans la base.
- Linux 3.18.140, LineageOS `725aa5ab01e5a1272f34f01764f09009edf32777` ; qcacld `48f9ab5d5c161549be098997fa0e3602c1547213`. Archives sources exactes dans `release/sources/` ; configuration et patches dans `src/port/linux-samsung-a5y17lte/`.
- Compiler GCC6 : requis par ce port, ne pas remplacer automatiquement par un GCC récent.
- Recovery installer postmarketOS 1.0.7 ; archive source incluse dans `release/sources/`.
- [TWRP officiel pour Galaxy A5 2017](https://twrp.me/samsung/samsunggalaxya52017.html), [image exacte 3.7.0_9-0](https://dl.twrp.me/a5y17lte/twrp-3.7.0_9-0-a5y17lte.img.html). SHA256 : `d31e7f918be2eec9422044c65544b02696a836872fb663e778ff2aa28dd9439c`.

## Correctifs conservés

Le `deviceinfo` conserve `deviceinfo_format_version="0"` et n'ajoute pas `deviceinfo_header_version`.

Le noyau est au pkgrel 3, avec MPTCP désactivé, correctif de liaison quickack, framebuffer console activé et `CONFIG_CMDLINE_EXTEND=y`. Le packaging inclut aussi les modules natifs, dont `evdev.ko`, en plus du WLAN externe. Les empreintes source de l'APKBUILD correspondent aux fichiers fournis.

Le BOOT de `release/boot-a5y17lte-r3.img` est l'image testée avec la console visible : noyau r3, DTB du modèle, initramfs `losetup --direct-io=off`, sortie sur tty1. Le rootfs distribué contient les mêmes vmlinuz et initramfs que cette image BOOT. Le packaging du noyau a été recompilé pour intégrer les modules.

Les patches de console sont fournis. Le changement direct-io consiste à remplacer l'option `--direct-io=on` par `--direct-io=off` dans `init_functions.sh` avant de construire le boot.img. Les sources du paquet postmarketos-initramfs sont aussi dans `src/port/`.

## Recréer un ZIP sans rebâtir le noyau

L'image livrée peut servir de base assainie. Linux avec droits root, Python 3 et un **QEMU user aarch64 statique** sont nécessaires sur le PC ; le script utilise une registration binfmt temporaire et des montages bind `/dev` et `/proc`, qu'il retire ensuite. Il ne lance aucun flasher et ne démarre aucun service réseau du rootfs.

Depuis le dossier du projet, choisir un répertoire de travail **neuf**, hors du dépôt :

```sh
sudo python3 scripts/construire-rom.py \
  --base-zip release/linux-serveur-samsung-a5-2017-v1.zip \
  --boot-image release/boot-a5y17lte-r3.img \
  --kernel-apk release/linux-samsung-a5y17lte-3.18.140-r3.apk \
  --evdev release/evdev.ko \
  --qemu /CHEMIN/qemu-aarch64-statique \
  --work /CHEMIN/travail-neuf \
  --output /CHEMIN/linux-serveur-a5-nouveau.zip

python3 scripts/verifier-rom.py /CHEMIN/linux-serveur-a5-nouveau.zip
```

Le script ajoute les paquets au rootfs isolé, télécharge récursivement les APK Wi-Fi, applique la configuration et les sources du tableau, verrouille les comptes, enlève les données privées puis réutilise les composants du recovery installer. Il nécessite Internet pour récupérer les paquets. Les versions exactes de la release initiale sont dans `release/paquets-installes.txt` et les APK Wi-Fi sont fournis ; les dépôts `edge` évoluent, une reconstruction ultérieure n'est pas forcément identique octet pour octet.

Le paquet local du noyau utilise `--allow-untrusted` seulement pendant cette reconstruction car il a été signé localement ; son empreinte est fournie dans `SHA256SUMS`. Les APK Wi-Fi officiels conservent leurs signatures.

Pour repartir du port et reconstruire le noyau, créer une copie de pmaports au commit cité, utiliser les dossiers de port fournis à la place des versions archivées, puis `pmbootstrap build --force --lax linux-samsung-a5y17lte` et `pmbootstrap install --android-recovery-zip`. Adapter la génération de BOOT avec les patches initramfs et la configuration inclus. Ne pas réutiliser des clés SSH ou un mot de passe personnel dans une image destinée au partage : le script d'assainissement doit être exécuté et le ZIP final vérifié.

## Tests effectués

- Reconstruction isolée aarch64 sous QEMU, installation des paquets et activation des services au prochain boot.
- Contrôle effectif `sshd -T` sous QEMU : PasswordAuthentication=yes, PermitRootLogin=no, PermitEmptyPasswords=no. Analyse des scripts du tableau avec le Python 3.14 installé dans la ROM.
- Vérification des APK et des sources, contrôle CRC de l'archive, contrôle des comptes verrouillés, du module evdev, des services et des fichiers de configuration.
- Correspondance exacte entre les composants du BOOT corrigé et `/boot` dans le rootfs ; garde du modèle et des partitions avant installation.
- Rendu des deux aperçus et tests de navigation du menu sans exécuter extinction/reboot.

Aucun flash ou remplacement de l'installation active du téléphone n'a été effectué pour préparer cette release. Le ZIP complet assaini reste à tester par une installation volontaire.
