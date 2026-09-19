# Contrôleur Mahali — Raspberry Pi

Nœud « edge » d'une serre hydroponique Mahali : lit les capteurs, pilote les
relais, diffuse la caméra, affiche un tableau de bord local sur l'écran, et
synchronise avec le cloud (`api.mikia-green.com`) + l'app mobile.

**Conçu pour un Pi vierge** : tu clones, tu lances, ça fait tout — enrôlement
automatique, appairage depuis le mobile, démarrage des services, survie au
reboot.

## Prérequis matériel
Voir **[docs/BRANCHEMENT.md](docs/BRANCHEMENT.md)** — branchement pas-à-pas des
capteurs, relais et écran, avec les numéros de broches.

Le code **s'adapte automatiquement au modèle** (Pi 3 B ou Pi 4) — voir
`config.py` (`PI_MODEL`). Aucune modif à faire pour changer de carte.

### ⚠️ Spécificités Raspberry Pi 3 Model B
- **WiFi 2,4 GHz UNIQUEMENT** → **SAHARA NET doit être diffusé en 2,4 GHz**
  (le Pi 3 ne voit pas le 5 GHz).
- **Ventilo de boîtier** : sur Pi 3, couper l'alim USB (uhubctl, hub `1-1`)
  coupe **aussi l'Ethernet** (même puce) — sans conséquence ici puisqu'on est
  en WiFi. L'emplacement du hub est choisi automatiquement (`1-1` sur Pi 3,
  `2` sur Pi 4).
- CPU plus faible : la caméra locale reste **déportée sur l'ESP32-CAM**
  (`MAHALI_LOCAL_CAMERA=false`), le Pi ne fait pas de vidéo.

## Installation logicielle (sur le Pi, en SSH)

**Le plus simple — une seule commande, à relancer après chaque `git pull`** :

```bash
git clone https://github.com/Infinitytech-org/mahali_device.git ~/mahali
cd ~/mahali/raspberry
./bootstrap.sh             # WiFi (SAHARA NET) + install + (re)démarrage
```

`bootstrap.sh` est **idempotent** : il configure le WiFi ouvert SAHARA NET,
installe les dépendances + services, et (re)démarre l'agent s'il est déjà
enrôlé. Au tout premier passage (Pi non enrôlé), il t'invite à lancer
`./start.sh` une fois pour l'appairage.

<details><summary>Étapes manuelles (équivalent)</summary>

```bash
./setup_wifi.sh            # connexion auto à SAHARA NET (ouvert, 2,4 GHz)
./install.sh               # I2C/SPI, mosquitto local, venv, services systemd, ventilo
```
</details>

## 1er démarrage — enrôlement

```bash
./start.sh
```
- La console détecte le matériel (caméra, capteurs I2C, écran).
- Elle demande un **nom** pour ce contrôleur.
- Elle s'enrôle sur le backend et affiche un **identifiant** du type
  `MAH-XXXX-XXXX` — **note-le**.

## Appairage (depuis l'app mobile)

1. App **Mahali** → **Créer une serre**.
2. Saisis l'identifiant `MAH-XXXX-XXXX` affiché sur le Pi.
3. Le Pi détecte l'appairage en quelques secondes, apprend sa serre, configure
   le pont MQTT cloud, et démarre tous les services.

## Démarrage automatique au boot

Une fois le 1er enrôlement réussi :
```bash
sudo systemctl enable --now mahali-agent
journalctl -u mahali-agent -f      # suivre les logs
```

## Interface locale (fonctionne SANS Internet)

- Tableau de bord + contrôle des relais + caméra : `http://<ip-du-pi>:8090`
- Sur l'écran du Pi (kiosque plein écran) : `./display/kiosk.sh`
- Les données passent par un **broker MQTT local** ; un pont mosquitto
  synchronise avec le cloud quand la connexion revient. Coupure Internet →
  l'écran et le contrôle local continuent de fonctionner.

## Architecture (fichiers)

| Élément | Rôle |
|---|---|
| `start.sh` / `agent/main.py` | point d'entrée : enrôlement + supervision |
| `agent/hardware.py` | détection caméra / I2C / écran |
| `agent/api.py` | client backend (enroll, heartbeat) |
| `agent/store.py` | identifiants locaux (`~/.mahali/device.json`) |
| `local_ui/` | tableau de bord web local (port 8090) |
| `sensor_service.py` | lecture capteurs → MQTT |
| `relay_controller.py` | commandes relais ← MQTT |
| `automation_service.py` | règles d'automatisation (seuils) |
| `camera_stream.py` | flux caméra MJPEG (port 8080) |
| `display/kiosk.sh` | affichage plein écran sur l'écran du Pi |

## Test sans matériel (simulation)

```bash
MAHALI_SIMULATE=true ./start.sh
```
Les capteurs génèrent des valeurs plausibles — utile pour valider l'enrôlement
et l'interface sans capteurs branchés.
