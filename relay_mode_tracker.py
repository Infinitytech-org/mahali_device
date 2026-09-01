"""
Suivi local (en mémoire) du mode auto/manuel de chaque canal de relais, à
partir des messages observés sur `mahali/relays/cmd`.

Utilisé à la fois par relay_controller.py (pour savoir s'il doit honorer une
commande "automation") et par automation_service.py (pour éviter de spammer
des commandes qui seraient ignorées). Les deux processus tournent côté Pi et
n'ont besoin de rien d'autre que le broker MQTT local pour rester cohérents
entre eux — aucune dépendance au backend Django (autonomie de la couche
edge, doc §3.1).
"""


class RelayModeTracker:
    def __init__(self, channels):
        self._mode = {channel: "auto" for channel in channels}

    def observe_command(self, payload: dict) -> None:
        try:
            channel = int(payload.get("channel"))
        except (TypeError, ValueError):
            return
        if channel not in self._mode:
            return

        mode = payload.get("mode")
        source = payload.get("source")
        if mode in ("auto", "manual"):
            self._mode[channel] = mode
        elif source == "mobile_app":
            # Pas de champ "mode" explicite : une commande manuelle verrouille
            # quand même le canal (compatibilité avec d'anciens clients).
            self._mode[channel] = "manual"

    def is_auto(self, channel: int) -> bool:
        return self._mode.get(channel, "auto") == "auto"

    def mode_of(self, channel: int) -> str:
        return self._mode.get(channel, "auto")
