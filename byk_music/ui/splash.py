"""Açılış animasyonu: logo büyüyerek belirir, yükleme çubuğu dolar, pencere solarak kapanır."""
from PySide6.QtCore import (Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

from .. import __version__
from ..config import APP_NAME, APP_TAGLINE, DEVELOPER
from .styles import SIDEBAR_TEXT, app_icon

STEPS = [(0.0, "Başlatılıyor…"), (0.25, "Arayüz hazırlanıyor…"), (0.5, "İndirme motoru yükleniyor…"),
         (0.75, "ffmpeg denetleniyor…"), (0.97, "Hazır")]


class Splash(QWidget):
    finished = Signal()

    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(560, 340)
        self._progress = 0.0
        self._logo = 0.0
        self._status = STEPS[0][1]
        self._pix = app_icon().pixmap(192, 192)
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.move(geo.center() - self.rect().center())

    # --- animasyon özellikleri
    def _get_progress(self):
        return self._progress

    def _set_progress(self, v):
        self._progress = v
        self._status = next(text for at, text in reversed(STEPS) if v >= at)
        self.update()

    def _get_logo(self):
        return self._logo

    def _set_logo(self, v):
        self._logo = v
        self.update()

    progress = Property(float, _get_progress, _set_progress)
    logo = Property(float, _get_logo, _set_logo)

    def start(self):
        self.setWindowOpacity(0.0)
        self.show()
        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(400)
        self._fade_in.setEndValue(1.0)
        self._fade_in.start()

        self._logo_anim = QPropertyAnimation(self, b"logo", self)
        self._logo_anim.setDuration(900)
        self._logo_anim.setStartValue(0.0)
        self._logo_anim.setEndValue(1.0)
        self._logo_anim.setEasingCurve(QEasingCurve.OutBack)
        self._logo_anim.start()

        self._prog_anim = QPropertyAnimation(self, b"progress", self)
        self._prog_anim.setDuration(2200)
        self._prog_anim.setStartValue(0.0)
        self._prog_anim.setEndValue(1.0)
        self._prog_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._prog_anim.finished.connect(lambda: QTimer.singleShot(250, self._fade_out))
        QTimer.singleShot(300, self._prog_anim.start)

    def _fade_out(self):
        self._out = QPropertyAnimation(self, b"windowOpacity", self)
        self._out.setDuration(350)
        self._out.setEndValue(0.0)
        self._out.finished.connect(self._done)
        self._out.start()

    def _done(self):
        self.finished.emit()
        self.close()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(16, 16, -16, -16)

        # yumuşak gölge
        p.setPen(Qt.NoPen)
        for i in range(14, 0, -2):
            p.setBrush(QColor(0, 0, 0, 7))
            p.drawRoundedRect(r.adjusted(-i, -i + 5, i, i + 5), 18 + i, 18 + i)

        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#0F1B2D"))
        g.setColorAt(1, QColor("#1B2F55"))
        p.setBrush(g)
        p.drawRoundedRect(r, 18, 18)

        # dekoratif halkalar
        p.save()
        p.setClipRect(r)
        p.setBrush(QColor(255, 255, 255, 9))
        p.drawEllipse(QPointF(r.right() - 30, r.top() + 20), 140 + 20 * self._logo, 140 + 20 * self._logo)
        p.drawEllipse(QPointF(r.left() + 10, r.bottom() + 10), 100, 100)
        p.restore()

        # logo
        k = max(0.0, self._logo)
        alpha = min(1.0, k * 1.5)
        size = 76 * (0.55 + 0.45 * k)
        cx, cy = r.center().x(), r.top() + 92
        p.setOpacity(alpha)
        p.drawPixmap(QRectF(cx - size / 2, cy - size / 2, size, size), self._pix, QRectF(self._pix.rect()))

        # başlık ve alt başlık
        f = QFont()
        f.setPixelSize(26)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRectF(r.left(), r.top() + 142 + (1 - alpha) * 10, r.width(), 34), Qt.AlignCenter, APP_NAME)
        f.setPixelSize(13)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(SIDEBAR_TEXT))
        p.drawText(QRectF(r.left(), r.top() + 178, r.width(), 22), Qt.AlignCenter, APP_TAGLINE)
        p.setOpacity(1.0)

        # yükleme çubuğu
        w, h = 280, 4
        x, y = cx - w / 2, r.bottom() - 66
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRoundedRect(QRectF(x, y, w, h), 2, 2)
        p.setBrush(QColor("#5B8CFF"))
        p.drawRoundedRect(QRectF(x, y, w * self._progress, h), 2, 2)

        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(SIDEBAR_TEXT))
        p.drawText(QRectF(x, y + 10, w, 18), Qt.AlignCenter, self._status)

        p.setPen(QColor("#6B7A93"))
        p.drawText(r.adjusted(20, 0, -20, -14), Qt.AlignBottom | Qt.AlignLeft, f"© {DEVELOPER['name']} · {DEVELOPER['brand']}")
        p.drawText(r.adjusted(20, 0, -20, -14), Qt.AlignBottom | Qt.AlignRight, f"Sürüm {__version__}")
        p.end()
