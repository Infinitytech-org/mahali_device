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
sudo apt-get install -y python3-venv python3-pip i2c-tools mosquitto mosquitto-clients git
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
After=network-online.target mosquitto.service
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$HERE
ExecStart=$HERE/.venv/bin/python -m agent.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
echo
echo "============================================================"
echo "  Installation terminée."
echo "  ENRÔLEMENT (1ère fois, interactif) :   ./start.sh"
echo
echo "  Pour un démarrage automatique au boot, APRÈS le 1er"
echo "  enrôlement réussi :"
echo "      sudo systemctl enable --now mahali-agent"
echo "      journalctl -u mahali-agent -f     # voir les logs"
echo "============================================================"
