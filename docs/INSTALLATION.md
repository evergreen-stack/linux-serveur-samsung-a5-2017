# Installer la ROM et connecter le serveur

## 1. Vérifier les fichiers

Extraire le paquet complet sur le PC puis ouvrir un terminal dans son dossier :

```sh
sha256sum -c SHA256SUMS
```

Le ZIP destiné à TWRP est **`release/linux-serveur-samsung-a5-2017-v1.zip`**. Installation propre : elle reformate SYSTEM et écrit BOOT. Elle remplace donc le système qui s'y trouve. Le recovery fourni cible exactement `a5y17lte` ; ne pas utiliser sur un A5 d'une autre année ni un A40. Les commandes de flash ci-dessous sont à lancer volontairement par l'utilisateur.

## 2. TWRP puis ROM

Télécharger exactement **twrp-3.7.0_9-0-a5y17lte.img** depuis la [page officielle Team Win](https://dl.twrp.me/a5y17lte/twrp-3.7.0_9-0-a5y17lte.img.html), puis placer le fichier dans `release/`. Vérifier son empreinte :

```sh
(cd release && sha256sum -c twrp-3.7.0_9-0-a5y17lte.img.sha256)
```

Cette image est fournie par Team Win ; le paquet publié ici ne la réhéberge pas.

Sur le PC, installer Heimdall, ADB et OpenSSH. Sur openSUSE, les outils sont fournis notamment par `heimdall`, `android-tools` et `openssh`.

Placer le téléphone en Download Mode, puis vérifier et flasher **RECOVERY uniquement** :

```sh
sudo heimdall detect
sudo heimdall flash --RECOVERY release/twrp-3.7.0_9-0-a5y17lte.img --no-reboot
```

Passer directement dans TWRP : interrompre/redémarrer avec Power + Volume bas, puis dès l'écran noir maintenir Volume haut + Home + Power. Dans TWRP, ouvrir **Advanced → ADB Sideload**, lancer le sideload, puis sur le PC :

```sh
adb sideload release/linux-serveur-samsung-a5-2017-v1.zip
```

Attendre le succès affiché par TWRP. **Ne pas encore redémarrer** : il faut choisir le mot de passe du compte `user`.

Aucune commande BOOTLOADER, EFS, RADIO ou PIT n'est prévue. Le ZIP vérifie le modèle et la correspondance BOOT=p10, SYSTEM=p19 avant de lancer l'installer postmarketOS. L'installer crée ses sous-partitions dans SYSTEM et écrit l'image dans BOOT. Il ne flashe pas RECOVERY.

## 3. Choisir son propre mot de passe dans TWRP

Quitter l'écran de sideload terminé pour réactiver le shell ADB normal. Après installation, l'installer laisse le nouveau rootfs monté dans `/tmp/postmarketos/chroot/mnt/pmOS`. Sur le PC :

```sh
adb shell
```

Dans **le shell TWRP** :

```sh
ROOTFS=/tmp/postmarketos/chroot/mnt/pmOS
mountpoint -q "$ROOTFS" || exit 1
ls "$ROOTFS/etc/passwd" || exit 1
mkdir -p "$ROOTFS/dev"
mount -o bind /dev "$ROOTFS/dev" || exit 1
chroot "$ROOTFS" /usr/bin/passwd user
umount "$ROOTFS/dev"
exit
```

Ou, depuis le terminal du PC, exécuter `sh scripts/choisir-mot-de-passe.sh` : ce script vérifie le montage, ouvre le dialogue `passwd`, puis retire son montage `/dev`.

Saisir deux fois **un nouveau mot de passe personnel** à la demande de `passwd`. Il n'est pas inclus dans le ZIP et ne doit pas être envoyé dans une conversation. Si la vérification de montage échoue, ne pas lancer `passwd` : consulter la partie dépannage ci-dessous.

Le compte root reste verrouillé ; `user` appartient au groupe `wheel` et utilise `sudo` avec son propre mot de passe. Redémarrer ensuite dans **System** depuis TWRP.

Si TWRP a été redémarré entre-temps et `/tmp/postmarketos/chroot/mnt/pmOS` n'est plus monté : SYSTEM est un disque partitionné par l'installer. **Ne pas monter directement toute la partition SYSTEM comme ext4**. Utiliser les outils inclus dans `/tmp/postmarketos/chroot` après un sideload réussi pour repérer les sous-partitions, ou revenir à une installation propre et effectuer cette étape avant de quitter TWRP. Ne pas saisir de mot de passe par défaut : il n'en existe aucun.

## 4. Se connecter par USB, sans Internet

Après démarrage du système, laisser le câble connecté. Le téléphone expose RNDIS avec l'adresse **`172.16.42.1`**. Sur le PC openSUSE :

```sh
sudo modprobe --ignore-install rndis_host
ip link
```

Repérer l'interface USB qui vient d'apparaître (nom du type `enp…u…`). Remplacer `INTERFACE_USB` par ce nom :

```sh
sudo ip link set INTERFACE_USB up
sudo ip address add 172.16.42.2/24 dev INTERFACE_USB
ssh user@172.16.42.1
```

L'adresse sur le PC est temporaire ; la remettre après un débranchement si nécessaire. Si elle est déjà présente, l'erreur « File exists » n'exige aucune suppression. Le premier démarrage génère de nouvelles clés SSH hôte : accepter leur empreinte pour ce téléphone. Utiliser le mot de passe choisi dans TWRP.

Sur un PC déjà utilisé avec une ancienne installation à cette adresse, une alerte de clé hôte changée est attendue après une réinstallation propre. Vérifier que c'est bien le téléphone réinstallé puis supprimer uniquement l'ancienne entrée :

```sh
ssh-keygen -R 172.16.42.1
ssh user@172.16.42.1
```

## 5. Connecter son propre Wi-Fi et Internet

Dans la session SSH du téléphone :

```sh
sudo nmcli radio wifi on
sudo nmcli device wifi list ifname wlan0 --rescan yes
sudo nmcli --ask device wifi connect "NOM_DE_VOTRE_WIFI" ifname wlan0 name "wifi-maison"
sudo nmcli connection modify "wifi-maison" connection.autoconnect yes
nmcli device status
nmcli -g IP4.ADDRESS device show wlan0
ping -c 3 1.1.1.1
ping -c 3 alpinelinux.org
sudo chronyc tracking
```

`--ask` demande le mot de passe sans le mettre dans la commande ou l'historique. Le profil créé est enregistré **sur votre téléphone**, pas dans le ZIP partagé. Commencer avec un réseau WPA2 2,4 GHz, configuration déjà essayée avec ce port ; un réseau WPA3 uniquement ne convient pas à la pile actuelle.

Le premier ping vérifie l'accès IP ; le deuxième teste aussi la résolution DNS. Une box peut bloquer le ping : en cas de doute, essayer `sudo apk update`. La synchronisation chrony peut demander quelques instants après l'accès à Internet.

Récupérer l'adresse Wi-Fi indiquée par `nmcli`, puis depuis le PC connecté au même réseau :

```sh
ssh user@ADRESSE_WIFI_DU_TELEPHONE
```

On peut ensuite débrancher l'USB. Le tableau masque le dernier octet, mais `nmcli` affiche l'adresse complète. Pour voir la MAC utilisée :

```sh
cat /sys/class/net/wlan0/address
```

Pour faire oublier le profil : `sudo nmcli connection delete "wifi-maison"`.

## 6. APK Wi-Fi hors ligne

Les paquets sont déjà installés. Une copie hors ligne reste dans :

```sh
ls /opt/linux-serveur-samsung-a5-2017/apk-wifi/
```

Pour restaurer les outils à partir de cette copie, sans réseau :

```sh
sudo apk add --no-network /opt/linux-serveur-samsung-a5-2017/apk-wifi/*.apk
sudo rc-update add wpa_supplicant default
sudo rc-update add networkmanager default
sudo rc-service wpa_supplicant restart
sudo rc-service networkmanager restart
```

La configuration D-Bus `wpa_supplicant_args="-u"` est intégrée. Les signatures des APK officiels sont conservées : ne pas désactiver leur vérification avec `--allow-untrusted` pour cette opération.

## 7. Écran et commandes

Home éteint/rallume l'écran ; cinq minutes sans appui mettent seulement l'écran en veille. SSH et le Wi-Fi continuent. Power ouvre le menu, Volume haut/bas navigue, Power confirme, Retour ferme. Désactiver le Wi-Fi coupe la session SSH Wi-Fi ; la même option devient « Activer le Wi-Fi ».

La console de secours est un mode de maintenance pour le prochain démarrage, avec les services réseau habituels. Elle ne remplace pas TWRP si le noyau ne démarre pas. Un redémarrage normal suivant rend le tableau.

Journal du tableau :

```sh
sudo cat /run/telephone-dashboard-grand.log
```

Langue et heure : `echo "$LANG"`, `date`, `sudo chronyc tracking`. Le gestionnaire de paquets est `apk`, pas `apt`.
