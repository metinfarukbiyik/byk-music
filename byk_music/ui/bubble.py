"""YouTube'da video algılandığında ekranın sağ kenarında beliren indirme balonu."""
from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .icons import icon, pixmap, set_icon
from .styles import app_icon

VISIBLE_MS = 12000


class DetectBubble(QWidget):
    download = Signal(dict, str)   # öğe, biçim
    open_list = Signal(dict)

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(380)
        self.item = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        box = QFrame()
        box.setObjectName("bubble")
        outer.addWidget(box)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 14, 12, 14)
        lay.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(36, 36))
        texts = QVBoxLayout()
        texts.setSpacing(2)
        src = QHBoxLayout()
        src.setSpacing(5)
        yt = QLabel()
        yt.setPixmap(pixmap("youtube", 14, "#FF0000"))
        self.caption = QLabel("YouTube'da algılandı")
        self.caption.setObjectName("small")
        src.addWidget(yt)
        src.addWidget(self.caption)
        src.addStretch()
        self.title = QLabel()
        self.title.setObjectName("bubbleTitle")
        self.title.setWordWrap(True)
        self.title.setMaximumHeight(40)
        texts.addLayout(src)
        texts.addWidget(self.title)
        close = QPushButton()
        close.setObjectName("toastClose")
        close.setIcon(icon("close", "#98A2B3"))
        close.setFixedSize(22, 22)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.dismiss)
        head.addWidget(logo, 0, Qt.AlignTop)
        head.addLayout(texts, 1)
        head.addWidget(close, 0, Qt.AlignTop)
        lay.addLayout(head)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.mp3 = QPushButton("MP3 indir")
        self.mp4 = QPushButton("MP4 indir")
        self.list_btn = QPushButton("Listeyi aç")
        self.list_btn.setObjectName("primary")
        set_icon(self.list_btn, "playlist-play", "#FFFFFF")
        for b in (self.mp3, self.mp4, self.list_btn):
            b.setCursor(Qt.PointingHandCursor)
            btns.addWidget(b, 1)
        self.mp3.clicked.connect(lambda: self._choose("mp3"))
        self.mp4.clicked.connect(lambda: self._choose("mp4"))
        self.list_btn.clicked.connect(self._open_list)
        lay.addLayout(btns)

        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self.dismiss)
        self._anim = None

    def show_item(self, item: dict, default_fmt: str):
        self.item = item
        playlist = item["kind"] == "playlist"
        self.caption.setText("YouTube'da oynatma listesi algılandı" if playlist else "YouTube'da algılandı")
        self.title.setText(item["title"] or item["url"])
        self.title.setToolTip(item["url"])
        self.mp3.setVisible(not playlist)
        self.mp4.setVisible(not playlist)
        self.list_btn.setVisible(playlist)
        for b, fmt, name in ((self.mp3, "mp3", "music-note"), (self.mp4, "mp4", "video-outline")):
            primary = fmt == default_fmt
            b.setObjectName("primary" if primary else "")
            set_icon(b, name, "#FFFFFF" if primary else "#344054")
            b.style().unpolish(b)
            b.style().polish(b)
        self.adjustSize()

        geo = QGuiApplication.primaryScreen().availableGeometry()
        target = QPoint(geo.right() - self.width() - 12, geo.top() + int(geo.height() * 0.62) - self.height() // 2)
        start = target + QPoint(60, 0) if not self.isVisible() else self.pos()
        self.move(start)
        self.setWindowOpacity(0.0 if not self.isVisible() else self.windowOpacity())
        self.show()
        self.raise_()
        self._animate(target, 1.0)
        self._timer.start(VISIBLE_MS)

    def _animate(self, pos: QPoint, opacity: float, on_done=None):
        slide = QPropertyAnimation(self, b"pos", self)
        slide.setDuration(320)
        slide.setEndValue(pos)
        slide.setEasingCurve(QEasingCurve.OutCubic)
        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(260)
        fade.setEndValue(opacity)
        if on_done:
            fade.finished.connect(on_done)
        slide.start()
        fade.start()
        self._anim = (slide, fade)

    def dismiss(self):
        if self.isVisible():
            self._timer.stop()
            self._animate(self.pos() + QPoint(60, 0), 0.0, self.hide)

    def enterEvent(self, event):
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._timer.start(5000)
        super().leaveEvent(event)

    def _choose(self, fmt: str):
        if self.item:
            self.download.emit(self.item, fmt)
        self.dismiss()

    def _open_list(self):
        if self.item:
            self.open_list.emit(self.item)
        self.dismiss()
