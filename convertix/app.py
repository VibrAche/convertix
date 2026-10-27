"""Point d'entrée : ligne de commande, instance unique, icône de la barre des tâches.

Usages :
    Convertix                       démarre en arrière-plan (icône) et ouvre la fenêtre
    Convertix --tray                démarre en arrière-plan sans fenêtre (démarrage auto)
    Convertix --convert F1 F2 …     ouvre la fenêtre de conversion pour ces fichiers
                                    (utilisé par le clic droit / Envoyer vers / Action rapide)
    Convertix --to png F1 F2 …      conversion directe sans interface (scripts, tests)
    Convertix --formats F           liste les formats proposés pour un fichier
    Convertix --install / --uninstall   ajoute / retire le clic droit + démarrage auto
"""
from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .settings import Settings, config_dir, setup_logging

log = logging.getLogger(__name__)

SERVER_NAME = f"convertix-{getpass.getuser()}".replace(" ", "_")
COLLECT_MS = 350  # temps d'attente pour regrouper les fichiers d'un clic droit multi-sélection


# =========================================================================== CLI sans interface

def run_cli(args) -> int:
    from . import engine
    from .engine import ConvertOptions

    if args.formats:
        for f in engine.collect_files(args.formats):
            print(f"{f.name}: " + ", ".join(f"{t.key} ({t.label})" for t, _ in engine.targets_for([f])))
        return 0

    files = engine.collect_files(args.files)
    if not files:
        print("Aucun fichier convertible.", file=sys.stderr)
        return 2
    s = Settings.load()
    opts = ConvertOptions(quality=args.quality or s.quality, keep_metadata=s.keep_metadata,
                          output_dir=Path(args.out) if args.out else None)
    if args.merge:
        print(engine.merge_to_pdf(engine.mergeable(files), opts))
        return 0
    rc = 0
    for f in files:
        try:
            for r in engine.convert(f, args.to, opts):
                print(r)
        except Exception as e:
            print(f"ERREUR {f}: {e}", file=sys.stderr)
            rc = 1
    return rc


# =========================================================================== instance unique

def send_to_running(message: dict, timeout_ms: int = 400) -> bool:
    from PySide6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(json.dumps(message).encode("utf-8") + b"\n")
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


class Controller:
    """Vit dans l'instance principale : icône, raccourci, réception des fichiers."""

    def __init__(self, app, settings: Settings):
        from PySide6.QtCore import QObject, Qt, QTimer, Signal
        from PySide6.QtNetwork import QLocalServer

        self.app = app
        self.settings = settings
        self.pending: list[Path] = []
        self.fan = None             # éventail « actif » (qui reçoit les nouveaux fichiers)
        self.fans: set = set()      # tous les éventails ouverts (références gardées en vie)
        self.settings_win = None

        class _Bridge(QObject):
            hotkey = Signal()
        self.bridge = _Bridge()
        # file d'attente : on sort du filtre d'événements natifs avant de lire la sélection (COM)
        self.bridge.hotkey.connect(self.on_hotkey, Qt.QueuedConnection)

        self.collect_timer = QTimer(singleShot=True, interval=COLLECT_MS, timeout=self._flush_pending)

        self.server = QLocalServer()
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        QLocalServer.removeServer(SERVER_NAME)
        if not self.server.listen(SERVER_NAME):
            log.error("Serveur local indisponible : %s", self.server.errorString())
        self.server.newConnection.connect(self._on_connection)

        self._setup_tray()
        self.hotkey = None
        self.apply_hotkey()

    # ------------------------------------------------------------------ icône
    def _setup_tray(self) -> None:
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon

        self.tray = QSystemTrayIcon(app_icon())
        self.tray.setToolTip(f"{APP_NAME} — {self.settings.hotkey} sur un fichier pour le convertir")
        menu = QMenu()
        menu.addAction(QAction("Convertir des fichiers…", menu, triggered=self.pick_files))
        menu.addAction(QAction("Réglages…", menu, triggered=self.open_settings))
        menu.addSeparator()
        menu.addAction(QAction("Quitter", menu, triggered=self.app.quit))
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.pick_files() if r == QSystemTrayIcon.Trigger else None)
        self.tray.messageClicked.connect(self._open_last_folder)
        self._last_output: Path | None = None
        self.tray.show()

    def apply_hotkey(self) -> None:
        from .platform_integration import make_hotkey
        if self.hotkey is None:
            self.hotkey = make_hotkey(self.bridge.hotkey.emit)
        if self.hotkey is None:
            return
        self.hotkey.unregister()
        if self.settings.hotkey_enabled:
            if not self.hotkey.register(self.settings.hotkey):
                self.tray.showMessage(APP_NAME, f"Le raccourci {self.settings.hotkey} est déjà utilisé "
                                                "par une autre application. Change-le dans les Paramètres.")
        self.tray.setToolTip(f"{APP_NAME} — {self.settings.hotkey} sur un fichier pour le convertir")

    # ------------------------------------------------------------------ réception
    def _on_connection(self) -> None:
        sock = self.server.nextPendingConnection()

        def read():
            while sock.canReadLine():
                try:
                    msg = json.loads(bytes(sock.readLine()).decode("utf-8"))
                except ValueError:
                    continue
                self.handle_message(msg)
        sock.readyRead.connect(read)
        sock.disconnected.connect(sock.deleteLater)
        read()

    def handle_message(self, msg: dict) -> None:
        cmd = msg.get("cmd")
        if cmd == "convert":
            files = [Path(f) for f in msg.get("files", [])]
            if files:
                self.pending += files
                self.collect_timer.start()  # on attend les autres fichiers du même clic droit
            else:
                self.pick_files()
        elif cmd == "show":
            self.tray.showMessage(APP_NAME, f"Prêt ! Sélectionne un fichier puis fais {self.settings.hotkey}. "
                                            "Clic droit sur cette icône pour les réglages.", app_icon(), 5000)
        elif cmd == "settings":
            self.open_settings()

    def _flush_pending(self) -> None:
        files, self.pending = self.pending, []
        self.open_fan(files)

    def on_hotkey(self) -> None:
        from .platform_integration import get_selected_files
        files = get_selected_files()
        log.info("Raccourci : %d fichier(s) sélectionné(s)", len(files))
        msg = "" if files else "Sélectionne d'abord un fichier, puis refais le raccourci"
        self.open_fan(files, msg)

    # ------------------------------------------------------------------ fenêtres
    def open_fan(self, files: list[Path], message: str = "") -> None:
        from .gui.fan import FanMenu
        f = self.fan
        if f is not None:
            try:
                if f.isVisible() and f.state == "choose":
                    if files:
                        f.add_files(files)
                    f.show_near_cursor()
                    return
            except RuntimeError:  # éventail déjà détruit
                pass
        # l'ancien éventail (conversion en cours ou résultat affiché) reste visible à côté
        f = FanMenu(files, self.settings, message)
        self.fans.add(f)
        self.fan = f
        f.finished_ok.connect(self._on_converted)
        f.destroyed.connect(lambda *_, f=f: self._forget_fan(f))
        f.show_near_cursor()
        if not files:  # rien à convertir : simple message, qui disparaît tout seul
            f.auto_close.start(2500)

    def _forget_fan(self, f) -> None:
        self.fans.discard(f)
        if self.fan is f:
            self.fan = None

    def pick_files(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(None, "Choisir des fichiers à convertir")
        if files:
            self.open_fan([Path(f) for f in files])

    def _on_converted(self, produced: list) -> None:
        self._last_output = Path(produced[0])
        n = len(produced)
        self.tray.showMessage(APP_NAME, f"{n} fichier{'s' if n > 1 else ''} converti{'s' if n > 1 else ''} — "
                                        "clique pour ouvrir le dossier", app_icon(), 4000)

    def _open_last_folder(self) -> None:
        from .platform_integration import open_folder
        if self._last_output:
            open_folder(self._last_output.parent, select=self._last_output)

    def open_settings(self) -> None:
        from PySide6.QtGui import QGuiApplication
        from .gui.settings_dialog import SettingsWindow
        w = self.settings_win
        if w is None:
            w = self.settings_win = SettingsWindow(self.settings)
            w.changed.connect(self.apply_hotkey)
            w.look_changed.connect(self.apply_look)
            w.open_log.connect(self.open_log)
            w.destroyed.connect(lambda *_: setattr(self, "settings_win", None))
            w.adjustSize()
            geo = QGuiApplication.primaryScreen().availableGeometry()
            w.move(geo.center() - w.rect().center())
        w.show()
        w.raise_()
        w.activateWindow()

    def apply_look(self) -> None:
        from .gui import style
        style.configure(self.settings.theme, self.settings.accent)
        self.app.setStyleSheet(style.stylesheet(style.is_dark()))

    def open_log(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(config_dir() / "convertix.log")))


def app_icon():
    from PySide6.QtGui import QIcon
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    for cand in (base / "assets" / "icon.png", Path(__file__).resolve().parents[1] / "assets" / "icon.png"):
        if cand.exists():
            return QIcon(str(cand))
    return QIcon()


def run_gui(args) -> int:
    from PySide6.QtCore import QLockFile, QThread
    from PySide6.QtWidgets import QApplication

    files = [str(Path(f).resolve()) for f in (args.files or [])]
    if args.convert is not None:
        files += [str(Path(f).resolve()) for f in args.convert]
    msg = {"cmd": "convert", "files": files} if (files or args.convert is not None) else \
          {"cmd": "settings"} if args.settings else {"cmd": "show"}

    app = QApplication.instance() or QApplication(sys.argv)

    # 1) une instance tourne déjà → on lui passe les fichiers et on s'arrête
    if send_to_running(msg):
        return 0
    # 2) plusieurs lancements simultanés (clic droit sur 10 fichiers) : un seul devient principal
    lock = QLockFile(str(config_dir() / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        for _ in range(30):  # l'instance principale démarre : on réessaie pendant ~3 s
            if send_to_running(msg, 100):
                return 0
            QThread.msleep(100)  # sous Windows, l'échec de connexion est immédiat
        log.warning("Instance principale injoignable, démarrage autonome")

    from .gui import style
    settings = Settings.load()
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # on reste dans la barre des tâches
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    style.configure(settings.theme, settings.accent)
    app.setStyleSheet(style.stylesheet(style.is_dark()))

    if getattr(sys, "frozen", False) and not settings.setup_done:
        from . import platform_integration as pi
        try:
            pi.install_integration()
        except Exception:
            log.exception("Installation du clic droit au premier lancement impossible")
        settings.setup_done = True
        settings.save()

    ctrl = Controller(app, settings)
    if not args.tray:
        ctrl.handle_message(msg)
    rc = app.exec()
    lock.unlock()
    return rc


# =========================================================================== main

def parse_args(argv):
    p = argparse.ArgumentParser(prog=APP_NAME, description="Convertisseur de fichiers universel")
    p.add_argument("files", nargs="*", help="fichiers ou dossiers")
    p.add_argument("--convert", nargs="*", metavar="FICHIER", help="ouvre la fenêtre de conversion")
    p.add_argument("--tray", action="store_true", help="démarre en arrière-plan")
    p.add_argument("--settings", action="store_true", help="ouvre les paramètres")
    p.add_argument("--to", metavar="FORMAT", help="conversion directe sans interface (ex. png, pdf, mp3)")
    p.add_argument("--merge", action="store_true", help="fusionne images/PDF en un seul PDF (sans interface)")
    p.add_argument("--out", metavar="DOSSIER", help="dossier de sortie (mode sans interface)")
    p.add_argument("--quality", type=int, help="qualité 10-100 (mode sans interface)")
    p.add_argument("--formats", nargs="+", metavar="FICHIER", help="liste les formats proposés")
    p.add_argument("--install", action="store_true", help="ajoute le clic droit et le démarrage auto")
    p.add_argument("--uninstall", action="store_true", help="retire le clic droit et le démarrage auto")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    # Windows peut passer des arguments inconnus via le menu contextuel : on les ignore
    args, _unknown = p.parse_known_args(argv)
    return args


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    setup_logging(args.verbose)
    log.info("Démarrage %s %s : %s", APP_NAME, __version__, sys.argv[1:])
    try:
        if args.install or args.uninstall:
            from . import platform_integration as pi
            (pi.install_integration if args.install else pi.uninstall_integration)()
            return 0
        if args.formats or args.to or args.merge:
            return run_cli(args)
        return run_gui(args)
    except Exception:
        log.exception("Erreur fatale")
        raise


if __name__ == "__main__":
    sys.exit(main())
