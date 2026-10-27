"""Intégration Windows : menu clic droit, « Envoyer vers », démarrage automatique,
lecture de la sélection de l'Explorateur et raccourci clavier global.

Tout est écrit dans HKEY_CURRENT_USER : aucun droit administrateur n'est nécessaire.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

from .. import APP_NAME

log = logging.getLogger(__name__)

MENU_LABEL = "Convertir avec Convertix"
VERB = "Convertix.Convert"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


# =========================================================================== commande de lancement

def launcher() -> tuple[str, list[str]]:
    """(exécutable, arguments de base) pour relancer l'app.

    - version installée (PyInstaller) : Convertix.exe
    - mode développement : pythonw.exe <repo>/run.py
    """
    if getattr(sys, "frozen", False):
        return sys.executable, []
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    run_py = Path(__file__).resolve().parents[2] / "run.py"
    return str(pyw if pyw.exists() else exe), [str(run_py)]


def _cmdline(*extra: str) -> str:
    exe, base = launcher()
    parts = [exe, *base, *extra]
    return " ".join(f'"{p}"' for p in parts)


def icon_path() -> str:
    exe, base = launcher()
    if getattr(sys, "frozen", False):
        return f"{exe},0"
    ico = Path(__file__).resolve().parents[2] / "assets" / "icon.ico"
    return str(ico)


# =========================================================================== registre

def _supported_exts() -> list[str]:
    from ..engine import registry
    return sorted(registry().supported_inputs())


def register_context_menu() -> int:
    """Ajoute « Convertir avec Convertix » au clic droit de chaque type de fichier pris en charge.

    On passe par SystemFileAssociations\\.ext : l'entrée n'apparaît que sur les fichiers
    convertibles. MultiSelectModel=Player autorise la sélection multiple (Windows lance une
    instance par fichier ; l'instance unique les regroupe dans une seule fenêtre).
    """
    import winreg
    cmd = _cmdline("--convert") + ' "%1"'
    n = 0
    for ext in _supported_exts():
        base = rf"Software\Classes\SystemFileAssociations\{ext}\shell\{VERB}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, MENU_LABEL)
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon_path())
            winreg.SetValueEx(k, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
        n += 1
    # clic droit sur un dossier → traitement par lot de tout son contenu
    base = rf"Software\Classes\Directory\shell\{VERB}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
        winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "Convertir le contenu avec Convertix")
        winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon_path())
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
    _notify_shell()
    log.info("Menu contextuel enregistré pour %d extensions", n)
    return n


def unregister_context_menu() -> None:
    import winreg
    root = r"Software\Classes\SystemFileAssociations"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, root) as k:
            i = 0
            exts = []
            while True:
                try:
                    exts.append(winreg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break
    except FileNotFoundError:
        return
    for ext in exts:
        _delete_tree(winreg.HKEY_CURRENT_USER, rf"{root}\{ext}\shell\{VERB}")
    _delete_tree(winreg.HKEY_CURRENT_USER, rf"Software\Classes\Directory\shell\{VERB}")
    _notify_shell()


def _delete_tree(hive, path: str) -> None:
    import winreg
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(hive, rf"{path}\{sub}")
        winreg.DeleteKey(hive, path)
    except FileNotFoundError:
        pass


def is_context_menu_registered() -> bool:
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                       rf"Software\Classes\SystemFileAssociations\.dng\shell\{VERB}"))
        return True
    except OSError:
        return False


def _notify_shell() -> None:
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except Exception:
        pass


def sendto_path() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "SendTo" / f"{APP_NAME}.lnk"


def register_sendto() -> None:
    """Raccourci « Envoyer vers > Convertix » : reçoit tous les fichiers sélectionnés d'un coup."""
    import win32com.client
    exe, base = launcher()
    sc = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(sendto_path()))
    sc.TargetPath = exe
    sc.Arguments = " ".join(f'"{a}"' for a in base) + " --convert"
    sc.IconLocation = icon_path()
    sc.Description = MENU_LABEL
    sc.Save()


def unregister_sendto() -> None:
    sendto_path().unlink(missing_ok=True)


def set_autostart(enabled: bool) -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _cmdline("--tray"))
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


def is_autostart() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


# =========================================================================== menu clic droit complet (Windows 11)

# Clé connue qui désactive le nouveau menu court de Windows 11 : le menu complet (avec Convertix) revient
# dès le premier clic droit. Elle concerne tout Windows, d'où un interrupteur désactivé par défaut.
CLASSIC_MENU_KEY = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32"
OWN_KEY = r"Software\Convertix"  # on retient que c'est Convertix qui l'a activé (pour le retirer proprement)


def is_windows11() -> bool:
    return sys.getwindowsversion().build >= 22000


def classic_menu_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLASSIC_MENU_KEY):
            return True
    except OSError:
        return False


def set_classic_menu(enabled: bool) -> None:
    import winreg
    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLASSIC_MENU_KEY) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, OWN_KEY) as k:
            winreg.SetValueEx(k, "ClassicMenu", 0, winreg.REG_DWORD, 1)
    else:
        for key in (CLASSIC_MENU_KEY, CLASSIC_MENU_KEY.rsplit("\\", 1)[0]):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
            except OSError:
                pass
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, OWN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, "ClassicMenu")
        except OSError:
            pass


def classic_menu_set_by_us() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, OWN_KEY) as k:
            return winreg.QueryValueEx(k, "ClassicMenu")[0] == 1
    except OSError:
        return False


def restart_explorer() -> None:
    """Relance l'Explorateur pour appliquer le changement de menu (les fenêtres de dossiers se ferment)."""
    import subprocess
    subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], capture_output=True, creationflags=0x08000000)
    subprocess.Popen(["explorer.exe"], creationflags=0x08000000)


# =========================================================================== notifications natives

AUMID = "VibrAche.Convertix"
_toaster = None


def register_aumid() -> None:
    """Identité de l'app pour les notifications Windows (nom + icône), sans paquet MSIX ni droits admin."""
    import winreg
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{AUMID}") as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, str(base / "assets" / "icon.png"))


def show_toast(title: str, body: str, button: str, on_click) -> bool:
    """Notification Windows avec un bouton. `on_click` est appelé depuis un autre thread.
    Retourne False si les notifications natives sont indisponibles (l'appelant prend le relais)."""
    global _toaster
    try:
        from windows_toasts import InteractableWindowsToaster, Toast, ToastButton
        if _toaster is None:
            register_aumid()
            _toaster = InteractableWindowsToaster(APP_NAME, notifierAUMID=AUMID)
        toast = Toast([title, body])
        toast.AddAction(ToastButton(button, "open"))
        toast.on_activated = lambda _args: on_click()  # clic sur le bouton ou sur la notification
        _toaster.show_toast(toast)
        return True
    except Exception:
        log.exception("Notification Windows indisponible")
        return False


def install_all() -> None:
    try:
        register_aumid()
    except Exception:
        log.exception("Identité de notification non enregistrée")
    register_context_menu()
    try:
        register_sendto()
    except Exception:
        log.exception("Raccourci « Envoyer vers » non créé")
    set_autostart(True)


def uninstall_all() -> None:
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{AUMID}")
    except OSError:
        pass
    if classic_menu_set_by_us():  # on ne retire le menu complet que si c'est Convertix qui l'avait mis
        set_classic_menu(False)
    unregister_context_menu()
    unregister_sendto()
    set_autostart(False)


# =========================================================================== sélection de l'Explorateur

user32 = ctypes.windll.user32 if sys.platform == "win32" else None

VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN = 0x11, 0x12, 0x10, 0x5B, 0x5C
KEYEVENTF_KEYUP = 0x0002


def _window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


EXPLORER_CLASSES = {"CabinetWClass", "ExploreWClass", "Progman", "WorkerW"}


def get_selected_files() -> list[Path]:
    """Fichiers sélectionnés dans la fenêtre au premier plan (Explorateur ou Bureau)."""
    hwnd = user32.GetForegroundWindow()
    cls = _window_class(hwnd)
    log.debug("Fenêtre au premier plan : %s (%s)", cls, _window_title(hwnd))
    if cls == "CabinetWClass":
        try:
            files = _explorer_selection_com(hwnd)
            if files is not None:
                return files
        except Exception:
            log.exception("Lecture COM de la sélection impossible, repli sur le presse-papiers")
    # Bureau (Progman / WorkerW) ou Explorateur à onglets ambigu : on passe par Ctrl+C.
    # Jamais dans les autres fenêtres (Ctrl+C dans un terminal interromprait un programme).
    if cls in EXPLORER_CLASSES:
        return _selection_via_clipboard()
    return []


def _explorer_selection_com(hwnd: int) -> list[Path] | None:
    import win32com.client
    shell = win32com.client.Dispatch("Shell.Application")
    cands = []
    for w in shell.Windows():
        try:
            if int(w.HWND) == hwnd:
                cands.append(w)
        except Exception:
            continue
    if len(cands) > 1:  # Windows 11 : plusieurs onglets partagent la même fenêtre
        title = _window_title(hwnd)
        cands = [w for w in cands if w.LocationName and title.startswith(w.LocationName)]
    if len(cands) != 1:
        return None
    items = cands[0].Document.SelectedItems()
    return [Path(items.Item(i).Path) for i in range(items.Count)]


def _wait_modifiers_released(timeout: float = 1.5) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN)):
            return
        time.sleep(0.02)


_owner_hwnd: int | None = None  # fenêtre cachée de l'app (fixée par HotkeyFilter), propriétaire du presse-papiers


def _open_clipboard(timeout: float = 0.5) -> bool:
    """OpenClipboard avec notre fenêtre comme propriétaire, en réessayant : juste après Ctrl+C,
    l'Explorateur peut encore tenir le presse-papiers."""
    import win32clipboard as cb
    end = time.monotonic() + timeout
    while True:
        try:
            cb.OpenClipboard(_owner_hwnd or 0)
            return True
        except Exception:
            if time.monotonic() > end:
                return False
            time.sleep(0.03)


def _selection_via_clipboard() -> list[Path]:
    """Envoie Ctrl+C à la fenêtre active, lit la liste de fichiers copiée puis restaure le presse-papiers.

    Seules les données texte / binaires sont restaurées (pas les images bitmap ni une
    ancienne liste de fichiers) : c'est le cas courant d'un texte copié auparavant."""
    import win32clipboard as cb
    import win32con

    _wait_modifiers_released()
    saved: list[tuple[int, bytes | str]] = []
    if _open_clipboard():
        try:
            fmt = 0
            while True:
                fmt = cb.EnumClipboardFormats(fmt)
                if not fmt:
                    break
                # CF_BITMAP, CF_METAFILEPICT, CF_DIB, CF_PALETTE, CF_ENHMETAFILE, CF_HDROP, CF_DIBV5
                if fmt in (2, 3, 8, 9, 14, 15, 17):
                    continue
                try:
                    data = cb.GetClipboardData(fmt)
                    if isinstance(data, (bytes, str)):
                        saved.append((fmt, data))
                except Exception:
                    pass
        finally:
            cb.CloseClipboard()

    seq = user32.GetClipboardSequenceNumber()
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(ord("C"), 0, 0, 0)
    user32.keybd_event(ord("C"), 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

    end = time.monotonic() + 0.8
    while time.monotonic() < end and user32.GetClipboardSequenceNumber() == seq:
        time.sleep(0.02)
    if user32.GetClipboardSequenceNumber() == seq:
        return []  # rien n'a été copié (aucune sélection)

    files: list[Path] = []
    if not _open_clipboard(1.0):
        log.error("Presse-papiers inaccessible après Ctrl+C")
        return []
    try:
        if cb.IsClipboardFormatAvailable(win32con.CF_HDROP):
            files = [Path(p) for p in cb.GetClipboardData(win32con.CF_HDROP)]
        cb.EmptyClipboard()  # on remet l'ancien contenu
        for fmt, data in saved:
            try:
                cb.SetClipboardData(fmt, data)
            except Exception:
                log.debug("Format %s non restauré", fmt)
    except Exception:
        log.exception("Lecture du presse-papiers impossible")
    finally:
        cb.CloseClipboard()
    return [f for f in files if f.exists()]


# =========================================================================== raccourci global

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY = 0x0312


def parse_hotkey(seq: str) -> tuple[int, int]:
    """"Ctrl+Alt+C" → (modificateurs, code de touche virtuelle)."""
    mods, vk = 0, 0
    for part in [p.strip().lower() for p in seq.split("+") if p.strip()]:
        if part in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif part in ("alt",):
            mods |= MOD_ALT
        elif part in ("shift", "maj"):
            mods |= MOD_SHIFT
        elif part in ("meta", "win"):
            mods |= MOD_WIN
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit():
            vk = 0x6F + int(part[1:])  # F1 = 0x70
        elif part in ("space", "espace"):
            vk = 0x20
    if not vk or not mods:
        raise ValueError(f"Raccourci invalide : {seq}")
    return mods, vk


class HotkeyFilter:
    """Enregistre un raccourci global (RegisterHotKey) sur une fenêtre Qt cachée."""

    HOTKEY_ID = 0xC0DE

    def __init__(self, callback):
        from PySide6.QtCore import QAbstractNativeEventFilter
        from PySide6.QtWidgets import QApplication, QWidget

        self.callback = callback
        self._hwnd = None

        outer = self

        class _Filter(QAbstractNativeEventFilter):
            def nativeEventFilter(self, event_type, message):
                et = bytes(event_type) if not isinstance(event_type, (bytes, str)) else event_type
                if isinstance(et, str):
                    et = et.encode()
                if et in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                    msg = wintypes.MSG.from_address(int(message))
                    if msg.message == WM_HOTKEY and msg.wParam == outer.HOTKEY_ID:
                        outer.callback()
                        return True, 0
                return False, 0

        self._filter = _Filter()
        QApplication.instance().installNativeEventFilter(self._filter)
        self._widget = QWidget()
        self._widget.setWindowTitle("Convertix hotkey")
        self._hwnd = int(self._widget.winId())
        global _owner_hwnd
        _owner_hwnd = self._hwnd

    def register(self, seq: str) -> bool:
        self.unregister()
        try:
            mods, vk = parse_hotkey(seq)
        except ValueError:
            log.error("Raccourci invalide : %s", seq)
            return False
        ok = bool(user32.RegisterHotKey(self._hwnd, self.HOTKEY_ID, mods | MOD_NOREPEAT, vk))
        if not ok:
            log.error("RegisterHotKey a échoué pour %s (déjà utilisé par une autre application ?)", seq)
        return ok

    def unregister(self) -> None:
        if self._hwnd:
            user32.UnregisterHotKey(self._hwnd, self.HOTKEY_ID)
