"""
Lecture des 3 capteurs BME280 (température + humidité, doc §3.3.1/§4.3.1),
multiplexés sur le même bus I2C via un TCA9548A (3 capteurs à la même
adresse 0x76 ne peuvent pas coexister sur un bus sans multiplexeur).

En mode simulation (config.SIMULATE) ou si les bibliothèques matérielles ne
sont pas installées, génère des valeurs plausibles (variation sinusoïdale
lente + bruit) pour permettre de développer/tester sans matériel.
"""

import json
import logging
import math
import random
import time
import urllib.request

import config

from .tca9548a import TCA9548A

logger = logging.getLogger("mahali.pi.bme280")

try:
    import smbus2
    import bme280 as bme280_lib

    HARDWARE_AVAILABLE = True
except ImportError:
    smbus2 = None
    bme280_lib = None
    HARDWARE_AVAILABLE = False


class BME280Array:
    """Façade lisant les 3 zones (entrée/centre/sortie) en basculant le
    multiplexeur I2C entre chaque lecture."""

    def __init__(self):
        self.source = getattr(config, "BME_SOURCE", "i2c")
        self.simulate = config.SIMULATE or (self.source == "i2c" and not HARDWARE_AVAILABLE)
        self._sim_t0 = time.time()
        self._bus = None
        self._mux = None
        self._calib = {}
        # Cache des dernières mesures ESP32 (source="esp32").
        self._esp_cache: dict = {}
        self._esp_water = None  # niveau d'eau % lu depuis l'ESP32 (ou None)
        self._esp_ts = 0.0

        # Source ESP32 : aucun accès I2C local, on lit tout en HTTP.
        if self.source == "esp32":
            self.simulate = False
            logger.info("Capteurs air = ESP32-CAM en WiFi (%s).", config.ESP32_NODE_URL)
            return

        if self.simulate:
            if not HARDWARE_AVAILABLE:
                logger.warning("smbus2/bme280 non installés -> mode simulation forcé pour les BME280.")
            return

        self._bus = smbus2.SMBus(config.I2C_BUS_NUMBER)
        self._mux = TCA9548A(config.I2C_BUS_NUMBER, config.TCA9548A_ADDRESS)
        for sensor_key, channel in config.BME280_MUX_CHANNELS.items():
            # Tolérant : un capteur absent/défaillant sur un canal ne doit pas
            # empêcher les autres zones de fonctionner.
            try:
                self._mux.select_channel(channel)
                self._calib[sensor_key] = bme280_lib.load_calibration_params(
                    self._bus, config.BME280_ADDRESS
                )
                logger.info("BME280 zone %s détecté (canal %s).", sensor_key, channel)
            except OSError as exc:
                logger.warning(
                    "BME280 zone %s (canal %s) absent/injoignable: %s — zone ignorée.",
                    sensor_key, channel, exc,
                )
        if not self._calib:
            logger.warning("Aucun BME280 détecté sur les canaux configurés.")

    def _esp_fetch(self) -> dict:
        """Récupère /telemetry de l'ESP32 (cache 5 s) -> {clé: (temp, hum)}."""
        now = time.time()
        if self._esp_cache and (now - self._esp_ts) < 5.0:
            return self._esp_cache
        url = f"{config.ESP32_NODE_URL}/telemetry"
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                payload = json.loads(r.read().decode())
        except Exception as exc:  # noqa: BLE001 - on garde l'ancien cache si dispo
            logger.warning("ESP32 injoignable (%s): %s", url, exc)
            self._esp_ts = now
            return self._esp_cache
        result: dict = {}
        for z in payload.get("zones", []):
            if not z.get("ok"):
                continue
            key = config.ESP32_ZONE_TO_KEY.get(z.get("name"))
            if not key:
                continue
            temp = z.get("temperature")
            hum = z.get("humidity")
            result[key] = (
                round(float(temp), 2) if temp is not None else float("nan"),
                round(float(hum), 2) if hum is not None else float("nan"),
            )
        if result:
            self._esp_cache = result
        wl = payload.get("water_level")
        self._esp_water = float(wl) if wl is not None else None
        self._esp_ts = now
        return self._esp_cache

    def water_level(self):
        """Niveau d'eau % lu depuis l'ESP32 (source='esp32'), ou None."""
        if self.source != "esp32":
            return None
        self._esp_fetch()
        return self._esp_water

    def available_zones(self) -> list:
        """Zones dont le capteur est réellement présent (ou toutes en simu)."""
        if self.source == "esp32":
            return list(self._esp_fetch().keys())
        if self.simulate:
            return list(config.BME280_MUX_CHANNELS.keys())
        return list(self._calib.keys())

    def read_zone(self, sensor_key: str) -> tuple[float, float]:
        """Retourne (température °C, humidité %) pour la zone `sensor_key`."""
        if self.source == "esp32":
            data = self._esp_fetch()
            if sensor_key not in data:
                raise RuntimeError(f"ESP32 zone {sensor_key} indisponible")
            return data[sensor_key]

        if self.simulate:
            return self._simulate(sensor_key)

        if sensor_key not in self._calib:
            # Zone sans capteur (absent à l'init) : on ne bloque pas le service.
            raise RuntimeError(f"BME280 zone {sensor_key} indisponible")
        channel = config.BME280_MUX_CHANNELS[sensor_key]
        self._mux.select_channel(channel)
        data = bme280_lib.sample(self._bus, config.BME280_ADDRESS, self._calib[sensor_key])
        return round(data.temperature, 2), round(data.humidity, 2)

    def _simulate(self, sensor_key: str) -> tuple[float, float]:
        elapsed = time.time() - self._sim_t0
        zone_offset = {
            config.SENSOR_TEMP_ENTRY: 0.0,
            config.SENSOR_TEMP_CENTER: 1.5,
            config.SENSOR_TEMP_EXIT: -0.5,
        }.get(sensor_key, 0.0)

        # Serre refroidie : on garde l'intérieur sensiblement SOUS la
        # température extérieure (Sahel ~30-40°C) -> base basse + faible
        # amplitude. Surchargeable via MAHALI_SIM_TEMP_BASE.
        base = config._float("MAHALI_SIM_TEMP_BASE", 24.0)
        temp = base + zone_offset + 2.0 * math.sin(elapsed / 300.0) + random.uniform(-0.3, 0.3)
        humidity = 74.0 + 8.0 * math.sin(elapsed / 420.0 + 1.0) + random.uniform(-1.5, 1.5)
        humidity = max(30.0, min(95.0, humidity))
        return round(temp, 2), round(humidity, 2)

    def close(self) -> None:
        if self._mux is not None:
            self._mux.close()
        if self._bus is not None:
            self._bus.close()
