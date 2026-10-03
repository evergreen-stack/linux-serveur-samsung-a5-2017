# Réduire l’attente du Wi-Fi au démarrage du A5

Sur l’installation examinée, le noyau passe la main au système vers 6 secondes, mais le pilote Wi-Fi ne termine son chargement que vers 188 secondes. Trois requêtes de firmware absent attendent chacune le secours utilisateur pendant 60 secondes : `bdwlan30.b00`, `qsetup30.bin` et `wlan/wlan_mac.bin`. Le pilote utilise ensuite `bdwlan30.bin` et poursuit le démarrage.

Le correctif installe un service OpenRC `a5-firmware-timeout` dans le runlevel `sysinit`, après `sysfs` et avant `udev`, `udev-trigger` et `udev-settle`. Il fixe `/sys/class/firmware/timeout` à **5 secondes**. Ce paramètre concerne le secours utilisateur du chargeur de firmware pour tous les périphériques ; les fichiers présents continuent d’être chargés directement.

Aucun firmware n’est remplacé ou supprimé. Aucun flash, téléchargement ou redémarrage n’est effectué. Aucun secret ni journal personnel n’est publié. La configuration précédente est sauvegardée dans `/var/backups/` avec un script de restauration.

## Installation sur un système déjà accessible en SSH

Sur le PC, après avoir téléchargé le script depuis le dépôt :

```sh
scp scripts/corriger-attente-wifi-a5.sh user@172.16.42.1:
```

Dans la session SSH du téléphone :

```sh
sudo sh ~/corriger-attente-wifi-a5.sh
cat /sys/class/firmware/timeout
```

La valeur attendue est `5`. Le contrôle du nom d’hôte exige `samsung-a5y17lte` ; le script s’arrête sur un autre hôte.

## Validation au prochain démarrage

Redémarrer seulement après avoir vérifié l’installation et conservé le chemin de restauration affiché :

```sh
sudo reboot
```

Reconnecter SSH puis vérifier le délai, le Wi-Fi et les services :

```sh
cat /sys/class/firmware/timeout
nmcli device status
sudo rc-status
sudo dmesg | grep -E 'firmware load|Falling back|wlan: driver loaded in'
```

Gain théorique pour les trois attentes observées : environ **165 secondes**. Le démarrage suivant doit confirmer le gain et le fonctionnement du Wi-Fi ; ce résultat n’a pas encore été mesuré lors de la publication du correctif. La syntaxe shell du script a été vérifiée et l’ordre des services a été examiné.

Les autres avertissements du noyau, notamment les IRQ des touches tactiles et les attentes des threads Samsung, ne sont pas corrigés par ce patch. La couleur de la console de démarrage ne change pas.

## Restauration

Utiliser le chemin exact affiché par l’installateur :

```sh
sudo sh /var/backups/a5-attente-wifi-<date>-<pid>/restaurer.sh
```

Ce script remet le service, son activation et la valeur du délai dans leur état précédent.

## Distribution v1.0.0

Le correctif est fourni séparément dans le dépôt. **Les ZIP de la release v1.0.0 déjà publiée ne sont pas reconstruits et ne contiennent pas ce service.** Installer le script après la ROM si ce délai est observé.
