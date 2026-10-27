"""Façade multiplateforme : l'app n'appelle que ces fonctions."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def get_selected_files() -> list[Path]:
    """Fichiers sélectionnés dans l'Explorateur / le Finder au moment du raccourci."""
    if IS_WIN:
        from . import windows
        return windows.get_selected_files()
    if IS_MAC:
        from . import macos
        return macos.get_selected_files()
    return []


def make_hotkey(callback):
    """Objet avec .register(seq) -> bool et .unregister(). `callback` peut être appelé
    depuis un autre thread (Mac) : passer une fonction qui émet un signal Qt."""
    if IS_WIN:
        from .windows import HotkeyFilter
        return HotkeyFilter(callback)
    if IS_MAC:
        from .macos import Hotkey
        return Hotkey(callback)
    return None


def install_integration() -> None:
    """Clic droit + Envoyer vers / Action rapide + démarrage automatique."""
    if IS_WIN:
        from . import windows
        windows.install_all()
    elif IS_MAC:
        from . import macos
        macos.install_all()


def uninstall_integration() -> None:
    if IS_WIN:
        from . import windows
        windows.uninstall_all()
    elif IS_MAC:
        from . import macos
        macos.uninstall_all()


def is_integrated() -> bool:
    if IS_WIN:
        from . import windows
        return windows.is_context_menu_registered()
    if IS_MAC:
        from . import macos
        return macos.SERVICE_DIR.exists()
    return False


def set_autostart(enabled: bool) -> None:
    if IS_WIN:
        from . import windows
        windows.set_autostart(enabled)
    elif IS_MAC:
        from . import macos
        macos.set_autostart(enabled)


def is_autostart() -> bool:
    if IS_WIN:
        from . import windows
        return windows.is_autostart()
    if IS_MAC:
        from . import macos
        return macos.is_autostart()
    return False


def notify(title: str, body: str, button: str, on_click) -> bool:
    """Notification native avec un bouton (Windows). False → l'appelant utilise la bulle de l'icône."""
    if IS_WIN:
        from . import windows
        return windows.show_toast(title, body, button, on_click)
    return False


def can_capture_screen() -> bool:
    """L'éventail peut-il capturer l'écran derrière lui (effet de réfraction) sans rien demander ?"""
    if IS_MAC:
        from . import macos
        return macos.can_capture_screen()
    return True


def open_folder(path: Path, select: Path | None = None) -> None:
    import subprocess
    if IS_WIN:
        if select:
            subprocess.Popen(["explorer", "/select,", str(select)])
        else:
            subprocess.Popen(["explorer", str(path)])
    elif IS_MAC:
        subprocess.Popen(["open", "-R", str(select)] if select else ["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
