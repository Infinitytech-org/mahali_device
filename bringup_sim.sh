#!/usr/bin/env bash
# Bring-up "sans matériel" du nœud edge Mahali sur CE Raspberry Pi.
#
# Lance les 3 services (capteurs / relais / automatisation) en mode SIMULATION
# (MAHALI_SIMULATE=true : valeurs générées, aucun accès I2C/GPIO) mais en
# publiant sur le VRAI broker MQTT du backend (pas 127.0.0.1). Objectif :
# valider la chaîne Pi -> MQTT -> backend -> mobile AVANT de brancher les
# capteurs. Quand le matériel sera là, utiliser setup_pi.sh (SIMULATE=false).
#
# À lancer SUR le Pi, depuis ~/mahali/raspberry :
#     ./bringup_sim.sh <BROKER_HOST> <SLUG>
#   ex :
#     ./bringup_sim.sh 192.168.1.232 serre-tilemse
#
# Ctrl+C pour tout arrêter.

set -euo pipefail

BROKER="${1:?usage: ./bringup_sim.sh <broker_host> <slug>   ex: ./bringup_sim.sh 192.168.1.232 serre-tilemse}"
SLUG="${2:?usage: ./bringup_sim.sh <broker_host> <slug>   ex: ./bringup_sim.sh 192.168.1.232 serre-tilemse}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# venv minimal : en simulation, paho-mqtt suffit (pas de smbus2/RPi.GPIO).
if [ ! -x ".venv/bin/python" ]; then
  echo "==> Création du venv + installation de paho-mqtt"
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip wheel >/dev/null
  ./.venv/bin/pip install paho-mqtt >/dev/null
fi

export MAHALI_SIMULATE=true
export MQTT_BROKER_HOST="$BROKER"
export MQTT_BROKER_PORT=1883
export MQTT_TOPIC_PREFIX="mahali/$SLUG"
export MAHALI_SENSOR_INTERVAL_S="${MAHALI_SENSOR_INTERVAL_S:-5}"
export MAHALI_AUTOMATION_TICK_S="${MAHALI_AUTOMATION_TICK_S:-5}"

echo "==> Bring-up SIMULATION"
echo "    broker  : $MQTT_BROKER_HOST:$MQTT_BROKER_PORT"
echo "    prefix  : $MQTT_TOPIC_PREFIX"
echo "    (les valeurs sont simulées — aucun capteur requis)"
echo

exec ./.venv/bin/python run_simulated.py
