"""Fenêtre « Réglages » (clic droit sur l'icône). Chaque changement s'applique tout de suite, comme sur iPhone."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QKeySequenceEdit, QLabel, QPushButton, QSlider, QVBoxLayout)

from .. import APP_NAME, __version__
from .. import platform_integration as pi
from ..settings import Settings
from . import style
from .glass import SHADOW, GlassWindow
from .widgets import Swatch, Switch

THEMES = [("auto", "Auto"), ("light", "Clair"), ("dark", "Sombre")]


class SettingsWindow(GlassWindow):
    changed = Signal()       # raccourci modifié
    look_changed = Signal()  # couleur ou thème modifiés : l'app recharge le style
    open_log = Signal()

    def __init__(self, settings: Settings):
        super().__init__(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"{APP_NAME} — Réglages")
        self.settings = settings
        v = QVBoxLayout(self)
        v.setContentsMargins(SHADOW + 22, SHADOW + 18, SHADOW + 22, SHADOW + 18)
        v.setSpacing(6)

        head = QHBoxLayout()
        head.addWidget(QLabel("Réglages", objectName="Title"), 1)
        head.addWidget(QPushButton("✕", objectName="Round", clicked=self.close, toolTip="Fermer (Échap)"))
        v.addLayout(head)
        v.addSpacing(6)

        # --- Apparence
        g = self._card(v, "Apparence")
        g.addWidget(QLabel("Couleur"), 0, 0)
        sw = QHBoxLayout()
        sw.setSpacing(4)
        self.swatches = QButtonGroup(self)
        for name, color in style.ACCENTS.items():
            b = Swatch(color, name)
            b.setChecked(color.lower() == settings.accent.lower())
            b.clicked.connect(lambda _=False, c=color: self._set_accent(c))
            self.swatches.addButton(b)
            sw.addWidget(b)
        sw.addStretch(1)
        g.addLayout(sw, 0, 1)
        g.addWidget(QLabel("Thème"), 1, 0)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.themes = QButtonGroup(self)
        for i, (key, label) in enumerate(THEMES):
            b = QPushButton(label, objectName="Seg", checkable=True)
            b.setProperty("pos", ["first", "mid", "last"][i])
            b.setChecked(settings.theme == key)
            b.clicked.connect(lambda _=False, k=key: self._set_theme(k))
            self.themes.addButton(b)
            seg.addWidget(b)
        seg.addStretch(1)
        g.addLayout(seg, 1, 1)

        # --- Raccourci
        g = self._card(v, "Raccourci clavier")
        self.hotkey = QKeySequenceEdit(QKeySequence(settings.hotkey))
        self.hotkey.editingFinished.connect(self._save_hotkey)
        self.hotkey_on = Switch("Activé", settings.hotkey_enabled)
        self.hotkey_on.toggled.connect(self._save_hotkey)
        g.addWidget(self.hotkey, 0, 0)
        g.addWidget(self.hotkey_on, 0, 1)
        g.setColumnStretch(0, 1)

        # --- Conversion
        g = self._card(v, "Conversion")
        g.addWidget(QLabel("Qualité"), 0, 0)
        self.quality = QSlider(Qt.Horizontal, minimum=10, maximum=100, value=settings.quality)
        self.quality_lbl = QLabel(f"{settings.quality} %")
        self.quality.valueChanged.connect(self._set_quality)
        g.addWidget(self.quality, 0, 1)
        g.addWidget(self.quality_lbl, 0, 2)
        g.addWidget(QLabel("Enregistrer"), 1, 0)
        self.output = QComboBox()
        self.output.addItem("à côté de l'original", "same")
        self.output.addItem(f"dans un sous-dossier « {settings.subfolder_name} »", "subfolder")
        self.output.setCurrentIndex(0 if settings.output_mode == "same" else 1)
        self.output.currentIndexChanged.connect(lambda _: self._set("output_mode", self.output.currentData()))
        g.addWidget(self.output, 1, 1, 1, 2)
        self.meta = Switch("Garder la date et l'appareil des photos", settings.keep_metadata)
        self.meta.toggled.connect(lambda on: self._set("keep_metadata", on))
        g.addWidget(self.meta, 2, 0, 1, 3)
        self.open_after = Switch("Ouvrir le dossier à la fin", settings.open_folder_after)
        self.open_after.toggled.connect(lambda on: self._set("open_folder_after", on))
        g.addWidget(self.open_after, 3, 0, 1, 3)
        g.setColumnStretch(1, 1)

        # --- Système
        g = self._card(v, "Système")
        self.autostart = Switch("Lancer au démarrage de l'ordinateur", pi.is_autostart())
        self.autostart.toggled.connect(pi.set_autostart)
        g.addWidget(self.autostart, 0, 0, 1, 2)
        self.integ_lbl = QLabel()
        self.integ_btn = QPushButton(clicked=self._toggle_integration)
        g.addWidget(self.integ_lbl, 1, 0)
        g.addWidget(self.integ_btn, 1, 1, Qt.AlignRight)
        g.setColumnStretch(0, 1)
        self._refresh_integration()

        v.addSpacing(8)
        foot = QHBoxLayout()
        foot.addWidget(QLabel(f"{APP_NAME} {__version__}", objectName="Muted"), 1)
        foot.addWidget(QPushButton("Journal", objectName="Link", clicked=self.open_log.emit))
        v.addLayout(foot)
        self.resize(520 + 2 * SHADOW, 0)

    def _card(self, v: QVBoxLayout, title: str) -> QGridLayout:
        v.addWidget(QLabel(title.upper(), objectName="GroupTitle"))
        card = QFrame(objectName="Card")
        g = QGridLayout(card)
        g.setContentsMargins(16, 12, 16, 12)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        v.addWidget(card)
        return g

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and not self.hotkey.hasFocus():
            self.close()
        else:
            super().keyPressEvent(e)

    # ------------------------------------------------------------------ enregistrement immédiat
    def _set(self, name: str, value) -> None:
        setattr(self.settings, name, value)
        self.settings.save()

    def _set_quality(self, q: int) -> None:
        self.quality_lbl.setText(f"{q} %")
        self._set("quality", q)

    def _set_accent(self, color: str) -> None:
        self._set("accent", color)
        self.look_changed.emit()
        self.update()

    def _set_theme(self, key: str) -> None:
        self._set("theme", key)
        self.look_changed.emit()
        self.update()

    def _save_hotkey(self, *_) -> None:
        seq = self.hotkey.keySequence().toString(QKeySequence.PortableText)
        if seq:
            self.settings.hotkey = seq.split(",")[0].strip()
        self.settings.hotkey_enabled = self.hotkey_on.isChecked()
        self.settings.save()
        self.changed.emit()

    def _refresh_integration(self) -> None:
        on = pi.is_integrated()
        if pi.IS_WIN:
            self.integ_lbl.setText("« Convertir avec Convertix » dans le clic droit" if on
                                   else "Pas dans le menu clic droit")
        elif pi.IS_MAC:
            self.integ_lbl.setText("Action rapide Finder installée" if on else "Action rapide Finder absente")
        else:
            self.integ_lbl.setText("Clic droit indisponible sur ce système")
            self.integ_btn.setEnabled(False)
        self.integ_btn.setText("Retirer" if on else "Ajouter")

    def _toggle_integration(self) -> None:
        if pi.is_integrated():
            pi.uninstall_integration()
        else:
            pi.install_integration()
        self.autostart.setChecked(pi.is_autostart())
        self._refresh_integration()
