"""Détection du matériel branché sur le Raspberry Pi.

Tout est best-effort et tolérant : si un outil manque ou qu'on n'est pas sur
un Pi (poste de dev), on renvoie des valeurs « inconnu/absent » sans planter.
Le résultat est remonté au backend (enrôlement + heartbeat) et affiché dans la
console.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
from pathlib import Path

# Adresses I2C connues des capteurs Mahali (voir config.py / doc matériel).
I2C_KNOWN = {
    0x76: "BME280 (temp/hum/pression)",
    0x77: "BME280 (adresse alt.)",
    0x48: "ADS1115 (pH / analogique)",
    0x23: "BH1750 (luminosité)",
    0x3c: "Écran OLED SSD1306",
}


def _run(cmd: list[str], timeout: int = 5) -> str:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""


def pi_model() -> str:
    for p in ("/proc/device-tree/model", "/sys/firmware/devicetree/base/model"):
        try:
            return Path(p).read_text().strip("\x00\n ")
        except OSError:
            continue
    return "Inconnu (pas un Raspberry Pi ?)"


def has_camera() -> tuple[bool, str]:
    # Pi caméra (libcamera) ou webcam USB (/dev/video*).
    out = _run(["libcamera-hello", "--list-cameras"]) or _run(["rpicam-hello", "--list-cameras"])
    if out and "Available cameras" in out and "no cameras" not in out.lower():
        m = re.search(r":\s*(.+?)\s*\[", out)
        return True, (m.group(1) if m else "Caméra CSI/libcamera")
    vids = glob.glob("/dev/video*")
    if vids:
        return True, f"Webcam USB ({', '.join(vids)})"
    return False, "Aucune caméra détectée"


def i2c_devices(bus: int = 1) -> list[str]:
    out = _run(["i2cdetect", "-y", str(bus)])
    found: list[str] = []
    for line in out.splitlines()[1:]:
        parts = line.split(":", 1)
        if len(parts) != 2:
            continue
        for tok in parts[1].split():
            if tok not in ("--", "UU"):
                try:
                    addr = int(tok, 16)
                except ValueError:
                    continue
                found.append(I2C_KNOWN.get(addr, f"Périphérique I2C 0x{addr:02x}"))
    return found


def has_display() -> tuple[bool, str]:
    # Écran DSI/SPI (framebuffer secondaire) ou HDMI.
    fbs = glob.glob("/dev/fb*")
    if "/dev/fb1" in fbs:
        return True, "Écran SPI/DSI (fb1) — écran 3 pouces probable"
    if fbs:
        return True, f"Écran ({', '.join(fbs)})"
    if os.environ.get("DISPLAY"):
        return True, "Session graphique (DISPLAY)"
    return False, "Aucun écran détecté"


def gpio_available() -> bool:
    return Path("/dev/gpiomem").exists() or Path("/dev/gpiochip0").exists()


def detect() -> dict:
    """Snapshot complet du matériel, prêt à envoyer au backend."""
    cam_ok, cam = has_camera()
    disp_ok, disp = has_display()
    i2c = i2c_devices()
    return {
        "model": pi_model(),
        "camera": {"present": cam_ok, "detail": cam},
        "display": {"present": disp_ok, "detail": disp},
        "i2c": i2c,
        "gpio": gpio_available(),
        "sensors_count": len(i2c),
    }
