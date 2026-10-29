"""Uygulama genelinde kullanılan ikon paketi (QtAwesome · Material Design Icons)."""
from functools import lru_cache

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap

from .styles import MUTED

try:
    import qtawesome as qta
except ImportError:  # paket yoksa ikonsuz çalış
    qta = None


@lru_cache(maxsize=256)
def icon(name: str, color: str = MUTED, active: str | None = None) -> QIcon:
    if qta is None:
        return QIcon()
    opts = {"color": color}
    if active:
        opts["color_active"] = active
    try:
        return qta.icon(f"mdi6.{name}", **opts)
    except Exception:
        return QIcon()


def pixmap(name: str, size: int = 18, color: str = MUTED) -> QPixmap:
    return icon(name, color).pixmap(QSize(size, size))


def set_icon(button, name: str, color: str = "#344054", size: int = 16):
    button.setIcon(icon(name, color))
    button.setIconSize(QSize(size, size))
