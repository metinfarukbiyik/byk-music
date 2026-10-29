from PySide6.QtCore import QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLayout,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from .icons import pixmap
from .styles import ACCENT, SIDEBAR_TEXT


def repolish(w: QWidget):
    w.style().unpolish(w)
    w.style().polish(w)


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


def field(label: str, content) -> QWidget:
    """Üst çubuktaki 'ETİKET + kontrol' grubu."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)
    lbl = QLabel(label.upper())
    lbl.setObjectName("fieldLabel")
    lay.addWidget(lbl)
    if isinstance(content, QLayout):
        lay.addLayout(content)
    else:
        lay.addWidget(content)
    return w


class Badge(QLabel):
    """Renkli durum rozeti; etkin durumlarda yumuşakça nabız atar."""

    def __init__(self, text="", kind="neutral", parent=None):
        super().__init__(parent)
        self.setObjectName("badge")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(22)
        self._anim = None
        self.set(text, kind)

    def set(self, text: str, kind: str = "neutral"):
        self.setText(text)
        if self.property("kind") != kind:
            self.setProperty("kind", kind)
            repolish(self)

    def set_pulse(self, on: bool):
        if on and self._anim is None:
            effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(1000)
            anim.setStartValue(1.0)
            anim.setKeyValueAt(0.5, 0.4)
            anim.setEndValue(1.0)
            anim.setLoopCount(-1)
            anim.start()
            self._anim = anim
        elif not on and self._anim is not None:
            self._anim.stop()
            self._anim = None
            self.setGraphicsEffect(None)


class NavButton(QPushButton):
    """Kenar çubuğu menü öğesi: simge + metin + sayaç rozeti."""

    def __init__(self, icon: str, text: str, checkable: bool = True):
        """icon: ikon paketi adı (örn. "download")."""
        super().__init__()
        self.setObjectName("nav")
        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(10)
        self.icon_name = icon
        self.icon = QLabel()
        self.icon.setObjectName("navIcon")
        self.icon.setFixedWidth(22)
        self.icon.setAlignment(Qt.AlignCenter)
        self.label = QLabel(text)
        self.label.setObjectName("navText")
        self.badge = QLabel()
        self.badge.setObjectName("navBadge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.hide()
        for w in (self.icon, self.label, self.badge):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.icon)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.badge)
        self.toggled.connect(self._sync)
        self._sync(False)

    def _sync(self, on: bool):
        self.icon.setPixmap(pixmap(self.icon_name, 18, "#FFFFFF" if on else SIDEBAR_TEXT))
        self.label.setProperty("active", on)
        repolish(self.label)

    def set_badge(self, value=None, kind: str = "accent"):
        if not value:
            self.badge.hide()
            return
        self.badge.setText(str(value))
        self.badge.setProperty("kind", kind)
        repolish(self.badge)
        self.badge.show()


class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]]):
        super().__init__()
        self.setObjectName("segment")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        group = QButtonGroup(self)
        self.buttons = {}
        for label, key in options:
            b = QPushButton(label)
            b.setObjectName("segBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b

    def set_value(self, key: str):
        self.buttons[key].setChecked(True)


class EmptyState(QWidget):
    """Boş liste / yükleniyor görünümü."""

    def __init__(self, icon: str, title: str, text: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)
        self.icon = QLabel()
        self.icon.setPixmap(pixmap(icon, 26, ACCENT))
        self.icon.setObjectName("emptyIcon")
        self.icon.setFixedSize(56, 56)
        self.icon.setAlignment(Qt.AlignCenter)
        self.title = QLabel(title)
        self.title.setObjectName("h2")
        self.text = QLabel(text)
        self.text.setObjectName("muted")
        self.text.setWordWrap(True)
        self.text.setAlignment(Qt.AlignCenter)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.setFixedWidth(220)
        self.busy.hide()
        lay.addWidget(self.icon, 0, Qt.AlignCenter)
        lay.addWidget(self.title, 0, Qt.AlignCenter)
        lay.addWidget(self.text, 0, Qt.AlignCenter)
        lay.addSpacing(4)
        lay.addWidget(self.busy, 0, Qt.AlignCenter)

    def set(self, icon: str, title: str, text: str, busy: bool = False):
        self.icon.setPixmap(pixmap(icon, 26, ACCENT))
        self.title.setText(title)
        self.text.setText(text)
        self.busy.setVisible(busy)


class Spinner(QWidget):
    """Dönen yay şeklinde yükleme göstergesi."""

    def __init__(self, size: int = 28, color: str = ACCENT):
        super().__init__()
        self.setFixedSize(size, size)
        self._angle = 0
        self._color = QColor(color)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._timer.start(16)

    def stop(self):
        self._timer.stop()

    def _tick(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        track = QColor(self._color)
        track.setAlpha(40)
        p.setPen(QPen(track, 3))
        p.drawEllipse(r)
        p.setPen(QPen(self._color, 3, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, -self._angle * 16, 100 * 16)
        p.end()


class SkeletonRows(QWidget):
    """Tablo satırlarını taklit eden, üzerinde ışık kayan iskelet görünüm."""

    WIDTHS = (0.62, 0.48, 0.71, 0.55, 0.66, 0.43, 0.58)

    def __init__(self, rows: int = 7):
        super().__init__()
        self.rows = rows
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(rows * 50)

    def start(self):
        self._timer.start(16)

    def stop(self):
        self._timer.stop()

    def _tick(self):
        self._phase = (self._phase + 0.012) % 1.6
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        base, line = QColor("#EEF1F5"), QColor("#F0F2F5")
        shimmer_x = (self._phase - 0.3) * w
        grad = QLinearGradient(shimmer_x - 160, 0, shimmer_x + 160, 0)
        grad.setColorAt(0.0, base)
        grad.setColorAt(0.5, QColor("#F8FAFC"))
        grad.setColorAt(1.0, base)
        brush = QBrush(grad)
        row_h = 50
        for i in range(self.rows):
            y = i * row_h
            p.setPen(Qt.NoPen)
            p.setBrush(brush)
            p.drawRoundedRect(QRectF(16, y + 17, 16, 16), 4, 4)                 # onay kutusu
            p.drawRoundedRect(QRectF(52, y + 20, 18, 10), 4, 4)                 # sıra no
            title_w = (w - 560) * self.WIDTHS[i % len(self.WIDTHS)]
            p.drawRoundedRect(QRectF(92, y + 19, max(title_w, 80), 12), 6, 6)   # başlık
            p.drawRoundedRect(QRectF(w - 470, y + 19, 40, 12), 6, 6)            # süre
            p.drawRoundedRect(QRectF(w - 390, y + 15, 86, 20), 10, 10)          # rozet
            p.drawRoundedRect(QRectF(w - 250, y + 22, 220, 6), 3, 3)            # ilerleme
            p.setPen(QPen(line, 1))
            p.drawLine(0, y + row_h, w, y + row_h)
        p.end()


class LoadingView(QFrame):
    """Bağlantı çözümlenirken gösterilen düzenli yükleme kartı."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QFrame()
        head.setObjectName("loadingHead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.setSpacing(14)
        self.spinner = Spinner()
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel("Bağlantı çözümleniyor")
        self.title.setObjectName("h2")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("small")
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        hl.addWidget(self.spinner)
        hl.addLayout(texts, 1)
        lay.addWidget(head)

        self.skeleton = SkeletonRows()
        lay.addWidget(self.skeleton, 1)

    def start(self, title: str, subtitle: str):
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.spinner.start()
        self.skeleton.start()

    def stop(self):
        self.spinner.stop()
        self.skeleton.stop()


class ContactCard(QPushButton):
    """İkonlu, tıklanabilir iletişim kartı (e-posta, web sitesi, WhatsApp)."""

    def __init__(self, icon_name: str, label: str, value: str, color: str, soft: str):
        super().__init__()
        self.setObjectName("contactCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(68)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(12)
        ic = QLabel()
        ic.setFixedSize(42, 42)
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(pixmap(icon_name, 22, color))
        ic.setStyleSheet(f"background: {soft}; border-radius: 10px;")
        texts = QVBoxLayout()
        texts.setSpacing(2)
        k = QLabel(label.upper())
        k.setObjectName("fieldLabel")
        v = QLabel(value)
        v.setObjectName("cardValue")
        texts.addWidget(k)
        texts.addWidget(v)
        arrow = QLabel()
        arrow.setPixmap(pixmap("open-in-new", 16, "#98A2B3"))
        for w in (ic, k, v, arrow):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(ic)
        lay.addLayout(texts, 1)
        lay.addWidget(arrow)
