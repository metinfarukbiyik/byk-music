import logging
import re
from datetime import datetime
from pathlib import Path

import yt_dlp
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QScrollArea, QStackedWidget,
                               QSystemTrayIcon,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import __version__
from ..config import APP_NAME, APP_TAGLINE
from ..core import updater
from ..core.bridge import PORT, BrowserBridge
from ..core.extension import BROWSERS, sync_extension_files
from ..core.downloader import DownloadWorker, InfoWorker, MultiInfoWorker, ffmpeg_path, fmt_duration
from ..core.history import TRASH_NAME, History, move_to_trash, reveal_in_folder
from ..core.links import analyze
from ..core.naming import clean_title, safe_filename
from ..core.net import ConnectionTestWorker, account_opts, url_opener, ydl_base_opts
from ..core.settings import Settings, config_dir
from ..core.watcher import BrowserWatcher
from .account import AccountPage
from .bubble import DetectBubble
from .contact import ContactPage
from .dev_dialog import DeveloperDialog, LogBuffer
from .extension_wizard import ExtensionWizard
from .icons import icon, set_icon
from .multilink import MultiLinkDialog, find_links
from .styles import ACCENT, app_icon
from .toast import ToastManager
from .update_dialog import UpdateDialog
from .widgets import Badge, ElidedLabel, EmptyState, LoadingView, NavButton, Segmented, card, field, repolish

YT_RE = re.compile(r"https?://(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/\S+")
COL_CHECK, COL_NO, COL_TITLE, COL_DUR, COL_FMT, COL_STATE, COL_PROGRESS = range(7)
FORMAT_BADGES = {"mp3": ("♫ MP3", "info"), "mp4": ("▶ MP4", "violet")}


def format_badge(fmt: str) -> Badge:
    text, kind = FORMAT_BADGES.get(fmt, FORMAT_BADGES["mp3"])
    b = Badge(text, kind)
    b.setToolTip("Ses dosyası (MP3)" if fmt == "mp3" else "Video dosyası (MP4)")
    return b
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
BUSY = ("queued", "active", "processing")
VIDEO_QUALITIES = [("En iyi", "best"), ("2160p (4K)", "2160"), ("1440p", "1440"), ("1080p", "1080"),
                   ("720p", "720"), ("480p", "480"), ("360p", "360")]
AUDIO_QUALITIES = ["320", "256", "192", "128"]
PAGE_DOWNLOAD, PAGE_HISTORY, PAGE_ACCOUNT, PAGE_SETTINGS, PAGE_CONTACT = range(5)
UPDATE_INTERVAL_MS = 30 * 60 * 1000  # çalışırken yarım saatte bir güncelleme denetle


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
        self._update_dialog_open = False
        self._update_prompted = False  # bu oturumda yeni sürüm penceresi gösterildi mi
        self._install_on_exit = False  # kullanıcı "Daha Sonra Kur" dedi
        self._ask_when_ready = False   # kullanıcı indirmeyi arka plana aldı; bitince sor
        self._active_update_dialog = None
        self._stale_workers = []       # daha yeni sürüm çıktığı için sonucu yok sayılan indirmeler
        self._installing = False
        self._last_clip = ""
        self._new_history = 0
        self._batch: list[int] = []
        self._cancelled = False
        self._pending_rows: list[int] = []   # kuyruk kapanırken eklenen satırlar (yeni partide başlar)
        self._resolvers: list[MultiInfoWorker] = []
        self._seen_urls: set[str] = set()     # balonda gösterilmiş bağlantılar

        self.setWindowTitle(f"{APP_NAME} – {APP_TAGLINE}")
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(1080, 660)

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
        cl.addWidget(self._build_update_banner())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_download_page())
        self.pages.addWidget(self._build_history_page())
        self.account_page = AccountPage(self.settings, self.notify, self.load_url, self.install_extension)
        self.pages.addWidget(self.account_page)
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
        self.bubble = DetectBubble()
        self.bubble.download.connect(lambda item, fmt: self.quick_add(item, fmt))
        self.bubble.open_list.connect(lambda item: self.load_url(item["url"]))
        self.bridge = BrowserBridge(self)
        self.bridge.detected.connect(self._on_detected)
        self.bridge.add_requested.connect(self._on_add_requested)
        self.bridge.cookies_received.connect(self._on_cookies_received)
        self.bridge.extension_hello.connect(self._on_extension_hello)
        self._wizard = None
        self._refresh_extension_status()
        try:
            sync_extension_files()  # eklenti yeni sürümü görünce kendini yeniden yükler
        except OSError as exc:
            logging.getLogger("byk").warning("Eklenti dosyaları güncellenemedi: %s", exc)
        if self.settings["browser_bridge"]:
            self.bridge.start()
        self.watcher = None
        self._load_settings_into_ui()
        self._refresh_history()
        QGuiApplication.instance().applicationStateChanged.connect(self._on_app_state)

    def after_show(self):
        """Açılış animasyonu bittikten sonra çalışır."""
        if self.settings["auto_update"]:
            self.check_updates(silent=True)
            self.update_timer.start()
        if self.settings["window_watch"]:
            self._start_watcher()
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
        self.nav = [NavButton("download", "İndir"), NavButton("history", "Geçmiş"),
                    NavButton("youtube", "YouTube Hesabım"), NavButton("cog-outline", "Ayarlar"),
                    NavButton("email-outline", "İletişim")]
        for i, b in enumerate(self.nav):
            b.clicked.connect(lambda _=False, idx=i: self._goto(idx))
            lay.addWidget(b)
        self.nav[0].setChecked(True)
        lay.addStretch()

        sec2 = QLabel("DİĞER")
        sec2.setObjectName("sideSection")
        lay.addWidget(sec2)
        lay.addSpacing(4)
        upd = NavButton("update", "Güncellemeler", checkable=False)
        upd.clicked.connect(self._on_update_nav)
        dev = NavButton("code-tags", "Geliştirici", checkable=False)
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
        lay.setSpacing(16)

        self.seg = Segmented([("MP3", "mp3"), ("MP4", "mp4")])
        self.seg.changed.connect(self._set_format)
        self.quality_combo = QComboBox()
        self.quality_combo.setMinimumWidth(130)
        self.quality_combo.currentIndexChanged.connect(self._quality_changed)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        self.dir_edit = QLineEdit(readOnly=True)
        self.dir_edit.setMinimumWidth(170)
        self.dir_btn = QPushButton()
        self.dir_btn.setObjectName("iconBtn")
        self.dir_btn.setToolTip("Kayıt klasörünü değiştir")
        set_icon(self.dir_btn, "folder-edit-outline", size=18)
        self.dir_btn.clicked.connect(self.choose_dir)
        open_btn = QPushButton()
        open_btn.setObjectName("iconBtn")
        open_btn.setToolTip("Kayıt klasörünü aç")
        set_icon(open_btn, "folder-open-outline", size=18)
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
        self.conc_combo = QComboBox()
        for n in range(1, 6):
            self.conc_combo.addItem(f"{n} dosya", n)
        self.conc_combo.setToolTip("Aynı anda kaç dosyanın indirileceği. İndirme sürerken de değiştirilebilir.")
        self.conc_combo.setCurrentIndex(max(self.conc_combo.findData(self.settings["concurrent"]), 0))
        self.conc_combo.currentIndexChanged.connect(self._concurrency_changed)
        lay.addWidget(field("Eşzamanlı", self.conc_combo))
        lay.addWidget(field("Kayıt klasörü", dir_row), 1)
        lay.addWidget(field("Durum", status_wrap))
        return bar

    def _build_update_banner(self) -> QFrame:
        """Yeni sürüm bulunduğunda üst çubuğun altında kalıcı olarak görünen şerit."""
        bar = QFrame()
        bar.setObjectName("updateBanner")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(28, 8, 20, 8)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icon("update", ACCENT).pixmap(18, 18))
        self.banner_text = QLabel()
        self.banner_text.setObjectName("bannerText")
        details = QPushButton("Yenilikler")
        details.setObjectName("link")
        details.setCursor(Qt.PointingHandCursor)
        details.clicked.connect(self._on_update_nav)
        self.banner_btn = QPushButton()
        self.banner_btn.setObjectName("primarySm")
        self.banner_btn.setCursor(Qt.PointingHandCursor)
        self.banner_btn.clicked.connect(self._banner_action)
        close = QPushButton()
        close.setObjectName("toastClose")
        close.setFixedSize(22, 22)
        close.setIcon(icon("close", "#98A2B3"))
        close.setToolTip("Bu oturumda gizle")
        close.clicked.connect(bar.hide)
        lay.addWidget(ic)
        lay.addWidget(self.banner_text, 1)
        lay.addWidget(details)
        lay.addWidget(self.banner_btn)
        lay.addWidget(close)
        bar.hide()
        self.update_banner = bar
        return bar

    def _refresh_banner(self, progress: int | None = None):
        if not self.update_info:
            self.update_banner.hide()
            return
        v = self.update_info["version"]
        if self._install_on_exit:
            ready = "hazır" if self._pending_update else "hazırlanıyor"
            self.banner_text.setText(f"<b>BYK Music v{v}</b> uygulamayı kapattığınızda kurulacak ({ready}).")
        elif self._pending_update:
            self.banner_text.setText(f"<b>BYK Music v{v}</b> indirildi ve kurulmaya hazır.")
        elif progress is not None:
            self.banner_text.setText(f"<b>BYK Music v{v}</b> hazırlanıyor… %{progress}")
        else:
            self.banner_text.setText(f"<b>Yeni sürüm: BYK Music v{v}</b> · kurulu sürüm v{__version__}")
        if self._pending_update:
            self.banner_btn.setText("Şimdi Kur")
            set_icon(self.banner_btn, "restart", "#FFFFFF", 15)
        else:
            self.banner_btn.setText("Güncelle…")
            set_icon(self.banner_btn, "download", "#FFFFFF", 15)
        self.update_banner.show()

    def _banner_action(self):
        if self._pending_update:
            self._install_now()
        else:
            self._prompt_update()

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
        self.url_edit.setPlaceholderText("Video ya da liste bağlantısı · birden fazla bağlantıyı aynı anda yapıştırabilirsiniz")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.addAction(icon("link-variant"), QLineEdit.LeadingPosition)
        self.url_edit.returnPressed.connect(self.fetch)
        paste = QPushButton("Yapıştır")
        set_icon(paste, "content-paste")
        paste.clicked.connect(lambda: self.url_edit.setText(QApplication.clipboard().text().strip()))
        self.fetch_btn = QPushButton("Listele")
        self.fetch_btn.setObjectName("primary")
        set_icon(self.fetch_btn, "playlist-play", "#FFFFFF")
        self.fetch_btn.clicked.connect(self.fetch)
        tl.addWidget(self.url_edit, 1)
        tl.addWidget(paste)
        multi = QPushButton("Çoklu Ekle")
        set_icon(multi, "playlist-plus")
        multi.setToolTip("Birden fazla bağlantıyı tek seferde ekleyin")
        multi.clicked.connect(self.open_multi_links)
        tl.addWidget(multi)
        tl.addWidget(self.fetch_btn)
        lay.addWidget(top)

        # liste başlığı, sayaç rozetleri ve araçlar
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.list_title = ElidedLabel("Liste")
        self.list_title.setObjectName("h2")
        self.chip_total = Badge("", "neutral")
        self.chip_sel = Badge("", "info")
        self.chip_done = Badge("", "success")
        self.chip_err = Badge("", "error")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Listede ara…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.addAction(icon("magnify"), QLineEdit.LeadingPosition)
        self.filter_edit.setMinimumWidth(140)
        self.filter_edit.setMaximumWidth(220)
        self.filter_edit.textChanged.connect(self._apply_filter)
        sel_all = QPushButton()
        sel_all.setObjectName("iconBtn")
        sel_all.setToolTip("Tümünü seç")
        set_icon(sel_all, "checkbox-multiple-marked-outline", size=18)
        sel_all.clicked.connect(lambda: self._set_all_checked(True))
        sel_none = QPushButton()
        sel_none.setObjectName("iconBtn")
        sel_none.setToolTip("Seçimi kaldır")
        set_icon(sel_none, "checkbox-multiple-blank-outline", size=18)
        sel_none.clicked.connect(lambda: self._set_all_checked(False))
        bar.addWidget(self.list_title, 1)
        for chip in (self.chip_total, self.chip_sel, self.chip_done, self.chip_err):
            bar.addWidget(chip)
        bar.addSpacing(8)
        self.clean_btn = QPushButton("Adları Temizle")
        set_icon(self.clean_btn, "format-list-bulleted")
        self.clean_btn.setToolTip("Seçili öğelerin adlarından (Official Video), [HD], #etiket gibi kısımları kaldırır")
        self.clean_btn.clicked.connect(self.clean_names)
        bar.addWidget(self.filter_edit)
        bar.addWidget(self.clean_btn)
        bar.addWidget(sel_all)
        bar.addWidget(sel_none)
        lay.addLayout(bar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["", "#", "DOSYA ADI  ·  düzenlemek için çift tıklayın",
                                              "SÜRE", "BİÇİM", "DURUM", "İLERLEME"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(50)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for col, width in ((COL_CHECK, 40), (COL_NO, 44), (COL_DUR, 66), (COL_FMT, 84), (COL_STATE, 130),
                           (COL_PROGRESS, 230)):
            hh.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, width)
        hh.setSectionResizeMode(COL_TITLE, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)

        self.list_empty = EmptyState("download", "Henüz liste yok",
                                     "Yukarıya bir YouTube bağlantısı yapıştırıp Listele'ye tıklayın "
                                     "ya da tarayıcı eklentisiyle YouTube'dan doğrudan gönderin.")
        self.loading = LoadingView()
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.list_empty)
        self.list_stack.addWidget(self.loading)
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
        set_icon(self.retry_btn, "refresh")
        self.retry_btn.clicked.connect(self.retry_failed)
        self.retry_btn.hide()
        self.cancel_btn = QPushButton("Durdur")
        self.cancel_btn.setObjectName("danger")
        set_icon(self.cancel_btn, "stop", "#B42318")
        self.cancel_btn.clicked.connect(self.cancel_download)
        self.cancel_btn.hide()
        self.dl_btn = QPushButton("Seçilenleri İndir")
        self.dl_btn.setObjectName("primary")
        set_icon(self.dl_btn, "download", "#FFFFFF")
        self.dl_btn.setMinimumWidth(220)
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
        self.hist_search.addAction(icon("magnify"), QLineEdit.LeadingPosition)
        self.hist_search.setFixedWidth(280)
        self.hist_search.textChanged.connect(self._refresh_history)
        self.hist_count = Badge("", "neutral")
        hist_all = QPushButton()
        hist_all.setObjectName("iconBtn")
        hist_all.setToolTip("Tümünü seç / seçimi kaldır")
        set_icon(hist_all, "checkbox-multiple-marked-outline", size=18)
        hist_all.clicked.connect(self._toggle_history_selection)
        self.hist_delete_btn = QPushButton("Seçilenleri Sil")
        self.hist_delete_btn.setObjectName("danger")
        self.hist_delete_btn.setMinimumWidth(170)
        set_icon(self.hist_delete_btn, "delete-outline", "#B42318")
        self.hist_delete_btn.clicked.connect(lambda: self._delete_history(self._checked_history()))
        clear = QPushButton("Geçmişi Temizle")
        set_icon(clear, "delete-sweep-outline")
        clear.clicked.connect(self._clear_history)
        bar.addWidget(self.hist_search)
        bar.addWidget(self.hist_count)
        bar.addStretch()
        bar.addWidget(hist_all)
        bar.addWidget(self.hist_delete_btn)
        bar.addWidget(clear)
        lay.addLayout(bar)

        self.hist_table = QTableWidget(0, 5)
        self.hist_table.setHorizontalHeaderLabels(["", "TARİH", "BAŞLIK", "BİÇİM", "İŞLEMLER"])
        self.hist_table.verticalHeader().setVisible(False)
        self.hist_table.setAlternatingRowColors(True)
        self.hist_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hist_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hist_table.setShowGrid(False)
        self.hist_table.setFocusPolicy(Qt.NoFocus)
        self.hist_table.verticalHeader().setDefaultSectionSize(46)
        hh = self.hist_table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for col, width in ((0, 40), (1, 130), (3, 90), (4, 250)):
            hh.setSectionResizeMode(col, QHeaderView.Fixed)
            self.hist_table.setColumnWidth(col, width)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.hist_table.itemChanged.connect(lambda _: self._update_history_actions())
        self._hist_view: list[dict] = []

        self.hist_empty = EmptyState("history", "Geçmiş boş", "İndirdiğiniz dosyalar burada listelenir.")
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

        def section(title: str, icon_name: str, options: list[tuple[str, str, str]]) -> tuple[QFrame, QVBoxLayout]:
            box = card()
            v = QVBoxLayout(box)
            v.setContentsMargins(20, 16, 20, 16)
            v.setSpacing(12)
            head = QHBoxLayout()
            ic = QLabel()
            ic.setPixmap(icon(icon_name, ACCENT).pixmap(18, 18))
            t = QLabel(title)
            t.setObjectName("h2")
            head.addWidget(ic)
            head.addWidget(t)
            head.addStretch()
            v.addLayout(head)
            for key, label, hint in options:
                cb = QCheckBox(label)
                cb.setChecked(bool(self.settings[key]))
                cb.toggled.connect(lambda on, k=key: self._toggle_setting(k, on))
                v.addWidget(cb)
                if hint:
                    h = QLabel(hint)
                    h.setObjectName("small")
                    h.setWordWrap(True)
                    h.setContentsMargins(28, 0, 0, 4)
                    v.addWidget(h)
            return box, v

        box, _ = section("Dosyalar ve adlandırma", "folder-outline", [
            ("clean_titles", "Dosya adlarını otomatik temizle",
             "“Şarkı (Official Video) [HD] #pop” → “Şarkı”. Adı indirmeden önce listede çift tıklayarak "
             "da değiştirebilirsiniz; ad MP3 etiketine de yazılır."),
            ("playlist_folder", "Liste indirmelerinde liste adıyla alt klasör oluştur", ""),
            ("number_prefix", "Liste sırasını dosya adının başına ekle", "Örnek: 01 - Şarkı adı.mp3"),
            ("embed_thumbnail", "MP3 dosyalarına kapak resmi ve etiket bilgisi göm", ""),
        ])
        lay.addWidget(box)

        box, v = section("Tarayıcı entegrasyonu", "web", [
            ("browser_bridge", "Tarayıcı eklentisinden gelen bağlantıları kabul et",
             f"Yalnızca bu bilgisayardan (127.0.0.1:{PORT}) bağlantı kabul edilir; dış ağa kapalıdır."),
            ("show_bubble", "YouTube'da video açıldığında sağ alt köşede indirme balonu göster", ""),
            ("window_watch", "Eklenti kurulu olmasa da tarayıcıda açılan YouTube videolarını algıla",
             "Windows'ta tarayıcı penceresinin başlığı, macOS'ta öndeki sekmenin adresi okunur. Bu bilgi "
             "bilgisayarınızdan çıkmaz; Windows'ta yalnızca video başlığı YouTube'da aranır. macOS ilk "
             "kullanımda tarayıcıya erişim izni ister."),
        ])
        row = QHBoxLayout()
        row.setContentsMargins(28, 0, 0, 0)
        ext_btn = QPushButton("Eklentiyi Kur")
        ext_btn.setObjectName("primary")
        set_icon(ext_btn, "puzzle-outline", "#FFFFFF")
        ext_btn.clicked.connect(self.install_extension)
        self.ext_status = Badge("", "neutral")
        row.addWidget(ext_btn)
        row.addWidget(self.ext_status)
        row.addStretch()
        v.addLayout(row)
        lay.addWidget(box)

        box, v = section("Ağ ve proxy", "lan", [])
        prow = QHBoxLayout()
        prow.setSpacing(18)
        self.proxy_mode = QComboBox()
        for label, key in (("Sistem ayarlarını kullan", "system"), ("Proxy kullanma", "none"),
                           ("Özel proxy", "custom")):
            self.proxy_mode.addItem(label, key)
        self.proxy_mode.setCurrentIndex(max(self.proxy_mode.findData(self.settings["proxy_mode"]), 0))
        self.proxy_mode.currentIndexChanged.connect(self._proxy_changed)
        self.proxy_edit = QLineEdit(self.settings["proxy_url"])
        self.proxy_edit.setPlaceholderText("http://kullanıcı:parola@sunucu:8080  ·  socks5://sunucu:1080")
        self.proxy_edit.editingFinished.connect(self._proxy_changed)
        self.proxy_test = QPushButton("Bağlantıyı Test Et")
        set_icon(self.proxy_test, "lan-connect")
        self.proxy_test.clicked.connect(self._test_connection)
        prow.addWidget(field("Bağlantı", self.proxy_mode))
        purl = QHBoxLayout()
        purl.setSpacing(6)
        purl.addWidget(self.proxy_edit, 1)
        purl.addWidget(self.proxy_test)
        prow.addWidget(field("Proxy adresi", purl), 1)
        v.addLayout(prow)
        hint = QLabel("İndirme, YouTube hesabı ve güncelleme bağlantılarının tamamı bu ayarı kullanır. "
                      "HTTP, HTTPS ve SOCKS5 desteklenir.")
        hint.setObjectName("small")
        hint.setWordWrap(True)
        v.addWidget(hint)
        lay.addWidget(box)
        self._proxy_changed(save=False)

        box, _ = section("Bildirimler ve güncellemeler", "update", [
            ("notify_system", "Uygulama arka plandayken sistem bildirimi göster", ""),
            ("clipboard_watch", "Panodaki YouTube bağlantısını otomatik algıla",
             "Uygulamaya geri döndüğünüzde kopyaladığınız bağlantı kutuya eklenir."),
            ("auto_update", "Güncellemeleri otomatik denetle", "Açılışta ve uygulama açıkken yarım saatte bir denetlenir; yeni sürüm bulununca güncelleme penceresi açılır."),
            ("auto_install", "Yeni sürümü arka planda önceden indir",
             "Kurulum için her zaman size sorulur: Şimdi Kur ya da Daha Sonra Kur (uygulama kapanınca)."),
        ])
        lay.addWidget(box)

        box, il = section("Sistem", "information-outline", [])
        for k, v in (("Sürüm", __version__), ("ffmpeg", ffmpeg_path() or "bulunamadı"),
                     ("yt-dlp", yt_dlp.version.__version__), ("Ayar klasörü", str(config_dir()))):
            l = QLabel(f"<span style='color:#64748B'>{k}:</span> {v}")
            l.setTextInteractionFlags(Qt.TextSelectableByMouse)
            l.setWordWrap(True)
            il.addWidget(l)
        lay.addWidget(box)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _proxy_changed(self, *_, save: bool = True):
        mode = self.proxy_mode.currentData()
        self.proxy_edit.setEnabled(mode == "custom")
        if save:
            self.settings["proxy_mode"] = mode
            self.settings["proxy_url"] = self.proxy_edit.text().strip()
            self.settings.save()

    def _test_connection(self):
        self._proxy_changed()
        self.proxy_test.setEnabled(False)
        self.proxy_test.setText("Deneniyor…")
        self._conn_worker = ConnectionTestWorker(url_opener(self.settings))

        def done(ok: bool, msg: str):
            self.proxy_test.setEnabled(True)
            self.proxy_test.setText("Bağlantıyı Test Et")
            self.notify("Bağlantı başarılı" if ok else "Bağlantı kurulamadı", msg, "success" if ok else "error")

        self._conn_worker.done.connect(done)
        self._conn_worker.start()

    def install_extension(self):
        """Eklenti kurulum sihirbazını açar."""
        if self._wizard:
            self._wizard.raise_()
            return
        self._wizard = ExtensionWizard(self, self.settings["extension_seen"], self._ensure_bridge)
        self._wizard.open_account.connect(lambda: self._goto(PAGE_ACCOUNT))
        self._wizard.exec()
        self._wizard = None

    def _ensure_bridge(self):
        if not self.bridge.running:
            self.settings["browser_bridge"] = True
            self.settings.save()
            if not self.bridge.start():
                self.notify("Tarayıcı bağlantısı açılamadı",
                            f"{PORT} numaralı yerel bağlantı noktası başka bir uygulama tarafından kullanılıyor.", "error")

    def _on_extension_hello(self, info: dict):
        first = self.settings["extension_seen"] != info
        self.settings["extension_seen"] = info
        self.settings.save()
        self._refresh_extension_status()
        if self._wizard:
            self._wizard.on_hello(info)
        elif first:
            self.notify("Tarayıcı eklentisi bağlandı", f"v{info.get('version', '')}", "success")

    def _refresh_extension_status(self):
        info = self.settings["extension_seen"]
        if info and info.get("version"):
            name = BROWSERS.get(info.get("browser"), ("Tarayıcı",))[0]
            self.ext_status.set(f"✓ Kurulu · {name} · v{info['version']}", "success")
        else:
            self.ext_status.set("Kurulu değil", "neutral")

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
        if idx == PAGE_ACCOUNT:
            self.account_page.on_shown()
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
        if key == "window_watch":
            self._start_watcher() if on else self._stop_watcher()
        if key == "browser_bridge":
            if on and not self.bridge.start():
                self.notify("Tarayıcı bağlantısı açılamadı",
                            f"{PORT} numaralı yerel bağlantı noktası başka bir uygulama tarafından kullanılıyor.",
                            "error")
            elif not on:
                self.bridge.stop()

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
        for r in range(len(self.rows)):
            self._update_fmt_badge(r)
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
    def load_url(self, url: str):
        """Bağlantıyı İndir sayfasında açar ve listeler (hesap sayfası, balon, eklenti)."""
        self._goto(PAGE_DOWNLOAD)
        self._bring_front()
        self.url_edit.setText(url)
        self.fetch()

    def fetch(self):
        url = self.url_edit.text().strip()
        if not url or self.info_worker:
            return
        links = find_links(url)
        if len(links) > 1 or (links and self.dl_worker):
            # birden fazla bağlantı ya da indirme sürerken: mevcut listenin sonuna ekle
            self.url_edit.clear()
            self.add_links(links)
            return
        if self.dl_worker:
            self.notify("İndirme sürüyor", "Bağlantı tanınmadı; YouTube video ya da liste bağlantısı girin.", "warning")
            return
        self._last_clip = url
        link = analyze(url)
        target = link.fetch_url
        if link.kind == "mix":
            self.notify("Otomatik karışık liste algılandı",
                        "Bu bağlantı YouTube'un öneri listesi (Mix) içeriyor; yalnızca bu video eklendi.", "info")
        elif link.kind == "both":
            box = QMessageBox(self)
            box.setWindowTitle("Video mu, liste mi?")
            box.setText("Bu bağlantı hem bir video hem de bir oynatma listesi içeriyor.")
            box.setInformativeText("Yalnızca bu videoyu mu, yoksa listenin tamamını mı eklemek istersiniz?")
            only = box.addButton("Yalnızca bu video", QMessageBox.AcceptRole)
            whole = box.addButton("Tüm liste", QMessageBox.ActionRole)
            box.addButton("Vazgeç", QMessageBox.RejectRole)
            box.setDefaultButton(only)
            box.exec()
            if box.clickedButton() is whole:
                target = link.playlist_url
            elif box.clickedButton() is not only:
                return

        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Yükleniyor…")
        self.loading.start("Bağlantı çözümleniyor",
                           f"Bilgiler YouTube'dan alınıyor · {target[:90]}")
        self.list_stack.setCurrentWidget(self.loading)
        self._set_status("● Çözümleniyor", "info", pulse=True)
        self.info_worker = InfoWorker(target, ydl_base_opts(self.settings, with_account=False),
                                      account_opts(self.settings))
        self.info_worker.result.connect(self._on_info)
        self.info_worker.failed.connect(self._on_info_failed)
        self.info_worker.finished.connect(self._fetch_done)
        self.info_worker.start()

    def _fetch_done(self):
        self.info_worker = None
        self.loading.stop()
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Listele")

    def _on_info_failed(self, msg: str):
        self._set_status("Hazır", "neutral")
        self.list_empty.set("alert-outline", "Bağlantı çözümlenemedi", msg[:300])
        self.list_stack.setCurrentWidget(self.table if self.rows else self.list_empty)
        self.notify("Bağlantı çözümlenemedi", msg[:160], "error")

    def _display_name(self, title: str) -> str:
        return clean_title(title) if self.settings["clean_titles"] else title

    def _append_row(self, it: dict) -> int:
        """Tabloya bir öğe ekler; satır numarasını döndürür."""
        i = self.table.rowCount()
        it.setdefault("name", self._display_name(it["title"]))
        self.table.blockSignals(True)
        self.table.insertRow(i)
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        chk.setCheckState(Qt.Checked)
        self.table.setItem(i, COL_CHECK, chk)
        no = QTableWidgetItem(str(i + 1))
        no.setFlags(Qt.ItemIsEnabled)
        no.setForeground(Qt.gray)
        self.table.setItem(i, COL_NO, no)
        t = QTableWidgetItem(it["name"])
        t.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        t.setToolTip(f"YouTube başlığı: {it['title']}\n{it.get('uploader') or ''}".strip())
        self.table.setItem(i, COL_TITLE, t)
        d = QTableWidgetItem(fmt_duration(it.get("duration")))
        d.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(i, COL_DUR, d)
        self.rows.append(self._make_row_widgets(i))
        self._set_row_state(i, "waiting")
        self.table.blockSignals(False)
        return i

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() == COL_TITLE and item.row() < len(self.playlist["items"]):
            it = self.playlist["items"][item.row()]
            name = safe_filename(item.text()) if item.text().strip() else ""
            self.table.blockSignals(True)
            if name:
                it["name"] = name
                it["custom"] = True
                item.setText(name)
            else:
                item.setText(it["name"])  # boş ad kabul edilmez
            self.table.blockSignals(False)
        self._update_counts()

    def _on_info(self, data: dict):
        self.playlist = data
        items = data["items"]
        for i, it in enumerate(items):
            it["playlist_title"] = data["title"] if data["is_playlist"] else None
            it["index"] = i + 1
        self.table.setRowCount(0)
        self.rows = []
        for it in items:
            self._append_row(it)
        self.filter_edit.clear()

        if data["is_playlist"]:
            self.list_title.setText(data["title"] or "Oynatma listesi")
        else:
            self.list_title.setText("Video")
        self.list_title.setToolTip(data["title"])
        self.list_stack.setCurrentWidget(self.table if items else self.list_empty)
        if not items:
            self.list_empty.set("alert-outline", "Liste boş", "Bu bağlantıda indirilebilir öğe bulunamadı.")
        self._set_status("Hazır", "neutral")
        self.overall_bar.setValue(0)
        self.overall_label.setText("İndirme bekleniyor")
        self._update_counts()
        kind = "Liste yüklendi" if data["is_playlist"] else "Video bulundu"
        self.notify(kind, f"{len(items)} öğe listelendi. Dosya adını değiştirmek için ada çift tıklayın.", "success")

    def clean_names(self):
        """Seçili satırların adlarını YouTube başlığından yeniden temizler."""
        rows = self._checked_rows()
        self.table.blockSignals(True)
        for r in rows:
            it = self.playlist["items"][r]
            it["name"] = clean_title(it["title"])
            self.table.item(r, COL_TITLE).setText(it["name"])
        self.table.blockSignals(False)
        self.notify("Adlar düzenlendi", f"{len(rows)} öğenin adı etiketlerden temizlendi.", "success")

    def _make_row_widgets(self, r: int) -> dict:
        badge = Badge()
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(6, 0, 6, 0)
        wl.addWidget(badge)
        wl.addStretch()
        self.table.setCellWidget(r, COL_STATE, wrap)

        fmt_wrap = QWidget()
        fl = QHBoxLayout(fmt_wrap)
        fl.setContentsMargins(6, 0, 6, 0)
        fmt_badge = Badge()
        fl.addWidget(fmt_badge)
        fl.addStretch()
        self.table.setCellWidget(r, COL_FMT, fmt_wrap)

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
        return {"badge": badge, "fmt_badge": fmt_badge, "bar": bar, "detail": detail, "state": "", "pct": 0.0,
                "path": None}

    def _row_format(self, r: int) -> str:
        """Satırın biçimi: indirmesi başlamış ya da balondan seçilmişse kendi biçimi, yoksa seçili biçim."""
        it = self.playlist["items"][r]
        if it.get("format") and (it.get("single") or self.rows[r]["state"] not in ("waiting", "cancelled")):
            return it["format"]
        return self.settings["format"]

    def _update_fmt_badge(self, r: int):
        text, kind = FORMAT_BADGES.get(self._row_format(r), FORMAT_BADGES["mp3"])
        self.rows[r]["fmt_badge"].set(text, kind)

    def _set_row_state(self, r: int, state: str, msg: str = ""):
        row = self.rows[r]
        row["state"] = state
        if r < len(self.playlist["items"]):
            self._update_fmt_badge(r)
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
        row["error"] = msg if state == "error" else ""
        row["badge"].setToolTip(msg if state == "error" else "")
        detail.setText(msg)
        detail.setToolTip(msg)
        # indirme başladıktan sonra ad değiştirilemez
        item = self.table.item(r, COL_TITLE)
        if item:
            editable = state in ("waiting", "error", "cancelled")
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | (Qt.ItemIsEditable if editable else Qt.NoItemFlags)
            item.setFlags(flags)

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
            it = self.playlist["items"][r]
            hay = f"{self.table.item(r, COL_TITLE).text()} {it['title']}".casefold()
            self.table.setRowHidden(r, bool(q) and q not in hay)

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
        ready = len(self._ready_rows()) if total else 0
        self.dl_btn.setEnabled(ready > 0)
        label = "Kuyruğa Ekle" if self.dl_worker else "Seçilenleri İndir"
        self.dl_btn.setText(f"{label} ({ready})" if ready else label)
        self.retry_btn.setVisible(err > 0)
        self.clean_btn.setEnabled(checked > 0)

    def _ready_rows(self) -> list[int]:
        """Seçili olup henüz indirilmemiş ve kuyrukta olmayan satırlar."""
        return [r for r in self._checked_rows() if self.rows[r]["state"] not in BUSY + ("done",)]

    # ============================================================ indirme
    def _make_job(self, r: int) -> dict:
        it = self.playlist["items"][r]
        self.rows[r].update(pct=0.0, path=None)
        self._set_row_state(r, "queued", "Sırada")
        if not (it.get("single") and it.get("format")):
            it["format"] = self.settings["format"]
        named = it.get("resolved", True) or it.get("custom")
        return {"row": r, "url": it["url"], "index": it.get("index") or r + 1, "format": it["format"],
                "name": it.get("name") if named else None, "playlist_title": it.get("playlist_title"),
                "clean": self.settings["clean_titles"]}

    def start_download(self, rows: list[int] | None = None):
        rows = self._ready_rows() if rows is None else [r for r in rows if self.rows[r]["state"] not in BUSY]
        if not rows:
            return
        if not ffmpeg_path():
            self.notify("ffmpeg bulunamadı", "Dönüştürme yapılamıyor.", "error")
            return
        jobs = [self._make_job(r) for r in rows]
        what = f"“{self.playlist['items'][rows[0]]['name']}”" if len(rows) == 1 else f"{len(rows)} öğe"

        if self.dl_worker:  # çalışan kuyruğa ekle
            if self.dl_worker.add_jobs(jobs):
                self._batch += rows
            else:
                self._pending_rows += rows
            self._update_overall()
            self._update_counts()
            self.notify("Kuyruğa eklendi", what, "info")
            return

        s = self.settings
        opts = {
            "download_dir": s["download_dir"], "format": s["format"],
            "audio_quality": s["audio_quality"], "video_quality": s["video_quality"],
            "playlist_folder": s["playlist_folder"], "number_prefix": s["number_prefix"],
            "embed_thumbnail": s["embed_thumbnail"],
        }
        self._batch = rows
        self._cancelled = False
        self.dl_worker = DownloadWorker(jobs, opts, ydl_base_opts(s, with_account=False), workers=s["concurrent"],
                                        account_opts=account_opts(s))
        self.dl_worker.progress.connect(self._on_progress)
        self.dl_worker.state.connect(self._on_state)
        self.dl_worker.saved.connect(lambda r, p: self.rows[r].__setitem__("path", p))
        self.dl_worker.finished_all.connect(self._on_finished)
        self._set_busy(True)
        self._update_overall()
        self.dl_worker.start()
        self.notify("İndirme başladı", f"{what} · {self._format_desc()} · aynı anda {s['concurrent']} dosya",
                    "info", system=True)

    def _concurrency_changed(self):
        n = self.conc_combo.currentData()
        self.settings["concurrent"] = n
        self.settings.save()
        if self.dl_worker:
            self.dl_worker.set_workers(n)

    # ------------------------------------------------------ bağlantı ekleme
    def open_multi_links(self):
        text = self.url_edit.text().strip()
        dlg = MultiLinkDialog(self, "\n".join(find_links(text)))
        if dlg.exec() and dlg.links():
            self.url_edit.clear()
            self.add_links(dlg.links(), start=dlg.start_now)

    def _show_table(self):
        if self.list_stack.currentWidget() is not self.table:
            if not self.rows:
                self.playlist = {"is_playlist": False, "title": "", "items": []}
            self.list_title.setText("İndirme listesi")
            self.list_stack.setCurrentWidget(self.table)

    def add_links(self, urls: list[str], start: bool = False):
        """Bağlantıları mevcut listenin sonuna ekler; bilgiler arka planda paralel alınır."""
        if not urls:
            return
        self._show_table()
        known = {it["url"] for it in self.playlist["items"]}
        tasks, new_rows, lists, skipped = [], [], 0, 0
        for url in urls:
            link = analyze(url)
            if link.kind == "playlist":
                tasks.append((("list", start), link.playlist_url))
                lists += 1
                continue
            target = link.video_url or url  # "both" ve "mix" bağlantılarında yalnızca video
            if target in known:
                skipped += 1
                continue
            known.add(target)
            it = {"title": target, "url": target, "duration": None, "uploader": "", "single": True,
                  "resolved": False}
            self.playlist["items"].append(it)
            r = self._append_row(it)
            self.rows[r]["detail"].setText("Bilgiler alınıyor…")
            tasks.append((r, target))
            new_rows.append(r)

        if tasks:
            worker = MultiInfoWorker(tasks, ydl_base_opts(self.settings, with_account=False),
                                     account_opts=account_opts(self.settings))
            worker.resolved.connect(self._on_link_resolved)
            worker.failed.connect(self._on_link_failed)
            worker.finished.connect(lambda w=worker: self._resolvers.remove(w))
            self._resolvers.append(worker)
            worker.start()
        if start and new_rows:
            self.start_download(new_rows)
        parts = [f"{len(new_rows)} video"] if new_rows else []
        if lists:
            parts.append(f"{lists} liste (öğeleri ekleniyor)")
        if skipped:
            parts.append(f"{skipped} tekrar atlandı")
        self.notify("Bağlantılar eklendi", " · ".join(parts) or "Yeni bağlantı yok", "success" if parts else "neutral")
        self._update_counts()

    def _on_link_resolved(self, key, data: dict):
        if isinstance(key, int):  # tek video satırı
            r = key
            if not data["items"] or r >= len(self.playlist["items"]):
                return
            it, info = self.playlist["items"][r], data["items"][0]
            it.update(title=info["title"], duration=info["duration"], uploader=info["uploader"], resolved=True)
            if not it.get("custom"):
                it["name"] = self._display_name(info["title"])
            self.table.blockSignals(True)
            cell = self.table.item(r, COL_TITLE)
            cell.setText(it["name"])
            cell.setToolTip(f"YouTube başlığı: {it['title']}\n{it['uploader']}".strip())
            self.table.item(r, COL_DUR).setText(fmt_duration(it["duration"]))
            self.table.blockSignals(False)
            if self.rows[r]["state"] == "waiting":
                self.rows[r]["detail"].setText("")
        else:  # oynatma listesi: öğeleri sona ekle
            _, start = key
            known = {it["url"] for it in self.playlist["items"]}
            new_rows = []
            for i, info in enumerate(data["items"]):
                if info["url"] in known:
                    continue
                it = {**info, "playlist_title": data["title"] or None, "index": i + 1}
                self.playlist["items"].append(it)
                new_rows.append(self._append_row(it))
            self.notify("Liste eklendi", f"{data['title'] or 'Oynatma listesi'} · {len(new_rows)} öğe", "success")
            if start and new_rows:
                self.start_download(new_rows)
        self._update_counts()

    def _on_link_failed(self, key, msg: str):
        if isinstance(key, int):
            if self.rows[key]["state"] == "waiting":
                self._set_row_state(key, "error", msg)
        else:
            self.notify("Liste alınamadı", msg[:160], "error")
        self._update_counts()

    def quick_add(self, item: dict, fmt: str | None = None):
        """Tarayıcıdan gelen tek videoyu listeye ekleyip indirir."""
        link = analyze(item["url"])
        if item.get("kind") == "playlist" or link.kind == "playlist":
            self.load_url(item["url"])
            return
        url = link.video_url or item["url"]
        fmt = fmt or self.settings["format"]
        for r, it in enumerate(self.playlist["items"]):
            if it["url"] == url and self.rows[r]["state"] in BUSY:
                self.notify("Zaten sırada", it["name"], "neutral")
                return
        self._show_table()
        it = {"title": item.get("title") or url, "url": url, "duration": None, "uploader": "",
              "single": True, "format": fmt}
        self.playlist["items"].append(it)
        r = self._append_row(it)
        self.start_download([r])
        self._update_counts()

    def _on_detected(self, item: dict):
        if not self.settings["show_bubble"] or item["url"] in self._seen_urls:
            return
        self._seen_urls.add(item["url"])
        self.bubble.show_item({**item, "title": self._display_name(item["title"])}, self.settings["format"])

    def _start_watcher(self):
        if self.watcher and self.watcher.isRunning():
            return
        self.watcher = BrowserWatcher(lambda: ydl_base_opts(self.settings, with_account=False))
        self.watcher.detected.connect(self._on_detected)
        self.watcher.start()

    def _stop_watcher(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher.wait(3000)
            self.watcher = None

    def _on_cookies_received(self, path: str, count: int):
        self._bring_front()
        self._goto(PAGE_ACCOUNT)
        self.notify("YouTube oturumu aktarıldı", "Kitaplığınız yükleniyor…", "success")
        self.account_page.on_cookies_received(path, count)

    def _on_add_requested(self, item: dict):
        self._seen_urls.add(item["url"])
        self.bubble.dismiss()
        self.quick_add(item, item.get("format"))

    def _set_busy(self, busy: bool):
        # Biçim ve kalite çalışan kuyruğun ayarlarıdır; indirme sürerken değiştirilemez.
        for w in (self.seg, self.quality_combo, self.dir_btn):
            w.setEnabled(not busy)
        self.cancel_btn.setVisible(busy)
        self.cancel_btn.setEnabled(True)
        self._update_counts()

    def retry_failed(self):
        rows = [i for i, r in enumerate(self.rows) if r["state"] == "error"]
        self.start_download(rows)

    def cancel_download(self):
        if self.dl_worker:
            self._cancelled = True
            for r in self._pending_rows:
                self._set_row_state(r, "cancelled", "İptal edildi")
            self._pending_rows = []
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
                self.history.add(item.get("name") or item["title"], item["url"], row["path"],
                                 item.get("format") or self.settings["format"])
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
        if self._pending_rows and not self._cancelled:
            # kuyruk kapanırken eklenenler: aynı parti içinde yeni bir kuyrukla devam et
            pending, self._pending_rows = self._pending_rows, []
            batch = self._batch
            self.dl_worker = None
            self.start_download(pending)
            self._batch = batch + pending
            return
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
            reason = next((r["error"] for r in rows if r.get("error")), "")
            what = "İndirilemedi" if err == 1 else f"{err} öğe indirilemedi"
            self.notify("İndirme başarısız", f"{what}: {reason}" if reason else what, "error",
                        action=("Yeniden dene", self.retry_failed), system=True)
        else:
            self._set_status("Tamamlandı (hatalı)", "processing")
            reason = next((r["error"] for r in rows if r.get("error")), "")
            self.notify("İndirme tamamlandı", f"{ok} başarılı · {err} hatalı. {reason}".strip(),
                        "warning", action=("Yeniden dene", self.retry_failed), system=True)
        QTimer.singleShot(6000, lambda: self.dl_worker is None and self._set_status("Hazır", "neutral"))
        if self.update_info and not self._update_prompted:
            QTimer.singleShot(2500, lambda: self.dl_worker is None and self._prompt_update())
        QApplication.alert(self)

    # ============================================================= geçmiş
    def _refresh_history(self):
        q = self.hist_search.text().casefold().strip()
        items = [h for h in self.history.items if q in h["title"].casefold()]
        self._hist_view = items
        self.hist_count.set(f"{len(self.history.items)} kayıt", "neutral")
        self.hist_table.blockSignals(True)
        self.hist_table.setRowCount(0)
        for i, h in enumerate(items):
            self.hist_table.insertRow(i)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            self.hist_table.setItem(i, 0, chk)
            try:
                date = datetime.fromisoformat(h["date"]).strftime("%d.%m.%Y %H:%M")
            except ValueError:
                date = h["date"]
            d = QTableWidgetItem(date)
            d.setForeground(Qt.gray)
            self.hist_table.setItem(i, 1, d)
            t = QTableWidgetItem(h["title"])
            t.setToolTip(h["path"])
            self.hist_table.setItem(i, 2, t)

            bw = QWidget()
            bl = QHBoxLayout(bw)
            bl.setContentsMargins(6, 0, 6, 0)
            bl.addWidget(format_badge(h.get("format", "mp3")))
            bl.addStretch()
            self.hist_table.setCellWidget(i, 3, bw)

            aw = QWidget()
            al = QHBoxLayout(aw)
            al.setContentsMargins(4, 0, 8, 0)
            al.setSpacing(4)
            if Path(h["path"]).exists():
                play = QPushButton("Aç")
                play.setObjectName("link")
                set_icon(play, "play-circle-outline", ACCENT)
                play.setCursor(Qt.PointingHandCursor)
                play.clicked.connect(lambda _=False, p=h["path"]: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
                show = QPushButton("Klasörde göster")
                show.setObjectName("link")
                set_icon(show, "folder-open-outline", ACCENT)
                show.setCursor(Qt.PointingHandCursor)
                show.clicked.connect(lambda _=False, p=h["path"]: reveal_in_folder(p))
                al.addWidget(play)
                al.addWidget(show)
            else:
                al.addWidget(Badge("Dosya yok", "error"))
            al.addStretch()
            delete = QPushButton()
            delete.setObjectName("rowDelete")
            delete.setToolTip("Bu kaydı sil")
            delete.setCursor(Qt.PointingHandCursor)
            set_icon(delete, "trash-can-outline", "#98A2B3", 17)
            delete.clicked.connect(lambda _=False, e=h: self._delete_history([e]))
            al.addWidget(delete)
            self.hist_table.setCellWidget(i, 4, aw)
        self.hist_table.blockSignals(False)
        self._update_history_actions()

        if items:
            self.hist_stack.setCurrentWidget(self.hist_table)
        else:
            self.hist_empty.set("history", "Sonuç yok" if q else "Geçmiş boş",
                                "Aramanızla eşleşen kayıt bulunamadı." if q
                                else "İndirdiğiniz dosyalar burada listelenir.")
            self.hist_stack.setCurrentWidget(self.hist_empty)

    def _checked_history(self) -> list[dict]:
        return [self._hist_view[r] for r in range(self.hist_table.rowCount())
                if self.hist_table.item(r, 0).checkState() == Qt.Checked]

    def _update_history_actions(self):
        n = len(self._checked_history())
        self.hist_delete_btn.setEnabled(n > 0)
        self.hist_delete_btn.setText(f"Seçilenleri Sil ({n})" if n else "Seçilenleri Sil")

    def _toggle_history_selection(self):
        rows = range(self.hist_table.rowCount())
        on = any(self.hist_table.item(r, 0).checkState() != Qt.Checked for r in rows)
        self.hist_table.blockSignals(True)
        for r in rows:
            self.hist_table.item(r, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.hist_table.blockSignals(False)
        self._update_history_actions()

    def _delete_history(self, entries: list[dict]):
        """Kayıtları siler; kullanıcı isterse dosyaları da Geri Dönüşüm Kutusu'na taşır."""
        if not entries:
            return
        existing = [e for e in entries if Path(e["path"]).exists()]
        box = QMessageBox(self)
        box.setWindowTitle("Kayıtları sil")
        box.setIconPixmap(icon("trash-can-outline", "#B42318").pixmap(40, 40))
        if len(entries) == 1:
            box.setText(f"“{entries[0]['title']}” geçmişten silinsin mi?")
        else:
            box.setText(f"{len(entries)} kayıt geçmişten silinsin mi?")
        files = None
        if existing:
            files = QCheckBox(f"İndirilen dosyaları da sil ({len(existing)} dosya {TRASH_NAME}'na taşınır)")
            box.setCheckBox(files)
            box.setInformativeText("İşaretlemezseniz yalnızca kayıtlar silinir, dosyalar bilgisayarınızda kalır.")
        delete_btn = box.addButton("Sil", QMessageBox.DestructiveRole)
        delete_btn.setObjectName("dangerSolid")
        cancel = box.addButton("Vazgeç", QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is not delete_btn:
            return

        moved = failed = 0
        if files is not None and files.isChecked():
            for e in existing:
                if move_to_trash(e["path"]):
                    moved += 1
                else:
                    failed += 1
        removed = self.history.remove(entries)
        self._refresh_history()

        text = f"{len(removed)} kayıt silindi" if len(removed) > 1 else "Kayıt silindi"
        if moved:
            text += f" · {moved} dosya {TRASH_NAME}'na taşındı"
        if failed:
            text += f" · {failed} dosya taşınamadı"
        undo = None if moved else ("Geri al", lambda: (self.history.restore(removed), self._refresh_history()))
        self.notify(text, "", "warning" if failed else "neutral", action=undo)

    def _clear_history(self):
        self._delete_history(list(self.history.items))

    # ================================================ güncelleme / diğer
    def open_developer(self):
        DeveloperDialog(self.logbuf, self).exec()

    def _on_update_nav(self):
        if self.update_info:
            self._prompt_update()
        else:
            self.check_updates(silent=False)

    def check_updates(self, silent: bool):
        if self.up_worker and self.up_worker.isRunning():
            return
        self.up_worker = updater.UpdateCheckWorker(url_opener(self.settings))
        self.up_worker.available.connect(self._on_update_available)
        if not silent:
            self.up_worker.up_to_date.connect(
                lambda: self.notify("Uygulama güncel", f"En son sürümü kullanıyorsunuz (v{__version__}).", "success"))
            self.up_worker.failed.connect(
                lambda m: self.notify("Güncelleme denetlenemedi", m, "warning"))
        self.up_worker.start()

    def _can_self_update(self) -> bool:
        return bool(self.update_info and self.update_info["url"] and updater.is_frozen())

    def _on_update_available(self, info: dict):
        """Yeni sürüm bulundu. Kurulum yalnızca kullanıcının seçimiyle yapılır.
        Her zaman en son sürümün tam kurulum dosyası kullanılır; aradaki sürümler tek tek kurulmaz."""
        if self.update_info:
            if updater.parse_version(info["version"]) <= updater.parse_version(self.update_info["version"]):
                return  # bu sürüm (ya da daha yenisi) zaten işleniyor
            # Daha yeni bir sürüm çıktı: eski sürüm için hazırlanan dosyayı bırak, doğrudan en yenisine geç
            logging.getLogger("byk.updater").info("v%s yerine doğrudan v%s kullanılacak",
                                                  self.update_info["version"], info["version"])
            self._discard_pending_update()
            self.update_info = info
            self.nav_update.set_badge("Yeni", "success")
            if self._install_on_exit or self._ask_when_ready:
                # kullanıcı kurulumu zaten onaylamıştı: en yeni sürümü hazırla, yeniden sorma
                if self._can_self_update():
                    self._download_update()
                self._refresh_banner()
                self.notify("Daha yeni sürüm bulundu", f"Doğrudan en son sürüm v{info['version']} kurulacak.", "info")
                return
        self.update_info = info
        self._update_prompted = False
        self.nav_update.set_badge("Yeni", "success")
        self._refresh_banner()
        if self.tray and self.tray.isVisible() and not self.isActiveWindow():
            self.tray.showMessage("Yeni sürüm hazır", f"BYK Music v{info['version']} yayınlandı.",
                                  QSystemTrayIcon.Information, 6000)
        if self.settings["auto_install"] and self._can_self_update():
            self._download_update()  # yalnızca önceden indirir; kurmak için her zaman sorulur
        if self.dl_worker:
            # kullanıcının indirmesini bölme: şerit görünür, pencere indirmeler bitince açılır
            self.notify("Yeni sürüm hazır", f"v{info['version']} · indirmeleriniz bitince size sorulacak.", "info")
            return
        QTimer.singleShot(400, self._prompt_update)

    def _prompt_update(self):
        """Güncelleme penceresini açar ve kullanıcıya ne zaman kurulacağını sorar."""
        if self._update_dialog_open or not self.update_info:
            return
        self._update_prompted = True
        self._update_dialog_open = True
        self._bring_front()
        dlg = UpdateDialog(self.update_info, __version__, self, ready=bool(self._pending_update))
        dlg.update_requested.connect(lambda: self._start_update_download(dlg))
        self._active_update_dialog = dlg
        dlg.exec()
        self._active_update_dialog = None
        self._update_dialog_open = False
        self._after_update_dialog(dlg)

    def _start_update_download(self, dlg: UpdateDialog):
        """Kullanıcı Şimdi Kur'a bastı ve dosya henüz hazır değil: indir, bitince kur."""
        if not self._can_self_update():
            QDesktopServices.openUrl(QUrl(self.update_info["page"]))
            dlg.reject()
            return
        if self._pending_update:
            dlg.accept()
            return
        dlg.set_downloading()
        running = self.up_dl_worker and self.up_dl_worker.isRunning()
        if running:  # önceden indirme sürüyor: aynı indirmeyi pencerede göster
            self.up_dl_worker.progress.connect(dlg.set_progress)
        else:
            self._download_update(dlg)

    def _discard_pending_update(self):
        """Eski sürüm için indirilmiş ya da inmekte olan dosyayı geçersiz kılar."""
        if self._pending_update:
            try:
                Path(self._pending_update).unlink()
            except OSError:
                pass
        self._pending_update = None
        if self.up_dl_worker and self.up_dl_worker.isRunning():
            self._stale_workers.append(self.up_dl_worker)  # sonucu yok sayılır
            self.up_dl_worker = None

    def _download_update(self, dlg: UpdateDialog | None = None):
        """Güncelleme dosyasını indirir. Kurulum burada yapılmaz."""
        if self.up_dl_worker and self.up_dl_worker.isRunning():
            return
        info = self.update_info
        version = info["version"]
        self.up_dl_worker = updater.UpdateDownloadWorker(info["url"], info["name"], url_opener(self.settings))
        self.up_dl_worker.progress.connect(lambda pct: self._refresh_banner(pct))
        if dlg:
            self.up_dl_worker.progress.connect(dlg.set_progress)

        def failed(msg):
            if not self.update_info or self.update_info["version"] != version:
                return
            self._refresh_banner()
            box = self._active_update_dialog
            if box and box.isVisible():
                box.set_failed(msg)
            elif self._install_on_exit or self._ask_when_ready:
                self.notify("Güncelleme indirilemedi", msg[:160], "error")

        def done(path):
            if not self.update_info or self.update_info["version"] != version:
                try:
                    Path(path).unlink()  # bu arada daha yeni sürüm çıktı; eski dosya kullanılmaz
                except OSError:
                    pass
                return
            self._pending_update = path
            self.nav_update.set_badge("Hazır", "success")
            self._refresh_banner()
            box = self._active_update_dialog
            if box and box.isVisible():
                if box.choice == "now":
                    box.accept()  # kullanıcı Şimdi Kur demişti → pencere kapanınca kurulur
                else:
                    box.set_ready()
            elif self._ask_when_ready:
                self._ask_when_ready = False
                if not self.dl_worker:
                    QTimer.singleShot(300, self._prompt_update)

        self.up_dl_worker.failed.connect(failed)
        self.up_dl_worker.done.connect(done)
        self.up_dl_worker.start()

    def _after_update_dialog(self, dlg: UpdateDialog):
        if dlg.choice == "now" and self._pending_update:
            self._install_now()
        elif dlg.choice == "later":
            self._install_on_exit = True
            if not self._pending_update and self._can_self_update():
                self._download_update()
            self._refresh_banner()
            self.notify("Güncelleme planlandı", "Yeni sürüm, uygulamayı kapattığınızda kurulacak.", "info")
        elif dlg.choice == "background":
            self._ask_when_ready = True  # indirme bitince yeniden sorulur
            self.notify("Güncelleme indiriliyor", "İndirme bitince kurulum için size sorulacak.", "info")

    def _install_now(self):
        if self.dl_worker and QMessageBox.question(
                self, "Güncellemeyi kur",
                "Süren indirmeler durdurulacak ve uygulama yeniden başlatılacak. Devam edilsin mi?") != QMessageBox.Yes:
            return
        if self.dl_worker:
            self.dl_worker.cancel()
            self.dl_worker.wait(3000)
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
        self.bridge.stop()
        self._stop_watcher()
        self.bubble.close()
        if self._install_on_exit:  # yalnızca kullanıcı "Daha Sonra Kur" dediyse
            self._install_pending(relaunch=False)
        event.accept()
