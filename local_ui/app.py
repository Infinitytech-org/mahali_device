"""Interface web LOCALE du contrôleur Mahali (tableau de bord + contrôle).

Tourne SUR le Pi (port 8090) et fonctionne même SANS Internet : elle lit les
capteurs et pilote les relais via le broker MQTT LOCAL du Pi (localhost). Le
pont mosquitto (voir install.sh) synchronise ensuite avec le cloud quand la
connexion revient.

- GET  /                     -> tableau de bord (HTML, auto-refresh, caméra)
- GET  /api/state            -> dernières mesures + états relais (JSON)
- POST /api/relay/<ch>/toggle-> bascule un relais (publie sur .../relays/cmd)

La caméra est servie par camera_stream.py sur le port 8080 ; le dashboard
l'affiche via <img src="/camera/stream">, proxifié ici pour rester same-origin.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import paho.mqtt.client as mqtt

PORT = int(os.environ.get("MAHALI_LOCAL_UI_PORT", "8090"))
BROKER = os.environ.get("MAHALI_LOCAL_BROKER", "localhost")
BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
PREFIX = os.environ.get("MQTT_TOPIC_PREFIX", "mahali")
SLUG = os.environ.get("MAHALI_GREENHOUSE_SLUG", "")
CAMERA_URL = os.environ.get("MAHALI_CAMERA_URL", "http://localhost:8080")

TEMPLATE = (Path(__file__).parent / "templates" / "dashboard.html").read_text(encoding="utf-8")

# État courant, alimenté par MQTT (thread-safe via GIL sur des dict simples).
_state: dict = {"sensors": {}, "relays": {}, "updated_at": None, "online": False}


# --- MQTT (broker local) ----------------------------------------------------
def _on_connect(client, userdata, flags, rc):
    client.subscribe(f"{PREFIX}/sensors/#", qos=1)
    client.subscribe(f"{PREFIX}/relays/state", qos=1)


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return
    parts = msg.topic.split("/")
    if "sensors" in parts:
        key = parts[-1]
        _state["sensors"][key] = {"value": payload.get("value"), "unit": payload.get("unit", "")}
    elif parts[-1] == "state":
        ch = payload.get("channel")
        if ch is not None:
            _state["relays"][str(ch)] = {
                "is_on": bool(payload.get("is_on")),
                "name": payload.get("name", f"Relais {ch}"),
                "key": payload.get("key", ""),
            }
    _state["updated_at"] = time.time()
    _state["online"] = True


_mqtt = mqtt.Client()
_mqtt.on_connect = _on_connect
_mqtt.on_message = _on_message


def _mqtt_loop() -> None:
    while True:
        try:
            _mqtt.connect(BROKER, BROKER_PORT, keepalive=30)
            _mqtt.loop_forever()
        except Exception:
            _state["online"] = False
            time.sleep(3)


def publish_relay(channel: int, state: bool) -> None:
    body = {"channel": channel, "state": state, "source": "local_ui"}
    _mqtt.publish(f"{PREFIX}/relays/cmd", json.dumps(body), qos=1)


# --- Serveur HTTP -----------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencieux
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            html = TEMPLATE.replace("{{SLUG}}", SLUG or "serre").replace("{{CAMERA}}", "/camera/stream")
            self._send(200, html.encode(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            fresh = _state["updated_at"] and (time.time() - _state["updated_at"] < 30)
            body = json.dumps({**_state, "fresh": bool(fresh), "slug": SLUG})
            self._send(200, body.encode())
        elif self.path.startswith("/camera/"):
            self._proxy_camera(self.path.replace("/camera", "", 1))
        else:
            self._send(404, b'{"detail":"not found"}')

    def do_POST(self):
        # /api/relay/<ch>/toggle  body {state: bool}
        parts = self.path.strip("/").split("/")
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "relay" and parts[3] == "toggle":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            try:
                publish_relay(int(parts[2]), bool(data.get("state")))
                self._send(200, b'{"ok":true}')
            except Exception as e:  # noqa: BLE001
                self._send(400, json.dumps({"detail": str(e)}).encode())
        else:
            self._send(404, b'{"detail":"not found"}')

    def _proxy_camera(self, sub: str) -> None:
        """Proxifie le flux caméra (8080) pour rester same-origin."""
        try:
            with urllib.request.urlopen(f"{CAMERA_URL}{sub}", timeout=5) as up:
                self.send_response(200)
                self.send_header("Content-Type", up.headers.get("Content-Type", "image/jpeg"))
                self.end_headers()
                while True:
                    chunk = up.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except Exception:
            self._send(503, b"camera indisponible", "text/plain")


def main() -> None:
    threading.Thread(target=_mqtt_loop, daemon=True).start()
    print(f"[local_ui] Tableau de bord sur http://0.0.0.0:{PORT}  (serre: {SLUG or '?'})")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
