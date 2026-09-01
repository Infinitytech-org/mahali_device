"""
Lecture du pH via l'ADC ADS1115 (I2C, 0x48) + électrode pH (doc §3.3.2).

Driver ADS1115 minimal écrit directement au-dessus de smbus2 (registres
documentés par Texas Instruments), pour éviter une dépendance lourde type
Adafruit-Blinka. Conversion en pH : pH = 7 + (2.5V - V_mesuré) / 0.1776
(électrode étalonnée à pH 7 -> 2.5 V, pente ~59.16 mV/pH -> 0.1776 V par
unité de pH sur 3 unités, cf. doc §3.3.2).
"""

import logging
import math
import random
import time

import config

logger = logging.getLogger("mahali.pi.ads1115_ph")

try:
    import smbus2

    HARDWARE_AVAILABLE = True
except ImportError:
    smbus2 = None
    HARDWARE_AVAILABLE = False

# Registres ADS1115
_REG_CONVERSION = 0x00
_REG_CONFIG = 0x01

# Config : début de conversion, MUX AINx vs GND, PGA +-4.096V, mode single-shot,
# 128 SPS, comparateur désactivé. (cf. datasheet ADS1115 table 8)
_MUX_SINGLE_ENDED = {0: 0x4, 1: 0x5, 2: 0x6, 3: 0x7}
_PGA_4_096V = 0x1
_FSR_VOLTS = 4.096
_OS_SINGLE = 0x1
_MODE_SINGLE_SHOT = 0x1
_DR_128SPS = 0x4


class PhSensor:
    def __init__(self):
        self.simulate = config.SIMULATE or not HARDWARE_AVAILABLE
        self._sim_t0 = time.time()
        self._bus = None
        if not self.simulate:
            self._bus = smbus2.SMBus(config.I2C_BUS_NUMBER)

    def read_ph(self) -> float:
        if self.simulate:
            return self._simulate()

        voltage = self._read_voltage(config.ADS1115_PH_CHANNEL)
        ph = 7.0 + (config.PH_NEUTRAL_VOLTAGE - voltage) / config.PH_SLOPE
        return round(ph, 2)

    def _read_voltage(self, channel: int) -> float:
        mux = _MUX_SINGLE_ENDED[channel]
        config_value = (
            (_OS_SINGLE << 15)
            | (mux << 12)
            | (_PGA_4_096V << 9)
            | (_MODE_SINGLE_SHOT << 8)
            | (_DR_128SPS << 5)
        )
        high = (config_value >> 8) & 0xFF
        low = config_value & 0xFF
        self._bus.write_i2c_block_data(config.ADS1115_ADDRESS, _REG_CONFIG, [high, low])
        time.sleep(0.01)  # ~8ms à 128 SPS, on laisse une marge

        data = self._bus.read_i2c_block_data(config.ADS1115_ADDRESS, _REG_CONVERSION, 2)
        raw = (data[0] << 8) | data[1]
        if raw > 0x7FFF:
            raw -= 0x10000
        return (raw / 32768.0) * _FSR_VOLTS

    def _simulate(self) -> float:
        elapsed = time.time() - self._sim_t0
        ph = 6.0 + 0.4 * math.sin(elapsed / 600.0) + random.uniform(-0.05, 0.05)
        return round(ph, 2)

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()
