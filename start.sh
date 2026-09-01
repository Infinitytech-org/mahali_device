#!/usr/bin/env bash
# Lance l'agent Mahali (enrôlement + supervision).  Usage : ./start.sh
# Au 1er lancement il demande un nom et affiche l'identifiant à saisir sur le
# mobile. Ensuite il tourne tout seul (et redémarre au reboot via systemd).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# venv créé par install.sh (sinon on tente le python système).
PY="$HERE/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

exec "$PY" -m agent.main
