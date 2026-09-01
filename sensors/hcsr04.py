"""
Mesure du niveau du réservoir (1000 L) via un capteur ultrason HC-SR04
(doc §3.3.3) : GPIO23 = Trig, GPIO24 = Echo (avec pont diviseur de tension
5V->3.3V sur l'Echo, câblage matériel, non géré ici).

Distance mesurée -> niveau % par interpolation linéaire entre
TANK_EMPTY_DISTANCE_CM (réservoir vide) et TANK_FULL_DISTANCE_CM (plein).
"""

import logging
import math
import random
import time

import config

logger = logging.getLogger("mahali.pi.hcsr04")

try:
    import RPi.GPIO as GPIO

    HARDWARE_AVAILABLE = True
except ImportError:
    GPIO = None
    HARDWARE_AVAILABLE = False

_SPEED_OF_SOUND_CM_PER_S = 34300.0
_ECHO_TIMEOUT_S = 0.04  # ~ 6.8 m aller-retour, largement suffisant pour la cuve


class WaterLevelSensor:
    def __init__(self):
        self.simulate = config.SIMULATE or not HARDWARE_AVAILABLE
        self._sim_t0 = time.time()
        self._sim_level = 80.0  # on simule une cuve qui se vide lentement et se remplit

        if not self.simulate:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(config.HCSR04_TRIG_PIN, GPIO.OUT)
            GPIO.setup(config.HCSR04_ECHO_PIN, GPIO.IN)
            GPIO.output(config.HCSR04_TRIG_PIN, False)
            time.sleep(0.2)

    def read_level_percent(self) -> float:
        if self.simulate:
            return self._simulate()

        distance_cm = self._measure_distance_cm()
        if distance_cm is None:
            logger.warning("Mesure HC-SR04 invalide (timeout écho).")
            return float("nan")
        return self._distance_to_percent(distance_cm)

    def _measure_distance_cm(self):
        GPIO.output(config.HCSR04_TRIG_PIN, True)
        time.sleep(0.00001)  # impulsion de 10µs
        GPIO.output(config.HCSR04_TRIG_PIN, False)

        start_wait = time.monotonic()
        while GPIO.input(config.HCSR04_ECHO_PIN) == 0:
            if time.monotonic() - start_wait > _ECHO_TIMEOUT_S:
                return None
        pulse_start = time.monotonic()

        while GPIO.input(config.HCSR04_ECHO_PIN) == 1:
            if time.monotonic() - pulse_start > _ECHO_TIMEOUT_S:
                return None
        pulse_end = time.monotonic()

        duration = pulse_end - pulse_start
        return (duration * _SPEED_OF_SOUND_CM_PER_S) / 2.0

    @staticmethod
    def _distance_to_percent(distance_cm: float) -> float:
        empty, full = config.TANK_EMPTY_DISTANCE_CM, config.TANK_FULL_DISTANCE_CM
        if empty == full:
            return 0.0
        pct = (empty - distance_cm) / (empty - full) * 100.0
        return round(max(0.0, min(100.0, pct)), 1)

    def _simulate(self) -> float:
        elapsed = time.time() - self._sim_t0
        # Dérive lente avec un cycle de "remplissage" toutes les ~20 min,
        # plus un peu de bruit de mesure.
        level = 55.0 + 40.0 * math.sin(elapsed / 1200.0) + random.uniform(-1.0, 1.0)
        return round(max(0.0, min(100.0, level)), 1)

    def close(self) -> None:
        if not self.simulate:
            GPIO.cleanup([config.HCSR04_TRIG_PIN, config.HCSR04_ECHO_PIN])
