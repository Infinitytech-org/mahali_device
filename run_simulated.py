#!/usr/bin/env python3
"""
Lance les 3 services Raspberry Pi (capteurs, relais, automatisation) en mode
simulation (MAHALI_SIMULATE=true), dans le même terminal — pratique pour le
développement et pour le test end-to-end sans matériel.

Usage :
    MQTT_BROKER_HOST=127.0.0.1 python run_simulated.py
"""

import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

SERVICES = ["sensor_service.py", "relay_controller.py", "automation_service.py"]


def main():
    env = os.environ.copy()
    env["MAHALI_SIMULATE"] = "true"
    env.setdefault("MQTT_BROKER_HOST", "127.0.0.1")

    procs = []
    for script in SERVICES:
        proc = subprocess.Popen([sys.executable, os.path.join(HERE, script)], env=env, cwd=HERE)
        procs.append(proc)
        print(f"[run_simulated] {script} démarré (pid={proc.pid})")

    def shutdown(*_args):
        print("\n[run_simulated] Arrêt des services simulés...")
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        for proc, script in zip(procs, SERVICES):
            if proc.poll() is not None:
                print(f"[run_simulated] {script} s'est arrêté (code {proc.returncode}) — arrêt global.")
                shutdown()
        time.sleep(1)


if __name__ == "__main__":
    main()
