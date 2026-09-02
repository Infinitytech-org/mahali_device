"""Point d'entrée unique de l'agent Mahali (Raspberry Pi).

Un Pi vierge fait simplement :  git clone …  puis  ./start.sh
et ce programme s'occupe de tout :

  1. Détecte le matériel (caméra, capteurs I2C, écran).
  2. S'ENRÔLE au premier lancement : demande un nom, appelle le backend en
     ligne, reçoit un `device_id` (à saisir sur le mobile) + un secret, et les
     stocke dans ~/.mahali/device.json.
  3. Attend l'APPAIRAGE : bat un heartbeat jusqu'à ce que l'utilisateur ait lié
     ce device à une serre depuis l'app mobile.
  4. Une fois appairé : lance et SUPERVISE les services (capteurs, relais,
     automatisation, caméra, interface web locale) avec le bon topic MQTT, et
     continue le heartbeat. Redémarre tout service qui tombe. Survit au reboot
     (via systemd, voir systemd/mahali-agent.service).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from . import api, console, hardware, store

HERE = Path(__file__).resolve().parent.parent  # dossier raspberry/
POLL_PAIRED = 5          # s entre deux vérifs d'appairage
HEARTBEAT_EVERY = 30     # s entre deux heartbeats une fois en marche


def _load_env() -> None:
    """Charge raspberry/.env dans os.environ (sans écraser l'existant).

    Permet de configurer le câblage via .env : broches relais, canaux du mux
    (MAHALI_MUX_CH_ENTRY/CENTER/EXIT), broker, etc. — repris par config.py et
    par tous les services lancés.
    """
    env_file = HERE / ".env"
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except FileNotFoundError:
        pass


def _show_hardware(hw: dict) -> None:
    console.title("Matériel détecté")
    console.kv("Modèle", hw.get("model", "?"))
    cam = hw.get("camera", {})
    console.kv("Caméra", cam.get("detail", "?"), good=cam.get("present"))
    disp = hw.get("display", {})
    console.kv("Écran", disp.get("detail", "?"), good=disp.get("present"))
    console.kv("GPIO", "disponible" if hw.get("gpio") else "absent", good=hw.get("gpio"))
    i2c = hw.get("i2c", [])
    if i2c:
        for dev in i2c:
            console.kv("Capteur I2C", dev, good=True)
    else:
        console.kv("Capteurs I2C", "aucun détecté (câblage ? I2C activé ?)", good=False)


def _ensure_enrolled(hw: dict) -> dict:
    data = store.load()
    if store.is_enrolled():
        console.ok(f"Déjà enrôlé : {console.BOLD}{data['device_id']}{console.RESET}")
        return data

    console.title("Enrôlement de ce contrôleur")
    if not api.reachable():
        console.error(f"Backend injoignable ({api.API_BASE}).")
        console.info("Vérifie la connexion Internet du Pi, puis relance.")
        sys.exit(1)

    default_name = hw.get("model", "Contrôleur Mahali").split("Rev")[0].strip()
    name = console.ask(f"Nom de ce contrôleur [{default_name}] :") or default_name

    console.step("Enregistrement auprès du backend…")
    try:
        resp = api.enroll(name=name, hardware=hw, model=hw.get("model", ""))
    except api.ApiError as e:
        console.error(f"Échec de l'enrôlement : {e}")
        sys.exit(1)

    data = store.update(
        device_id=resp["device_id"], secret=resp["secret"], name=resp.get("name", name)
    )
    console.ok("Contrôleur enrôlé avec succès.")
    console.info("Saisis cet identifiant dans l'app mobile (Créer une serre) :")
    console.big_code(resp["device_id"])
    return data


def _wait_for_pairing(secret: str, hw: dict) -> dict:
    console.title("En attente d'appairage")
    console.info("Ouvre l'app mobile → Créer une serre → saisis l'identifiant ci-dessus.")
    while True:
        try:
            hb = api.heartbeat(secret, hardware=hw)
        except api.ApiError as e:
            console.warn(f"Heartbeat : {e} — nouvelle tentative…")
            time.sleep(POLL_PAIRED)
            continue
        if hb.get("paired"):
            gh = hb["greenhouse"]
            store.update(greenhouse=gh["slug"], greenhouse_name=gh["name"], mqtt=hb["mqtt"])
            console.ok(f"Appairé à la serre : {console.BOLD}{gh['name']}{console.RESET} ({gh['slug']})")
            return hb
        time.sleep(POLL_PAIRED)


def _service_env(mqtt: dict) -> dict:
    # Les services + l'UI locale parlent au broker LOCAL du Pi (offline-first).
    # Un pont mosquitto (voir _setup_cloud_bridge) synchronise avec le cloud.
    env = os.environ.copy()
    env["MQTT_BROKER_HOST"] = "localhost"
    env["MQTT_BROKER_PORT"] = "1883"
    env["MQTT_TOPIC_PREFIX"] = str(mqtt.get("topic_prefix") or "mahali")
    data = store.load()
    env["MAHALI_GREENHOUSE_SLUG"] = str(data.get("greenhouse", ""))
    return env


def _setup_cloud_bridge(mqtt: dict) -> None:
    """Configure le pont mosquitto local -> cloud pour la serre appairée.

    Best-effort (nécessite sudo, dispo en NOPASSWD sur le Pi). Si ça échoue,
    l'UI locale fonctionne quand même ; seule la synchro cloud est retardée.
    """
    data = store.load()
    slug = data.get("greenhouse")
    host = mqtt.get("host")
    port = mqtt.get("port", 1883)
    prefix = str(mqtt.get("topic_prefix") or f"mahali/{slug}")
    if not (slug and host):
        return
    conf = (
        f"connection mahali-cloud-{slug}\n"
        f"address {host}:{port}\n"
        f"topic {prefix}/# both 0\n"
        f"remote_clientid mahali-bridge-{slug}\n"
        f"try_private false\n"
        f"cleansession true\n"
        f"bridge_protocol_version mqttv311\n"
    )
    try:
        subprocess.run(
            ["sudo", "tee", "/etc/mosquitto/conf.d/mahali-bridge.conf"],
            input=conf, text=True, capture_output=True, check=True,
        )
        subprocess.run(["sudo", "systemctl", "restart", "mosquitto"], check=False)
        console.ok("Pont MQTT cloud configuré (synchro avec l'app mobile).")
    except Exception as e:  # noqa: BLE001
        console.warn(f"Pont cloud non configuré ({e}). L'UI locale reste fonctionnelle.")


def _supervise(mqtt: dict, hw: dict, secret: str) -> None:
    """Lance et surveille les services ; relance ceux qui tombent."""
    env = _service_env(mqtt)
    py = sys.executable

    services: dict[str, list[str]] = {
        "capteurs": [py, str(HERE / "sensor_service.py")],
        "relais": [py, str(HERE / "relay_controller.py")],
        "automatisation": [py, str(HERE / "automation_service.py")],
        "caméra": [py, str(HERE / "camera_stream.py")],
        "interface-web": [py, "-m", "local_ui.app"],
    }
    # La caméra n'est lancée que si détectée.
    if not hw.get("camera", {}).get("present"):
        services.pop("caméra", None)

    procs: dict[str, subprocess.Popen] = {}

    def start(name: str) -> None:
        try:
            procs[name] = subprocess.Popen(services[name], env=env, cwd=str(HERE))
            console.ok(f"Service démarré : {name}")
        except Exception as e:  # noqa: BLE001
            console.error(f"Impossible de lancer {name} : {e}")

    _setup_cloud_bridge(mqtt)
    console.title("Démarrage des services")
    for name in services:
        start(name)

    console.title("En marche")
    console.info(f"Topic MQTT : {env['MQTT_TOPIC_PREFIX']}  ·  broker : {env['MQTT_BROKER_HOST']}")
    console.info("Interface locale : http://localhost:8090  (Ctrl+C pour arrêter)")

    last_hb = 0.0
    try:
        while True:
            # Relance les services morts.
            for name, proc in list(procs.items()):
                if proc.poll() is not None:
                    console.warn(f"Service '{name}' arrêté (code {proc.returncode}) — relance…")
                    start(name)
            # Heartbeat périodique (garde la serre « en ligne » + MAJ matériel).
            if time.time() - last_hb > HEARTBEAT_EVERY:
                try:
                    api.heartbeat(secret, hardware=hw)
                except api.ApiError:
                    pass  # hors-ligne : les services locaux continuent
                last_hb = time.time()
            time.sleep(2)
    except KeyboardInterrupt:
        console.warn("Arrêt demandé — extinction des services…")
        for proc in procs.values():
            proc.terminate()


def main() -> None:
    _load_env()
    console.banner()
    hw = hardware.detect()
    _show_hardware(hw)

    data = _ensure_enrolled(hw)
    secret = data["secret"]

    # Déjà appairé (reboot) ? On récupère la config MQTT stockée, sinon on attend.
    if data.get("greenhouse") and data.get("mqtt"):
        console.ok(f"Serre appairée : {data.get('greenhouse_name', data['greenhouse'])}")
        mqtt = data["mqtt"]
    else:
        hb = _wait_for_pairing(secret, hw)
        mqtt = hb["mqtt"]

    _supervise(mqtt, hw, secret)


if __name__ == "__main__":
    main()
