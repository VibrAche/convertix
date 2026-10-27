"""Feuille de style Qt « liquid glass » (clair / sombre selon le système)."""
from __future__ import annotations

FONT = '"SF Pro Display", "Segoe UI Variable Display", "Segoe UI", sans-serif'
# couleurs d'accent proposées dans les Réglages (nom affiché → couleur)
ACCENTS = {"Bleu": "#0A84FF", "Violet": "#8B5CF6", "Rose": "#FF2D78", "Orange": "#FF9500",
           "Vert": "#30C15B", "Menthe": "#00C7BE", "Graphite": "#8E8E93"}

_theme = "auto"
_accent = ACCENTS["Bleu"]


def configure(theme: str, accent: str) -> None:
    global _theme, _accent
    _theme, _accent = theme, accent


def accent() -> str:
    return _accent


def stylesheet(dark: bool) -> str:
    from PySide6.QtGui import QColor
    ACCENT = _accent
    ACCENT_HOVER = QColor(ACCENT).darker(112).name()
    light_accent = QColor(ACCENT).lighter(125).name()
    bg = "#1C1C22" if dark else "#F5F6FA"     # fenêtres classiques (Paramètres)
    text = "#F5F5F7" if dark else "#1D1D1F"
    muted = "rgba(235,235,245,0.6)" if dark else "rgba(60,60,67,0.62)"
    # verre : dégradé vertical (reflet en haut) + liseré clair
    glass_top = "rgba(255,255,255,0.16)" if dark else "rgba(255,255,255,0.92)"
    glass_bot = "rgba(255,255,255,0.06)" if dark else "rgba(255,255,255,0.55)"
    glass_hover_top = "rgba(255,255,255,0.26)" if dark else "rgba(255,255,255,1)"
    glass_hover_bot = "rgba(255,255,255,0.12)" if dark else "rgba(255,255,255,0.80)"
    edge = "rgba(255,255,255,0.22)" if dark else "rgba(255,255,255,0.95)"
    edge_low = "rgba(255,255,255,0.06)" if dark else "rgba(0,0,0,0.07)"
    field = "rgba(255,255,255,0.08)" if dark else "rgba(255,255,255,0.65)"
    glass = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {glass_top}, stop:1 {glass_bot})"
    glass_hover = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {glass_hover_top}, stop:1 {glass_hover_bot})"
    primary = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {light_accent}, stop:1 {ACCENT})"
    return f"""
    QWidget {{ font-family: {FONT}; font-size: 13px; color: {text}; }}
    QWidget#Root {{ background: {bg}; }}
    QWidget#Glass, QStackedWidget, QStackedWidget > QWidget, QScrollArea, QScrollArea > QWidget > QWidget
        {{ background: transparent; }}
    QLabel {{ background: transparent; }}
    QLabel#Title {{ font-size: 24px; font-weight: 700; }}
    QLabel#Muted, QLabel#GroupTitle {{ color: {muted}; }}
    QLabel#GroupTitle {{ font-size: 11px; font-weight: 600; letter-spacing: 1.2px; margin: 8px 0 2px 4px; }}
    QLabel#Big {{ font-size: 46px; color: {text}; }}
    QLabel#Check {{ font-size: 34px; font-weight: 700; color: white; border-radius: 36px;
                    min-width: 72px; max-width: 72px; min-height: 72px; max-height: 72px;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4ADE80, stop:1 #22C55E); }}
    QLabel#Check[fail="true"] {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FDBA74, stop:1 #F97316); }}

    QFrame#Card, QLabel#DropZone {{ background: {glass}; border: 1px solid {edge};
                    border-bottom-color: {edge_low}; border-radius: 20px; }}
    QLabel#DropZone {{ color: {muted}; font-size: 15px; padding: 30px; }}
    QLabel#DropZone[hover="true"] {{ border: 2px solid {ACCENT}; }}

    QPushButton {{ background: {glass}; border: 1px solid {edge}; border-bottom-color: {edge_low};
                   border-radius: 17px; padding: 8px 18px; min-height: 18px; font-weight: 600; }}
    QPushButton:hover {{ background: {glass_hover}; }}
    QPushButton:pressed {{ background: {glass_bot}; }}
    QPushButton:disabled {{ color: {muted}; }}
    QPushButton#Primary {{ background: {primary}; color: white; border: 1px solid rgba(255,255,255,0.35); }}
    QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
    QPushButton#Round {{ border-radius: 16px; padding: 0; min-width: 32px; max-width: 32px;
                         min-height: 32px; max-height: 32px; font-size: 15px; }}
    QPushButton#Link {{ border: none; background: transparent; color: {ACCENT}; padding: 4px 6px; }}
    QPushButton#Link:hover {{ text-decoration: underline; }}
    QPushButton#Seg {{ border-radius: 0; padding: 6px 16px; font-weight: 600; }}
    QPushButton#Seg[pos="first"] {{ border-top-left-radius: 15px; border-bottom-left-radius: 15px; }}
    QPushButton#Seg[pos="last"] {{ border-top-right-radius: 15px; border-bottom-right-radius: 15px; }}
    QPushButton#Seg:checked {{ background: {primary}; color: white; }}
    QKeySequenceEdit QLineEdit {{ padding: 6px 14px; }}

    QLineEdit {{ background: {field}; border: 1px solid {edge}; border-radius: 17px;
                 padding: 8px 16px; font-size: 14px; }}
    QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
    QComboBox {{ background: {field}; border: 1px solid {edge}; border-radius: 12px; padding: 5px 12px; }}
    QComboBox::drop-down {{ border: none; width: 0; }}
    QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
    QComboBox QAbstractItemView {{ background: {bg}; border-radius: 8px; selection-background-color: {ACCENT}; }}
    QCheckBox {{ background: transparent; spacing: 10px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 10px; background: {field};
                            border: 1px solid {"rgba(255,255,255,0.3)" if dark else "rgba(0,0,0,0.18)"}; }}
    QCheckBox::indicator:checked {{ background: {primary}; border: 4px solid {field}; }}
    QProgressBar {{ background: {field}; border: 1px solid {edge}; border-radius: 7px;
                    min-height: 12px; max-height: 12px; }}
    QProgressBar::chunk {{ background: {primary}; border-radius: 6px; }}
    QPlainTextEdit, QListWidget {{ background: {field}; border: 1px solid {edge}; border-radius: 14px; padding: 6px; }}
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {muted}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page
        {{ background: none; height: 0; }}
    QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {field}; }}
    QSlider::sub-page:horizontal {{ border-radius: 2px; background: {ACCENT}; }}
    QSlider::handle:horizontal {{ background: white; border: 1px solid rgba(0,0,0,0.12);
                                  width: 20px; height: 20px; margin: -8px 0; border-radius: 10px; }}
    QToolTip {{ background: {bg}; color: {text}; border: 1px solid {edge_low}; border-radius: 6px; padding: 4px 8px; }}
    """


def is_dark() -> bool:
    if _theme in ("light", "dark"):
        return _theme == "dark"
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False
