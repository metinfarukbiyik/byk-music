import platform
from urllib.parse import quote

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from .. import __version__
from ..config import APP_NAME, DEVELOPER
from .widgets import card

SUBJECTS = ["Genel soru", "Hata bildirimi", "Öneri / istek", "İş birliği"]


def mailto_url(subject: str, body: str) -> QUrl:
    return QUrl(f"mailto:{DEVELOPER['email']}?subject={quote(subject)}&body={quote(body)}")


def whatsapp_url(text: str = "") -> QUrl | None:
    number = "".join(ch for ch in DEVELOPER.get("whatsapp", "") if ch.isdigit())
    if not number:
        return None
    return QUrl(f"https://wa.me/{number}" + (f"?text={quote(text)}" if text else ""))


class ContactPage(QWidget):
    """Geliştiriciye e-posta ya da WhatsApp ile ulaşma sayfası."""

    def __init__(self, notify):
        super().__init__()
        self.setObjectName("page")
        self.notify = notify
        d = DEVELOPER

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 20)
        lay.setSpacing(14)
        h = QLabel("İletişim")
        h.setObjectName("h1")
        s = QLabel("Soru, öneri ve hata bildirimleriniz için geliştiriciye doğrudan ulaşın.")
        s.setObjectName("muted")
        lay.addWidget(h)
        lay.addWidget(s)

        row = QHBoxLayout()
        row.setSpacing(14)

        # --- geliştirici kartı
        prof = card()
        prof.setFixedWidth(320)
        pl = QVBoxLayout(prof)
        pl.setContentsMargins(22, 22, 22, 22)
        pl.setSpacing(6)
        initials = "".join(part[0] for part in d["name"].split()[:2]).upper()
        avatar = QLabel(initials)
        avatar.setObjectName("avatar")
        avatar.setFixedSize(64, 64)
        avatar.setAlignment(Qt.AlignCenter)
        name = QLabel(d["name"])
        name.setObjectName("h2")
        brand = QLabel(f"{d['title']} · {d['brand']}")
        brand.setObjectName("muted")
        pl.addWidget(avatar)
        pl.addSpacing(6)
        pl.addWidget(name)
        pl.addWidget(brand)
        pl.addSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        contacts = [("E-posta", d["email"], f"mailto:{d['email']}"),
                    ("Web", d["brand"], d["website"]),
                    ("GitHub", d["github"].split("github.com/")[-1], d["github"])]
        if d.get("whatsapp"):
            wa = whatsapp_url()
            contacts.insert(1, ("WhatsApp", "+" + "".join(c for c in d["whatsapp"] if c.isdigit()), wa.toString()))
        for i, (label, text, url) in enumerate(contacts):
            k = QLabel(label)
            k.setObjectName("small")
            v = QPushButton(text)
            v.setObjectName("link")
            v.setCursor(Qt.PointingHandCursor)
            v.setToolTip(url)
            v.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            grid.addWidget(k, i, 0)
            grid.addWidget(v, i, 1, Qt.AlignLeft)
        pl.addLayout(grid)
        pl.addStretch()
        copy = QPushButton("E-posta adresini kopyala")
        copy.clicked.connect(self._copy_email)
        pl.addWidget(copy)
        row.addWidget(prof)

        # --- mesaj formu
        form = card()
        fl = QVBoxLayout(form)
        fl.setContentsMargins(22, 20, 22, 20)
        fl.setSpacing(10)
        t = QLabel("Mesaj gönder")
        t.setObjectName("h2")
        fl.addWidget(t)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Adınız")
        self.subject = QComboBox()
        self.subject.addItems(SUBJECTS)
        self.subject.setMinimumWidth(170)
        self.subject.currentTextChanged.connect(lambda txt: self.sysinfo.setChecked(txt == "Hata bildirimi"))
        top.addWidget(self.name_edit, 1)
        top.addWidget(self.subject)
        fl.addLayout(top)

        self.message = QPlainTextEdit()
        self.message.setObjectName("messageEdit")
        self.message.setFont(QGuiApplication.font())
        self.message.setPlaceholderText("Mesajınızı yazın…")
        fl.addWidget(self.message, 1)

        self.sysinfo = QCheckBox("Sürüm ve işletim sistemi bilgisini ekle (hata bildirimleri için önerilir)")
        fl.addWidget(self.sysinfo)

        btns = QHBoxLayout()
        btns.addStretch()
        self.wa_btn = QPushButton("WhatsApp ile gönder")
        self.wa_btn.setObjectName("whatsapp")
        self.wa_btn.setCursor(Qt.PointingHandCursor)
        self.wa_btn.clicked.connect(self._send_whatsapp)
        if whatsapp_url() is None:
            self.wa_btn.setEnabled(False)
            self.wa_btn.setToolTip("WhatsApp numarası henüz tanımlanmadı.")
        mail_btn = QPushButton("E-posta ile gönder")
        mail_btn.setObjectName("primary")
        mail_btn.setCursor(Qt.PointingHandCursor)
        mail_btn.clicked.connect(self._send_mail)
        btns.addWidget(self.wa_btn)
        btns.addWidget(mail_btn)
        fl.addLayout(btns)
        row.addWidget(form, 1)

        lay.addLayout(row, 1)

    def _compose(self) -> tuple[str, str] | None:
        text = self.message.toPlainText().strip()
        if not text:
            self.notify("Mesaj boş", "Lütfen göndermeden önce bir mesaj yazın.", "warning")
            self.message.setFocus()
            return None
        subject = f"[{APP_NAME}] {self.subject.currentText()}"
        body = text
        name = self.name_edit.text().strip()
        if name:
            body += f"\n\n— {name}"
        if self.sysinfo.isChecked():
            body += (f"\n\n---\n{APP_NAME} v{__version__}\n"
                     f"{platform.system()} {platform.release()} ({platform.machine()})")
        return subject, body

    def _send_mail(self):
        msg = self._compose()
        if msg and QDesktopServices.openUrl(mailto_url(*msg)):
            self.notify("E-posta hazırlandı", "Mesajınız e-posta uygulamanızda açıldı.", "success")

    def _send_whatsapp(self):
        msg = self._compose()
        url = whatsapp_url(f"{msg[0]}\n\n{msg[1]}") if msg else None
        if url and QDesktopServices.openUrl(url):
            self.notify("WhatsApp açıldı", "Mesajınız WhatsApp'ta gönderime hazır.", "success")

    def _copy_email(self):
        QGuiApplication.clipboard().setText(DEVELOPER["email"])
        self.notify("Kopyalandı", DEVELOPER["email"], "success")
