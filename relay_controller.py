"""
Contrôleur de relais Raspberry Pi (doc §3.4.2) : pilote les 8 canaux du
module relais (actif à l'état BAS) via GPIO, et fait le pont avec MQTT.

- S'abonne à `mahali/relays/cmd` :
      {"channel": int, "state": bool, "source": "mobile_app"|"automation",
       "mode": "auto"|"manual"?}
- Publie `mahali/relays/state` à chaque changement réel d'état (et un état
  complet à la connexion, pour resynchronisation) :
      {"channel": int, "is_on": bool, "source": str}

Arbitrage manuel/automatique (purement local, ne dépend pas du backend) :
- une commande source="mobile_app" est TOUJOURS appliquée (priorité à
  l'utilisateur) et verrouille le canal en mode "manual", sauf si elle
  précise explicitement mode="auto" (l'utilisateur rend la main à
  l'automatisme) ;
- une commande source="automation" n'est appliquée QUE si le canal est
  actuellement en mode "auto" (sinon elle est ignorée silencieusement).

Lancement :
    python relay_controller.py                       # matériel réel (Pi)
    MAHALI_SIMULATE=true python relay_controller.py   # sans matériel (dev/CI)
"""

import json
import logging
import threading
import time

import config
import mqtt_client
from relay_mode_tracker import RelayModeTracker

logger = logging.getLogger("mahali.pi.relay_controller")

try:
    import RPi.GPIO as GPIO

    HARDWARE_AVAILABLE = True
except ImportError:
    GPIO = None
    HARDWARE_AVAILABLE = False


class RelayController:
    def __init__(self):
        self.simulate = config.SIMULATE or not HARDWARE_AVAILABLE
        self._state = {channel: False for channel in config.ALL_CHANNELS}
        self._tracker = RelayModeTracker(config.ALL_CHANNELS)
        self._client = mqtt_client.build_client(config.CLIENT_ID_RELAYS)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        # Last Will : si le Pi se déconnecte brutalement, le broker publie
        # automatiquement l'état hors-ligne -> la serre bascule tout de suite.
        self._client.will_set(
            config.TOPIC_STATUS, json.dumps({"online": False}), qos=1, retain=True
        )

        if self.simulate:
            logger.info("Mode SIMULATION : état des 8 relais conservé en mémoire (pas de GPIO réel).")
        else:
            GPIO.setmode(GPIO.BCM)
            for channel, pin in config.RELAY_GPIO_PINS.items():
                GPIO.setup(pin, GPIO.OUT)
                self._write_pin(channel, False)

    # --- GPIO bas niveau ----------------------------------------------------
    def _write_pin(self, channel: int, is_on: bool) -> None:
        self._state[channel] = is_on
        if self.simulate:
            return
        pin = config.RELAY_GPIO_PINS[channel]
        if config.RELAY_ACTIVE_LOW:
            level = GPIO.LOW if is_on else GPIO.HIGH
        else:
            level = GPIO.HIGH if is_on else GPIO.LOW
        GPIO.output(pin, level)

    # --- MQTT ----------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc):
        client.subscribe(config.TOPIC_RELAY_CMD, qos=1)
        logger.info("Abonné à %s (rc=%s).", config.TOPIC_RELAY_CMD, rc)
        self._publish_full_state(source="startup")
        self._publish_online(True)

    def _publish_online(self, online: bool) -> None:
        self._client.publish(
            config.TOPIC_STATUS, json.dumps({"online": online}), qos=1, retain=True
        )

    def _heartbeat_loop(self) -> None:
        """Republie périodiquement la présence du Pi (serre « en ligne »)."""
        while True:
            time.sleep(config.HEARTBEAT_INTERVAL_SECONDS)
            try:
                self._publish_online(True)
            except Exception:  # noqa: BLE001 - un hoquet réseau ne tue pas le heartbeat
                logger.debug("Heartbeat non publié (reconnexion en cours).")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Commande relais non-JSON ignorée.")
            return
        self._tracker.observe_command(payload)
        self._handle_command(payload)

    def _handle_command(self, payload: dict) -> None:
        try:
            channel = int(payload["channel"])
            desired_state = bool(payload["state"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Commande relais invalide ignorée: %s", payload)
            return
        if channel not in config.ALL_CHANNELS:
            logger.warning("Canal relais inconnu: %s", channel)
            return

        source = payload.get("source", "unknown")
        if source == "automation" and not self._tracker.is_auto(channel):
            logger.info("Commande automatisation ignorée (canal %s verrouillé en manuel).", channel)
            return

        if self._state[channel] == desired_state:
            return

        self._write_pin(channel, desired_state)
        logger.info("Relais %s -> %s (source=%s)", channel, "ON" if desired_state else "OFF", source)
        self._publish_state(channel, source)

    def _publish_state(self, channel: int, source: str) -> None:
        payload = json.dumps({"channel": channel, "is_on": self._state[channel], "source": source})
        self._client.publish(config.TOPIC_RELAY_STATE, payload, qos=1)

    def _publish_full_state(self, source: str) -> None:
        for channel in config.ALL_CHANNELS:
            self._publish_state(channel, source)

    def run(self) -> None:
        mqtt_client.connect_with_retry(self._client)
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        try:
            self._client.loop_forever(retry_first_connection=True)
        finally:
            if not self.simulate:
                GPIO.cleanup()


def main():
    mqtt_client.setup_logging()
    RelayController().run()


if __name__ == "__main__":
    main()
