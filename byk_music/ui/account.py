from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..core.account import LibraryWorker
from ..core.bridge import cookie_file
from ..core.net import installed_browsers, ydl_base_opts
from .icons import pixmap, set_icon
from .styles import ACCENT
from .widgets import Badge, EmptyState, Segmented, card, field

KIND_ICONS = {"liked": "thumb-up-outline", "later": "clock-outline", "playlist": "playlist-music"}
METHODS = ["extension", "browser", "file"]


def _step(num: int, text: str) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    n = QLabel(str(num))
    n.setObjectName("stepNum")
    n.setFixedSize(22, 22)
    n.setAlignment(Qt.AlignCenter)
    t = QLabel(text)
    t.setWordWrap(True)
    lay.addWidget(n, 0, Qt.AlignTop)
    lay.addWidget(t, 1)
    return w


class AccountPage(QWidget):
    """YouTube oturumu ve kitaplık (beğenilenler, daha sonra izle, oynatma listeleri)."""

    def __init__(self, settings, notify, open_url, install_extension):
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

        self.method = Segmented([("Eklenti ile aktar  ·  önerilen", "extension"),
                                 ("Tarayıcıdan oku", "browser"), ("cookies.txt", "file")])
        self.method.changed.connect(self._method_changed)
        cl.addWidget(self.method, 0, Qt.AlignLeft)

        # yöntem 1: eklenti
        ext = QWidget()
        el = QVBoxLayout(ext)
        el.setContentsMargins(0, 2, 0, 0)
        el.setSpacing(8)
        el.addWidget(_step(1, "BYK Music tarayıcı eklentisini kurun (bir kez yapılır)."))
        el.addWidget(_step(2, "YouTube'a giriş yaptığınız tarayıcıda araç çubuğundaki BYK Music simgesine tıklayın."))
        el.addWidget(_step(3, "“Oturumu BYK Music'e aktar” düğmesine basın; kitaplığınız burada otomatik açılır."))
        ext_btn = QPushButton("Eklentiyi Kur")
        set_icon(ext_btn, "web")
        ext_btn.clicked.connect(install_extension)
        el.addWidget(ext_btn, 0, Qt.AlignLeft)

        # yöntem 2: tarayıcı
        self.browser = QComboBox()
        self.browser.setMinimumWidth(190)
        browsers = installed_browsers()
        for label, key in browsers:
            self.browser.addItem(label, key)
        if not browsers:
            self.browser.addItem("Kurulu tarayıcı bulunamadı", "")
            self.browser.setEnabled(False)
        self.profile = QLineEdit()
        self.profile.setPlaceholderText("Varsayılan profil")
        self.profile.setFixedWidth(170)
        brw = QWidget()
        bl = QVBoxLayout(brw)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        brow = QHBoxLayout()
        brow.setSpacing(18)
        brow.addWidget(field("Tarayıcı", self.browser))
        brow.addWidget(field("Profil (isteğe bağlı)", self.profile))
        brow.addStretch()
        bl.addLayout(brow)
        warn = QLabel("Windows'ta Chrome, Edge ve Brave çerezleri şifreli tuttuğu için bu yöntem çoğu zaman "
                      "çalışmaz; tarayıcı açıkken de okunamaz. Bu durumda “Eklenti ile aktar” yöntemini kullanın.")
        warn.setObjectName("small")
        warn.setWordWrap(True)
        bl.addWidget(warn)

        # yöntem 3: dosya
        self.file_edit = QLineEdit(readOnly=True)
        self.file_edit.setPlaceholderText("cookies.txt seçilmedi")
        pick = QPushButton("Seç…")
        set_icon(pick, "cookie-outline")
        pick.clicked.connect(self._pick_file)
        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(pick)
        file_box = field("Çerez dosyası (Netscape biçimi)", file_row)

        self.method_stack = QStackedWidget()
        for w in (ext, brw, file_box):
            self.method_stack.addWidget(w)
        cl.addWidget(self.method_stack)

        note = QHBoxLayout()
        shield = QLabel()
        shield.setPixmap(pixmap("shield-check-outline", 16, "#067647"))
        info = QLabel("BYK Music parolanızı görmez ve saklamaz. Yalnızca youtube.com oturum bilgisi bu bilgisayarda, "
                      "size ait ayar klasöründe tutulur ve yalnızca YouTube ile iletişimde kullanılır.")
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

        self.empty = EmptyState("youtube", "Hesap bağlı değil", self._empty_text())
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.table)
        lay.addWidget(self.stack, 1)

        self._items: list[dict] = []
        self._load_from_settings()

    @staticmethod
    def _empty_text() -> str:
        return ("Eklentiden oturumu aktardığınızda ya da Bağlan'a tıkladığınızda beğendiğiniz videolar ve "
                "oynatma listeleriniz burada görünür.")

    # ------------------------------------------------------------- durum
    def _current_method(self) -> str:
        return METHODS[self.method_stack.currentIndex()]

    def _load_from_settings(self):
        s = self.settings
        method = s["account_source"] or s["account_method"]
        if method not in METHODS:
            method = "extension"
        self.method.set_value(method)
        self.method_stack.setCurrentIndex(METHODS.index(method))
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
            src = {"extension": "Eklenti", "file": "cookies.txt"}.get(s["account_source"], self.browser.currentText())
            self.status.set(f"✓ Bağlı · {src}", "success")
        else:
            self.status.set("Bağlı değil", "neutral")
        self.status.set_pulse(busy)
        self.connect_btn.setVisible(not on and not busy)
        self.refresh_btn.setVisible(on and not busy)
        self.logout_btn.setVisible(on and not busy)
        self.method.setEnabled(not on and not busy)
        self.method_stack.setEnabled(not on and not busy)

    def on_shown(self):
        """Sayfa ilk kez açıldığında kayıtlı oturumun kitaplığını getirir."""
        if self.settings["account_source"] and not self._loaded and not self.worker:
            self.connect_account()

    def on_cookies_received(self, path: str, count: int):
        """Eklentiden oturum aktarıldı: eklenti yöntemine geç ve kitaplığı getir."""
        self.method.set_value("extension")
        self.method_stack.setCurrentIndex(0)
        self.settings["account_source"] = ""
        self.connect_account()

    def _method_changed(self, key: str):
        self.method_stack.setCurrentIndex(METHODS.index(key))
        self.settings["account_method"] = key
        self.settings.save()

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
        method = s["account_source"] or self._current_method()
        if method == "extension" and not cookie_file().exists():
            self.notify("Oturum henüz aktarılmadı",
                        "Tarayıcıda BYK Music eklentisine tıklayıp “Oturumu BYK Music'e aktar” düğmesine basın.",
                        "warning")
            return
        if method == "file" and not self.file_edit.text():
            self.notify("Dosya seçilmedi", "Önce bir cookies.txt dosyası seçin.", "warning")
            return
        if method == "browser" and not self.browser.currentData():
            self.notify("Tarayıcı bulunamadı", "Bu bilgisayarda desteklenen bir tarayıcı profili yok.", "warning")
            return
        s["account_source"] = method
        s["account_browser"] = self.browser.currentData() or s["account_browser"]
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
        if self.settings["account_source"] == "extension":
            try:
                cookie_file().unlink()  # aktarılan oturum bilgisini sil
            except OSError:
                pass
        self.settings["account_source"] = ""
        self.settings.save()
        self._items = []
        self._loaded = False
        self.table.setRowCount(0)
        self.lib_count.hide()
        self.empty.set("youtube", "Hesap bağlı değil", self._empty_text())
        self.stack.setCurrentWidget(self.empty)
        self._set_connected(False)
        self.notify("Bağlantı kesildi", "YouTube oturum bilgisi bu uygulamadan kaldırıldı.", "neutral")

    def _on_failed(self, msg: str):
        self.settings["account_source"] = ""
        self.settings.save()
        self._set_connected(False)
        self.empty.set("alert-outline", "Hesaba bağlanılamadı", msg[:300])
        self.stack.setCurrentWidget(self.empty)
        self.notify("Hesaba bağlanılamadı", msg[:200], "error")

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
