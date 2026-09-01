"""Client HTTP de l'agent Pi vers le backend Mahali en ligne.

Utilise urllib (aucune dépendance) pour rester fonctionnel sur un Pi vierge.
Base par défaut : https://api.mikia-green.com (surchargée par MAHALI_API_BASE).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_BASE = os.environ.get("MAHALI_API_BASE", "https://api.mikia-green.com").rstrip("/")


class ApiError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def _request(method: str, path: str, body: dict | None = None, secret: str | None = None) -> dict:
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if secret:
        headers["X-Device-Secret"] = secret
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode()).get("detail", "")
        except Exception:
            pass
        raise ApiError(detail or f"HTTP {e.code}", e.code) from e
    except urllib.error.URLError as e:
        raise ApiError(f"Réseau injoignable ({e.reason})") from e


def enroll(name: str, hardware: dict, model: str = "", firmware: str = "") -> dict:
    """POST /api/controllers/enroll/ → {device_id, secret, ...}"""
    return _request(
        "POST", "/api/controllers/enroll/",
        {"name": name, "hardware": hardware, "model": model, "firmware_version": firmware},
    )


def heartbeat(secret: str, hardware: dict | None = None) -> dict:
    """POST /api/controllers/heartbeat/ → {paired, greenhouse, mqtt, ...}"""
    return _request("POST", "/api/controllers/heartbeat/", {"hardware": hardware or {}}, secret=secret)


def reachable() -> bool:
    try:
        _request("GET", "/api/health/")
        return True
    except ApiError:
        return False
