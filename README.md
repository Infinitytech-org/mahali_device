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

## Installation logicielle (sur le Pi, en SSH)

```bash
git clone https://github.com/Infinitytech-org/mahali_device.git
cd mahali_device
./install.sh               # I2C/SPI, mosquitto local, venv, services systemd
```

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
