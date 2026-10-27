"""Fenêtre « liquid glass » : sans cadre, coins arrondis, fond dégradé avec taches de couleur floues,
ombre portée. Les cartes et boutons en verre dépoli sont dans la feuille de style (style.py)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from .style import accent, is_dark

RADIUS = 26
SHADOW = 18  # marge autour du verre réservée à l'ombre


class GlassWindow(QWidget):
    def __init__(self, flags=Qt.Window):
        super().__init__(None, flags | Qt.FramelessWindowHint)
        self.setObjectName("Glass")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._drag: QPointF | None = None

    def glass_margins(self) -> int:
        return SHADOW

    # déplacer la fenêtre en attrapant n'importe quelle zone vide
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition() - QPointF(self.pos())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move((e.globalPosition() - self._drag).toPoint())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        dark = is_dark()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)

        # ombre douce : anneaux superposés, l'opacité s'accumule vers le bord du verre
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 7 if dark else 3))
        for i in range(SHADOW, 0, -1):
            p.drawRoundedRect(r.adjusted(-i, -i + 5, i, i + 5), RADIUS + i, RADIUS + i)

        path = QPainterPath()
        path.addRoundedRect(r, RADIUS, RADIUS)
        p.setClipPath(path)

        base = QLinearGradient(r.topLeft(), r.bottomRight())
        if dark:
            base.setColorAt(0, QColor("#0E1324"))
            base.setColorAt(1, QColor("#1B1430"))
            blobs = [(0.12, 0.05, 0.65, accent(), 150), (0.95, 0.40, 0.55, "#8B5CF6", 130),
                     (0.25, 1.00, 0.60, "#EC4899", 90)]
        else:
            base.setColorAt(0, QColor("#EEF4FF"))
            base.setColorAt(1, QColor("#F8F0FF"))
            blobs = [(0.12, 0.05, 0.65, accent(), 110), (0.95, 0.40, 0.55, "#C4B5FD", 160),
                     (0.25, 1.00, 0.60, "#FBC4E4", 150)]
        p.fillRect(r, base)
        for fx, fy, fr, color, alpha in blobs:
            c = QPointF(r.left() + fx * r.width(), r.top() + fy * r.height())
            g = QRadialGradient(c, fr * max(r.width(), r.height()))
            col = QColor(color)
            col.setAlpha(alpha)
            g.setColorAt(0, col)
            col.setAlpha(0)
            g.setColorAt(1, col)
            p.fillRect(r, g)

        # voile dépoli + reflet en haut (le côté « liquide »)
        p.fillRect(r, QColor(255, 255, 255, 18) if dark else QColor(255, 255, 255, 70))
        sheen = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + 120))
        sheen.setColorAt(0, QColor(255, 255, 255, 40 if dark else 120))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(r, sheen)

        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 45 if dark else 230), 1.2))
        p.drawRoundedRect(r.adjusted(0.6, 0.6, -0.6, -0.6), RADIUS, RADIUS)
        p.end()
