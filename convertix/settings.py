"""Paramètres utilisateur persistés en JSON + configuration du journal."""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import APP_NAME

log = logging.getLogger(__name__)


def config_dir() -> Path:
    """Dossier de configuration selon l'OS (AppData sur Windows, Application Support sur Mac)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Settings:
    # Raccourci global, au format Qt. Sur Mac, Qt nomme « Meta » la touche Control
    # (Meta+Alt+C = ⌃⌥C ; on évite ⌘⌥C qui sert déjà à « Copier le chemin » dans le Finder).
    hotkey: str = "Meta+Alt+C" if sys.platform == "darwin" else "Ctrl+Alt+C"
    hotkey_enabled: bool = True
    # Qualité JPEG / WebP / HEIC / AVIF (1-100)
    quality: int = 92
    # "same" = même dossier que l'original ; "subfolder" = sous-dossier "Convertis"
    output_mode: str = "same"
    subfolder_name: str = "Convertis"
    # Ouvre le dossier de sortie à la fin d'une conversion
    open_folder_after: bool = False
    # Conserve les métadonnées EXIF quand c'est possible
    keep_metadata: bool = True
    # Derniers formats choisis (affichés en premier)
    recent_targets: list[str] = field(default_factory=list)
    # Apparence : couleur d'accent et thème ("auto" = celui du système, "light", "dark")
    accent: str = "#0A84FF"
    theme: str = "auto"
    # Premier lancement de l'app compilée : clic droit + démarrage auto installés une fois (utile sur Mac,
    # où il n'y a pas d'installeur, et pour la version portable Windows)
    setup_done: bool = False

    @classmethod
    def path(cls) -> Path:
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        p = cls.path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**known)
            except Exception:  # fichier corrompu → valeurs par défaut
                log.exception("Lecture des paramètres impossible, valeurs par défaut utilisées")
        return cls()

    def save(self) -> None:
        self.path().write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def remember_target(self, key: str) -> None:
        if key in self.recent_targets:
            self.recent_targets.remove(key)
        self.recent_targets.insert(0, key)
        del self.recent_targets[8:]


def setup_logging(verbose: bool = False) -> Path:
    log_path = config_dir() / "convertix.log"
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:  # absent dans un exe PyInstaller "windowed"
        sh = logging.StreamHandler()
        sh.setLevel(logging.DEBUG if verbose else logging.WARNING)
        root.addHandler(sh)
    return log_path
