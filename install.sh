#!/usr/bin/env bash
# ============================================================================
#  Installation du contrôleur Mahali sur un Raspberry Pi VIERGE.
#  Sur le Pi :   git clone <repo>   &&   cd raspberry   &&   ./install.sh
#  Puis :        ./start.sh          (enrôlement + démarrage)
#
#  Ce script est IDEMPOTENT (on peut le relancer). Il :
#   1. active l'I2C + SPI, installe les paquets système
#   2. installe un broker MQTT LOCAL (mosquitto) -> l'interface web marche
#      même sans Internet ; un pont vers le cloud est ajouté après appairage
#   3. crée le venv Python + dépendances
#   4. installe les services systemd (agent + kiosque écran) -> auto-démarrage
#      au boot et redémarrage automatique en cas de crash
# ============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
USER_NAME="$(whoami)"

echo "==> 1/6  Interfaces matérielles (I2C + SPI)"
sudo raspi-config nonint do_i2c 0 2>/dev/null || echo "   (active l'I2C à la main si besoin)"
sudo raspi-config nonint do_spi 0 2>/dev/null || echo "   (active le SPI à la main si besoin)"

echo "==> 2/6  Paquets système"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip i2c-tools mosquitto mosquitto-clients git uhubctl
# Caméra + GPIO : paquets SYSTÈME (pas pip). Le venv les verra via
# --system-site-packages. python3-picamera2 = flux caméra ; python3-rpi.gpio = relais.
sudo apt-get install -y python3-picamera2 python3-rpi.gpio python3-pil || \
  echo "   (picamera2/rpi.gpio/pil partiels — non bloquant)"
# libgpiod : nom du paquet différent selon la version de l'OS (2 sur Bookworm,
# 3 sur Trixie). Non bloquant si absent.
sudo apt-get install -y libgpiod2 || sudo apt-get install -y libgpiod3 || \
  echo "   (libgpiod introuvable — non bloquant, on continue)"

echo "==> 3/6  Groupes gpio/i2c/spi pour $USER_NAME"
sudo usermod -aG gpio,i2c,spi "$USER_NAME" 2>/dev/null || true

echo "==> 4/6  Broker MQTT local (mosquitto)"
sudo tee /etc/mosquitto/conf.d/mahali.conf >/dev/null <<'EOF'
listener 1883 localhost
allow_anonymous true
persistence true
EOF
sudo systemctl enable mosquitto 2>/dev/null || true
sudo systemctl restart mosquitto 2>/dev/null || true

echo "==> 5/6  Environnement Python (.venv, avec accès aux paquets système)"
# --system-site-packages : indispensable pour que le venv voie picamera2 et
# RPi.GPIO installés par APT (impossibles à installer par pip sous Bookworm+).
python3 -m venv --system-site-packages .venv
./.venv/bin/pip install --upgrade pip wheel >/dev/null
./.venv/bin/pip install -r requirements.txt || {
  echo "   RPi.GPIO a échoué -> tentative rpi-lgpio (Bookworm/Pi5)"
  ./.venv/bin/pip install paho-mqtt smbus2 RPi.bme280 rpi-lgpio
}

echo "==> 6/6  Services systemd (agent + kiosque)"
sudo tee /etc/systemd/system/mahali-agent.service >/dev/null <<EOF
[Unit]
Description=Agent Mahali (contrôleur de serre)
# Démarre dès le boot, CONNECTÉ OU NON (pas d'attente du réseau) : une fois
# enrôlé/appairé, l'agent tourne hors-ligne et synchronise le cloud au retour.
After=mosquitto.service
Wants=mosquitto.service

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$HERE
ExecStart=$HERE/start.sh
Restart=always
RestartSec=5
# Journalise proprement (pas de TTY interactif attendu une fois enrôlé)
StandardInput=null

[Install]
WantedBy=multi-user.target
EOF

# Ventilo de boîtier (refroidissement CPU) — service ROOT (uhubctl exige root).
# L'emplacement du hub USB est choisi automatiquement selon le modèle
# (Pi 3 = "1-1", Pi 4 = "2") dans config.py / box_fan.py.
echo "==> Service ventilo boîtier (mahali-boxfan, root)"
PY_BIN="$HERE/.venv/bin/python"
[ -x "$PY_BIN" ] || PY_BIN="$(command -v python3)"
sudo tee /etc/systemd/system/mahali-boxfan.service >/dev/null <<EOF
[Unit]
Description=Mahali - ventilo de boitier (refroidissement CPU du Pi)
After=multi-user.target

[Service]
Type=simple
User=root
WorkingDirectory=$HERE
ExecStart=$PY_BIN $HERE/box_fan.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now mahali-boxfan 2>/dev/null || true

# ---------------------------------------------------------------------------
# Écran tactile SPI 3,5" ILI9486 + tactile ADS7846 (overlay "piscreen").
# Idempotent : ajoute l'overlay dans config.txt (si absent), installe evdev,
# et pose le service mahali-display (root + MAHALI_HOME pour lire le slug).
# ---------------------------------------------------------------------------
echo "==> Écran tactile SPI (mahali-display)"
sudo apt-get install -y python3-evdev python3-pil >/dev/null 2>&1 || \
  echo "   (python3-evdev/pil partiels — tactile éventuellement indisponible)"

# config.txt : Bookworm = /boot/firmware/config.txt, sinon /boot/config.txt
BOOTCFG=/boot/firmware/config.txt
[ -f "$BOOTCFG" ] || BOOTCFG=/boot/config.txt
if [ -f "$BOOTCFG" ]; then
  grep -q "^dtparam=spi=on" "$BOOTCFG" || echo "dtparam=spi=on" | sudo tee -a "$BOOTCFG" >/dev/null
  if grep -q "^dtoverlay=piscreen" "$BOOTCFG"; then
    echo "   overlay écran déjà présent dans $BOOTCFG"
  else
    echo "dtoverlay=piscreen,speed=16000000,rotate=90" | sudo tee -a "$BOOTCFG" >/dev/null
    echo "   overlay écran ajouté dans $BOOTCFG -> REBOOT requis pour l'activer"
    NEED_REBOOT=1
  fi
else
  echo "   (config.txt introuvable — ajoute l'overlay manuellement, voir docs/BRANCHEMENT.md)"
fi

# Service : root (accès /dev/fb* et /dev/input), MAHALI_HOME pour trouver le
# store ~/.mahali/device.json (sinon root lit /root/.mahali -> mauvais préfixe MQTT).
sudo tee /etc/systemd/system/mahali-display.service >/dev/null <<EOF
[Unit]
Description=Mahali - ecran tactile local (framebuffer SPI)
After=mosquitto.service
Wants=mosquitto.service

[Service]
Type=simple
User=root
Environment=MAHALI_HOME=$HOME/.mahali
WorkingDirectory=$HERE
ExecStart=$PY_BIN $HERE/display/fb_display.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now mahali-display 2>/dev/null || true

echo
echo "============================================================"
echo "  Installation terminée."
[ "${NEED_REBOOT:-0}" = "1" ] && echo "  ⚠️  REBOOT requis (overlay écran) :  sudo reboot"
echo "  ENRÔLEMENT (1ère fois, interactif) :   ./start.sh"
echo
echo "  Pour un démarrage automatique au boot, APRÈS le 1er"
echo "  enrôlement réussi :"
echo "      sudo systemctl enable --now mahali-agent"
echo "      journalctl -u mahali-agent -f     # voir les logs"
echo "============================================================"
