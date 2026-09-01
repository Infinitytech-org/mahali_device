"""
Driver minimal pour le multiplexeur I2C TCA9548A (doc §3.3.1).

Permet de basculer le bus I2C sur un des 8 canaux (un seul à la fois), ce qui
permet de connecter 3 BME280 à la même adresse 0x76 sans collision.
"""

import logging

logger = logging.getLogger("mahali.pi.tca9548a")

try:
    import smbus2

    HARDWARE_AVAILABLE = True
except ImportError:  # pas de RPi / smbus2 installé (dev, CI, simulation)
    smbus2 = None
    HARDWARE_AVAILABLE = False


class TCA9548A:
    def __init__(self, bus_number: int, address: int):
        self.address = address
        self._bus = smbus2.SMBus(bus_number) if HARDWARE_AVAILABLE else None
        self._current_channel = None

    def select_channel(self, channel: int) -> None:
        if not HARDWARE_AVAILABLE:
            return
        if channel == self._current_channel:
            return
        if not 0 <= channel <= 7:
            raise ValueError(f"Canal TCA9548A invalide: {channel}")
        self._bus.write_byte(self.address, 1 << channel)
        self._current_channel = channel

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()
