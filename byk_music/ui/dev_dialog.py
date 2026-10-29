import logging
import platform
import sys

import yt_dlp
from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from .. import __version__
from ..config import APP_NAME, COPYRIGHT, DEVELOPER
from ..core.downloader import ffmpeg_path
from ..core.settings import config_dir
from .contact import whatsapp_display, whatsapp_url
from .styles import ACCENT, ACCENT_SOFT, app_icon
from .widgets import ContactCard


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
        self.resize(680, 600)
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
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(16)

        # --- üst kart: geliştirici kimliği
        hero = QFrame()
        hero.setObjectName("devHero")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(22, 22, 22, 22)
        hl.setSpacing(18)
        avatar = QLabel("".join(p[0] for p in d["name"].split()[:2]).upper())
        avatar.setObjectName("heroAvatar")
        avatar.setFixedSize(76, 76)
        avatar.setAlignment(Qt.AlignCenter)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        name = QLabel(d["name"])
        name.setObjectName("heroName")
        sub = QLabel(f"{d['title']} · {d['brand']}")
        sub.setObjectName("heroSub")
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for text in (f"{APP_NAME} v{__version__}", "Windows · macOS"):
            c = QLabel(text)
            c.setObjectName("heroChip")
            chips.addWidget(c)
        chips.addStretch()
        texts.addWidget(name)
        texts.addWidget(sub)
        texts.addSpacing(6)
        texts.addLayout(chips)
        hl.addWidget(avatar)
        hl.addLayout(texts, 1)
        lay.addWidget(hero)

        about = QLabel(d["about"])
        about.setWordWrap(True)
        about.setObjectName("muted")
        lay.addWidget(about)

        # --- iletişim kartları
        title = QLabel("İletişim")
        title.setObjectName("h2")
        lay.addWidget(title)
        grid = QGridLayout()
        grid.setSpacing(10)
        cards = [ContactCard("email-outline", "E-posta", d["email"], ACCENT, ACCENT_SOFT),
                 ContactCard("web", "Web sitesi", d["brand"], "#5925DC", "#EBE9FE")]
        urls = [f"mailto:{d['email']}", d["website"]]
        wa = whatsapp_url()
        if wa:
            cards.append(ContactCard("whatsapp", "WhatsApp", whatsapp_display(), "#128C7E", "#DCFAE6"))
            urls.append(wa.toString())
        for i, (card_btn, url) in enumerate(zip(cards, urls)):
            card_btn.setToolTip(url)
            card_btn.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            grid.addWidget(card_btn, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addStretch()

        foot = QLabel(COPYRIGHT)
        foot.setObjectName("small")
        foot.setAlignment(Qt.AlignCenter)
        lay.addWidget(foot)
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
        w.setObjectName("sysInfo")
        w.setHtml("<table cellpadding='6'>" + "".join(
            f"<tr><td style='color:#64748B'>{k}</td><td>{v}</td></tr>" for k, v in info) + "</table>")
        return w
