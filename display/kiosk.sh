#!/usr/bin/env bash
# Kiosque plein écran pour l'écran 3 pouces du Pi : affiche l'interface locale
# (http://localhost:8090) en boucle. Chromium redémarre tout seul s'il est fermé.
# Le retour au tableau de bord après 3 min d'inactivité est géré côté page.
#
# Installé par install.sh via display/mahali-kiosk.service (session graphique).
set -u
URL="http://localhost:8090"

# Empêche la mise en veille de l'écran.
xset s off      2>/dev/null || true
xset -dpms      2>/dev/null || true
xset s noblank  2>/dev/null || true

CHROME="$(command -v chromium-browser || command -v chromium || echo chromium-browser)"

while true; do
  "$CHROME" \
    --kiosk --incognito --noerrdialogs --disable-infobars \
    --disable-session-crashed-bubble --disable-features=TranslateUI \
    --check-for-update-interval=31536000 \
    --app="$URL" 2>/dev/null || true
  # Si Chromium se ferme (crash, sortie), on attend et on relance.
  sleep 3
done
