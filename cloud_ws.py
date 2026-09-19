#!/usr/bin/env python3
"""Canal TEMPS RÉEL bidirectionnel : WebSocket Pi <-> cloud.

- DESCENDANT : l'app bascule un relais -> le cloud pousse la commande ici ->
  on la republie sur le MQTT LOCAL -> relay_controller l'applique aussitôt.
- MONTANT : quand un relais change sur le Pi (automatisme OU commande), le
  relay_controller publie `relays/state` en local -> on le renvoie au cloud
  par le WS -> l'app le voit INSTANTANÉMENT (au lieu d'attendre 15 s).

Reconnexion automatique. Secours : cloud_uploader (télémétrie 15 s) + MQTT.
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

# Référence vers la connexion WS courante (partagée avec le callback MQTT).
_ws = {"app": None}


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

    # MQTT local : on écoute l'état des relais pour le renvoyer au cloud (montant).
    def _on_mqtt_connect(client, userdata, flags, rc):
        client.subscribe(config.TOPIC_RELAY_STATE, qos=1)

    def _on_mqtt_message(client, userdata, msg):
        app = _ws["app"]
        if app is None:
            return
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            return
        try:
            app.send(json.dumps({"type": "relay_state", "data": payload}))
        except Exception:
            pass

    mclient = mqtt_client.build_client("mahali-pi-cloudws")
    mclient.on_connect = _on_mqtt_connect
    mclient.on_message = _on_mqtt_message
    mqtt_client.connect_with_retry(mclient)
    mclient.loop_start()

    # WS <- cloud : commandes relais -> republiées en local (descendant).
    def on_message(_wsapp, message):
        try:
            msg = json.loads(message)
        except Exception:
            return
        if msg.get("type") == "relay_command":
            body = msg.get("data", {})
            mclient.publish(config.TOPIC_RELAY_CMD, json.dumps(body), qos=1)
            print(f"[cloud-ws] commande relais reçue -> local : {body}")

    def on_open(wsapp):
        _ws["app"] = wsapp
        print("[cloud-ws] connecté au cloud (temps réel relais actif, 2 sens)")

    def on_error(_wsapp, err):
        print(f"[cloud-ws] erreur : {err}")

    def on_close(_wsapp, *_a):
        _ws["app"] = None
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
        _ws["app"] = None
        time.sleep(5)


if __name__ == "__main__":
    main()
