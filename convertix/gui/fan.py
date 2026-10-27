"""Éventail de conversion : des bulles de verre s'ouvrent autour de la souris, une par format.

Effet « liquid glass » : juste avant l'affichage, on capture l'écran derrière la fenêtre, on le floute,
et chaque bulle en montre un morceau légèrement grossi (réfraction), avec reflet et liseré lumineux.
"""
from __future__ import annotations

import logging
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QWidget

from .. import engine
from ..engine import ConvertOptions
from ..settings import Settings
from . import style
from .worker import ConvertWorker

log = logging.getLogger(__name__)

GROUP_ORDER = ["Image", "Document", "Tableur", "Présentation", "Vidéo", "Audio"]
# à quoi sert chaque format, en deux mots (affiché au survol d'une bulle)
HINTS = {"jpg": "Photo légère", "png": "Sans perte", "webp": "Pour le web", "avif": "Très compact",
         "heic": "Format iPhone", "tiff": "Impression", "bmp": "Image brute", "gif": "Simple ou animé",
         "ico": "Icône", "svg": "Vectoriel", "pdf": "Document", "docx": "Word", "odt": "LibreOffice",
         "rtf": "Texte riche", "txt": "Texte brut", "xlsx": "Excel", "ods": "LibreOffice",
         "csv": "Tableau simple", "pptx": "PowerPoint", "odp": "LibreOffice", "mp4": "Vidéo partout",
         "mov": "Vidéo Apple", "mkv": "Vidéo MKV", "webm": "Vidéo web", "mp3": "Musique",
         "m4a": "Musique Apple", "wav": "Audio brut", "flac": "Audio sans perte", "ogg": "Audio libre",
         "opus": "Audio léger"}
MERGE, MORE = "__merge__", "__more__"

W, H = 600, 440           # fenêtre transparente qui contient l'éventail
BUBBLE_R, HUB_R = 33, 36  # rayons des bulles et du moyeu central
R1, R2 = 150, 240         # rayons des deux arcs
GAP = 12                  # espace entre deux bulles d'un même arc
INNER_MAX = 7             # au-delà : 6 bulles + une bulle « +N » qui ouvre le 2e arc (demi-cercle max)
HUB_MARGIN = 128          # distance entre le moyeu et le bord de la fenêtre, côté opposé à l'éventail


@dataclass
class Bubble:
    key: str
    text: str
    hint: str
    ring: int
    pos: QPointF = field(default_factory=QPointF)  # position finale (éventail ouvert)


def _kind(files: list[Path]) -> str:
    """Emoji du type de fichier dominant, affiché dans le moyeu."""
    from ..converters import documents as d, images as i, media as m
    kinds = {e: k for k, exts in (("🖼️", i.ALL_IMAGE_EXTS | i.SVG_EXTS), ("📄", d.PDF_EXTS | d.WORD_EXTS | d.TEXT_EXTS),
                                  ("📚", d.EBOOK_EXTS), ("📊", d.EXCEL_EXTS | d.CSV_EXTS), ("📽️", d.PPT_EXTS),
                                  ("🎬", m.VIDEO_EXTS), ("🎵", m.AUDIO_EXTS)) for e in exts}
    found = {kinds.get(engine.ext_of(f), "📁") for f in files}
    return found.pop() if len(found) == 1 else "🗂️"


class FanMenu(QWidget):
    finished_ok = Signal(list)  # fichiers produits (pour la notification)

    def __init__(self, files: list[Path], settings: Settings, message: str = ""):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)  # Mac : visible même si l'app n'est pas active
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.resize(W, H)
        self.settings = settings
        self.files: list[Path] = []
        self.bubbles: list[Bubble] = []
        self.hover: int | None = None
        self.state = "choose"            # choose | working | done | error
        self.message = message
        self.up = True                   # éventail au-dessus du moyeu (sinon en dessous)
        self.hub = QPointF(W / 2, H - HUB_MARGIN)
        self.worker: ConvertWorker | None = None
        self.produced: list[Path] = []
        self.status = ""
        self.progress = (0, 0)
        self.frac = 0.0                  # avancement du fichier en cours, s'il est connu (vidéos)
        self.spin = 0.0
        self._close_when_done = False
        self.bg: QPixmap | None = None   # capture floutée de l'écran derrière la fenêtre
        self.bg_small: QImage | None = None

        self.t_open = self._anim(320)    # ouverture de l'éventail (0 → 1)
        self.t_outer = self._anim(280)   # ouverture du 2e arc
        self.spin_timer = QTimer(self, interval=16, timeout=self._tick)
        self.auto_close = QTimer(self, singleShot=True, timeout=self.close)
        self.add_files(files)

    def _anim(self, ms: int) -> QVariantAnimation:
        a = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=ms)
        a.setEasingCurve(QEasingCurve.OutBack)
        a.valueChanged.connect(self.update)
        return a

    # ------------------------------------------------------------------ fichiers et bulles
    def add_files(self, files: list[Path]) -> None:
        if self.state != "choose":
            return
        self.files = engine.collect_files(self.files + list(files))
        if self.files:
            self.message = ""
        self._build_bubbles()
        self._layout()
        self.update()

    def _build_bubbles(self) -> None:
        total = len(self.files)
        targets = engine.targets_for(self.files)
        recent = {k: i for i, k in enumerate(self.settings.recent_targets)}
        group = {g: i for i, g in enumerate(GROUP_ORDER)}
        targets.sort(key=lambda tn: (recent.get(tn[0].key, 99), group.get(tn[0].group, 9)))
        items = []
        for t, n in targets:
            hint = HINTS.get(t.key, t.label)
            if n < total:
                hint += f" · {n} fichier{'s' if n > 1 else ''} sur {total}"
            items.append((t.key, t.key.upper(), hint))
        if len(engine.mergeable(self.files)) >= 2:
            items.insert(min(len(items), 3), (MERGE, "1 PDF", "Tout fusionner en un seul PDF"))
        if len(items) > INNER_MAX:
            inner, outer = items[:INNER_MAX - 1], items[INNER_MAX - 1:]
            inner.append((MORE, f"+{len(outer)}", "Voir tous les formats"))
        else:
            inner, outer = items, []
        self.bubbles = [Bubble(k, txt, h, 1) for k, txt, h in inner] + [Bubble(k, txt, h, 2) for k, txt, h in outer]
        self.hover = None

    def _layout(self) -> None:
        base = -math.pi / 2 if self.up else math.pi / 2
        for ring, radius in ((1, R1), (2, R2)):
            row = [b for b in self.bubbles if b.ring == ring]
            if not row:
                continue
            step = (2 * BUBBLE_R + GAP) / radius
            if ring == 2:
                step = max(step, math.radians(30))  # 2e arc aéré : bulles bien séparées
            step = min(step, math.radians(196) / max(len(row) - 1, 1))  # jamais sous le moyeu
            start = base - step * (len(row) - 1) / 2
            for i, b in enumerate(row):
                a = start + i * step
                b.pos = QPointF(self.hub.x() + radius * math.cos(a), self.hub.y() + radius * math.sin(a))

    def _current(self, b: Bubble) -> tuple[QPointF, float]:
        """Position et échelle animées d'une bulle (elle sort du moyeu)."""
        t = self.t_open.currentValue() or 0.0
        if b.ring == 2:
            t = min(t, self.t_outer.currentValue() or 0.0)
        return self.hub + (b.pos - self.hub) * t, max(0.0, min(1.0, t))

    def _visible(self) -> list[int]:
        if self.state != "choose":
            return []
        outer = self.t_outer.currentValue() or 0.0
        return [i for i, b in enumerate(self.bubbles) if b.ring == 1 or outer > 0.01]

    # ------------------------------------------------------------------ affichage
    def show_near_cursor(self) -> None:
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.up = pos.y() - geo.top() > R2 + BUBBLE_R + 30
        hub_y = H - HUB_MARGIN if self.up else HUB_MARGIN
        x = min(max(pos.x() - W // 2, geo.left()), geo.right() - W)
        y = min(max(pos.y() - hub_y, geo.top()), geo.bottom() - H)
        self.move(x, y)
        self.hub = QPointF(pos.x() - x, pos.y() - y)
        # le moyeu suit la souris, sans que l'éventail sorte de la fenêtre
        self.hub.setX(min(max(self.hub.x(), R2 + BUBBLE_R + 8), W - R2 - BUBBLE_R - 8))
        self.hub.setY(min(max(self.hub.y(), HUB_R + 8), H - HUB_R - 8))
        self._layout()
        if not self.isVisible():
            self._grab_background(screen, x, y)
            self.show()
            self.t_open.start()
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            _force_foreground(int(self.winId()))
        self.setFocus()

    def _grab_background(self, screen, x: int, y: int) -> None:
        from ..platform_integration import can_capture_screen
        if not can_capture_screen():  # Mac sans autorisation : verre dessiné, sans fenêtre de demande
            return
        try:
            g = screen.geometry()
            shot = screen.grabWindow(0, x - g.x(), y - g.y(), W, H)
            if not shot.isNull():
                self.set_background(shot.toImage())
        except Exception:
            log.exception("Capture de l'arrière-plan impossible, verre dessiné sans réfraction")

    def set_background(self, img: QImage) -> None:
        """Fond vu à travers le verre (capture de l'écran sous la fenêtre)."""
        try:
            dpr = img.width() / W
            # flou rapide : réduire fortement puis agrandir en lissant (deux passes)
            small = img.scaled(max(1, img.width() // 4), max(1, img.height() // 4),
                               Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self.bg_small = small.scaled(max(1, W // 14), max(1, H // 14),
                                         Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            blurred = self.bg_small.scaled(small.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            blurred = blurred.scaled(img.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self.bg = QPixmap.fromImage(blurred)
            self.bg.setDevicePixelRatio(dpr)
        except Exception:
            log.exception("Flou de l'arrière-plan impossible, verre dessiné sans réfraction")

    def _light_behind(self, c: QPointF) -> bool:
        """L'écran derrière ce point est-il clair ? (choix de la couleur du texte)"""
        if self.bg_small is None:
            return not style.is_dark()
        sx = min(max(int(c.x() / W * self.bg_small.width()), 0), self.bg_small.width() - 1)
        sy = min(max(int(c.y() / H * self.bg_small.height()), 0), self.bg_small.height() - 1)
        col = QColor(self.bg_small.pixel(sx, sy))
        return 0.299 * col.red() + 0.587 * col.green() + 0.114 * col.blue() > 150

    # ------------------------------------------------------------------ dessin
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        for i in self._visible():
            c, s = self._current(self.bubbles[i])
            if s > 0.02:
                self._bubble(p, self.bubbles[i], c, BUBBLE_R * (1.12 if i == self.hover else 1.0) * s, i == self.hover)
        self._draw_hub(p)
        self._draw_pill(p)
        p.end()

    def _glass(self, p: QPainter, path: QPainterPath, rect: QRectF, tint: QColor | None = None) -> bool:
        """Peint une forme en verre liquide. Retourne True si le fond derrière est clair."""
        light = self._light_behind(rect.center())
        r = min(rect.width(), rect.height()) / 2
        # ombre portée douce : formes de plus en plus grandes, décalées vers le bas, qui s'accumulent
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 9))
        for k in range(7, 0, -1):
            p.drawPath(_rounded(rect.adjusted(-k, -k + 3, k, k + 3), r + k))
        p.restore()

        p.save()
        p.setClipPath(path)
        # réfraction : le fond flou, grossi ~25 % autour du centre de la forme
        if self.bg is not None:
            dpr = self.bg.devicePixelRatio()
            src = QRectF(rect.center().x() - rect.width() * 0.4, rect.center().y() - rect.height() * 0.4,
                         rect.width() * 0.8, rect.height() * 0.8)
            p.drawPixmap(rect, self.bg, QRectF(src.x() * dpr, src.y() * dpr, src.width() * dpr, src.height() * dpr))
        else:
            g = QLinearGradient(rect.topLeft(), rect.bottomRight())
            g.setColorAt(0, QColor(120, 170, 255, 120))
            g.setColorAt(1, QColor(200, 150, 255, 120))
            p.fillPath(path, g)
        # voile : blanc laiteux sur fond clair, plus léger sur fond sombre
        p.fillPath(path, QColor(255, 255, 255, 70 if light else 38))
        if tint is not None:
            p.fillPath(path, tint)
        # bord lumineux (effet de Fresnel)
        fres = QRadialGradient(rect.center(), r)
        fres.setColorAt(0.0, QColor(255, 255, 255, 0))
        fres.setColorAt(0.70, QColor(255, 255, 255, 0))
        fres.setColorAt(1.0, QColor(255, 255, 255, 120 if light else 80))
        p.fillPath(path, fres)
        # reflet spéculaire en haut, lueur caustique en bas
        hl = QRectF(rect.left() + rect.width() * 0.16, rect.top() + rect.height() * 0.05,
                    rect.width() * 0.68, rect.height() * 0.42)
        g = QLinearGradient(hl.topLeft(), hl.bottomLeft())
        g.setColorAt(0, QColor(255, 255, 255, 175 if light else 120))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(hl, hl.height() / 2, hl.height() / 2)
        low = QRadialGradient(QPointF(rect.center().x(), rect.bottom()), rect.width() * 0.45)
        low.setColorAt(0, QColor(255, 255, 255, 70))
        low.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillPath(path, low)
        p.restore()

        # liseré : clair en haut, plus discret en bas
        edge = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        edge.setColorAt(0, QColor(255, 255, 255, 230))
        edge.setColorAt(0.5, QColor(255, 255, 255, 70))
        edge.setColorAt(1, QColor(255, 255, 255, 150))
        p.setPen(QPen(edge, 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        return light

    def _bubble(self, p: QPainter, b: Bubble, c: QPointF, r: float, hovered: bool) -> None:
        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        path = QPainterPath()
        path.addEllipse(rect)
        tint = None
        if hovered or b.key == MERGE:
            tint = QColor(style.accent())
            tint.setAlpha(150 if hovered else 70)
        light = self._glass(p, path, rect, tint)
        dark_text = light and not hovered
        f = QFont(p.font())
        f.setFamilies(["SF Pro Display", "Segoe UI Variable Display", "Segoe UI"])
        f.setBold(True)
        f.setPixelSize(int(r * (0.42 if len(b.text) <= 4 else 0.34)))
        p.setFont(f)
        p.setPen(QColor(29, 29, 31) if dark_text else QColor(255, 255, 255))
        p.drawText(rect, Qt.AlignCenter, b.text)

    def _draw_hub(self, p: QPainter) -> None:
        c, r = self.hub, HUB_R
        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        path = QPainterPath()
        path.addEllipse(rect)
        if self.state == "done":
            g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            g.setColorAt(0, QColor("#4ADE80"))
            g.setColorAt(1, QColor("#22C55E"))
            p.fillPath(path, g)
            self._glass_edge(p, path, rect)
            check = QPainterPath(QPointF(c.x() - 13, c.y() + 1))
            check.lineTo(c.x() - 4, c.y() + 10)
            check.lineTo(c.x() + 14, c.y() - 10)
            p.setPen(QPen(QColor("white"), 4.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(check)
            return
        if self.state == "error":
            g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            g.setColorAt(0, QColor("#FDBA74"))
            g.setColorAt(1, QColor("#F97316"))
            p.fillPath(path, g)
            self._glass_edge(p, path, rect)
            f = QFont(p.font())
            f.setBold(True)
            f.setPixelSize(30)
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(rect, Qt.AlignCenter, "!")
            return

        light = self._glass(p, path, rect)
        if self.state == "working":
            done, total = self.progress
            ring = rect.adjusted(5, 5, -5, -5)
            p.setPen(QPen(QColor(255, 255, 255, 70), 5, Qt.SolidLine, Qt.RoundCap))
            p.drawEllipse(ring)
            p.setPen(QPen(QColor(style.accent()), 5, Qt.SolidLine, Qt.RoundCap))
            if total > 1 or self.frac > 0:
                span = max(0.04, (done + self.frac) / max(total, 1))
                p.drawArc(ring, 90 * 16, int(-360 * 16 * span))
            else:
                p.drawArc(ring, int(-self.spin * 16), 100 * 16)
            if self.frac > 0:  # pourcentage au centre (conversions longues : vidéos)
                f = QFont(p.font())
                f.setFamilies(["SF Pro Display", "Segoe UI Variable Display", "Segoe UI"])
                f.setBold(True)
                f.setPixelSize(13)
                p.setFont(f)
                p.setPen(QColor(29, 29, 31) if light else QColor("white"))
                pct = int(100 * (done + self.frac) / max(total, 1))
                p.drawText(rect, Qt.AlignCenter, f"{pct} %")
            return

        f = QFont(p.font())
        f.setFamilies(["Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji"])
        f.setPixelSize(28)
        p.setFont(f)
        p.setPen(QColor(29, 29, 31) if light else QColor("white"))
        p.drawText(rect, Qt.AlignCenter, _kind(self.files) if self.files else "✨")
        if len(self.files) > 1:  # pastille avec le nombre de fichiers
            badge = QRectF(rect.right() - 22, rect.top() - 4, 26, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(style.accent()))
            p.drawRoundedRect(badge, 11, 11)
            fb = QFont(p.font())
            fb.setFamilies(["SF Pro Display", "Segoe UI Variable Display", "Segoe UI"])
            fb.setBold(True)
            fb.setPixelSize(12)
            p.setFont(fb)
            p.setPen(QColor("white"))
            p.drawText(badge, Qt.AlignCenter, str(len(self.files)) if len(self.files) < 100 else "99+")

    def _glass_edge(self, p: QPainter, path: QPainterPath, rect: QRectF) -> None:
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        g.setColorAt(0, QColor(255, 255, 255, 120))
        g.setColorAt(0.5, QColor(255, 255, 255, 0))
        p.fillPath(path, g)
        p.setPen(QPen(QColor(255, 255, 255, 200), 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def _pill_text(self) -> str:
        if self.state == "choose":
            if self.hover is not None and self.hover < len(self.bubbles):
                b = self.bubbles[self.hover]
                return b.hint if b.key in (MERGE, MORE) else f"{b.text} · {b.hint}"
            if self.message:
                return self.message
            if not self.files:
                return "Aucun fichier sélectionné"
            if len(self.files) == 1:
                return self.files[0].name
            return f"{len(self.files)} fichiers · choisis un format"
        return self.status

    def _draw_pill(self, p: QPainter) -> None:
        text = self._pill_text()
        if not text:
            return
        f = QFont(p.font())
        f.setFamilies(["SF Pro Display", "Segoe UI Variable Display", "Segoe UI"])
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        max_w = W - 80
        text = fm.elidedText(text, Qt.ElideMiddle, max_w * 3) if len(text) > 400 else text
        br = fm.boundingRect(0, 0, max_w, 200, Qt.AlignCenter | Qt.TextWordWrap, text)
        pw, ph = br.width() + 32, br.height() + 16
        y = self.hub.y() + HUB_R + 16 if self.up else self.hub.y() - HUB_R - 16 - ph
        rect = QRectF(min(max(self.hub.x() - pw / 2, 8), W - pw - 8), y, pw, ph)
        path = _rounded(rect, min(ph / 2, 18))
        light = self._glass(p, path, rect)
        p.setFont(f)
        p.setPen(QColor(29, 29, 31) if light else QColor("white"))
        p.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, text)

    # ------------------------------------------------------------------ interaction
    def _hit(self, pos: QPointF) -> int | None:
        for i in reversed(self._visible()):
            c, s = self._current(self.bubbles[i])
            if s > 0.5 and (pos - c).manhattanLength() < BUBBLE_R * 1.5 and \
                    math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= BUBBLE_R * 1.08:
                return i
        return None

    def _on_hub(self, pos: QPointF) -> bool:
        return math.hypot(pos.x() - self.hub.x(), pos.y() - self.hub.y()) <= HUB_R

    def mouseMoveEvent(self, e):
        h = self._hit(e.position())
        if h != self.hover:
            self.hover = h
            self.update()
        clickable = h is not None or (self.state == "done" and self._on_hub(e.position()))
        self.setCursor(Qt.PointingHandCursor if clickable else Qt.ArrowCursor)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        h = self._hit(e.position())
        if h is not None:
            self._choose(self.bubbles[h])
        elif self._on_hub(e.position()):
            if self.state == "done":
                self._open_folder()
                self.close()
        elif self.state != "working":
            self.close()  # clic à côté : on referme

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            self._cancel() if self.worker else self.close()
        elif self.state == "choose" and k in (Qt.Key_Return, Qt.Key_Enter):
            vis = self._visible()
            if vis:
                self._choose(self.bubbles[self.hover if self.hover is not None else vis[0]])
        elif self.state == "choose" and Qt.Key_1 <= k <= Qt.Key_9:
            vis = self._visible()
            i = k - Qt.Key_1
            if i < len(vis):
                self._choose(self.bubbles[vis[i]])
        else:
            super().keyPressEvent(e)

    def enterEvent(self, e):  # la souris sur l'éventail → on ne le ferme pas tout seul
        if self.state in ("choose", "done") and self.files:
            self.auto_close.stop()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if self.hover is not None:
            self.hover = None
            self.update()
        # la souris s'en va : on referme (filet de sécurité si l'éventail n'a jamais eu le focus, ex. Mac)
        if self.state == "done":
            self.auto_close.start(1200)
        elif self.state == "choose" and self.files:
            self.auto_close.start(2500)
        super().leaveEvent(e)

    def changeEvent(self, e):
        # l'utilisateur clique ailleurs : l'éventail se referme (sauf pendant une conversion)
        if e.type() == e.Type.ActivationChange and not self.isActiveWindow() and self.state == "choose":
            QTimer.singleShot(0, self.close)
        super().changeEvent(e)

    def _choose(self, b: Bubble) -> None:
        if b.key == MORE:
            if (self.t_outer.currentValue() or 0.0) > 0.5:
                self.t_outer.setDirection(QVariantAnimation.Backward)
            else:
                self.t_outer.setDirection(QVariantAnimation.Forward)
            self.t_outer.start()
            return
        self.start(b.key)

    # ------------------------------------------------------------------ conversion
    def start(self, key: str) -> None:
        if not self.files or self.worker:
            return
        merge = key == MERGE
        files = engine.mergeable(self.files) if merge else list(self.files)
        s = self.settings
        s.remember_target("pdf" if merge else key)
        s.save()
        opts = ConvertOptions(quality=s.quality, keep_metadata=s.keep_metadata,
                              subfolder=s.subfolder_name if s.output_mode == "subfolder" else None)
        self.state = "working"
        self.hover = None
        self.status = "Fusion en un seul PDF…" if merge else f"Conversion en {key.upper()}…"
        self.setCursor(Qt.ArrowCursor)
        self.spin_timer.start()
        self.worker = ConvertWorker(files, "pdf" if merge else key, opts, merge)
        self.worker.progress.connect(self._on_progress)
        self.worker.fraction.connect(self._on_fraction)
        self.worker.done.connect(self._on_done)
        self.worker.start()
        self.update()

    def _tick(self) -> None:
        self.spin = (self.spin + 7) % 360
        self.update()

    def _on_fraction(self, f: float) -> None:
        self.frac = f
        self.update()

    def _on_progress(self, i: int, total: int, name: str) -> None:
        self.progress = (i, total)
        self.frac = 0.0
        base = self.status.split("…")[0]
        self.status = f"{base}… {i + 1}/{total}" if total > 1 else f"{base}…"
        self.update()

    def _cancel(self) -> None:
        if self.worker:
            self.status = "Annulation…"
            self.worker.cancel()
            self.update()

    def _on_done(self, produced: list, errors: list, cancelled: bool) -> None:
        self.worker.wait()
        self.worker = None
        self.spin_timer.stop()
        if self._close_when_done:
            self.close()
            return
        self.produced = [Path(p) for p in produced]
        n = len(self.produced)
        plural = "s" if n > 1 else ""
        if cancelled:
            self.state, self.status = "error", "Conversion annulée"
        elif errors:
            self.state = "error"
            head = f"{n} fichier{plural} converti{plural}, " if n else ""
            more = f" (+{len(errors) - 1} autre{'s' if len(errors) > 2 else ''})" if len(errors) > 1 else ""
            self.status = f"{head}{errors[0]}{more}"
        else:
            self.state = "done"
            self.status = f"{n} fichier{plural} converti{plural} · clique ✓ pour ouvrir"
        if self.produced:
            self.finished_ok.emit(self.produced)
            if self.settings.open_folder_after:
                self._open_folder()
        self.auto_close.start(1800 if self.state == "done" else 7000)
        self.update()

    def _open_folder(self) -> None:
        from ..platform_integration import open_folder
        if self.produced:
            open_folder(self.produced[0].parent, select=self.produced[0])

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            # une conversion Office/ffmpeg peut mettre du temps à s'arrêter : on masque l'éventail
            # et on le détruira à la fin du thread (détruire un QThread actif ferait planter l'app)
            self.worker.cancel()
            self._close_when_done = True
            self.hide()
            e.ignore()
            return
        super().closeEvent(e)


def _rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def _force_foreground(hwnd: int) -> None:
    """Met la fenêtre au premier plan. Après un raccourci global, Windows l'autorise directement ;
    sinon on utilise l'astuce classique de la touche Alt."""
    try:
        import ctypes
        u = ctypes.windll.user32
        if not u.SetForegroundWindow(hwnd):
            u.keybd_event(0x12, 0, 0, 0)
            u.keybd_event(0x12, 0, 2, 0)
            u.SetForegroundWindow(hwnd)
    except Exception:
        pass
