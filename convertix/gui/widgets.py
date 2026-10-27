"""Petits contrôles dessinés à la main, façon iOS : interrupteur et pastille de couleur."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QCheckBox

from . import style


class Switch(QCheckBox):
    """Case à cocher affichée comme un interrupteur iOS (le texte à gauche, l'interrupteur à droite)."""
    TRACK_W, TRACK_H = 44, 26

    def __init__(self, text: str = "", checked: bool = False):
        super().__init__(text)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self, duration=160)
        self._anim.valueChanged.connect(self._move)
        self.toggled.connect(self._animate)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _move(self, v) -> None:
        self._pos = float(v)
        self.update()

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.text()) + self.TRACK_W + 16, max(self.TRACK_H + 4, fm.height() + 6))

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = style.is_dark()
        track = QRectF(self.width() - self.TRACK_W - 1, (self.height() - self.TRACK_H) / 2, self.TRACK_W, self.TRACK_H)
        off = QColor(255, 255, 255, 40) if dark else QColor(120, 120, 128, 60)
        on = QColor(style.accent())
        col = QColor(int(off.red() + (on.red() - off.red()) * self._pos),
                     int(off.green() + (on.green() - off.green()) * self._pos),
                     int(off.blue() + (on.blue() - off.blue()) * self._pos),
                     int(off.alpha() + (255 - off.alpha()) * self._pos))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(track, self.TRACK_H / 2, self.TRACK_H / 2)
        d = self.TRACK_H - 4
        x = track.left() + 2 + (self.TRACK_W - d - 4) * self._pos
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QRectF(x, track.top() + 3, d, d))
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, track.top() + 2, d, d))
        p.setPen(self.palette().windowText().color() if self.isEnabled() else QColor(150, 150, 150))
        p.drawText(QRectF(0, 0, track.left() - 10, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()


class Swatch(QAbstractButton):
    """Pastille de couleur ronde ; un anneau entoure la couleur choisie."""

    def __init__(self, color: str, name: str):
        super().__init__()
        self.color = color
        self.setCheckable(True)
        self.setToolTip(name)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(30, 30)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(c, 10, 10)
        p.setBrush(QColor(255, 255, 255, 70))  # petit reflet
        p.drawEllipse(QPointF(c.x(), c.y() - 4), 6, 3)
        if self.isChecked() or self.underMouse():
            ring = QColor(self.color)
            if not self.isChecked():
                ring.setAlpha(110)
            p.setPen(QPen(ring, 2.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, 13.5, 13.5)
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)
