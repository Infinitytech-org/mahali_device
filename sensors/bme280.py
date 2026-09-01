"""
Lecture des 3 capteurs BME280 (température + humidité, doc §3.3.1/§4.3.1),
multiplexés sur le même bus I2C via un TCA9548A (3 capteurs à la même
adresse 0x76 ne peuvent pas coexister sur un bus sans multiplexeur).

En mode simulation (config.SIMULATE) ou si les bibliothèques matérielles ne
sont pas installées, génère des valeurs plausibles (variation sinusoïdale
lente + bruit) pour permettre de développer/tester sans matériel.
"""

import logging
import math
import random
import time

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
        self.simulate = config.SIMULATE or not HARDWARE_AVAILABLE
        self._sim_t0 = time.time()
        self._bus = None
        self._mux = None
        self._calib = {}

        if self.simulate:
            if not HARDWARE_AVAILABLE:
                logger.warning("smbus2/bme280 non installés -> mode simulation forcé pour les BME280.")
            return

        self._bus = smbus2.SMBus(config.I2C_BUS_NUMBER)
        self._mux = TCA9548A(config.I2C_BUS_NUMBER, config.TCA9548A_ADDRESS)
        for sensor_key, channel in config.BME280_MUX_CHANNELS.items():
            self._mux.select_channel(channel)
            self._calib[sensor_key] = bme280_lib.load_calibration_params(self._bus, config.BME280_ADDRESS)

    def read_zone(self, sensor_key: str) -> tuple[float, float]:
        """Retourne (température °C, humidité %) pour la zone `sensor_key`."""
        if self.simulate:
            return self._simulate(sensor_key)

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
