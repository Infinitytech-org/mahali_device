#!/usr/bin/env bash
# Provisionne CE Raspberry Pi comme nœud edge Mahali pour UNE serre :
# active l'I2C, installe les dépendances, écrit le .env, et installe les
# 3 services systemd (capteurs / relais / automatisation).
#
# À lancer SUR le Pi, depuis ~/mahali/raspberry :
#     ./setup_pi.sh <BROKER_HOST> <SLUG>
#   ex :
#     ./setup_pi.sh 192.168.1.89 serre-tilemse
#
# (BROKER_HOST = IP du broker MQTT ; ici le Mac. SLUG = serre pilotée.)

set -euo pipefail

BROKER="${1:?usage: ./setup_pi.sh <broker_host> <slug>}"
SLUG="${2:?usage: ./setup_pi.sh <broker_host> <slug>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

echo "==> 1/6  Activation de l'I2C (raspi-config nonint)"
sudo raspi-config nonint do_i2c 0 || echo "   (raspi-config indisponible — active l'I2C manuellement si besoin)"

echo "==> 2/6  Paquets système (i2c-tools, venv, libgpiod)"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip i2c-tools libgpiod2

echo "==> 3/6  Groupes gpio/i2c pour $USER"
sudo usermod -aG gpio,i2c "$USER" || true

echo "==> 4/6  Environnement Python (.venv) + dépendances"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip wheel
# rpi-lgpio = shim RPi.GPIO compatible Bookworm/Pi4 (au cas où RPi.GPIO échoue)
./.venv/bin/pip install -r requirements.txt || {
  echo "   RPi.GPIO a échoué -> tentative avec rpi-lgpio"
  ./.venv/bin/pip install paho-mqtt smbus2 bme280 rpi-lgpio
}

echo "==> 5/6  Fichier .env (broker=$BROKER, prefix=mahali/$SLUG)"
[ -f .env ] || cp .env.example .env
python3 - "$BROKER" "$SLUG" <<'PY'
import re, sys, pathlib
broker, slug = sys.argv[1], sys.argv[2]
p = pathlib.Path(".env"); t = p.read_text()
def setkv(t, k, v):
    if re.search(rf'^{k}=.*$', t, flags=re.M):
        return re.sub(rf'^{k}=.*$', f'{k}={v}', t, flags=re.M)
    return t.rstrip() + f'\n{k}={v}\n'
t = setkv(t, 'MAHALI_SIMULATE', 'false')
t = setkv(t, 'MQTT_BROKER_HOST', broker)
t = setkv(t, 'MQTT_BROKER_PORT', '1883')
t = setkv(t, 'MQTT_TOPIC_PREFIX', f'mahali/{slug}')
p.write_text(t)
print("   .env ->", "MQTT_BROKER_HOST="+broker, "| MQTT_TOPIC_PREFIX=mahali/"+slug)
PY

echo "==> 6/6  Services systemd (adaptés à l'utilisateur $USER / $HOME)"
# Les units du dépôt sont écrites pour l'utilisateur « pi » (/home/pi). On les
# adapte à l'utilisateur courant pour que ça marche quel que soit le compte.
for u in systemd/*.service; do
  sed "s#/home/pi#$HOME#g; s#^User=pi#User=$USER#" "$u" \
    | sudo tee "/etc/systemd/system/$(basename "$u")" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable --now mahali-sensors mahali-relays mahali-automation
sleep 2
sudo systemctl --no-pager --lines=0 status mahali-sensors mahali-relays mahali-automation || true

echo
echo "OK. Vérifs utiles :"
echo "  i2cdetect -y 1                 # doit montrer 0x70 (mux), 0x48 (ADS1115) ; 0x76 apparaît via le mux"
echo "  journalctl -u mahali-sensors -f   # mesures publiées"
echo "  journalctl -u mahali-relays -f    # commandes/états relais"
echo
echo "Note : si les groupes gpio/i2c viennent d'être ajoutés, un 'sudo reboot' peut être nécessaire."
