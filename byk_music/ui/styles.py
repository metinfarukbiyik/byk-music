from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPalette, QPen, QPixmap

ACCENT = "#1F4FD8"
ACCENT_HOVER = "#1A43B8"
ACCENT_SOFT = "#E8EEFC"
BG = "#F4F6FA"
SURFACE = "#FFFFFF"
BORDER = "#E3E8EF"
TEXT = "#0F172A"
MUTED = "#64748B"
SIDEBAR = "#0F1B2D"
SIDEBAR_HOVER = "#1A2940"
SIDEBAR_ACTIVE = "#1C3263"
SIDEBAR_TEXT = "#A9B4C6"
SUCCESS = "#12B76A"
WARNING = "#F79009"
ERROR = "#F04438"

# rozet türü: (yazı, zemin)
BADGES = {
    "neutral": ("#475467", "#EEF1F5"),
    "info": ("#1F4FD8", "#E8EEFC"),
    "processing": ("#B54708", "#FEF0C7"),
    "success": ("#067647", "#DCFAE6"),
    "error": ("#B42318", "#FEE4E2"),
    "violet": ("#5925DC", "#EBE9FE"),
}


def _icon_png(path: Path, draw) -> str:
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw(p)
    p.end()
    pm.save(str(path))
    return path.as_posix()


def _assets(asset_dir: Path) -> dict:
    asset_dir.mkdir(parents=True, exist_ok=True)

    def chevron(p):
        p.setPen(QPen(QColor(MUTED), 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(9, 12), QPointF(16, 19), QPointF(23, 12)])

    def check(p):
        p.setPen(QPen(QColor("white"), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(8, 16.5), QPointF(13.5, 22), QPointF(24, 10)])

    return {"chevron": _icon_png(asset_dir / "chevron.png", chevron),
            "check": _icon_png(asset_dir / "check.png", check)}


def build_qss(asset_dir: Path) -> str:
    a = _assets(asset_dir)
    badges = "\n".join(
        f'QLabel#badge[kind="{k}"] {{ color: {fg}; background: {bg}; }}' for k, (fg, bg) in BADGES.items())
    return f"""
QWidget {{ color: {TEXT}; font-size: 13px; }}
QMainWindow, QDialog, QWidget#content, QWidget#page {{ background: {BG}; }}

/* kenar çubuğu */
QWidget#sidebar {{ background: {SIDEBAR}; }}
QLabel#brand {{ color: white; font-size: 15px; font-weight: 700; }}
QLabel#brandSub, QLabel#sideSection {{ color: #6B7A93; font-size: 11px; }}
QLabel#sideSection {{ font-weight: 700; }}
QPushButton#nav {{ background: transparent; border: none; border-radius: 8px; }}
QPushButton#nav:hover {{ background: {SIDEBAR_HOVER}; }}
QPushButton#nav:checked {{ background: {SIDEBAR_ACTIVE}; }}
QLabel#navText, QLabel#navIcon {{ color: {SIDEBAR_TEXT}; background: transparent; }}
QLabel#navText[active="true"], QLabel#navIcon[active="true"] {{ color: white; font-weight: 600; }}
QLabel#navIcon {{ font-size: 15px; }}
QLabel#navBadge {{ background: {ACCENT}; color: white; border-radius: 9px; padding: 0 6px;
                   min-width: 6px; min-height: 18px; max-height: 18px; font-size: 11px; font-weight: 700; }}
QLabel#navBadge[kind="success"] {{ background: {SUCCESS}; }}

/* üst çubuk */
QFrame#topbar {{ background: {SURFACE}; border: none; border-bottom: 1px solid {BORDER}; }}
QLabel#fieldLabel {{ color: {MUTED}; font-size: 10px; font-weight: 700; }}

/* tipografi */
QLabel#h1 {{ font-size: 20px; font-weight: 700; }}
QLabel#h2 {{ font-size: 14px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#small {{ color: {MUTED}; font-size: 11px; }}
QLabel#emptyIcon {{ background: {ACCENT_SOFT}; color: {ACCENT}; border-radius: 28px; font-size: 24px; font-weight: 700; }}

QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QScrollArea#pageScroll {{ background: {BG}; border: none; }}
QScrollArea#pageScroll > QWidget > QWidget#page {{ background: {BG}; }}
QPushButton#contactCard {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; padding: 0; }}
QPushButton#contactCard:hover {{ border-color: {ACCENT}; background: #FAFBFF; }}
QLabel#cardValue {{ font-size: 14px; font-weight: 700; color: {TEXT}; }}
QFrame#devHero {{ border: none; border-radius: 14px;
                  background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0F1B2D, stop:1 #1B2F55); }}
QFrame#devHero QLabel {{ color: white; background: transparent; }}
QLabel#heroName {{ font-size: 22px; font-weight: 800; }}
QFrame#devHero QLabel#heroSub {{ color: {SIDEBAR_TEXT}; font-size: 13px; }}
QFrame#devHero QLabel#heroAvatar {{ background: {ACCENT}; color: white; border: 3px solid #3B5EA8; border-radius: 38px;
                     font-size: 26px; font-weight: 800; }}
QFrame#devHero QLabel#heroChipNew {{ background: {SUCCESS}; color: white; border-radius: 10px; padding: 3px 10px;
                                     font-size: 11px; font-weight: 800; }}
QFrame#devHero QLabel#heroChip {{ background: rgba(255, 255, 255, 34); color: #DCE6FF; border-radius: 10px; padding: 3px 10px;
                   font-size: 11px; font-weight: 700; }}
QFrame#loadingHead {{ background: transparent; border: none; border-bottom: 1px solid {BORDER}; }}
QFrame#bubble {{ background: {SURFACE}; border: 1px solid #D0D5DD; border-radius: 14px; }}
QLabel#bubbleTitle {{ font-size: 14px; font-weight: 700; }}

/* düğmeler */
QPushButton {{ background: {SURFACE}; border: 1px solid #D0D5DD; border-radius: 8px; padding: 7px 14px;
               font-weight: 600; color: #344054; }}
QPushButton:hover {{ background: #F9FAFB; border-color: #98A2B3; }}
QPushButton:disabled {{ color: #98A2B3; background: #F2F4F7; border-color: #E4E7EC; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: white; padding: 8px 18px; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: #A4BCFD; border-color: #A4BCFD; color: white; }}
QPushButton#iconBtn {{ padding: 6px; min-width: 22px; }}
QPushButton#danger {{ color: #B42318; border-color: #FDA29B; }}
QPushButton#danger:hover {{ background: #FEF3F2; }}
QPushButton#whatsapp {{ background: #25D366; border-color: #25D366; color: white; padding: 8px 18px; }}
QPushButton#whatsapp:hover {{ background: #1EBE5A; }}
QPushButton#whatsapp:disabled {{ background: #A6E9C0; border-color: #A6E9C0; color: white; }}
QLabel#avatar {{ background: {ACCENT}; color: white; border-radius: 32px; font-size: 22px; font-weight: 700; }}
QPlainTextEdit#messageEdit {{ border: 1px solid #D0D5DD; border-radius: 8px; padding: 8px; font-size: 13px; }}
QPlainTextEdit#messageEdit:focus {{ border-color: {ACCENT}; }}
QPushButton#link {{ background: transparent; border: none; color: {ACCENT}; padding: 2px 4px; }}
QPushButton#link:hover {{ color: {ACCENT_HOVER}; text-decoration: underline; }}
QPushButton#link:disabled {{ color: #98A2B3; }}

/* segment (MP3 / MP4) */
QFrame#segment {{ background: #F2F4F7; border: 1px solid {BORDER}; border-radius: 8px; }}
QPushButton#segBtn {{ background: transparent; border: 1px solid transparent; border-radius: 6px;
                      padding: 5px 20px; color: {MUTED}; font-weight: 700; }}
QPushButton#segBtn:hover {{ color: {TEXT}; }}
QPushButton#segBtn:checked {{ background: {SURFACE}; color: {ACCENT}; border-color: {BORDER}; }}
QPushButton#segBtn:disabled {{ color: #98A2B3; }}

/* girişler */
QLineEdit, QComboBox {{ background: {SURFACE}; border: 1px solid #D0D5DD; border-radius: 8px;
                        padding: 6px 10px; min-height: 20px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:read-only {{ background: #F9FAFB; color: #475467; }}
QLineEdit#bigInput {{ padding: 9px 12px; font-size: 14px; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({a['chevron']}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER}; outline: 0; padding: 4px;
                               selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; }}

/* tablo */
QTableWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; gridline-color: transparent;
                alternate-background-color: #FAFBFC; selection-background-color: #F2F6FF; selection-color: {TEXT}; outline: 0; }}
QTableWidget::item {{ border-bottom: 1px solid #F0F2F5; padding-left: 4px; }}
QHeaderView::section {{ background: #F9FAFB; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
                        padding: 8px 6px; font-size: 11px; font-weight: 700; }}
QTableCornerButton::section {{ background: #F9FAFB; border: none; }}

QCheckBox {{ spacing: 10px; }}
QTableView::indicator, QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid #D0D5DD;
                                               border-radius: 4px; background: white; }}
QTableView::indicator:checked, QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT};
                                                               image: url({a['check']}); }}

/* ilerleme */
QProgressBar {{ background: #EAECF0; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QProgressBar[kind="success"]::chunk {{ background: {SUCCESS}; }}
QProgressBar[kind="error"]::chunk {{ background: {ERROR}; }}
QProgressBar[kind="processing"]::chunk {{ background: {WARNING}; }}

/* rozetler */
QLabel#badge {{ border-radius: 10px; padding: 2px 10px; font-size: 11px; font-weight: 700; }}
{badges}

/* bildirim kartı */
QFrame#toast {{ background: {SURFACE}; border: 1px solid #D0D5DD; border-radius: 10px; }}
QLabel#toastTitle {{ font-weight: 700; }}
QPushButton#toastClose {{ background: transparent; border: none; color: #98A2B3; padding: 0; font-size: 12px; }}
QPushButton#toastClose:hover {{ color: {TEXT}; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; background: {SURFACE}; border-radius: 10px; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 16px; font-weight: 600;
                border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom-color: {ACCENT}; }}
QTextBrowser#releaseNotes {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 10px 12px; }}
QPlainTextEdit#logView, QTextBrowser#sysInfo {{ background: {SURFACE}; border: none; font-family: Menlo, Consolas, monospace;
                                font-size: 12px; padding: 6px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #D0D5DD; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #D0D5DD; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0; background: none; }}
QToolTip {{ background: {TEXT}; color: white; border: none; padding: 6px 8px; }}
"""


def light_palette() -> QPalette:
    pal = QPalette()
    for role, color in ((QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, SURFACE),
                        (QPalette.AlternateBase, "#FAFBFC"), (QPalette.Text, TEXT), (QPalette.Button, SURFACE),
                        (QPalette.ButtonText, TEXT), (QPalette.Highlight, ACCENT),
                        (QPalette.HighlightedText, "#FFFFFF"), (QPalette.ToolTipBase, TEXT),
                        (QPalette.ToolTipText, "#FFFFFF"), (QPalette.PlaceholderText, "#98A2B3"),
                        (QPalette.Link, ACCENT)):
        pal.setColor(role, QColor(color))
    return pal


def app_icon(size: int = 256) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(QPointF(0, 0), QPointF(size, size))
    g.setColorAt(0, QColor("#3B6CF0"))
    g.setColorAt(1, QColor(ACCENT))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
    p.setPen(QColor("white"))
    f = QFont()
    f.setPixelSize(int(size * 0.58))
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "♫")
    p.end()
    return QIcon(pm)
