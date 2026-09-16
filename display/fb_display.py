#!/usr/bin/env python3
"""Interface TACTILE locale pour l'écran SPI (ILI9486 480x320) — 100% NATIVE.

Écrit directement dans le framebuffer (fiable sur fbtft, contrairement à
Xorg/Chromium qui ne rafraîchit pas cette dalle). Pages : Vue / Climat /
Caméra / Contrôles, navigation au doigt, contrôle des relais, caméra live
depuis l'ESP32. Lit les mesures sur le MQTT local.

Lancement :  sudo .venv/bin/python display/fb_display.py
"""

import io
import json
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont

import config
import mqtt_client

# ------------------------------------------------------------- framebuffer ---
def find_fb() -> str:
    override = os.environ.get("MAHALI_FB_DEVICE")
    if override:
        return override
    import glob
    for path in sorted(glob.glob("/sys/class/graphics/fb*/name")):
        try:
            name = open(path).read().strip().lower()
        except Exception:
            continue
        if any(k in name for k in ("ili9", "tft", "fb_", "st77")):
            return "/dev/" + path.split("/")[-2]
    return "/dev/fb0"


def fb_geometry(dev: str):
    base = "/sys/class/graphics/" + os.path.basename(dev)
    w, h, bpp = 480, 320, 16
    try:
        w, h = (int(x) for x in open(base + "/virtual_size").read().strip().split(","))
        bpp = int(open(base + "/bits_per_pixel").read().strip())
    except Exception:
        pass
    return w, h, bpp


def fb_stride(dev: str) -> int:
    try:
        return int(open("/sys/class/graphics/" + os.path.basename(dev) + "/stride").read().strip())
    except Exception:
        return 0  # 0 => on calculera W*bpp


FB = find_fb()
W, H, BPP = fb_geometry(FB)
STRIDE = fb_stride(FB) or (W * (BPP // 8))

# --------------------------------------------------------------- palette -----
BG = (8, 18, 11)
CARD = (22, 40, 24)
OLIVE = (17, 69, 2)
LIME = (153, 255, 11)
WHITE = (234, 243, 221)
GREY = (140, 160, 130)
RED = (255, 90, 80)
BLUE = (59, 130, 246)
ORANGE = (245, 165, 36)
CYAN = (34, 211, 238)

_FDIR = "/usr/share/fonts/truetype/dejavu/"


def font(sz, bold=True):
    try:
        return ImageFont.truetype(_FDIR + ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), sz)
    except Exception:
        return ImageFont.load_default()


# ------------------------------------------------------------- état MQTT -----
state = {"sensors": {}, "relays": {}, "online": False}


def _on_connect(client, userdata, flags, rc):
    client.subscribe(config.TOPIC_SENSOR_WILDCARD, qos=1)
    client.subscribe(config.TOPIC_RELAY_STATE, qos=1)
    client.subscribe(config.TOPIC_STATUS, qos=1)


def _on_message(client, userdata, msg):
    try:
        p = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        return
    t = msg.topic
    if t.startswith(config.MQTT_TOPIC_PREFIX + "/sensors/"):
        state["sensors"][t.rsplit("/", 1)[-1]] = p.get("value")
    elif t == config.TOPIC_RELAY_STATE:
        state["relays"][p.get("channel")] = p.get("is_on")
    elif t == config.TOPIC_STATUS:
        state["online"] = bool(p.get("online"))


_client = mqtt_client.build_client("mahali-pi-display")
_client.on_connect = _on_connect
_client.on_message = _on_message


def relay_toggle(ch: int):
    cur = bool(state["relays"].get(ch))
    body = json.dumps({"channel": ch, "state": not cur, "source": "mobile_app"})
    _client.publish(config.TOPIC_RELAY_CMD, body, qos=1)


# --------------------------------------------------------------- caméra ------
CAMERA_URL = os.environ.get("MAHALI_CAMERA_URL", "http://mahali-cam.local").rstrip("/")
_cam = {"img": None}


def _camera_loop():
    while True:
        if PAGE == "cam":
            try:
                with urllib.request.urlopen(f"{CAMERA_URL}/capture", timeout=4) as r:
                    data = r.read()
                img = Image.open(io.BytesIO(data)).convert("RGB")
                _cam["img"] = img
            except Exception:
                _cam["img"] = None
            time.sleep(0.25)
        else:
            time.sleep(0.5)


# --------------------------------------------------------------- tactile -----
# Dernier appui (coord écran) à traiter par la boucle principale.
_tap = {"xy": None}
# Calibration : l'ADS7846 (rotate=90) a souvent x/y inversés. Réglable par env.
T_SWAP = os.environ.get("MAHALI_TOUCH_SWAP", "1") == "1"
T_INVX = os.environ.get("MAHALI_TOUCH_INVX", "0") == "1"
T_INVY = os.environ.get("MAHALI_TOUCH_INVY", "1") == "1"


def _touch_loop():
    try:
        from evdev import InputDevice, ecodes, list_devices
    except Exception:
        print("python3-evdev manquant -> pas de tactile (sudo apt install python3-evdev)")
        return
    dev = None
    for path in list_devices():
        d = InputDevice(path)
        caps = d.capabilities()
        if ecodes.EV_ABS in caps:
            dev = d
            break
    if not dev:
        print("Aucun écran tactile trouvé")
        return
    ax = dev.absinfo(ecodes.ABS_X)
    ay = dev.absinfo(ecodes.ABS_Y)
    cx, cy = 0, 0
    for e in dev.read_loop():
        if e.type == ecodes.EV_ABS:
            if e.code == ecodes.ABS_X:
                cx = e.value
            elif e.code == ecodes.ABS_Y:
                cy = e.value
        elif e.type == ecodes.EV_KEY and e.code == ecodes.BTN_TOUCH and e.value == 0:
            # relâchement -> on enregistre l'appui, mappé en coord écran
            fx = (cx - ax.min) / max(1, (ax.max - ax.min))
            fy = (cy - ay.min) / max(1, (ay.max - ay.min))
            if T_INVX:
                fx = 1 - fx
            if T_INVY:
                fy = 1 - fy
            if T_SWAP:
                fx, fy = fy, fx
            _tap["xy"] = (int(fx * W), int(fy * H))


# --------------------------------------------------------------- pages -------
PAGE = "vue"
TABH = 40  # hauteur barre d'onglets
TABS = [("vue", "Vue"), ("climat", "Climat"), ("cam", "Camera"), ("ctrl", "Relais")]
RELAY_LABELS = {1: "Pompe", 2: "Ventilos bas", 3: "Ventilos haut", 4: "Canari"}
_relay_rects = {}  # rempli au rendu de la page Contrôles


def _avg(keys):
    v = [state["sensors"].get(k) for k in keys]
    v = [x for x in v if isinstance(x, (int, float))]
    return sum(v) / len(v) if v else None


def _fmt(v, unit="", dec=1):
    return "--" if v is None else f"{v:.{dec}f}{unit}"


def _card(d, x, y, w, h, label, value, color=WHITE, vsize=34):
    d.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=CARD)
    d.text((x + 10, y + 8), label, font=font(12), fill=GREY)
    d.text((x + 10, y + 26), value, font=font(vsize), fill=color)


def render():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Bandeau titre
    d.rectangle([0, 0, W, 34], fill=OLIVE)
    d.text((10, 7), "MAHALI", font=font(19), fill=LIME)
    dot = LIME if state["online"] else RED
    d.ellipse([W - 26, 11, W - 12, 25], fill=dot)

    top, ch = 40, H - 34 - TABH - 46

    if PAGE == "vue":
        temp = _avg([config.SENSOR_TEMP_CENTER, config.SENSOR_TEMP_EXIT, config.SENSOR_TEMP_ENTRY])
        hum = _avg([config.SENSOR_HUMIDITY_CENTER, config.SENSOR_HUMIDITY_EXIT, config.SENSOR_HUMIDITY_ENTRY])
        water = state["sensors"].get(config.SENSOR_WATER_LEVEL)
        relays_on = sum(1 for v in state["relays"].values() if v)
        cw = (W - 30) // 2
        _card(d, 10, top, cw, ch, "TEMPÉRATURE", _fmt(temp, " C"), ORANGE)
        _card(d, 20 + cw, top, cw, ch, "HUMIDITÉ", _fmt(hum, " %"), CYAN)
        _card(d, 10, top + ch + 8, cw, ch, "RÉSERVOIR", _fmt(water, " %", 0), BLUE)
        _card(d, 20 + cw, top + ch + 8, cw, ch, "RELAIS ON", f"{relays_on}/{len(config.ALL_CHANNELS)}", LIME)

    elif PAGE == "climat":
        zones = [("Entrée", config.SENSOR_TEMP_ENTRY, config.SENSOR_HUMIDITY_ENTRY),
                 ("Centre", config.SENSOR_TEMP_CENTER, config.SENSOR_HUMIDITY_CENTER),
                 ("Sortie", config.SENSOR_TEMP_EXIT, config.SENSOR_HUMIDITY_EXIT)]
        y = top
        rh = (H - 34 - TABH - 40) // 3
        for name, tk, hk in zones:
            d.rounded_rectangle([10, y, W - 10, y + rh - 6], radius=8, fill=CARD)
            d.text((18, y + 8), name, font=font(14), fill=WHITE)
            d.text((150, y + 6), _fmt(state["sensors"].get(tk), " C"), font=font(20), fill=ORANGE)
            d.text((330, y + 6), _fmt(state["sensors"].get(hk), " %"), font=font(20), fill=CYAN)
            y += rh

    elif PAGE == "cam":
        area = (10, top, W - 10, H - TABH - 6)
        aw, ah = area[2] - area[0], area[3] - area[1]
        cam = _cam["img"]
        if cam is not None:
            c = cam.copy()
            c.thumbnail((aw, ah))
            img.paste(c, (area[0] + (aw - c.width) // 2, area[1] + (ah - c.height) // 2))
        else:
            d.rounded_rectangle(list(area), radius=8, fill=CARD)
            d.text((area[0] + 20, area[1] + ah // 2 - 8), "Caméra indisponible…", font=font(14), fill=GREY)

    elif PAGE == "ctrl":
        _relay_rects.clear()
        y = top
        bh = (H - 34 - TABH - 40) // max(1, len(config.ALL_CHANNELS))
        for chn in config.ALL_CHANNELS:
            on = bool(state["relays"].get(chn))
            col = LIME if on else CARD
            txtcol = (10, 14, 6) if on else WHITE
            d.rounded_rectangle([10, y, W - 10, y + bh - 6], radius=8, fill=col)
            d.text((20, y + (bh - 6) // 2 - 10), RELAY_LABELS.get(chn, f"Relais {chn}"), font=font(16), fill=txtcol)
            d.text((W - 70, y + (bh - 6) // 2 - 10), "ON" if on else "OFF", font=font(16), fill=txtcol)
            _relay_rects[chn] = (10, y, W - 10, y + bh - 6)
            y += bh

    # Barre d'onglets (bas)
    ty = H - TABH
    d.rectangle([0, ty, W, H], fill=(0, 0, 0))
    tw = W // len(TABS)
    for i, (pid, lbl) in enumerate(TABS):
        active = (pid == PAGE)
        d.text((i * tw + tw // 2 - len(lbl) * 4, ty + 12),
               lbl, font=font(14), fill=(LIME if active else GREY))
        if active:
            d.rectangle([i * tw + 8, ty + 2, (i + 1) * tw - 8, ty + 4], fill=LIME)
    return img


def handle_tap(x, y):
    global PAGE
    if y >= H - TABH:  # barre d'onglets
        idx = x // (W // len(TABS))
        if 0 <= idx < len(TABS):
            PAGE = TABS[idx][0]
        return
    if PAGE == "ctrl":
        for chn, (x0, y0, x1, y1) in _relay_rects.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                relay_toggle(chn)
                return


# --------------------------------------------------------------- sortie fb ---
def to_rgb565(img):
    import numpy as np
    a = np.asarray(img, dtype=np.uint16)
    rgb = (((a[:, :, 0] & 0xF8) << 8) | ((a[:, :, 1] & 0xFC) << 3) | (a[:, :, 2] >> 3)).astype("<u2")
    line = W * 2
    if STRIDE == line:
        return rgb.tobytes()
    # Le framebuffer a des lignes plus larges (padding) -> on cale chaque ligne.
    padded = np.zeros((H, STRIDE // 2), dtype="<u2")
    padded[:, :W] = rgb
    return padded.tobytes()


def main():
    mqtt_client.setup_logging()
    mqtt_client.connect_with_retry(_client)
    _client.loop_start()
    threading.Thread(target=_touch_loop, daemon=True).start()
    threading.Thread(target=_camera_loop, daemon=True).start()

    fbf = os.open(FB, os.O_RDWR)
    try:
        while True:
            if _tap["xy"]:
                x, y = _tap["xy"]
                _tap["xy"] = None
                handle_tap(x, y)
            data = to_rgb565(render()) if BPP == 16 else render().convert("RGBA").tobytes()
            os.lseek(fbf, 0, os.SEEK_SET)
            os.write(fbf, data)
            time.sleep(0.3 if PAGE == "cam" else 0.6)
    finally:
        os.close(fbf)
        _client.loop_stop()


if __name__ == "__main__":
    main()
