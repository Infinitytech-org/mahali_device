#!/usr/bin/env python3
"""Canal descendant TEMPS RÉEL : WebSocket Pi <-> cloud.

Le Pi ouvre une connexion permanente (sortante -> franchit le NAT) vers le
backend. Quand l'app bascule un relais, la commande arrive INSTANTANÉMENT ici
et on la republie sur le MQTT LOCAL -> relay_controller l'applique aussitôt.

Secours : le pont MQTT cloud (si activé) et l'application optimiste côté app.
Si le WebSocket tombe, on se reconnecte tout seul (boucle + ping).

Lancement :  .venv/bin/python cloud_ws.py
"""

import json
import os
import sys
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import mqtt_client
from agent import store

API_BASE = os.environ.get("MAHALI_API_BASE", "https://api.mikia-green.com").rstrip("/")


def ws_url(slug: str, secret: str) -> str:
    base = API_BASE.replace("https://", "wss://").replace("http://", "ws://")
    return f"{base}/ws/device/{slug}/?secret={quote(secret, safe='')}"


def main() -> None:
    try:
        import websocket  # websocket-client
    except Exception:
        print("[cloud-ws] websocket-client manquant -> pip install websocket-client")
        return

    data = store.load()
    slug = data.get("greenhouse")
    secret = data.get("secret")
    if not (slug and secret):
        print("[cloud-ws] pas de slug/secret (pas encore appairé) -> WS désactivé")
        return

    client = mqtt_client.build_client("mahali-pi-cloudws")
    mqtt_client.connect_with_retry(client)
    client.loop_start()

    def on_message(_wsapp, message):
        try:
            msg = json.loads(message)
        except Exception:
            return
        if msg.get("type") == "relay_command":
            body = msg.get("data", {})
            client.publish(config.TOPIC_RELAY_CMD, json.dumps(body), qos=1)
            print(f"[cloud-ws] commande relais reçue -> local : {body}")

    def on_open(_wsapp):
        print("[cloud-ws] connecté au cloud (temps réel relais actif)")

    def on_error(_wsapp, err):
        print(f"[cloud-ws] erreur : {err}")

    def on_close(_wsapp, *_a):
        print("[cloud-ws] déconnecté, reconnexion dans 5 s…")

    url = ws_url(slug, secret)
    while True:
        try:
            app = websocket.WebSocketApp(
                url, on_open=on_open, on_message=on_message,
                on_error=on_error, on_close=on_close,
            )
            app.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:  # noqa: BLE001
            print(f"[cloud-ws] run_forever : {e}")
        time.sleep(5)


if __name__ == "__main__":
    main()
