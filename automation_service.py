"""
Service d'automatisation Raspberry Pi (doc §3.6.2) : applique les règles de
pilotage automatique à partir des relevés capteurs reçus sur MQTT, et
commande les relais en publiant sur `mahali/relays/cmd` (source="automation")
— c'est relay_controller.py qui reste seul maître du GPIO réel, ce service
ne fait que décider et publier des intentions.

Règles :
1) Ventilation (canaux 2-7) + pompes canari (canal 8) : hystérésis sur la
   température MAX des 3 zones -> ON si > 32°C, OFF si < 28°C (sinon on
   conserve l'état précédent, pas d'oscillation rapide).
2) Pompe principale (canal 1) : cycle 15 min ON / 15 min OFF, sauf :
   - niveau d'eau < 20% : pompe coupée (alerte gérée côté Django) ;
   - niveau d'eau < 5% : arrêt d'urgence (priorité absolue).
   Le cycle normal reprend dès que le niveau remonte au-dessus de 20%.
3) Le pH n'est PAS corrigé automatiquement (action manuelle requise) ; seule
   l'alerte (mqtt_bridge côté Django) signale un dépassement.

Ce service ne dépend que du broker MQTT *local* : il continue de fonctionner
même si le backend Django/l'app mobile sont injoignables (autonomie de la
couche edge, doc §3.1).

Lancement :
    python automation_service.py
    MAHALI_SIMULATE=true python automation_service.py   # tests sans matériel
"""

import json
import logging
import time

import config
import mqtt_client
from relay_mode_tracker import RelayModeTracker

logger = logging.getLogger("mahali.pi.automation")

_TEMP_KEYS = (config.SENSOR_TEMP_ENTRY, config.SENSOR_TEMP_CENTER, config.SENSOR_TEMP_EXIT)


class AutomationService:
    def __init__(self):
        self._tracker = RelayModeTracker(config.ALL_CHANNELS)
        self._temps: dict[str, float] = {}
        self._water_level: float | None = None

        self._fans_on = False
        self._pump_phase_on = True
        self._pump_phase_started_at = time.monotonic()
        self._pump_emergency_stopped = False

        self._client = mqtt_client.build_client(config.CLIENT_ID_AUTOMATION)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    # --- MQTT -----------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc):
        client.subscribe(config.TOPIC_SENSOR_WILDCARD, qos=1)
        client.subscribe(config.TOPIC_RELAY_CMD, qos=1)
        logger.info("Automatisation connectée (rc=%s) : abonnée aux capteurs + commandes relais.", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

        if msg.topic == config.TOPIC_RELAY_CMD:
            self._tracker.observe_command(payload)
            return

        sensor_key = msg.topic.rsplit("/", 1)[-1]
        try:
            value = float(payload["value"])
        except (KeyError, TypeError, ValueError):
            return

        if sensor_key in _TEMP_KEYS:
            self._temps[sensor_key] = value
            self._evaluate_temperature()
        elif sensor_key == config.SENSOR_WATER_LEVEL:
            self._water_level = value

    # --- règle 1 : ventilation + pompes canari --------------------------
    def _evaluate_temperature(self) -> None:
        if not self._temps:
            return
        max_temp = max(self._temps.values())

        if not self._fans_on and max_temp > config.AUTOMATION_TEMP_HIGH:
            self._fans_on = True
            self._apply(config.COOLING_FAN_CHANNELS + [config.CANARI_PUMP_CHANNEL], True)
            logger.warning(
                "Température max %.1f°C > %.1f°C -> ventilation + pompes canari ON.",
                max_temp, config.AUTOMATION_TEMP_HIGH,
            )
        elif self._fans_on and max_temp < config.AUTOMATION_TEMP_LOW_RESET:
            self._fans_on = False
            self._apply(config.COOLING_FAN_CHANNELS + [config.CANARI_PUMP_CHANNEL], False)
            logger.info(
                "Température max %.1f°C < %.1f°C -> ventilation + pompes canari OFF.",
                max_temp, config.AUTOMATION_TEMP_LOW_RESET,
            )

    # --- règle 2 : pompe principale --------------------------------------
    def _tick_main_pump(self) -> None:
        level = self._water_level

        if level is not None and level < config.WATER_LEVEL_CRITICAL:
            if not self._pump_emergency_stopped:
                self._pump_emergency_stopped = True
                self._apply([config.MAIN_PUMP_CHANNEL], False)
                logger.error(
                    "Niveau d'eau critique (%.1f%% < %.1f%%) -> ARRÊT D'URGENCE pompe principale.",
                    level, config.WATER_LEVEL_CRITICAL,
                )
            return

        if level is not None and level < config.WATER_LEVEL_LOW:
            if not self._pump_emergency_stopped:
                self._pump_emergency_stopped = True
                self._apply([config.MAIN_PUMP_CHANNEL], False)
                logger.warning(
                    "Niveau d'eau bas (%.1f%% < %.1f%%) -> pompe principale coupée.",
                    level, config.WATER_LEVEL_LOW,
                )
            return

        if self._pump_emergency_stopped:
            self._pump_emergency_stopped = False
            self._pump_phase_on = True
            self._pump_phase_started_at = time.monotonic()
            self._apply([config.MAIN_PUMP_CHANNEL], True)
            logger.info("Niveau d'eau revenu à %.1f%% -> reprise du cycle normal de la pompe.", level)
            return

        elapsed = time.monotonic() - self._pump_phase_started_at
        duration = (
            config.MAIN_PUMP_CYCLE_ON_SECONDS if self._pump_phase_on else config.MAIN_PUMP_CYCLE_OFF_SECONDS
        )
        if elapsed >= duration:
            self._pump_phase_on = not self._pump_phase_on
            self._pump_phase_started_at = time.monotonic()
            self._apply([config.MAIN_PUMP_CHANNEL], self._pump_phase_on)
            logger.info("Cycle pompe principale -> %s", "ON" if self._pump_phase_on else "OFF")

    # --- publication des intentions --------------------------------------
    def _apply(self, channels, state: bool) -> None:
        for channel in channels:
            if not self._tracker.is_auto(channel):
                logger.debug("Canal %s verrouillé en manuel : automatisation ignorée.", channel)
                continue
            payload = json.dumps({"channel": channel, "state": state, "source": "automation"})
            self._client.publish(config.TOPIC_RELAY_CMD, payload, qos=1)

    def run(self) -> None:
        mqtt_client.connect_with_retry(self._client)
        self._client.loop_start()
        try:
            self._apply([config.MAIN_PUMP_CHANNEL], True)  # démarre le cycle normal
            while True:
                self._tick_main_pump()
                time.sleep(config.AUTOMATION_TICK_SECONDS)
        finally:
            self._client.loop_stop()


def main():
    mqtt_client.setup_logging()
    AutomationService().run()


if __name__ == "__main__":
    main()
