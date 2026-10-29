"""Pencerenin sağ üstünde kayarak beliren bildirim kartları."""
from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPoint,
                            QPropertyAnimation, Qt, QTimer, Signal)
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout, QWidget)

from .icons import icon as icon_for, pixmap
from .styles import ACCENT, ERROR, MUTED, SUCCESS, WARNING

KINDS = {
    "info": (ACCENT, "information-outline"),
    "success": (SUCCESS, "check"),
    "warning": (WARNING, "alert-outline"),
    "error": (ERROR, "close"),
    "neutral": (MUTED, "information-outline"),
}
MARGIN = 10  # kartlar arası boşluk


class Toast(QWidget):
    close_requested = Signal(object)

    def __init__(self, parent, title, text, kind, action):
        super().__init__(parent)
        self.closing = False
        color, glyph = KINDS.get(kind, KINDS["info"])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        box = QFrame()
        box.setObjectName("toast")
        outer.addWidget(box)

        row = QHBoxLayout(box)
        row.setContentsMargins(14, 12, 10, 12)
        row.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(pixmap(glyph, 16, "#FFFFFF"))
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"background:{color}; border-radius:13px;")
        row.addWidget(icon, 0, Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("toastTitle")
        col.addWidget(t)
        if text:
            m = QLabel(text)
            m.setObjectName("muted")
            m.setWordWrap(True)
            col.addWidget(m)
        if action:
            b = QPushButton(action[0])
            b.setObjectName("link")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(action[1])
            b.clicked.connect(lambda: self.close_requested.emit(self))
            col.addWidget(b, 0, Qt.AlignLeft)
        row.addLayout(col, 1)

        close = QPushButton()
        close.setIcon(icon_for("close", "#98A2B3"))
        close.setObjectName("toastClose")
        close.setFixedSize(20, 20)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(lambda: self.close_requested.emit(self))
        row.addWidget(close, 0, Qt.AlignTop)

        self.setFixedWidth(360 + 2 * MARGIN)
        self.opacity = QGraphicsOpacityEffect(self)
        self.opacity.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity)


class ToastManager(QObject):
    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.items: list[Toast] = []
        self._anims = {}
        host.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.host and event.type() == QEvent.Resize:
            self._relayout(animate=False)
        return False

    def show(self, title: str, text: str = "", kind: str = "info", action=None, duration: int = 4500):
        toast = Toast(self.host, title, text, kind, action)
        toast.close_requested.connect(self.dismiss)
        toast.adjustSize()
        self.items.insert(0, toast)
        target = self._positions()[0]
        toast.move(target + QPoint(60, 0))
        toast.show()
        toast.raise_()

        slide = QPropertyAnimation(toast, b"pos", toast)
        slide.setDuration(380)
        slide.setEndValue(target)
        slide.setEasingCurve(QEasingCurve.OutCubic)
        slide.start()
        self._anims[toast] = slide
        fade = QPropertyAnimation(toast.opacity, b"opacity", toast)
        fade.setDuration(300)
        fade.setEndValue(1.0)
        fade.start()
        self._relayout(animate=True, skip=toast)

        for old in self.items[4:]:
            self.dismiss(old)
        QTimer.singleShot(duration, lambda: self.dismiss(toast))

    def dismiss(self, toast: Toast):
        if toast not in self.items or toast.closing:
            return
        toast.closing = True
        fade = QPropertyAnimation(toast.opacity, b"opacity", toast)
        fade.setDuration(220)
        fade.setEndValue(0.0)
        fade.finished.connect(lambda: self._remove(toast))
        fade.start()

    def _remove(self, toast: Toast):
        if toast in self.items:
            self.items.remove(toast)
        self._anims.pop(toast, None)
        toast.deleteLater()
        self._relayout(animate=True)

    def _positions(self) -> list[QPoint]:
        pts, y = [], 8
        for t in self.items:
            pts.append(QPoint(self.host.width() - t.width() - 8, y))
            y += t.height() - MARGIN
        return pts

    def _relayout(self, animate: bool, skip=None):
        for t, pos in zip(self.items, self._positions()):
            if t is skip:
                continue
            t.raise_()
            running = self._anims.get(t)
            if running:
                running.stop()  # giriş kayması yeni konumla çakışmasın
            if not animate:
                t.move(pos)
                continue
            anim = QPropertyAnimation(t, b"pos", t)
            anim.setDuration(260)
            anim.setEndValue(pos)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            self._anims[t] = anim
