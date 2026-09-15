#!/usr/bin/env python3
"""Afficheur local LÉGER pour l'écran SPI (ILI9486 480x320) — SANS navigateur.

Conçu pour un Raspberry Pi 3B : Chromium/X sont trop lourds (rendu logiciel ->
crash/flash). Ici on lit les mesures sur le MQTT local et on les dessine
directement dans le framebuffer (/dev/fb1) avec Pillow. Stable, léger, fluide.

Lancement :
    .venv/bin/python display/fb_display.py
    MAHALI_FB_DEVICE=/dev/fb1 .venv/bin/python display/fb_display.py
"""

import json
import os
import struct
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

import config
import mqtt_client

FB = os.environ.get("MAHALI_FB_DEVICE", "/dev/fb1")


def fb_geometry(dev: str):
    """Récupère (largeur, hauteur, bpp, stride) depuis /sys, avec repli 480x320x16."""
    base = "/sys/class/graphics/" + os.path.basename(dev)
    w, h, bpp = 480, 320, 16
    try:
        vs = open(base + "/virtual_size").read().strip()
        w, h = (int(x) for x in vs.split(","))
        bpp = int(open(base + "/bits_per_pixel").read().strip())
    except Exception:
        pass
    try:
        stride = int(open(base + "/stride").read().strip())
    except Exception:
        stride = w * (bpp // 8)
    return w, h, bpp, stride


W, H, BPP, STRIDE = fb_geometry(FB)

# Palette marque Mahali
BG = (8, 18, 11)
OLIVE = (17, 69, 2)
LIME = (153, 255, 11)
WHITE = (234, 243, 221)
GREY = (140, 160, 130)
RED = (255, 90, 80)

_FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


def font(size: int, bold: bool = True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(_FONT_DIR + name, size)
    except Exception:
        return ImageFont.load_default()


state = {"sensors": {}, "relays": {}, "online": False}


def _on_connect(client, userdata, flags, rc):
    client.subscribe(config.TOPIC_SENSOR_WILDCARD, qos=1)
    client.subscribe(config.TOPIC_RELAY_STATE, qos=1)
    client.subscribe(config.TOPIC_STATUS, qos=1)


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        return
    topic = msg.topic
    if topic.startswith(config.MQTT_TOPIC_PREFIX + "/sensors/"):
        state["sensors"][topic.rsplit("/", 1)[-1]] = payload.get("value")
    elif topic == config.TOPIC_RELAY_STATE:
        state["relays"][payload.get("channel")] = payload.get("is_on")
    elif topic == config.TOPIC_STATUS:
        state["online"] = bool(payload.get("online"))


def _avg(keys):
    vals = [state["sensors"].get(k) for k in keys]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else None


def _fmt(v, unit="", dec=1):
    return "--" if v is None else f"{v:.{dec}f}{unit}"


def draw_frame() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Bandeau titre
    d.rectangle([0, 0, W, 42], fill=OLIVE)
    d.text((12, 9), "MAHALI", font=font(24), fill=LIME)
    d.text((160, 14), "serre s001", font=font(18), fill=WHITE)
    dot = LIME if state["online"] else RED
    d.ellipse([W - 32, 15, W - 15, 32], fill=dot)

    temp = _avg([config.SENSOR_TEMP_CENTER, config.SENSOR_TEMP_EXIT, config.SENSOR_TEMP_ENTRY])
    hum = _avg([config.SENSOR_HUMIDITY_CENTER, config.SENSOR_HUMIDITY_EXIT, config.SENSOR_HUMIDITY_ENTRY])
    water = state["sensors"].get(config.SENSOR_WATER_LEVEL)
    relays_on = sum(1 for v in state["relays"].values() if v)

    cells = [
        ("TEMPERATURE", _fmt(temp, " C")),
        ("HUMIDITE", _fmt(hum, " %")),
        ("RESERVOIR", _fmt(water, " %", 0)),
        ("RELAIS", f"{relays_on}/8"),
    ]
    cw, ch = W // 2, (H - 42 - 30) // 2
    for i, (label, val) in enumerate(cells):
        cx, cy = (i % 2) * cw, 42 + (i // 2) * ch
        d.text((cx + 14, cy + 12), label, font=font(15), fill=GREY)
        d.text((cx + 14, cy + 36), val, font=font(40), fill=WHITE)

    d.text((12, H - 26), datetime.now().strftime("%H:%M:%S"), font=font(18), fill=GREY)
    d.text((W - 92, H - 26), "live" if state["online"] else "hors-ligne",
           font=font(16), fill=dot)
    return img


def to_rgb565(img: Image.Image) -> bytes:
    try:
        import numpy as np

        a = np.asarray(img, dtype=np.uint16)
        r = (a[:, :, 0] & 0xF8) << 8
        g = (a[:, :, 1] & 0xFC) << 3
        b = a[:, :, 2] >> 3
        return (r | g | b).astype("<u2").tobytes()
    except Exception:
        out = bytearray()
        for (r, g, b) in img.getdata():
            out += struct.pack("<H", ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))
        return bytes(out)


def main() -> None:
    mqtt_client.setup_logging()
    client = mqtt_client.build_client("mahali-pi-display")
    client.on_connect = _on_connect
    client.on_message = _on_message
    mqtt_client.connect_with_retry(client)
    client.loop_start()

    fbf = os.open(FB, os.O_RDWR)
    try:
        while True:
            img = draw_frame()
            data = to_rgb565(img) if BPP == 16 else img.convert("RGBA").tobytes()
            try:
                os.lseek(fbf, 0, os.SEEK_SET)
                os.write(fbf, data)
            except Exception as exc:  # noqa: BLE001
                print("Ecriture framebuffer échouée:", exc)
            time.sleep(1)
    finally:
        os.close(fbf)
        client.loop_stop()


if __name__ == "__main__":
    main()
