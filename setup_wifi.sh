#!/usr/bin/env bash
# ============================================================================
#  WiFi Mahali — connexion automatique au hotspot OUVERT "SAHARA NET".
#  Idempotent. Gère NetworkManager (Raspberry Pi OS Bookworm) ET wpa_supplicant
#  (Bullseye et antérieurs). Réseau OUVERT => aucun mot de passe.
#
#  ⚠️ Le Pi 3 B n'a que du WiFi 2,4 GHz : SAHARA NET DOIT être diffusé en 2,4 GHz.
#
#  Usage :   ./setup_wifi.sh            (SSID par défaut "SAHARA NET")
#  Surcharge : MAHALI_WIFI_SSID="Autre" MAHALI_WIFI_COUNTRY=NE ./setup_wifi.sh
# ============================================================================
set -euo pipefail

SSID="${MAHALI_WIFI_SSID:-SAHARA NET}"
COUNTRY="${MAHALI_WIFI_COUNTRY:-NE}"   # domaine réglementaire (sinon WiFi bloqué)
IFACE="${MAHALI_WIFI_IFACE:-wlan0}"

echo "==> WiFi : '$SSID' (ouvert), pays=$COUNTRY, iface=$IFACE"

# Domaine réglementaire (débloque la radio). Non bloquant.
sudo raspi-config nonint do_wifi_country "$COUNTRY" 2>/dev/null || true
sudo rfkill unblock wifi 2>/dev/null || true

if command -v nmcli >/dev/null 2>&1; then
  echo "   NetworkManager détecté"
  if nmcli -t -f NAME connection show 2>/dev/null | grep -qx "$SSID"; then
    echo "   profil '$SSID' déjà présent — mise à jour"
  else
    sudo nmcli connection add type wifi ifname "$IFACE" con-name "$SSID" ssid "$SSID"
  fi
  # Réseau ouvert + reconnexion auto au boot + priorité haute.
  sudo nmcli connection modify "$SSID" \
    wifi-sec.key-mgmt none \
    connection.autoconnect yes \
    connection.autoconnect-priority 100
  sudo nmcli connection up "$SSID" \
    || echo "   (connexion différée — hotspot pas encore à portée ? auto-reconnexion active)"
else
  echo "   wpa_supplicant (pas de NetworkManager)"
  WPA="/etc/wpa_supplicant/wpa_supplicant.conf"
  sudo touch "$WPA"
  sudo grep -q "^country=" "$WPA" || echo "country=$COUNTRY" | sudo tee -a "$WPA" >/dev/null
  if sudo grep -q "ssid=\"$SSID\"" "$WPA"; then
    echo "   réseau '$SSID' déjà dans wpa_supplicant.conf"
  else
    sudo tee -a "$WPA" >/dev/null <<EOF

network={
    ssid="$SSID"
    key_mgmt=NONE
    priority=10
}
EOF
  fi
  sudo wpa_cli -i "$IFACE" reconfigure 2>/dev/null \
    || sudo systemctl restart "wpa_supplicant@$IFACE" 2>/dev/null \
    || sudo systemctl restart dhcpcd 2>/dev/null || true
fi

echo "==> Fait. IP obtenue :"
ip -4 addr show "$IFACE" 2>/dev/null | awk '/inet /{print "   "$2}' || true
