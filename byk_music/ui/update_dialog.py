"""Yeni sürüm penceresi: sürüm bilgisi, biçimli sürüm notları, indirme ilerlemesi ve kurulum seçimi."""
import html
import re

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QStackedWidget,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..config import APP_NAME
from .icons import pixmap, set_icon
from .styles import ACCENT, SUCCESS, app_icon

def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return re.sub(r"(https?://\S+)", rf'<a href="\1" style="color:{ACCENT}; text-decoration:none;">bağlantı</a>', text)


def notes_html(text: str) -> str:
    """Sürüm notlarını (Markdown) uygulamanın görünümüne uygun HTML'e çevirir."""
    out, items = [], []

    def flush():
        if items:
            rows = "".join(
                f"<tr><td width='22' valign='top' style='color:{SUCCESS}; font-weight:bold;'>✓</td>"
                f"<td style='color:#344054; padding-bottom:5px;'>{i}</td></tr>" for i in items)
            out.append(f"<table cellspacing='0' cellpadding='1' width='100%'>{rows}</table>")
            items.clear()

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line == "---" or "Co-Authored-By" in line or line.startswith("**Full Changelog**") \
                or line.startswith("**İndirme:**") or re.match(r"^#{1,2}\s", line):
            continue
        if line.startswith("### "):
            flush()
            out.append(f"<p style='color:{ACCENT}; font-size:14px; font-weight:700; "
                       f"margin-top:10px; margin-bottom:4px;'>{_inline(line[4:])}</p>")
        elif line.startswith(("- ", "* ")):
            items.append(_inline(line[2:]))
        else:
            flush()
            out.append(f"<p style='color:#475467; margin-top:2px; margin-bottom:6px;'>{_inline(line)}</p>")
    flush()
    return "".join(out) or "<p style='color:#475467;'>Bu sürüm için not eklenmemiş.</p>"


def fmt_mb(num: float) -> str:
    return f"{num / 1e6:.1f} MB"


class UpdateDialog(QDialog):
    """Modlar: available (yeni sürüm) → downloading (indiriliyor) → ready (kurulmaya hazır)."""

    update_requested = Signal()

    def __init__(self, info: dict, current: str, parent=None, ready: bool = False):
        super().__init__(parent)
        self.info = info
        self.choice = "later"   # later | update | install_now | install_on_exit
        self.setWindowTitle(f"{APP_NAME} güncellemesi")
        self.setMinimumSize(560, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(14)

        # --- başlık kartı
        hero = QFrame()
        hero.setObjectName("devHero")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(20, 20, 20, 20)
        hl.setSpacing(16)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(60, 60))
        texts = QVBoxLayout()
        texts.setSpacing(4)
        self.title = QLabel()
        self.title.setObjectName("heroName")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("heroSub")
        chips = QHBoxLayout()
        chips.setSpacing(6)
        cur = QLabel(f"Kurulu  v{current}")
        cur.setObjectName("heroChip")
        arrow = QLabel()
        arrow.setPixmap(pixmap("arrow-right", 14, "#A9B4C6"))
        new = QLabel(f"Yeni  v{info['version']}")
        new.setObjectName("heroChipNew")
        size = QLabel(fmt_mb(info["size"])) if info.get("size") else None
        chips.addWidget(cur)
        chips.addWidget(arrow)
        chips.addWidget(new)
        if size:
            size.setObjectName("heroChip")
            chips.addWidget(size)
        chips.addStretch()
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        texts.addSpacing(6)
        texts.addLayout(chips)
        hl.addWidget(logo, 0, Qt.AlignTop)
        hl.addLayout(texts, 1)
        root.addWidget(hero)

        # --- sürüm notları
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(pixmap("format-list-checks", 18, ACCENT))
        h = QLabel("Bu sürümde neler var?")
        h.setObjectName("h2")
        head.addWidget(ic)
        head.addWidget(h)
        head.addStretch()
        root.addLayout(head)

        notes = QTextBrowser()
        notes.setObjectName("releaseNotes")
        notes.setOpenExternalLinks(True)
        notes.setHtml(notes_html(info.get("notes", "")))
        root.addWidget(notes, 1)

        # --- alt bölüm: durum (bilgi / ilerleme)
        self.status_stack = QStackedWidget()
        info_row = QWidget()
        il = QHBoxLayout(info_row)
        il.setContentsMargins(0, 0, 0, 0)
        shield = QLabel()
        shield.setPixmap(pixmap("shield-check-outline", 16, "#067647"))
        self.info_text = QLabel("Güncelleme, uygulamanın resmi GitHub sürüm sayfasından indirilir.")
        self.info_text.setObjectName("small")
        self.info_text.setWordWrap(True)
        il.addWidget(shield)
        il.addWidget(self.info_text, 1)
        prog = QWidget()
        pl = QVBoxLayout(prog)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)
        self.prog_label = QLabel("İndiriliyor…")
        self.prog_label.setObjectName("small")
        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setTextVisible(False)
        pl.addWidget(self.prog_label)
        pl.addWidget(self.prog_bar)
        self.status_stack.addWidget(info_row)
        self.status_stack.addWidget(prog)
        root.addWidget(self.status_stack)

        # --- düğmeler
        btns = QHBoxLayout()
        page = QPushButton("Sürüm sayfası")
        page.setObjectName("link")
        page.setCursor(Qt.PointingHandCursor)
        set_icon(page, "open-in-new", ACCENT, 14)
        page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(info["page"])))
        btns.addWidget(page)
        btns.addStretch()
        self.later_btn = QPushButton("Daha Sonra")
        self.later_btn.clicked.connect(self._later)
        self.primary_btn = QPushButton()
        self.primary_btn.setObjectName("primary")
        self.primary_btn.setMinimumWidth(190)
        self.primary_btn.clicked.connect(self._primary)
        btns.addWidget(self.later_btn)
        btns.addWidget(self.primary_btn)
        root.addLayout(btns)

        self._mode = ""
        self.set_ready() if ready else self._set_available()

    # ------------------------------------------------------------ modlar
    def _set_available(self):
        self._mode = "available"
        self.title.setText("Yeni sürüm hazır")
        self.subtitle.setText(f"{APP_NAME} v{self.info['version']} yayınlandı.")
        self.later_btn.setText("Daha Sonra")
        self.primary_btn.setText("Şimdi Güncelle")
        set_icon(self.primary_btn, "download", "#FFFFFF")
        self.status_stack.setCurrentIndex(0)

    def set_downloading(self):
        self._mode = "downloading"
        self.title.setText("Güncelleme indiriliyor")
        self.subtitle.setText("İndirme arka planda sürer; pencereyi kapatabilirsiniz.")
        self.later_btn.setText("Arka Planda Sürdür")
        self.primary_btn.setText("İndiriliyor…")
        self.primary_btn.setEnabled(False)
        self.prog_bar.setValue(0)
        self.status_stack.setCurrentIndex(1)

    def set_progress(self, pct: int):
        self.prog_bar.setValue(pct)
        size = self.info.get("size") or 0
        detail = f" · {fmt_mb(size * pct / 100)} / {fmt_mb(size)}" if size else ""
        self.prog_label.setText(f"İndiriliyor… %{pct}{detail}")

    def set_ready(self):
        self._mode = "ready"
        self.title.setText("Güncelleme kurulmaya hazır")
        self.subtitle.setText("Uygulama kısa bir süre kapanıp yeni sürümle yeniden açılacak.")
        self.later_btn.setText("Kapanınca Kur")
        self.primary_btn.setText("Şimdi Yeniden Başlat")
        self.primary_btn.setEnabled(True)
        set_icon(self.primary_btn, "restart", "#FFFFFF")
        self.status_stack.setCurrentIndex(0)
        self.info_text.setText("İndirme tamamlandı. Kurulum sırasında Windows yönetici onayı isteyebilir.")

    def set_failed(self, msg: str):
        self._set_available()
        self.primary_btn.setText("Yeniden Dene")
        self.primary_btn.setEnabled(True)
        self.info_text.setText(f"Güncelleme indirilemedi: {msg[:160]}")

    # ---------------------------------------------------------- düğmeler
    def _primary(self):
        if self._mode == "available":
            self.choice = "update"
            self.update_requested.emit()
        elif self._mode == "ready":
            self.choice = "install_now"
            self.accept()

    def _later(self):
        self.choice = "install_on_exit" if self._mode == "ready" else "later"
        self.reject()
