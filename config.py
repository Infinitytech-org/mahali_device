"""
Configuration du code Raspberry Pi "Mahali" (serre hydroponique intelligente).

Toutes les valeurs peuvent être surchargées par variables d'environnement
(utile pour les tests, la simulation, ou un déploiement avec un câblage
légèrement différent). Voir Tilemse.docx, chapitres 3 et 4, pour le détail
matériel.

Ce fichier est le pendant, côté Raspberry Pi, de backend/common/constants.py
— les deux doivent rester cohérents (mêmes clés de capteurs, mêmes canaux
de relais, mêmes topics MQTT).
"""

import os


def _bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# --- Mode simulation ---------------------------------------------------------
# A activer (SIMULATE=true) quand il n'y a pas de matériel réel branché : les
# modules sensors_hw/*.py génèrent alors des valeurs plausibles (bruitées,
# avec une légère dérive sinusoïdale) au lieu de lire les bus I2C/GPIO réels.
# C'est ce mode qui permet le test end-to-end sans Raspberry Pi physique.
SIMULATE = _bool("MAHALI_SIMULATE", "false")

# --- MQTT ---------------------------------------------------------------
MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = _int("MQTT_BROKER_PORT", 1883)
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "") or None
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "") or None
MQTT_TOPIC_PREFIX = os.environ.get("MQTT_TOPIC_PREFIX", "mahali")

TOPIC_SENSOR = lambda key: f"{MQTT_TOPIC_PREFIX}/sensors/{key}"  # noqa: E731
TOPIC_SENSOR_WILDCARD = f"{MQTT_TOPIC_PREFIX}/sensors/#"
TOPIC_RELAY_CMD = f"{MQTT_TOPIC_PREFIX}/relays/cmd"
TOPIC_RELAY_STATE = f"{MQTT_TOPIC_PREFIX}/relays/state"
TOPIC_ALERT = f"{MQTT_TOPIC_PREFIX}/alerts"
# Présence du Pi : heartbeat périodique + Last Will (à la déconnexion), pour
# que la serre apparaisse « en ligne » dès que le Pi tourne, sans capteurs.
TOPIC_STATUS = f"{MQTT_TOPIC_PREFIX}/status"

# --- Clés de capteurs (doivent correspondre à common.constants.SENSOR_CHOICES) ---
SENSOR_TEMP_ENTRY = "temp_entry"
SENSOR_HUMIDITY_ENTRY = "humidity_entry"
SENSOR_TEMP_CENTER = "temp_center"
SENSOR_HUMIDITY_CENTER = "humidity_center"
SENSOR_TEMP_EXIT = "temp_exit"
SENSOR_HUMIDITY_EXIT = "humidity_exit"
SENSOR_PH = "ph"
SENSOR_WATER_LEVEL = "water_level"

SENSOR_UNITS = {
    SENSOR_TEMP_ENTRY: "°C", SENSOR_TEMP_CENTER: "°C", SENSOR_TEMP_EXIT: "°C",
    SENSOR_HUMIDITY_ENTRY: "%", SENSOR_HUMIDITY_CENTER: "%", SENSOR_HUMIDITY_EXIT: "%",
    SENSOR_PH: "pH", SENSOR_WATER_LEVEL: "%",
}

# --- I2C : multiplexeur TCA9548A + 3x BME280 (doc §3.3.1 / §4.3.1) ----------
# Le bus I2C "réel" est partagé : un seul BME280 peut exister à l'adresse
# 0x76 à la fois, on bascule donc de capteur via les canaux du TCA9548A.
TCA9548A_ADDRESS = int(os.environ.get("MAHALI_TCA9548A_ADDR", "0x70"), 16)
BME280_ADDRESS = int(os.environ.get("MAHALI_BME280_ADDR", "0x76"), 16)
I2C_BUS_NUMBER = _int("MAHALI_I2C_BUS", 1)

# Zone -> canal du multiplexeur (0..7). Capteur 1 = entrée est (1 m du sol),
# capteur 2 = zone centrale (2 m), capteur 3 = sortie ouest (3 m).
# Configurable par variable d'environnement (utile si un canal du mux est
# défaillant : on branche le capteur sur un autre canal).
BME280_MUX_CHANNELS = {
    SENSOR_TEMP_ENTRY: _int("MAHALI_MUX_CH_ENTRY", 0),
    SENSOR_TEMP_CENTER: _int("MAHALI_MUX_CH_CENTER", 1),
    SENSOR_TEMP_EXIT: _int("MAHALI_MUX_CH_EXIT", 2),
}
BME280_HUMIDITY_KEY_FOR = {
    SENSOR_TEMP_ENTRY: SENSOR_HUMIDITY_ENTRY,
    SENSOR_TEMP_CENTER: SENSOR_HUMIDITY_CENTER,
    SENSOR_TEMP_EXIT: SENSOR_HUMIDITY_EXIT,
}

# --- Source des capteurs air (temp/humidité) --------------------------------
# "i2c"  : BME280 branchés directement sur le Pi (montage historique).
# "esp32": lus depuis un ESP32-CAM en WiFi local (caméra + capteurs déportés).
BME_SOURCE = os.environ.get("MAHALI_BME_SOURCE", "i2c").strip().lower()
# URL de base du noeud ESP32-CAM (endpoints /telemetry et /snapshot). Le mDNS
# du firmware l'expose en http://mahali-cam.local/.
ESP32_NODE_URL = os.environ.get("MAHALI_ESP32_URL", "http://mahali-cam.local").rstrip("/")
# Correspondance nom de zone renvoyé par l'ESP32 -> clé capteur Django.
ESP32_ZONE_TO_KEY = {
    "entry": SENSOR_TEMP_ENTRY,
    "center": SENSOR_TEMP_CENTER,
    "exit": SENSOR_TEMP_EXIT,
}

# Capteurs optionnels : désactiver ceux qui ne sont pas branchés pour éviter
# des tentatives de lecture (et des logs) inutiles.
PH_ENABLED = _bool("MAHALI_PH_ENABLED", "true")
WATER_LEVEL_ENABLED = _bool("MAHALI_WATER_LEVEL_ENABLED", "true")

# --- ADS1115 + électrode pH (doc §3.3.2) ------------------------------------
ADS1115_ADDRESS = int(os.environ.get("MAHALI_ADS1115_ADDR", "0x48"), 16)
ADS1115_PH_CHANNEL = _int("MAHALI_ADS1115_PH_CHANNEL", 0)  # entrée A0
# pH = 7 + (2.5V - V_mesuré) / 0.1776  (étalonnage électrode, doc §3.3.2)
PH_NEUTRAL_VOLTAGE = _float("MAHALI_PH_NEUTRAL_VOLTAGE", 2.5)
PH_SLOPE = _float("MAHALI_PH_SLOPE", 0.1776)

# --- HC-SR04 : niveau du réservoir (doc §3.3.3) -----------------------------
HCSR04_TRIG_PIN = _int("MAHALI_HCSR04_TRIG_PIN", 23)
HCSR04_ECHO_PIN = _int("MAHALI_HCSR04_ECHO_PIN", 24)
# Géométrie du réservoir 1000 L (cuve cylindrique) : distance capteur->fond
# (cuve vide) et distance capteur->surface (cuve pleine), en cm. Le niveau %
# est interpolé linéairement entre ces deux bornes.
TANK_EMPTY_DISTANCE_CM = _float("MAHALI_TANK_EMPTY_DISTANCE_CM", 100.0)
TANK_FULL_DISTANCE_CM = _float("MAHALI_TANK_FULL_DISTANCE_CM", 10.0)

# --- Relais (doc §3.4.2) : 8 canaux, module actif à l'état BAS --------------
RELAY_ACTIVE_LOW = _bool("MAHALI_RELAY_ACTIVE_LOW", "true")
# Broches choisies dans la ZONE DU FOND du connecteur (broches physiques 29-40),
# libres même quand l'écran SPI est posé (il occupe l'avant + les broches SPI
# GPIO7/8/9/10/11). Format : GPIO (BCM) = broche physique.
#   1: GPIO5=pin29   2: GPIO6=pin31   3: GPIO13=pin33  4: GPIO16=pin36
#   5: GPIO19=pin35  6: GPIO20=pin38  7: GPIO21=pin40  8: GPIO26=pin37
# NB actif-bas : GPIO5/6 (pull-up par défaut) démarrent OFF au boot -> on y met
# la POMPE (canal 1) et le canal 2. Les autres (pull-down) peuvent cliqueter
# ~30 s au boot avant le démarrage du service : ajouter une résistance 10k du IN
# vers +3.3V si c'est gênant.
RELAY_GPIO_PINS = {
    1: _int("MAHALI_RELAY1_PIN", 5),    # Pompe principale hydroponique (pin 29)
    2: _int("MAHALI_RELAY2_PIN", 6),    # Ventilateur bas est — gauche   (pin 31)
    3: _int("MAHALI_RELAY3_PIN", 13),   # Ventilateur bas est — droite   (pin 33)
    4: _int("MAHALI_RELAY4_PIN", 16),   # Ventilateur haut est           (pin 36)
    5: _int("MAHALI_RELAY5_PIN", 19),   # Ventilateur ouest 1            (pin 35)
    6: _int("MAHALI_RELAY6_PIN", 20),   # Ventilateur ouest 2            (pin 38)
    7: _int("MAHALI_RELAY7_PIN", 21),   # Ventilateur ouest 3            (pin 40)
    8: _int("MAHALI_RELAY8_PIN", 26),   # Pompes canari                  (pin 37)
}
MAIN_PUMP_CHANNEL = 1
COOLING_FAN_CHANNELS = [2, 3, 4, 5, 6, 7]
CANARI_PUMP_CHANNEL = 8
ALL_CHANNELS = list(RELAY_GPIO_PINS.keys())

# --- Règles d'automatisation (doc §3.6.2) -----------------------------------
# Hystérésis ventilateurs + pompes canari (basé sur la température max des
# 3 zones, approche "pire cas").
AUTOMATION_TEMP_HIGH = _float("MAHALI_AUTOMATION_TEMP_HIGH", 32.0)
AUTOMATION_TEMP_LOW_RESET = _float("MAHALI_AUTOMATION_TEMP_LOW_RESET", 28.0)
# Pompe principale : cycle 15 min ON / 15 min OFF tant que le réservoir le permet.
# (Ancien cycle fixe, conservé pour compat / repli.)
MAIN_PUMP_CYCLE_ON_SECONDS = _int("MAHALI_MAIN_PUMP_ON_S", 15 * 60)
MAIN_PUMP_CYCLE_OFF_SECONDS = _int("MAHALI_MAIN_PUMP_OFF_S", 15 * 60)

# Cycle pompe adapté au système HYBRIDE tomate : pot coco (tampon) + RACINES
# NUES dans le tuyau. Contrainte clé = les racines nues ne doivent jamais
# sécher (pas de réserve) MAIS ont besoin d'air -> impulsions courtes et
# FRÉQUENTES le jour, réduites (sans jamais laisser sécher) la nuit.
# Tout réglable par env.
PUMP_DAY_ON_SECONDS    = _int("MAHALI_PUMP_DAY_ON_S", 5 * 60)         # jour: 5 min ON
PUMP_DAY_OFF_SECONDS   = _int("MAHALI_PUMP_DAY_OFF_S", 25 * 60)       # jour: 25 min OFF (~2/h)
PUMP_NIGHT_ON_SECONDS  = _int("MAHALI_PUMP_NIGHT_ON_S", 4 * 60)       # nuit: 4 min ON
PUMP_NIGHT_OFF_SECONDS = _int("MAHALI_PUMP_NIGHT_OFF_S", 90 * 60)     # nuit: 90 min OFF
# Fenêtre "jour" (heure locale du Pi). Gère aussi le cas start>end (nuit à cheval).
DAY_START_HOUR = _int("MAHALI_DAY_START_HOUR", 6)
DAY_END_HOUR   = _int("MAHALI_DAY_END_HOUR", 18)
# Niveau d'eau : sous 20% on coupe la pompe principale (+ alerte), sous 5%
# arrêt d'urgence de tout ce qui consomme de l'eau.
WATER_LEVEL_LOW = _float("MAHALI_WATER_LEVEL_LOW", 20.0)
WATER_LEVEL_CRITICAL = _float("MAHALI_WATER_LEVEL_CRITICAL", 5.0)

# --- Cadence des boucles -----------------------------------------------------
SENSOR_READ_INTERVAL_SECONDS = _float("MAHALI_SENSOR_INTERVAL_S", 10.0)
AUTOMATION_TICK_SECONDS = _float("MAHALI_AUTOMATION_TICK_S", 5.0)
# Intervalle du heartbeat de présence (doit rester < ONLINE_WINDOW_SECONDS=150
# côté backend pour ne jamais faussement basculer hors-ligne).
HEARTBEAT_INTERVAL_SECONDS = _float("MAHALI_HEARTBEAT_S", 45.0)

CLIENT_ID_SENSORS = os.environ.get("MAHALI_CLIENT_ID_SENSORS", "mahali-pi-sensors")
CLIENT_ID_RELAYS = os.environ.get("MAHALI_CLIENT_ID_RELAYS", "mahali-pi-relays")
CLIENT_ID_AUTOMATION = os.environ.get("MAHALI_CLIENT_ID_AUTOMATION", "mahali-pi-automation")
