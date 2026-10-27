"""Vérification des mises à jour : une seule requête à GitHub pour connaître la dernière version publiée.
Aucun fichier ni aucune donnée personnelle n'est envoyé ; désactivable dans les Réglages."""
from __future__ import annotations

import json
import logging
import re
import urllib.request

from . import __version__

log = logging.getLogger(__name__)

REPO = "VibrAche/convertix"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def is_newer(remote: str, local: str = __version__) -> bool:
    try:
        return _parse(remote) > _parse(local)
    except ValueError:
        return False


def latest_release(timeout: float = 8) -> tuple[str, str] | None:
    """(version, page de téléchargement) si une version plus récente existe, sinon None."""
    try:
        req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": f"Convertix/{__version__}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        tag = str(data.get("tag_name", "")).lstrip("v")
        if tag and is_newer(tag):
            return tag, data.get("html_url") or PAGE
    except Exception as e:  # hors ligne, GitHub indisponible… : on réessaiera au prochain démarrage
        log.info("Vérification des mises à jour impossible : %s", e)
    return None
