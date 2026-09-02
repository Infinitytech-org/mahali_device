"""Envoi des mesures vers le backend en ligne, en HTTPS (fiable derrière un NAT).

S'abonne au broker MQTT LOCAL du Pi (mêmes topics que l'interface locale) et
POSTe périodiquement les dernières mesures + états relais sur
`/api/controllers/telemetry/` avec le secret de l'appareil. C'est ce qui fait
passer la serre « en ligne » dans l'app mobile, sans exposer le MQTT du VPS.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

import paho.mqtt.client as mqtt

from agent import store

API_BASE = os.environ.get("MAHALI_API_BASE", "https://api.mikia-green.com").rstrip("/")
BROKER = os.environ.get("MQTT_BROKER_HOST", "localhost")
PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
PREFIX = os.environ.get("MQTT_TOPIC_PREFIX", "mahali")
INTERVAL = int(os.environ.get("MAHALI_UPLOAD_INTERVAL_S", "15"))
# Caméra : on pousse un snapshot au backend toutes les SNAPSHOT_INTERVAL s.
SNAPSHOT_INTERVAL = int(os.environ.get("MAHALI_SNAPSHOT_INTERVAL_S", "2"))
CAMERA_URL = os.environ.get("MAHALI_CAMERA_URL", "http://localhost:8080")

_sensors: dict = {}   # key -> {"value", "unit"}
_relays: dict = {}    # channel -> {"is_on", "name", "key"}


def _on_connect(client, userdata, flags, rc):
    client.subscribe(f"{PREFIX}/sensors/#", qos=0)
    client.subscribe(f"{PREFIX}/relays/state", qos=0)
    print(f"[cloud] abonné au broker local ({PREFIX}/…)")


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return
    parts = msg.topic.split("/")
    if "sensors" in parts:
        _sensors[parts[-1]] = {"value": payload.get("value"), "unit": payload.get("unit", "")}
    elif parts[-1] == "state":
        ch = payload.get("channel")
        if ch is not None:
            _relays[ch] = {
                "is_on": payload.get("is_on"),
                "name": payload.get("name"),
                "key": payload.get("key"),
            }


def _upload() -> None:
    secret = store.load().get("secret")
    if not secret:
        return
    sensors = [
        {"key": k, "value": v["value"], "unit": v["unit"]}
        for k, v in _sensors.items()
        if v.get("value") is not None
    ]
    relays = [{"channel": ch, **info} for ch, info in _relays.items()]
    if not sensors and not relays:
        return
    body = json.dumps({"sensors": sensors, "relays": relays}).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/controllers/telemetry/",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Device-Secret": secret},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except urllib.error.URLError as exc:
        print(f"[cloud] envoi échoué ({exc.reason if hasattr(exc,'reason') else exc}) — on réessaiera")
    except Exception as exc:  # noqa: BLE001
        print(f"[cloud] envoi échoué: {exc}")


def _post_snapshot(secret: str, jpeg: bytes) -> None:
    boundary = "----mahaliboundary"
    body = b"".join([
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="s.jpg"\r\n'.encode(),
        b"Content-Type: image/jpeg\r\n\r\n",
        jpeg,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{API_BASE}/api/controllers/snapshot/",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Device-Secret": secret,
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def _snapshot_loop() -> None:
    """Récupère le dernier snapshot local (8080) et le pousse au backend."""
    while True:
        time.sleep(SNAPSHOT_INTERVAL)
        secret = store.load().get("secret")
        if not secret:
            continue
        try:
            with urllib.request.urlopen(f"{CAMERA_URL}/snapshot", timeout=5) as r:
                jpeg = r.read()
            if jpeg:
                _post_snapshot(secret, jpeg)
        except Exception:  # noqa: BLE001 - caméra absente / réseau : on réessaie
            pass


def main() -> None:
    threading.Thread(target=_snapshot_loop, daemon=True).start()
    client = mqtt.Client()
    client.on_connect = _on_connect
    client.on_message = _on_message
    while True:
        try:
            client.connect(BROKER, PORT, keepalive=30)
            break
        except Exception:  # noqa: BLE001
            time.sleep(3)
    client.loop_start()
    print(f"[cloud] uploader démarré -> {API_BASE} (toutes les {INTERVAL}s)")
    while True:
        time.sleep(INTERVAL)
        _upload()


if __name__ == "__main__":
    main()
