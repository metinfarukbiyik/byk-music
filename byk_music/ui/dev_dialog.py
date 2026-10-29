import logging
import platform
import sys

import yt_dlp
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from .. import __version__
from ..config import APP_NAME, APP_TAGLINE, COPYRIGHT, DEVELOPER
from ..core.downloader import ffmpeg_path
from ..core.settings import config_dir
from .contact import whatsapp_url
from .styles import app_icon


class LogBuffer(QObject, logging.Handler):
    """Uygulama günlüğünü bellekte tutar ve geliştirici penceresine aktarır."""

    line = Signal(str)

    def __init__(self):
        QObject.__init__(self)
        logging.Handler.__init__(self)
        self.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
        self.lines: list[str] = []

    def emit(self, record):
        text = self.format(record)
        self.lines.append(text)
        del self.lines[:-2000]
        self.line.emit(text)


class DeveloperDialog(QDialog):
    def __init__(self, logbuf: LogBuffer, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Geliştirici – {APP_NAME}")
        self.setWindowIcon(app_icon())
        self.resize(640, 520)
        self.logbuf = logbuf

        tabs = QTabWidget()
        tabs.addTab(self._about_tab(), "Geliştirici")
        tabs.addTab(self._log_tab(), "Günlük")
        tabs.addTab(self._system_tab(), "Sistem")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.addWidget(tabs)

    def _about_tab(self) -> QWidget:
        d = DEVELOPER
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(84, 84))
        name = QLabel(d["name"])
        name.setObjectName("h1")
        title = QLabel(f"{d['title']} · {d['brand']}")
        title.setObjectName("muted")
        about = QLabel(d["about"])
        about.setWordWrap(True)
        ver = QLabel(f"{APP_NAME} · {APP_TAGLINE} · v{__version__}\n{COPYRIGHT}")
        ver.setObjectName("muted")

        lay.addWidget(logo)
        lay.addWidget(name)
        lay.addWidget(title)
        lay.addSpacing(6)
        lay.addWidget(about)
        lay.addSpacing(6)
        lay.addWidget(ver)
        lay.addStretch()

        row = QHBoxLayout()
        wa = whatsapp_url()
        for label, url in (("E-posta", f"mailto:{d['email']}"), ("WhatsApp", wa.toString() if wa else ""),
                           (d["brand"], d["website"]), ("GitHub", d["github"])):
            if not url:
                continue
            b = QPushButton(label)
            b.setToolTip(url)
            b.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        return w

    def _log_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setObjectName("logView")
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setPlainText("\n".join(self.logbuf.lines))
        self.logbuf.line.connect(self.log_view.appendPlainText)
        row = QHBoxLayout()
        copy = QPushButton("Kopyala")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.log_view.toPlainText()))
        clear = QPushButton("Temizle")
        clear.clicked.connect(self.log_view.clear)
        row.addWidget(copy)
        row.addWidget(clear)
        row.addStretch()
        lay.addWidget(self.log_view)
        lay.addLayout(row)
        return w

    def _system_tab(self) -> QWidget:
        info = [
            ("Uygulama sürümü", __version__),
            ("yt-dlp sürümü", yt_dlp.version.__version__),
            ("Python", sys.version.split()[0]),
            ("İşletim sistemi", f"{platform.system()} {platform.release()} ({platform.machine()})"),
            ("ffmpeg", ffmpeg_path() or "bulunamadı"),
            ("Ayar klasörü", str(config_dir())),
            ("Paketlenmiş (frozen)", "evet" if getattr(sys, "frozen", False) else "hayır"),
        ]
        w = QTextBrowser()
        w.setHtml("<table cellpadding='6'>" + "".join(
            f"<tr><td style='color:#64748B'>{k}</td><td>{v}</td></tr>" for k, v in info) + "</table>")
        return w
