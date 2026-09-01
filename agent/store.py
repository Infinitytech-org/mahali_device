"""Stockage local des identifiants du contrôleur (~/.mahali/device.json).

Une fois le Pi enrôlé, on garde ici son device_id + secret + le slug de sa
serre (appris via heartbeat). Ce fichier survit aux redémarrages : au reboot,
l'agent le relit et repart directement en mode supervision (pas de ré-enrôlement).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

STORE_DIR = Path(os.environ.get("MAHALI_HOME", str(Path.home() / ".mahali")))
STORE_FILE = STORE_DIR / "device.json"


def load() -> dict[str, Any]:
    try:
        return json.loads(STORE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(data: dict[str, Any]) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(STORE_FILE)
    # Le secret ne doit être lisible que par le propriétaire.
    try:
        os.chmod(STORE_FILE, 0o600)
    except OSError:
        pass


def is_enrolled() -> bool:
    d = load()
    return bool(d.get("device_id") and d.get("secret"))


def update(**fields: Any) -> dict[str, Any]:
    data = load()
    data.update(fields)
    save(data)
    return data
