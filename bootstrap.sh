#!/usr/bin/env bash
# ============================================================================
#  Bootstrap Mahali — À LANCER APRÈS CHAQUE `git pull`.
#  Tout en une commande, idempotent : WiFi (SAHARA NET) + installation
#  (dépendances, venv, services systemd) + (re)démarrage.
#
#  Sur le Pi (Pi 3 B, Pi 4, ...) :
#      cd ~/mahali/raspberry
#      git pull
#      ./bootstrap.sh
#
#  Adapté automatiquement au modèle (hub USB du ventilo, etc.).
# ============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo 'modèle inconnu')"
echo "============================================================"
echo "  Bootstrap Mahali — $MODEL"
echo "============================================================"

echo; echo "### 1/3  WiFi (SAHARA NET, 2,4 GHz)"
bash ./setup_wifi.sh || echo "   (WiFi à vérifier — on continue)"

echo; echo "### 2/3  Installation (dépendances + services, idempotent)"
chmod +x ./setup_wifi.sh ./install.sh ./start.sh 2>/dev/null || true
./install.sh

echo; echo "### 3/3  Démarrage"
STORE="${MAHALI_HOME:-$HOME/.mahali}/device.json"
if [ -f "$STORE" ]; then
  echo "   Déjà enrôlé -> (re)démarrage de l'agent"
  sudo systemctl enable --now mahali-agent 2>/dev/null || true
  sudo systemctl restart mahali-agent 2>/dev/null || true
  echo "   Logs :  journalctl -u mahali-agent -f"
else
  echo "   PAS encore enrôlé sur ce Pi."
  echo "   Lance UNE fois (interactif) pour appairer avec le mobile :"
  echo "       ./start.sh"
  echo "   puis :  sudo systemctl enable --now mahali-agent"
fi

echo; echo "Ventilo boîtier : journalctl -u mahali-boxfan -f"
echo "Écran tactile   : journalctl -u mahali-display -f"
echo "   (si l'écran vient d'être activé, un 'sudo reboot' peut être requis)"
echo "Terminé."
