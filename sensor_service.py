"""
Service Raspberry Pi : lit tous les capteurs (3x BME280, pH via ADS1115,
niveau d'eau via HC-SR04) et publie chaque mesure sur MQTT
(`mahali/sensors/<clé>`), consommée par mqtt_bridge côté Django (doc §3.6.1).

Lancement :
    python sensor_service.py                  # matériel réel (sur le Pi)
    MAHALI_SIMULATE=true python sensor_service.py   # sans matériel (dev/CI)
"""

import json
import logging
import time
from datetime import datetime, timezone

import config
import mqtt_client
from sensors.ads1115_ph import PhSensor
from sensors.bme280 import BME280Array
from sensors.hcsr04 import WaterLevelSensor

logger = logging.getLogger("mahali.pi.sensor_service")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SensorService:
    def __init__(self):
        self._bme = BME280Array()
        self._ph = PhSensor()
        self._water = WaterLevelSensor()
        self._client = mqtt_client.build_client(config.CLIENT_ID_SENSORS)
        self._client.on_connect = self._on_connect
        mode = "SIMULATION" if (config.SIMULATE or self._bme.simulate) else "MATERIEL REEL"
        logger.info("Service capteurs démarré en mode %s.", mode)

    def _on_connect(self, client, userdata, flags, rc):
        logger.info("Connecté au broker MQTT (rc=%s), publication des capteurs démarrée.", rc)

    def _publish(self, sensor_key: str, value: float, unit: str) -> None:
        if value is None or (isinstance(value, float) and value != value):  # NaN
            logger.warning("Valeur invalide pour %s, mesure ignorée.", sensor_key)
            return
        payload = json.dumps({"value": value, "unit": unit, "recorded_at": _now_iso()})
        topic = config.TOPIC_SENSOR(sensor_key)
        self._client.publish(topic, payload, qos=1)
        logger.debug("Publié %s = %s %s", sensor_key, value, unit)

    def read_and_publish_once(self) -> None:
        # On ne lit QUE les zones dont le capteur a été détecté à l'init
        # (available_zones) : pas de capteur = pas de tentative = pas d'erreur.
        for sensor_key in self._bme.available_zones():
            try:
                temp, humidity = self._bme.read_zone(sensor_key)
            except Exception as exc:  # noqa: BLE001 - on continue malgré une panne
                logger.warning("Lecture BME280 %s ignorée: %s", sensor_key, exc)
                continue
            self._publish(sensor_key, temp, config.SENSOR_UNITS[sensor_key])
            humidity_key = config.BME280_HUMIDITY_KEY_FOR[sensor_key]
            self._publish(humidity_key, humidity, config.SENSOR_UNITS[humidity_key])

        # pH et niveau d'eau : désactivables (capteur non branché) via config.
        if config.PH_ENABLED:
            try:
                ph_value = self._ph.read_ph()
                self._publish(config.SENSOR_PH, ph_value, config.SENSOR_UNITS[config.SENSOR_PH])
            except Exception as exc:  # noqa: BLE001
                logger.warning("Lecture pH ignorée: %s", exc)

        if config.WATER_LEVEL_ENABLED:
            try:
                level = self._water.read_level_percent()
                self._publish(config.SENSOR_WATER_LEVEL, level, config.SENSOR_UNITS[config.SENSOR_WATER_LEVEL])
            except Exception as exc:  # noqa: BLE001
                logger.warning("Lecture niveau d'eau ignorée: %s", exc)

    def run(self) -> None:
        mqtt_client.connect_with_retry(self._client)
        self._client.loop_start()
        try:
            while True:
                self.read_and_publish_once()
                time.sleep(config.SENSOR_READ_INTERVAL_SECONDS)
        finally:
            self._client.loop_stop()
            self._bme.close()
            self._ph.close()
            self._water.close()


def main():
    mqtt_client.setup_logging()
    SensorService().run()


if __name__ == "__main__":
    main()
