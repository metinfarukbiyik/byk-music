"""Birden fazla YouTube bağlantısını tek seferde ekleme penceresi."""
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from .icons import pixmap, set_icon
from .styles import ACCENT
from .widgets import Badge

URL_RE = re.compile(r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)/[^\s<>\"']+")


def find_links(text: str) -> list[str]:
    """Metindeki YouTube bağlantılarını sırasıyla ve tekrarsız döndürür."""
    seen, out = set(), []
    for url in URL_RE.findall(text or ""):
        url = url.rstrip(".,;)")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


class MultiLinkDialog(QDialog):
    def __init__(self, parent=None, initial: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Birden fazla bağlantı ekle")
        self.setMinimumSize(620, 440)
        self.start_now = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(pixmap("playlist-plus", 22, ACCENT))
        title = QLabel("Birden fazla bağlantı ekle")
        title.setObjectName("h2")
        head.addWidget(ic)
        head.addWidget(title)
        head.addStretch()
        self.count = Badge("0 bağlantı", "neutral")
        head.addWidget(self.count)
        lay.addLayout(head)

        hint = QLabel("Her satıra bir YouTube bağlantısı yapıştırın. Video, Shorts ve oynatma listesi bağlantıları "
                      "desteklenir; Mix / Radyo listelerinde yalnızca video eklenir. Bağlantılar mevcut listenin "
                      "sonuna eklenir.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.edit = QPlainTextEdit()
        self.edit.setObjectName("messageEdit")
        self.edit.setFont(QGuiApplication.font())
        self.edit.setPlaceholderText("https://www.youtube.com/watch?v=…\nhttps://youtu.be/…\n"
                                     "https://www.youtube.com/playlist?list=…")
        self.edit.textChanged.connect(self._update)
        lay.addWidget(self.edit, 1)

        btns = QHBoxLayout()
        paste = QPushButton("Panodan Yapıştır")
        set_icon(paste, "content-paste")
        paste.clicked.connect(self._paste)
        btns.addWidget(paste)
        btns.addStretch()
        cancel = QPushButton("Vazgeç")
        cancel.clicked.connect(self.reject)
        self.add_btn = QPushButton("Listeye Ekle")
        set_icon(self.add_btn, "playlist-plus")
        self.add_btn.clicked.connect(lambda: self._finish(False))
        self.start_btn = QPushButton("Ekle ve İndir")
        self.start_btn.setObjectName("primary")
        set_icon(self.start_btn, "download", "#FFFFFF")
        self.start_btn.clicked.connect(lambda: self._finish(True))
        for b in (cancel, self.add_btn, self.start_btn):
            btns.addWidget(b)
        lay.addLayout(btns)

        if initial:
            self.edit.setPlainText(initial)
        self._update()
        self.edit.setFocus(Qt.OtherFocusReason)

    def links(self) -> list[str]:
        return find_links(self.edit.toPlainText())

    def _paste(self):
        text = QGuiApplication.clipboard().text().strip()
        if text:
            current = self.edit.toPlainText().rstrip()
            self.edit.setPlainText(f"{current}\n{text}".strip())

    def _update(self):
        n = len(self.links())
        self.count.set(f"{n} bağlantı", "info" if n else "neutral")
        self.add_btn.setEnabled(n > 0)
        self.start_btn.setEnabled(n > 0)

    def _finish(self, start: bool):
        self.start_now = start
        self.accept()
