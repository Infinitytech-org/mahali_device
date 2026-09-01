"""
Client MQTT partagé par les 3 services Raspberry Pi (sensor_service,
relay_controller, automation_service). Centralise la connexion/reconnexion
avec backoff, pour ne pas dupliquer cette logique trois fois.
"""

import logging
import time

import paho.mqtt.client as mqtt

import config

logger = logging.getLogger("mahali.pi")


def build_client(client_id: str) -> mqtt.Client:
    client = mqtt.Client(client_id=client_id, clean_session=True)
    if config.MQTT_USERNAME:
        client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    return client


def connect_with_retry(client: mqtt.Client) -> None:
    """Boucle de connexion avec backoff exponentiel (2s -> 30s).

    Le Raspberry Pi doit pouvoir démarrer (et continuer de fonctionner pour
    l'automatisation locale) même si le broker MQTT n'est pas encore prêt
    (ex : redémarrage simultané du Pi et du conteneur backend).
    """
    delay = 2.0
    while True:
        try:
            client.connect(config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT, keepalive=30)
            logger.info("Connecté au broker MQTT %s:%s", config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT)
            return
        except (OSError, ConnectionRefusedError) as exc:
            logger.warning(
                "Broker MQTT %s:%s indisponible (%s) — nouvelle tentative dans %.0fs",
                config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT, exc, delay,
            )
            time.sleep(delay)
            delay = min(delay * 1.5, 30.0)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
    )
