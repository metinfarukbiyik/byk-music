import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..core.account import LibraryWorker
from ..core.net import BROWSERS, ydl_base_opts
from .icons import pixmap, set_icon
from .styles import ACCENT
from .widgets import Badge, EmptyState, Segmented, card, field

KIND_ICONS = {"liked": "thumb-up-outline", "later": "clock-outline", "playlist": "playlist-music"}


class AccountPage(QWidget):
    """YouTube oturumu ve kitaplık (beğenilenler, daha sonra izle, oynatma listeleri)."""

    def __init__(self, settings, notify, open_url):
        super().__init__()
        self.setObjectName("page")
        self.settings = settings
        self.notify = notify
        self.open_url = open_url
        self.worker = None
        self._loaded = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 20)
        lay.setSpacing(14)
        h = QLabel("YouTube Hesabım")
        h.setObjectName("h1")
        s = QLabel("Beğendiğiniz videolara ve oynatma listelerinize erişin, doğrudan indirin.")
        s.setObjectName("muted")
        lay.addWidget(h)
        lay.addWidget(s)

        # --- bağlantı kartı
        conn = card()
        cl = QVBoxLayout(conn)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(12)

        head = QHBoxLayout()
        yt = QLabel()
        yt.setPixmap(pixmap("youtube", 26, "#FF0000"))
        title = QLabel("Hesap bağlantısı")
        title.setObjectName("h2")
        self.status = Badge("Bağlı değil", "neutral")
        head.addWidget(yt)
        head.addWidget(title)
        head.addWidget(self.status)
        head.addStretch()
        self.refresh_btn = QPushButton("Yenile")
        set_icon(self.refresh_btn, "refresh")
        self.refresh_btn.clicked.connect(self.connect_account)
        self.logout_btn = QPushButton("Bağlantıyı Kes")
        self.logout_btn.setObjectName("danger")
        set_icon(self.logout_btn, "logout", "#B42318")
        self.logout_btn.clicked.connect(self.disconnect_account)
        self.connect_btn = QPushButton("Bağlan")
        self.connect_btn.setObjectName("primary")
        set_icon(self.connect_btn, "login", "#FFFFFF")
        self.connect_btn.clicked.connect(self.connect_account)
        head.addWidget(self.refresh_btn)
        head.addWidget(self.logout_btn)
        head.addWidget(self.connect_btn)
        cl.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(18)
        self.method = Segmented([("Tarayıcı oturumu", "browser"), ("cookies.txt dosyası", "file")])
        self.method.changed.connect(self._method_changed)
        row.addWidget(field("Yöntem", self.method))

        self.browser = QComboBox()
        for label, key in BROWSERS:
            if key == "safari" and sys.platform != "darwin":
                continue
            self.browser.addItem(label, key)
        self.browser.setMinimumWidth(170)
        self.profile = QLineEdit()
        self.profile.setPlaceholderText("Varsayılan profil")
        self.profile.setFixedWidth(170)
        self.browser_box = QWidget()
        bl = QHBoxLayout(self.browser_box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(18)
        bl.addWidget(field("Tarayıcı", self.browser))
        bl.addWidget(field("Profil (isteğe bağlı)", self.profile))
        bl.addStretch()

        self.file_edit = QLineEdit(readOnly=True)
        self.file_edit.setPlaceholderText("cookies.txt seçilmedi")
        pick = QPushButton("Seç…")
        set_icon(pick, "cookie-outline")
        pick.clicked.connect(self._pick_file)
        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(pick)
        self.file_box = field("Çerez dosyası (Netscape biçimi)", file_row)

        self.method_stack = QStackedWidget()
        self.method_stack.addWidget(self.browser_box)
        self.method_stack.addWidget(self.file_box)
        row.addWidget(self.method_stack, 1)
        cl.addLayout(row)

        note = QHBoxLayout()
        shield = QLabel()
        shield.setPixmap(pixmap("shield-check-outline", 16, "#067647"))
        info = QLabel("BYK Music parolanızı görmez ve saklamaz. Seçtiğiniz tarayıcıda YouTube'a giriş yapmış "
                      "olmanız yeterlidir; oturum bilgisi yalnızca bu bilgisayarda, YouTube ile iletişimde kullanılır. "
                      "Windows'ta Chrome ve Edge çerezleri şifreli tuttuğu için Firefox önerilir.")
        info.setObjectName("small")
        info.setWordWrap(True)
        note.addWidget(shield, 0, Qt.AlignTop)
        note.addWidget(info, 1)
        cl.addLayout(note)
        lay.addWidget(conn)

        # --- kitaplık
        bar = QHBoxLayout()
        lib_title = QLabel("Kitaplığım")
        lib_title.setObjectName("h2")
        self.lib_count = Badge("", "neutral")
        self.lib_count.hide()
        bar.addWidget(lib_title)
        bar.addWidget(self.lib_count)
        bar.addStretch()
        lay.addLayout(bar)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["LİSTE", "ÖĞE", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.doubleClicked.connect(lambda idx: self._open_row(idx.row()))
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, width in ((1, 90), (2, 150)):
            hh.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, width)

        self.empty = EmptyState("youtube", "Hesap bağlı değil",
                                "Tarayıcınızı seçip Bağlan'a tıklayın; beğendiğiniz videolar ve "
                                "oynatma listeleriniz burada görünür.")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.table)
        lay.addWidget(self.stack, 1)

        self._items: list[dict] = []
        self._load_from_settings()

    # ------------------------------------------------------------- durum
    def _load_from_settings(self):
        s = self.settings
        method = s["cookies_file"] and s["account_source"] == "file" and "file" or "browser"
        self.method.set_value(method)
        self.method_stack.setCurrentIndex(0 if method == "browser" else 1)
        idx = self.browser.findData(s["account_browser"])
        self.browser.setCurrentIndex(max(idx, 0))
        self.profile.setText(s["account_profile"])
        self.file_edit.setText(s["cookies_file"])
        self._set_connected(bool(s["account_source"]))

    def _set_connected(self, on: bool, busy: bool = False):
        s = self.settings
        if busy:
            self.status.set("● Bağlanıyor", "info")
        elif on:
            src = self.browser.currentText() if s["account_source"] == "browser" else "cookies.txt"
            self.status.set(f"✓ Bağlı · {src}", "success")
        else:
            self.status.set("Bağlı değil", "neutral")
        self.status.set_pulse(busy)
        self.connect_btn.setVisible(not on and not busy)
        self.refresh_btn.setVisible(on and not busy)
        self.logout_btn.setVisible(on and not busy)
        for w in (self.method, self.browser, self.profile, self.file_box):
            w.setEnabled(not on and not busy)

    def on_shown(self):
        """Sayfa ilk kez açıldığında kayıtlı oturumun kitaplığını getirir."""
        if self.settings["account_source"] and not self._loaded and not self.worker:
            self.connect_account()

    def _method_changed(self, key: str):
        self.method_stack.setCurrentIndex(0 if key == "browser" else 1)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "cookies.txt dosyasını seçin", "",
                                              "Çerez dosyası (*.txt);;Tüm dosyalar (*)")
        if path:
            self.file_edit.setText(path)

    # ----------------------------------------------------------- işlemler
    def connect_account(self):
        if self.worker:
            return
        s = self.settings
        method = "file" if self.method_stack.currentIndex() == 1 else "browser"
        if method == "file" and not self.file_edit.text():
            self.notify("Dosya seçilmedi", "Önce bir cookies.txt dosyası seçin.", "warning")
            return
        s["account_source"] = method
        s["account_browser"] = self.browser.currentData()
        s["account_profile"] = self.profile.text().strip()
        s["cookies_file"] = self.file_edit.text()
        self._set_connected(False, busy=True)
        self.empty.set("youtube", "Hesap bilgileri alınıyor",
                       "Kitaplığınız YouTube'dan okunuyor. Bu işlem birkaç saniye sürebilir.", busy=True)
        self.stack.setCurrentWidget(self.empty)
        self.worker = LibraryWorker(ydl_base_opts(s))
        self.worker.result.connect(self._on_library)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(lambda: setattr(self, "worker", None))
        self.worker.start()

    def disconnect_account(self):
        self.settings["account_source"] = ""
        self.settings.save()
        self._items = []
        self._loaded = False
        self.table.setRowCount(0)
        self.lib_count.hide()
        self.empty.set("youtube", "Hesap bağlı değil",
                       "Tarayıcınızı seçip Bağlan'a tıklayın; beğendiğiniz videolar ve "
                       "oynatma listeleriniz burada görünür.")
        self.stack.setCurrentWidget(self.empty)
        self._set_connected(False)
        self.notify("Bağlantı kesildi", "YouTube hesabı bu uygulamadan ayrıldı.", "neutral")

    def _on_failed(self, msg: str):
        self.settings["account_source"] = ""
        self.settings.save()
        self._set_connected(False)
        self.empty.set("alert-outline", "Hesaba bağlanılamadı", msg[:300])
        self.stack.setCurrentWidget(self.empty)
        self.notify("Hesaba bağlanılamadı", msg[:160], "error")

    def _on_library(self, items: list):
        self.settings.save()
        self._loaded = True
        self._items = items
        self._set_connected(True)
        self.table.setRowCount(0)
        for i, it in enumerate(items):
            self.table.insertRow(i)
            t = QTableWidgetItem(it["title"])
            t.setIcon(pixmap(KIND_ICONS.get(it["kind"], "playlist-music"), 18,
                             ACCENT if it["kind"] != "liked" else "#E11D48"))
            t.setToolTip(it["url"])
            self.table.setItem(i, 0, t)
            c = QTableWidgetItem("" if it["count"] is None else str(it["count"]))
            c.setForeground(Qt.gray)
            self.table.setItem(i, 1, c)
            btn = QPushButton("Listele")
            btn.setObjectName("link")
            btn.setCursor(Qt.PointingHandCursor)
            set_icon(btn, "playlist-play", ACCENT)
            btn.clicked.connect(lambda _=False, r=i: self._open_row(r))
            wrap = QWidget()
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(6, 0, 6, 0)
            wl.addWidget(btn)
            wl.addStretch()
            self.table.setCellWidget(i, 2, wrap)
        self.lib_count.set(f"{len(items)} liste", "neutral")
        self.lib_count.show()
        self.stack.setCurrentWidget(self.table)
        self.notify("YouTube hesabı bağlandı", f"{len(items)} liste bulundu.", "success")

    def _open_row(self, row: int):
        if 0 <= row < len(self._items):
            self.open_url(self._items[row]["url"])
