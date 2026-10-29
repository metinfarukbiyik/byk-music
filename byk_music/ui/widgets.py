from PySide6.QtCore import QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLayout,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)


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
        super().__init__()
        self.setObjectName("nav")
        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(10)
        self.icon = QLabel(icon)
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
        for w in (self.icon, self.label):
            w.setProperty("active", on)
            repolish(w)

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
        self.icon = QLabel(icon)
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
        self.icon.setText(icon)
        self.title.setText(title)
        self.text.setText(text)
        self.busy.setVisible(busy)
