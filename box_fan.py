#!/usr/bin/env python3
"""Ventilo de BOÎTIER (sur port USB du Pi), piloté par la température du CPU.

Allume le ventilo au-dessus de MAHALI_FAN_ON_C, l'éteint sous MAHALI_FAN_OFF_C
(hystérésis pour éviter les à-coups). Coupe/rallume l'alimentation USB via
`uhubctl`.

⚠️ Sur Pi 4, uhubctl coupe le hub USB-A en entier (tous les ports d'un coup) :
le ventilo doit être le SEUL périphérique branché sur l'USB-A (l'ESP32 est
déporté en WiFi, donc c'est bon).

Lancement :
    sudo .venv/bin/python box_fan.py
"""

import os
import subprocess
import time

FAN_ON = float(os.environ.get("MAHALI_FAN_ON_C", "60"))    # allume à >= 60°C
FAN_OFF = float(os.environ.get("MAHALI_FAN_OFF_C", "50"))   # éteint à <= 50°C
INTERVAL = float(os.environ.get("MAHALI_FAN_INTERVAL_S", "10"))
# Emplacement uhubctl : Pi 4 = "2" (hub VL805). Port "a" = tous les ports du hub.
HUB_LOC = os.environ.get("MAHALI_FAN_HUB", "2")
HUB_PORT = os.environ.get("MAHALI_FAN_PORT", "a")


def cpu_temp() -> float:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return 0.0


def set_usb(on: bool) -> None:
    action = "on" if on else "off"
    try:
        r = subprocess.run(
            ["uhubctl", "-l", HUB_LOC, "-p", HUB_PORT, "-a", action],
            check=False, capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"uhubctl {action} a échoué: {r.stderr.strip() or r.stdout.strip()}")
    except FileNotFoundError:
        print("uhubctl non installé -> sudo apt install uhubctl")


def main() -> None:
    print(f"Ventilo boîtier : ON>={FAN_ON}°C, OFF<={FAN_OFF}°C (USB hub {HUB_LOC} port {HUB_PORT})")
    state = None  # inconnu au départ -> on force une décision
    while True:
        t = cpu_temp()
        if state is not True and t >= FAN_ON:
            set_usb(True)
            state = True
            print(f"CPU {t:.1f}°C >= {FAN_ON} -> ventilo ON")
        elif state is not False and t <= FAN_OFF:
            set_usb(False)
            state = False
            print(f"CPU {t:.1f}°C <= {FAN_OFF} -> ventilo OFF")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
