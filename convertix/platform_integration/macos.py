"""Intégration macOS (À TESTER sur un Mac — voir CLAUDE.md).

- Sélection du Finder lue par AppleScript (osascript).
- Raccourci global via pynput (nécessite l'autorisation « Accessibilité »
  dans Réglages Système > Confidentialité et sécurité).
- Clic droit : Action rapide (Quick Action) Finder installée dans ~/Library/Services.
- Démarrage automatique : LaunchAgent ~/Library/LaunchAgents/com.convertix.app.plist.
"""
from __future__ import annotations

import logging
import plistlib
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "com.convertix.app.plist"
SERVICE_DIR = Path.home() / "Library" / "Services" / "Convertir avec Convertix.workflow"

_FINDER_SCRIPT = '''
tell application "Finder"
    set sel to selection
    set out to ""
    repeat with f in sel
        set out to out & POSIX path of (f as alias) & linefeed
    end repeat
    return out
end tell
'''


def launcher() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve().parents[2] / "run.py")]


def get_selected_files() -> list[Path]:
    try:
        res = subprocess.run(["osascript", "-e", _FINDER_SCRIPT], capture_output=True, text=True, timeout=5)
        return [Path(line) for line in res.stdout.splitlines() if line.strip() and Path(line).is_file()]
    except Exception:
        log.exception("Lecture de la sélection du Finder impossible")
        return []


class Hotkey:
    """Raccourci global via pynput. `callback` est appelé dans un thread : l'appelant
    doit le relayer vers le thread Qt (signal)."""

    def __init__(self, callback):
        self.callback = callback
        self._listener = None

    @staticmethod
    def to_pynput(seq: str) -> str:
        # Qt sur Mac : Ctrl = ⌘ (cmd), Meta = ⌃ (ctrl), Alt = ⌥
        m = {"ctrl": "<cmd>", "meta": "<ctrl>", "alt": "<alt>", "shift": "<shift>"}
        return "+".join(m.get(p.strip().lower(), p.strip().lower()) for p in seq.split("+"))

    def register(self, seq: str) -> bool:
        self.unregister()
        if not ensure_accessibility():
            log.warning("Autorisation Accessibilité absente : le raccourci marchera une fois Convertix autorisé")
        try:
            from pynput import keyboard
            self._listener = keyboard.GlobalHotKeys({self.to_pynput(seq): self.callback})
            self._listener.start()
            return True
        except Exception:
            log.exception("Raccourci global indisponible (autorisation Accessibilité ?)")
            return False

    def unregister(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None


def _framework(name: str):
    import ctypes
    return ctypes.cdll.LoadLibrary(f"/System/Library/Frameworks/{name}.framework/{name}")


def ensure_accessibility() -> bool:
    """Le raccourci global a besoin de l'autorisation « Accessibilité ». Si elle manque, macOS
    affiche sa fenêtre qui envoie vers Réglages Système. Retourne True si c'est déjà autorisé."""
    import ctypes
    try:
        ax = _framework("ApplicationServices")
        cf = _framework("CoreFoundation")
        ax.AXIsProcessTrusted.restype = ctypes.c_bool
        if ax.AXIsProcessTrusted():
            return True
        key = ctypes.c_void_p.in_dll(ax, "kAXTrustedCheckOptionPrompt")
        yes = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
        cf.CFDictionaryCreate.restype = ctypes.c_void_p
        cf.CFDictionaryCreate.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                          ctypes.POINTER(ctypes.c_void_p), ctypes.c_long,
                                          ctypes.c_void_p, ctypes.c_void_p]
        keys = (ctypes.c_void_p * 1)(key.value)
        values = (ctypes.c_void_p * 1)(yes.value)
        opts = cf.CFDictionaryCreate(
            None, keys, values, 1,
            ctypes.addressof(ctypes.c_void_p.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")),
            ctypes.addressof(ctypes.c_void_p.in_dll(cf, "kCFTypeDictionaryValueCallBacks")))
        ax.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
        ax.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
        return bool(ax.AXIsProcessTrustedWithOptions(opts))
    except Exception:
        log.exception("Vérification de l'autorisation Accessibilité impossible")
        return False


def can_capture_screen() -> bool:
    """Vrai si l'app a déjà l'autorisation « Enregistrement de l'écran » (ne déclenche aucune demande)."""
    import ctypes
    try:
        cg = _framework("CoreGraphics")
        cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        return bool(cg.CGPreflightScreenCaptureAccess())
    except Exception:
        return False


def set_autostart(enabled: bool) -> None:
    if enabled:
        LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
        with open(LAUNCH_AGENT, "wb") as f:
            plistlib.dump({"Label": "com.convertix.app", "ProgramArguments": launcher() + ["--tray"],
                           "RunAtLoad": True}, f)
    else:
        LAUNCH_AGENT.unlink(missing_ok=True)


def is_autostart() -> bool:
    return LAUNCH_AGENT.exists()


def register_quick_action() -> None:
    """Crée une Action rapide Finder « Convertir avec Convertix » (clic droit > Actions rapides)."""
    cmd = " ".join(f'"{a}"' for a in launcher()) + ' --convert "$@"'
    contents = SERVICE_DIR / "Contents"
    contents.mkdir(parents=True, exist_ok=True)
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump({
            "NSServices": [{
                "NSMenuItem": {"default": "Convertir avec Convertix"},
                "NSMessage": "runWorkflowAsService",
                "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
                "NSSendFileTypes": ["public.item"],
            }],
        }, f)
    with open(contents / "document.wflow", "wb") as f:
        plistlib.dump(_workflow(cmd), f)
    subprocess.run(["/System/Library/CoreServices/pbs", "-update"], check=False)


def unregister_quick_action() -> None:
    import shutil
    shutil.rmtree(SERVICE_DIR, ignore_errors=True)


def install_all() -> None:
    register_quick_action()
    set_autostart(True)


def uninstall_all() -> None:
    unregister_quick_action()
    set_autostart(False)


def _workflow(shell_cmd: str) -> dict:
    """Workflow Automator minimal : « Exécuter un script shell » avec les fichiers en arguments."""
    return {
        "AMApplicationBuild": "523",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [{
            "action": {
                "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.string"]},
                "AMActionVersion": "2.0.3",
                "AMApplication": ["Automator"],
                "AMParameterProperties": {"COMMAND_STRING": {}, "CheckedForUserDefaultShell": {},
                                          "inputMethod": {}, "shell": {}, "source": {}},
                "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
                "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
                "ActionName": "Run Shell Script",
                "ActionParameters": {"COMMAND_STRING": shell_cmd, "CheckedForUserDefaultShell": True,
                                     "inputMethod": 1, "shell": "/bin/zsh", "source": ""},
                "BundleIdentifier": "com.apple.RunShellScript",
                "CFBundleVersion": "2.0.3",
                "CanShowSelectedItemsWhenRun": False,
                "CanShowWhenRun": True,
                "Category": ["AMCategoryUtilities"],
                "Class Name": "RunShellScriptAction",
                "InputUUID": "0B0F2D3C-0000-4000-8000-000000000001",
                "OutputUUID": "0B0F2D3C-0000-4000-8000-000000000002",
                "UUID": "0B0F2D3C-0000-4000-8000-000000000003",
                "isViewVisible": True,
            },
        }],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleIDsByPath": {},
            "applicationPaths": [],
            "inputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 15,
            "processesInput": False,
            "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": False,
            "systemImageName": "NSActionTemplate",
            "useAutomaticInputType": False,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }
