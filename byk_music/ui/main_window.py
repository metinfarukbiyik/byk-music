import re
from datetime import datetime
from pathlib import Path

import yt_dlp
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QProgressDialog, QPushButton, QStackedWidget, QSystemTrayIcon,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import __version__
from ..config import APP_NAME, APP_TAGLINE
from ..core import updater
from ..core.downloader import DownloadWorker, InfoWorker, ffmpeg_path, fmt_duration
from ..core.history import History, reveal_in_folder
from ..core.settings import Settings, config_dir
from .contact import ContactPage
from .dev_dialog import DeveloperDialog, LogBuffer
from .styles import app_icon
from .toast import ToastManager
from .widgets import Badge, EmptyState, NavButton, Segmented, card, field, repolish

YT_RE = re.compile(r"https?://(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/\S+")
COL_CHECK, COL_NO, COL_TITLE, COL_DUR, COL_STATE, COL_PROGRESS = range(6)
STATES = {  # durum: (rozet metni, rozet türü)
    "waiting": ("Bekliyor", "neutral"),
    "queued": ("Sırada", "neutral"),
    "active": ("● İndiriliyor", "info"),
    "processing": ("● İşleniyor", "processing"),
    "done": ("✓ Tamamlandı", "success"),
    "error": ("✕ Hata", "error"),
    "cancelled": ("İptal", "neutral"),
}
FINAL = ("done", "error", "cancelled")
VIDEO_QUALITIES = [("En iyi", "best"), ("2160p (4K)", "2160"), ("1440p", "1440"), ("1080p", "1080"),
                   ("720p", "720"), ("480p", "480"), ("360p", "360")]
AUDIO_QUALITIES = ["320", "256", "192", "128"]
PAGE_DOWNLOAD, PAGE_HISTORY, PAGE_SETTINGS, PAGE_CONTACT = range(4)
UPDATE_INTERVAL_MS = 60 * 60 * 1000  # çalışırken saatte bir güncelleme denetle


def page_header(title: str, subtitle: str) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(2)
    h = QLabel(title)
    h.setObjectName("h1")
    s = QLabel(subtitle)
    s.setObjectName("muted")
    lay.addWidget(h)
    lay.addWidget(s)
    return lay


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, logbuf: LogBuffer):
        super().__init__()
        self.settings = settings
        self.logbuf = logbuf
        self.history = History()
        self.info_worker = self.dl_worker = self.up_worker = self.up_dl_worker = None
        self.playlist = {"is_playlist": False, "title": "", "items": []}
        self.rows: list[dict] = []
        self.update_info = None
        self._pending_update = None   # indirilmiş, kurulmayı bekleyen güncelleme dosyası
        self._installing = False
        self._last_clip = ""
        self._new_history = 0
        self._batch: list[int] = []
        self._batch_fmt = settings["format"]
        self._cancelled = False

        self.setWindowTitle(f"{APP_NAME} – {APP_TAGLINE}")
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        content = QWidget()
        content.setObjectName("content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._build_topbar())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_download_page())
        self.pages.addWidget(self._build_history_page())
        self.pages.addWidget(self._build_settings_page())
        self.pages.addWidget(ContactPage(self.notify))
        cl.addWidget(self.pages, 1)
        root.addWidget(content, 1)

        self.toasts = ToastManager(content)
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(UPDATE_INTERVAL_MS)
        self.update_timer.timeout.connect(lambda: self.check_updates(silent=True))
        self.tray = None
        self._setup_tray()
        self._load_settings_into_ui()
        self._refresh_history()
        QGuiApplication.instance().applicationStateChanged.connect(self._on_app_state)

    def after_show(self):
        """Açılış animasyonu bittikten sonra çalışır."""
        if self.settings["auto_update"]:
            self.check_updates(silent=True)
            self.update_timer.start()
        self._check_clipboard()

    # ================================================================ yapı
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(224)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 20, 14, 16)
        lay.setSpacing(4)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(34, 34))
        names = QVBoxLayout()
        names.setSpacing(0)
        b1 = QLabel(APP_NAME)
        b1.setObjectName("brand")
        b2 = QLabel("MP3 & MP4 İndirici")
        b2.setObjectName("brandSub")
        names.addWidget(b1)
        names.addWidget(b2)
        brand.addWidget(logo)
        brand.addLayout(names, 1)
        lay.addLayout(brand)
        lay.addSpacing(26)

        sec = QLabel("MENÜ")
        sec.setObjectName("sideSection")
        lay.addWidget(sec)
        lay.addSpacing(4)
        self.nav = [NavButton("↓", "İndir"), NavButton("◷", "Geçmiş"), NavButton("⚙", "Ayarlar"),
                    NavButton("✉", "İletişim")]
        for i, b in enumerate(self.nav):
            b.clicked.connect(lambda _=False, idx=i: self._goto(idx))
            lay.addWidget(b)
        self.nav[0].setChecked(True)
        lay.addStretch()

        sec2 = QLabel("DİĞER")
        sec2.setObjectName("sideSection")
        lay.addWidget(sec2)
        lay.addSpacing(4)
        upd = NavButton("⟳", "Güncellemeler", checkable=False)
        upd.clicked.connect(self._on_update_nav)
        dev = NavButton("</>", "Geliştirici", checkable=False)
        dev.clicked.connect(self.open_developer)
        self.nav_update = upd
        lay.addWidget(upd)
        lay.addWidget(dev)
        lay.addSpacing(10)
        ver = QLabel(f"Sürüm {__version__}")
        ver.setObjectName("sideSection")
        lay.addWidget(ver)
        return side

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(28, 14, 28, 14)
        lay.setSpacing(22)

        self.seg = Segmented([("MP3", "mp3"), ("MP4", "mp4")])
        self.seg.changed.connect(self._set_format)
        self.quality_combo = QComboBox()
        self.quality_combo.setMinimumWidth(150)
        self.quality_combo.currentIndexChanged.connect(self._quality_changed)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        self.dir_edit = QLineEdit(readOnly=True)
        self.dir_edit.setMinimumWidth(220)
        self.dir_btn = QPushButton("Değiştir")
        self.dir_btn.clicked.connect(self.choose_dir)
        open_btn = QPushButton("Aç")
        open_btn.clicked.connect(self.open_dir)
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(self.dir_btn)
        dir_row.addWidget(open_btn)

        self.status_badge = Badge("Hazır", "neutral")
        status_wrap = QWidget()
        sl = QHBoxLayout(status_wrap)
        sl.setContentsMargins(0, 4, 0, 4)
        sl.addWidget(self.status_badge)

        lay.addWidget(field("Biçim", self.seg))
        lay.addWidget(field("Kalite", self.quality_combo))
        lay.addWidget(field("Kayıt klasörü", dir_row), 1)
        lay.addWidget(field("Durum", status_wrap))
        return bar

    def _build_download_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 22, 28, 20)
        lay.setSpacing(14)
        lay.addLayout(page_header("İndir", "Bir video ya da oynatma listesi bağlantısı yapıştırın, "
                                           "listeden istediklerinizi seçip indirin."))

        top = card()
        tl = QHBoxLayout(top)
        tl.setContentsMargins(14, 14, 14, 14)
        tl.setSpacing(8)
        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("bigInput")
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=…  ya da  …/playlist?list=…")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self.fetch)
        paste = QPushButton("Yapıştır")
        paste.clicked.connect(lambda: self.url_edit.setText(QApplication.clipboard().text().strip()))
        self.fetch_btn = QPushButton("Listele")
        self.fetch_btn.setObjectName("primary")
        self.fetch_btn.clicked.connect(self.fetch)
        tl.addWidget(self.url_edit, 1)
        tl.addWidget(paste)
        tl.addWidget(self.fetch_btn)
        lay.addWidget(top)

        # liste başlığı, sayaç rozetleri ve araçlar
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.list_title = QLabel("Liste")
        self.list_title.setObjectName("h2")
        self.chip_total = Badge("", "neutral")
        self.chip_sel = Badge("", "info")
        self.chip_done = Badge("", "success")
        self.chip_err = Badge("", "error")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Listede ara…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setFixedWidth(220)
        self.filter_edit.textChanged.connect(self._apply_filter)
        sel_all = QPushButton("Tümünü Seç")
        sel_all.clicked.connect(lambda: self._set_all_checked(True))
        sel_none = QPushButton("Seçimi Kaldır")
        sel_none.clicked.connect(lambda: self._set_all_checked(False))
        bar.addWidget(self.list_title)
        for chip in (self.chip_total, self.chip_sel, self.chip_done, self.chip_err):
            bar.addWidget(chip)
        bar.addStretch()
        bar.addWidget(self.filter_edit)
        bar.addWidget(sel_all)
        bar.addWidget(sel_none)
        lay.addLayout(bar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "#", "BAŞLIK", "SÜRE", "DURUM", "İLERLEME"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.verticalHeader().setDefaultSectionSize(50)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for col, width in ((COL_CHECK, 40), (COL_NO, 44), (COL_DUR, 70), (COL_STATE, 130), (COL_PROGRESS, 240)):
            hh.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, width)
        hh.setSectionResizeMode(COL_TITLE, QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda _: self._update_counts())

        self.list_empty = EmptyState("↓", "Henüz liste yok",
                                     "Yukarıya bir YouTube bağlantısı yapıştırıp Listele'ye tıklayın.")
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.list_empty)
        self.list_stack.addWidget(self.table)
        lay.addWidget(self.list_stack, 1)

        # alt çubuk: genel ilerleme + işlemler
        bottom = card()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(16, 12, 12, 12)
        bl.setSpacing(10)
        prog_col = QVBoxLayout()
        prog_col.setSpacing(6)
        self.overall_label = QLabel("İndirme bekleniyor")
        self.overall_label.setObjectName("small")
        self.overall_bar = QProgressBar()
        self.overall_bar.setRange(0, 100)
        self.overall_bar.setTextVisible(False)
        prog_col.addWidget(self.overall_label)
        prog_col.addWidget(self.overall_bar)
        self.retry_btn = QPushButton("Hatalıları Yeniden Dene")
        self.retry_btn.clicked.connect(self.retry_failed)
        self.retry_btn.hide()
        self.cancel_btn = QPushButton("Durdur")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self.cancel_download)
        self.cancel_btn.hide()
        self.dl_btn = QPushButton("Seçilenleri İndir")
        self.dl_btn.setObjectName("primary")
        self.dl_btn.setEnabled(False)
        self.dl_btn.clicked.connect(lambda: self.start_download())
        bl.addLayout(prog_col, 1)
        bl.addSpacing(12)
        bl.addWidget(self.retry_btn)
        bl.addWidget(self.cancel_btn)
        bl.addWidget(self.dl_btn)
        lay.addWidget(bottom)
        self._update_counts()
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 22, 28, 20)
        lay.setSpacing(14)
        lay.addLayout(page_header("Geçmiş", "Bu bilgisayarda indirilen tüm dosyalar."))

        bar = QHBoxLayout()
        self.hist_search = QLineEdit()
        self.hist_search.setPlaceholderText("Geçmişte ara…")
        self.hist_search.setClearButtonEnabled(True)
        self.hist_search.setFixedWidth(280)
        self.hist_search.textChanged.connect(self._refresh_history)
        self.hist_count = Badge("", "neutral")
        clear = QPushButton("Geçmişi Temizle")
        clear.setObjectName("danger")
        clear.clicked.connect(self._clear_history)
        bar.addWidget(self.hist_search)
        bar.addWidget(self.hist_count)
        bar.addStretch()
        bar.addWidget(clear)
        lay.addLayout(bar)

        self.hist_table = QTableWidget(0, 4)
        self.hist_table.setHorizontalHeaderLabels(["TARİH", "BAŞLIK", "BİÇİM", "İŞLEMLER"])
        self.hist_table.verticalHeader().setVisible(False)
        self.hist_table.setAlternatingRowColors(True)
        self.hist_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hist_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hist_table.setShowGrid(False)
        self.hist_table.setFocusPolicy(Qt.NoFocus)
        self.hist_table.verticalHeader().setDefaultSectionSize(46)
        hh = self.hist_table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for col, width in ((0, 140), (2, 90), (3, 200)):
            hh.setSectionResizeMode(col, QHeaderView.Fixed)
            self.hist_table.setColumnWidth(col, width)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)

        self.hist_empty = EmptyState("◷", "Geçmiş boş", "İndirdiğiniz dosyalar burada listelenir.")
        self.hist_stack = QStackedWidget()
        self.hist_stack.addWidget(self.hist_empty)
        self.hist_stack.addWidget(self.hist_table)
        lay.addWidget(self.hist_stack, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 22, 28, 20)
        lay.setSpacing(14)
        lay.addLayout(page_header("Ayarlar", "Değişiklikler otomatik kaydedilir."))

        def section(title: str, options: list[tuple[str, str, str]]) -> QFrame:
            box = card()
            v = QVBoxLayout(box)
            v.setContentsMargins(20, 16, 20, 16)
            v.setSpacing(12)
            t = QLabel(title)
            t.setObjectName("h2")
            v.addWidget(t)
            for key, label, hint in options:
                cb = QCheckBox(label)
                cb.setChecked(bool(self.settings[key]))
                cb.toggled.connect(lambda on, k=key: self._toggle_setting(k, on))
                v.addWidget(cb)
                if hint:
                    h = QLabel(hint)
                    h.setObjectName("small")
                    h.setContentsMargins(28, 0, 0, 4)
                    v.addWidget(h)
            return box

        lay.addWidget(section("Dosyalar", [
            ("playlist_folder", "Liste indirmelerinde liste adıyla alt klasör oluştur", ""),
            ("number_prefix", "Liste sırasını dosya adının başına ekle", "Örnek: 01 - Şarkı adı.mp3"),
            ("embed_thumbnail", "MP3 dosyalarına kapak resmi ve etiket bilgisi göm", ""),
        ]))
        lay.addWidget(section("Bildirimler ve kolaylıklar", [
            ("notify_system", "Uygulama arka plandayken sistem bildirimi göster", ""),
            ("clipboard_watch", "Panodaki YouTube bağlantısını otomatik algıla",
             "Uygulamaya geri döndüğünüzde kopyaladığınız bağlantı kutuya eklenir."),
            ("auto_update", "Güncellemeleri otomatik denetle", "Açılışta ve uygulama açıkken saatte bir denetlenir."),
            ("auto_install", "Güncellemeleri arka planda indir ve kur",
             "Yeni sürüm indirildiğinde hemen ya da uygulama kapanırken kurulur."),
        ]))

        info = card()
        il = QVBoxLayout(info)
        il.setContentsMargins(20, 16, 20, 16)
        il.setSpacing(6)
        t = QLabel("Sistem")
        t.setObjectName("h2")
        il.addWidget(t)
        for k, v in (("ffmpeg", ffmpeg_path() or "bulunamadı"), ("yt-dlp", yt_dlp.version.__version__),
                     ("Ayar klasörü", str(config_dir()))):
            l = QLabel(f"<span style='color:#64748B'>{k}:</span> {v}")
            l.setTextInteractionFlags(Qt.TextSelectableByMouse)
            l.setWordWrap(True)
            il.addWidget(l)
        lay.addWidget(info)
        lay.addStretch()
        return page

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction("Göster", self._bring_front)
        menu.addAction("Çıkış", self.close)
        self.tray.setContextMenu(menu)
        self.tray.messageClicked.connect(self._bring_front)
        self.tray.activated.connect(lambda reason: reason == QSystemTrayIcon.Trigger and self._bring_front())
        self.tray.setVisible(bool(self.settings["notify_system"]))

    def _bring_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ======================================================== gezinme/ayar
    def _goto(self, idx: int):
        self.pages.setCurrentIndex(idx)
        for i, b in enumerate(self.nav):
            b.setChecked(i == idx)
        if idx == PAGE_HISTORY:
            self._new_history = 0
            self.nav[PAGE_HISTORY].set_badge(None)
            self._refresh_history()

    def _toggle_setting(self, key: str, on: bool):
        self.settings[key] = on
        self.settings.save()
        if key == "notify_system" and self.tray:
            self.tray.setVisible(on)
        if key == "auto_update":
            self.update_timer.start() if on else self.update_timer.stop()

    def _load_settings_into_ui(self):
        self.dir_edit.setText(self.settings["download_dir"])
        self.dir_edit.setToolTip(self.settings["download_dir"])
        self._set_format(self.settings["format"], save=False)

    def _set_format(self, fmt: str, save=True):
        self.settings["format"] = fmt
        self.seg.set_value(fmt)
        self.quality_combo.blockSignals(True)
        self.quality_combo.clear()
        if fmt == "mp3":
            for q in AUDIO_QUALITIES:
                self.quality_combo.addItem(f"{q} kbps", q)
            idx = self.quality_combo.findData(self.settings["audio_quality"])
        else:
            for label, val in VIDEO_QUALITIES:
                self.quality_combo.addItem(label, val)
            idx = self.quality_combo.findData(self.settings["video_quality"])
        self.quality_combo.setCurrentIndex(max(idx, 0))
        self.quality_combo.blockSignals(False)
        if save:
            self.settings.save()

    def _quality_changed(self):
        key = "audio_quality" if self.settings["format"] == "mp3" else "video_quality"
        self.settings[key] = self.quality_combo.currentData()
        self.settings.save()

    def _format_desc(self) -> str:
        return f"{self.settings['format'].upper()} · {self.quality_combo.currentText()}"

    def choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "İndirme klasörünü seçin", self.settings["download_dir"])
        if d:
            self.settings["download_dir"] = d
            self.settings.save()
            self.dir_edit.setText(d)
            self.dir_edit.setToolTip(d)

    def open_dir(self):
        Path(self.settings["download_dir"]).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.settings["download_dir"]))

    # ============================================================ bildirim
    def notify(self, title: str, text: str = "", kind: str = "info", action=None, system: bool = False):
        self.toasts.show(title, text, kind, action)
        if system and self.tray and self.tray.isVisible() and not self.isActiveWindow():
            icon = QSystemTrayIcon.Critical if kind == "error" else QSystemTrayIcon.Information
            self.tray.showMessage(title, text, icon, 5000)

    def _set_status(self, text: str, kind: str, pulse: bool = False):
        self.status_badge.set(text, kind)
        self.status_badge.set_pulse(pulse)

    def _on_app_state(self, state):
        if state == Qt.ApplicationActive:
            self._check_clipboard()

    def _check_clipboard(self):
        if not self.settings["clipboard_watch"] or self.dl_worker or self.info_worker:
            return
        text = QGuiApplication.clipboard().text().strip()
        if not text or text == self._last_clip or text == self.url_edit.text().strip() or not YT_RE.fullmatch(text):
            return
        self._last_clip = text
        self.url_edit.setText(text)
        self.notify("Bağlantı algılandı", "Panodaki YouTube bağlantısı kutuya eklendi.", "info",
                    action=("Hemen listele", self.fetch))

    # =============================================================== liste
    def fetch(self):
        url = self.url_edit.text().strip()
        if not url or self.info_worker or self.dl_worker:
            return
        self._last_clip = url
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Yükleniyor…")
        self.list_empty.set("…", "Bağlantı çözümleniyor", "Video bilgileri YouTube'dan alınıyor.", busy=True)
        self.list_stack.setCurrentWidget(self.list_empty)
        self._set_status("● Çözümleniyor", "info", pulse=True)
        self.info_worker = InfoWorker(url)
        self.info_worker.result.connect(self._on_info)
        self.info_worker.failed.connect(self._on_info_failed)
        self.info_worker.finished.connect(self._fetch_done)
        self.info_worker.start()

    def _fetch_done(self):
        self.info_worker = None
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Listele")

    def _on_info_failed(self, msg: str):
        self._set_status("Hazır", "neutral")
        self.list_empty.set("!", "Bağlantı çözümlenemedi", msg[:300])
        if self.rows:
            self.list_stack.setCurrentWidget(self.table)
        self.notify("Bağlantı çözümlenemedi", msg[:160], "error")

    def _on_info(self, data: dict):
        self.playlist = data
        items = data["items"]
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.rows = []
        for i, it in enumerate(items):
            self.table.insertRow(i)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked)
            self.table.setItem(i, COL_CHECK, chk)
            no = QTableWidgetItem(str(i + 1))
            no.setForeground(Qt.gray)
            self.table.setItem(i, COL_NO, no)
            t = QTableWidgetItem(it["title"])
            t.setToolTip(f"{it['title']}\n{it['uploader']}".strip())
            self.table.setItem(i, COL_TITLE, t)
            self.table.setItem(i, COL_DUR, QTableWidgetItem(fmt_duration(it["duration"])))
            self.rows.append(self._make_row_widgets(i))
            self._set_row_state(i, "waiting")
        self.table.blockSignals(False)
        self.filter_edit.clear()

        if data["is_playlist"]:
            self.list_title.setText(data["title"] or "Oynatma listesi")
        else:
            self.list_title.setText("Video")
        self.list_title.setToolTip(data["title"])
        self.list_stack.setCurrentWidget(self.table if items else self.list_empty)
        if not items:
            self.list_empty.set("!", "Liste boş", "Bu bağlantıda indirilebilir öğe bulunamadı.")
        self._set_status("Hazır", "neutral")
        self.overall_bar.setValue(0)
        self.overall_label.setText("İndirme bekleniyor")
        self._update_counts()
        kind = "Liste yüklendi" if data["is_playlist"] else "Video bulundu"
        self.notify(kind, f"{len(items)} öğe listelendi. İndirmek istediklerinizi seçin.", "success")

    def _make_row_widgets(self, r: int) -> dict:
        badge = Badge()
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(6, 0, 6, 0)
        wl.addWidget(badge)
        wl.addStretch()
        self.table.setCellWidget(r, COL_STATE, wrap)

        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(6, 8, 14, 8)
        pl.setSpacing(5)
        detail = QLabel("")
        detail.setObjectName("small")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        pl.addWidget(detail)
        pl.addWidget(bar)
        self.table.setCellWidget(r, COL_PROGRESS, pw)
        return {"badge": badge, "bar": bar, "detail": detail, "state": "", "pct": 0.0, "path": None}

    def _set_row_state(self, r: int, state: str, msg: str = ""):
        row = self.rows[r]
        row["state"] = state
        text, kind = STATES[state]
        row["badge"].set(text, kind)
        row["badge"].set_pulse(state in ("active", "processing"))
        bar, detail = row["bar"], row["detail"]
        bar.setRange(0, 0 if state == "processing" else 100)
        bar.setProperty("kind", {"done": "success", "error": "error", "processing": "processing"}.get(state, ""))
        repolish(bar)
        if state in ("done", "error"):
            bar.setValue(100)
        elif state in ("waiting", "queued", "cancelled"):
            bar.setValue(0)
        if state == "done" and row["path"]:
            msg = Path(row["path"]).name
        detail.setText(msg)
        detail.setToolTip(msg)

    def _checked_rows(self) -> list[int]:
        return [r for r in range(self.table.rowCount())
                if self.table.item(r, COL_CHECK).checkState() == Qt.Checked]

    def _set_all_checked(self, on: bool):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                self.table.item(r, COL_CHECK).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_counts()

    def _apply_filter(self, text: str):
        q = text.casefold().strip()
        for r in range(self.table.rowCount()):
            self.table.setRowHidden(r, bool(q) and q not in self.table.item(r, COL_TITLE).text().casefold())

    def _update_counts(self):
        total = len(self.rows)
        checked = len(self._checked_rows()) if total else 0
        done = sum(r["state"] == "done" for r in self.rows)
        err = sum(r["state"] == "error" for r in self.rows)
        self.chip_total.set(f"{total} öğe", "neutral")
        self.chip_sel.set(f"{checked} seçili", "info")
        self.chip_done.set(f"{done} tamamlandı", "success")
        self.chip_err.set(f"{err} hata", "error")
        self.chip_total.setVisible(total > 0)
        self.chip_sel.setVisible(total > 0)
        self.chip_done.setVisible(done > 0)
        self.chip_err.setVisible(err > 0)
        idle = self.dl_worker is None
        self.dl_btn.setEnabled(checked > 0 and idle)
        self.dl_btn.setText(f"Seçilenleri İndir ({checked})" if checked else "Seçilenleri İndir")
        self.retry_btn.setVisible(err > 0 and idle)

    # ============================================================ indirme
    def start_download(self, rows: list[int] | None = None):
        rows = rows if rows is not None else self._checked_rows()
        if not rows or self.dl_worker:
            return
        if not ffmpeg_path():
            self.notify("ffmpeg bulunamadı", "Dönüştürme yapılamıyor.", "error")
            return
        s = self.settings
        opts = {
            "download_dir": s["download_dir"], "format": s["format"],
            "audio_quality": s["audio_quality"], "video_quality": s["video_quality"],
            "playlist_folder": s["playlist_folder"], "number_prefix": s["number_prefix"],
            "embed_thumbnail": s["embed_thumbnail"],
            "is_playlist": self.playlist["is_playlist"], "playlist_title": self.playlist["title"],
        }
        jobs = []
        for r in rows:
            self.rows[r].update(pct=0.0, path=None)
            self._set_row_state(r, "queued")
            jobs.append({"row": r, "url": self.playlist["items"][r]["url"], "index": r + 1})
        self._batch = rows
        self._batch_fmt = s["format"]
        self._cancelled = False

        self.dl_worker = DownloadWorker(jobs, opts)
        self.dl_worker.progress.connect(self._on_progress)
        self.dl_worker.state.connect(self._on_state)
        self.dl_worker.saved.connect(lambda r, p: self.rows[r].__setitem__("path", p))
        self.dl_worker.finished_all.connect(self._on_finished)
        self._set_busy(True)
        self._update_overall()
        self.dl_worker.start()
        self.notify("İndirme başladı", f"{len(rows)} öğe sıraya alındı · {self._format_desc()}", "info",
                    system=True)

    def _set_busy(self, busy: bool):
        for w in (self.seg, self.quality_combo, self.dir_btn, self.fetch_btn, self.url_edit):
            w.setEnabled(not busy)
        self.cancel_btn.setVisible(busy)
        self.cancel_btn.setEnabled(True)
        if busy:
            self.dl_btn.setEnabled(False)
        self._update_counts()

    def retry_failed(self):
        rows = [i for i, r in enumerate(self.rows) if r["state"] == "error"]
        self.start_download(rows)

    def cancel_download(self):
        if self.dl_worker:
            self._cancelled = True
            self.dl_worker.cancel()
            self.cancel_btn.setEnabled(False)
            self._set_status("Durduruluyor…", "processing")

    def _on_progress(self, r: int, pct: float, text: str):
        row = self.rows[r]
        if row["state"] != "active":
            self._set_row_state(r, "active")
        row["pct"] = pct
        row["bar"].setValue(int(pct))
        row["detail"].setText(text)
        self._update_overall()

    def _on_state(self, r: int, state: str, msg: str):
        self._set_row_state(r, state, msg)
        if state == "done":
            row = self.rows[r]
            item = self.playlist["items"][r]
            if row["path"]:
                self.history.add(item["title"], item["url"], row["path"], self._batch_fmt)
                self._new_history += 1
                if self.pages.currentIndex() != PAGE_HISTORY:
                    self.nav[PAGE_HISTORY].set_badge(self._new_history, "success")
        self._update_overall()
        self._update_counts()

    def _update_overall(self):
        n = len(self._batch)
        if not n:
            return
        rows = [self.rows[r] for r in self._batch]
        finished = sum(r["state"] in FINAL for r in rows)
        current = sum(r["pct"] for r in rows if r["state"] in ("active", "processing"))
        pct = (finished * 100 + current) / n
        self.overall_bar.setValue(int(pct))
        remaining = n - finished
        if self.dl_worker:
            self.overall_label.setText(f"{finished} / {n} tamamlandı · %{pct:.0f}")
            self._set_status(f"● İndiriliyor {finished}/{n}", "info", pulse=True)
            self.nav[PAGE_DOWNLOAD].set_badge(remaining)
            self.setWindowTitle(f"(%{pct:.0f}) {APP_NAME}")

    def _on_finished(self):
        rows = [self.rows[r] for r in self._batch]
        ok = sum(r["state"] == "done" for r in rows)
        err = sum(r["state"] == "error" for r in rows)
        self.dl_worker = None
        self._set_busy(False)
        self.nav[PAGE_DOWNLOAD].set_badge(None)
        self.setWindowTitle(f"{APP_NAME} – {APP_TAGLINE}")
        self.overall_label.setText(f"{ok} başarılı" + (f" · {err} hatalı" if err else "")
                                   + (" · durduruldu" if self._cancelled else ""))

        if self._cancelled:
            self._set_status("Durduruldu", "neutral")
            self.notify("İndirme durduruldu", f"{ok} öğe tamamlandı.", "neutral", system=True)
        elif err == 0:
            self._set_status("✓ Tamamlandı", "success")
            self.notify("İndirme tamamlandı", f"{ok} öğe başarıyla indirildi.", "success",
                        action=("Klasörü aç", self.open_dir), system=True)
        elif ok == 0:
            self._set_status("✕ Başarısız", "error")
            self.notify("İndirme başarısız", f"{err} öğe indirilemedi.", "error",
                        action=("Günlüğü göster", self.open_developer), system=True)
        else:
            self._set_status("Tamamlandı (hatalı)", "processing")
            self.notify("İndirme tamamlandı", f"{ok} başarılı · {err} hatalı. Hatalıları yeniden deneyebilirsiniz.",
                        "warning", action=("Yeniden dene", self.retry_failed), system=True)
        QTimer.singleShot(6000, lambda: self.dl_worker is None and self._set_status("Hazır", "neutral"))
        QApplication.alert(self)

    # ============================================================= geçmiş
    def _refresh_history(self):
        q = self.hist_search.text().casefold().strip()
        items = [h for h in self.history.items if q in h["title"].casefold()]
        self.hist_count.set(f"{len(self.history.items)} kayıt", "neutral")
        self.hist_table.setRowCount(0)
        for i, h in enumerate(items):
            self.hist_table.insertRow(i)
            try:
                date = datetime.fromisoformat(h["date"]).strftime("%d.%m.%Y %H:%M")
            except ValueError:
                date = h["date"]
            d = QTableWidgetItem(date)
            d.setForeground(Qt.gray)
            self.hist_table.setItem(i, 0, d)
            t = QTableWidgetItem(h["title"])
            t.setToolTip(h["path"])
            self.hist_table.setItem(i, 1, t)

            fmt = h.get("format", "mp3")
            bw = QWidget()
            bl = QHBoxLayout(bw)
            bl.setContentsMargins(6, 0, 6, 0)
            bl.addWidget(Badge(fmt.upper(), "info" if fmt == "mp3" else "violet"))
            bl.addStretch()
            self.hist_table.setCellWidget(i, 2, bw)

            aw = QWidget()
            al = QHBoxLayout(aw)
            al.setContentsMargins(4, 0, 4, 0)
            al.setSpacing(4)
            exists = Path(h["path"]).exists()
            if exists:
                play = QPushButton("Aç")
                play.setObjectName("link")
                play.setCursor(Qt.PointingHandCursor)
                play.clicked.connect(lambda _=False, p=h["path"]: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
                show = QPushButton("Klasörde göster")
                show.setObjectName("link")
                show.setCursor(Qt.PointingHandCursor)
                show.clicked.connect(lambda _=False, p=h["path"]: reveal_in_folder(p))
                al.addWidget(play)
                al.addWidget(show)
            else:
                al.addWidget(Badge("Dosya yok", "error"))
            al.addStretch()
            self.hist_table.setCellWidget(i, 3, aw)

        if items:
            self.hist_stack.setCurrentWidget(self.hist_table)
        else:
            self.hist_empty.set("◷", "Sonuç yok" if q else "Geçmiş boş",
                                "Aramanızla eşleşen kayıt bulunamadı." if q
                                else "İndirdiğiniz dosyalar burada listelenir.")
            self.hist_stack.setCurrentWidget(self.hist_empty)

    def _clear_history(self):
        if not self.history.items:
            return
        if QMessageBox.question(self, "Geçmişi temizle",
                                "Tüm geçmiş kayıtları silinsin mi?\nİndirilen dosyalar silinmez.") != QMessageBox.Yes:
            return
        self.history.clear()
        self._refresh_history()
        self.notify("Geçmiş temizlendi", "", "neutral")

    # ================================================ güncelleme / diğer
    def open_developer(self):
        DeveloperDialog(self.logbuf, self).exec()

    def _on_update_nav(self):
        if self._pending_update:
            self._update_ready()
        elif self.update_info:
            self._prompt_update()
        else:
            self.check_updates(silent=False)

    def check_updates(self, silent: bool):
        if self.up_worker and self.up_worker.isRunning():
            return
        self.up_worker = updater.UpdateCheckWorker()
        self.up_worker.available.connect(self._on_update_available)
        if not silent:
            self.up_worker.up_to_date.connect(
                lambda: self.notify("Uygulama güncel", f"En son sürümü kullanıyorsunuz (v{__version__}).", "success"))
            self.up_worker.failed.connect(
                lambda m: self.notify("Güncelleme denetlenemedi", m[:160], "error"))
        self.up_worker.start()

    def _can_self_update(self) -> bool:
        return bool(self.update_info and self.update_info["url"] and updater.is_frozen())

    def _on_update_available(self, info: dict):
        if self.update_info and self.update_info["version"] == info["version"]:
            return  # bu sürüm zaten işleniyor
        self.update_info = info
        self.nav_update.set_badge("Yeni", "success")
        if self._can_self_update() and self.settings["auto_install"]:
            self.notify("Yeni sürüm bulundu", f"v{info['version']} arka planda indiriliyor…", "info", system=True)
            self._download_update(interactive=False)
        else:
            self.notify(f"Yeni sürüm: v{info['version']}", "Yenilikleri görmek ve güncellemek için tıklayın.",
                        "info", action=("Güncelle", self._prompt_update), system=True)

    def _prompt_update(self):
        info = self.update_info
        box = QMessageBox(self)
        box.setWindowTitle("Yeni sürüm var")
        box.setText(f"{APP_NAME} v{info['version']} yayınlandı (kurulu: v{__version__}).")
        box.setInformativeText(info["notes"][:800] or "Sürüm notu yok.")
        update_btn = box.addButton("Şimdi Güncelle", QMessageBox.AcceptRole)
        box.addButton("Daha Sonra", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not update_btn:
            return
        if self._can_self_update():
            self._download_update(interactive=True)
        else:
            QDesktopServices.openUrl(QUrl(info["page"]))

    def _download_update(self, interactive: bool):
        if self.up_dl_worker and self.up_dl_worker.isRunning():
            return
        info = self.update_info
        self.up_dl_worker = updater.UpdateDownloadWorker(info["url"], info["name"])
        dlg = None
        if interactive:
            dlg = QProgressDialog("Güncelleme indiriliyor…", None, 0, 100, self)
            dlg.setWindowTitle(APP_NAME)
            dlg.setWindowModality(Qt.WindowModal)
            dlg.setAutoClose(False)
            dlg.show()
            self.up_dl_worker.progress.connect(dlg.setValue)

        def failed(msg):
            if dlg:
                dlg.close()
            self.notify("Güncelleme indirilemedi", msg[:160], "error",
                        action=("İndirme sayfası", lambda: QDesktopServices.openUrl(QUrl(info["page"]))))

        def done(path):
            if dlg:
                dlg.close()
            self._pending_update = path
            self._update_ready()

        self.up_dl_worker.failed.connect(failed)
        self.up_dl_worker.done.connect(done)
        self.up_dl_worker.start()

    def _update_ready(self):
        version = self.update_info["version"]
        self.nav_update.set_badge("Hazır", "success")
        if self.dl_worker:
            self.notify("Güncelleme hazır", f"v{version} indirildi; uygulama kapanırken kurulacak.", "success",
                        system=True)
            return
        box = QMessageBox(self)
        box.setWindowTitle("Güncelleme hazır")
        box.setText(f"{APP_NAME} v{version} kurulmaya hazır.")
        box.setInformativeText("Uygulama kısa bir süre kapanıp yeni sürümle yeniden açılacak.")
        now = box.addButton("Şimdi Yeniden Başlat", QMessageBox.AcceptRole)
        box.addButton("Kapanınca Kur", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is now:
            self._install_pending(relaunch=True)

    def _install_pending(self, relaunch: bool) -> bool:
        if not self._pending_update or self._installing:
            return False
        if updater.install_update(self._pending_update, relaunch=relaunch):
            self._installing = True
            if relaunch:
                QApplication.quit()
            return True
        self.notify("Güncelleme kurulamadı", "Kurulum dosyası indirme sayfasından alınabilir.", "error",
                    action=("İndirme sayfası", lambda: QDesktopServices.openUrl(QUrl(self.update_info["page"]))))
        return False

    def closeEvent(self, event):
        if self.dl_worker:
            if QMessageBox.question(self, "Çıkış", "İndirmeler sürüyor. Çıkılsın mı?") != QMessageBox.Yes:
                event.ignore()
                return
            self.dl_worker.cancel()
            self.dl_worker.wait(3000)
        if self.tray:
            self.tray.hide()
        self._install_pending(relaunch=False)
        event.accept()
