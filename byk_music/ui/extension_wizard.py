"""Tarayıcı eklentisi kurulum sihirbazı.

Adımlar: İzin → Tarayıcı → Kurulum → Tamam. Sihirbaz dosyaları hazırlar, uzantılar sayfasını ve
eklenti klasörünü açar, klasör yolunu panoya kopyalar. Eklenti yüklendiğinde uygulamaya haber verir
(on_hello) ve sihirbaz kendiliğinden son adıma geçer.
"""
import sys

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..core.extension import BROWSERS, available_browsers, open_extensions_page, sync_extension_files
from .icons import pixmap, set_icon
from .styles import ACCENT, SUCCESS
from .widgets import Spinner, repolish

STEPS = ["İzin", "Tarayıcı", "Kurulum", "Tamam"]
BROWSER_ICONS = {"chrome": "google-chrome", "edge": "microsoft-edge", "firefox": "firefox", "opera": "opera"}
PASTE = "⌘⇧G ile yolu yapıştırabilirsiniz" if sys.platform == "darwin" else "adres çubuğuna Ctrl+V ile yapıştırabilirsiniz"


def _row(icon_name: str, color: str, text: str) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    ic = QLabel()
    ic.setPixmap(pixmap(icon_name, 18, color))
    t = QLabel(text)
    t.setWordWrap(True)
    t.setTextFormat(Qt.RichText)
    lay.addWidget(ic, 0, Qt.AlignTop)
    lay.addWidget(t, 1)
    return w


def _numbered(num: int, html: str) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(12)
    n = QLabel(str(num))
    n.setObjectName("stepNum")
    n.setFixedSize(22, 22)
    n.setAlignment(Qt.AlignCenter)
    t = QLabel(html)
    t.setWordWrap(True)
    t.setTextFormat(Qt.RichText)
    lay.addWidget(n, 0, Qt.AlignTop)
    lay.addWidget(t, 1)
    return w


class ExtensionWizard(QDialog):
    open_account = Signal()

    def __init__(self, parent=None, installed: dict | None = None, ensure_bridge=None):
        super().__init__(parent)
        self.setWindowTitle("Tarayıcı eklentisini kur")
        self.setFixedSize(620, 600)
        self.installed = installed or {}
        self.ensure_bridge = ensure_bridge
        self.browser = ""
        self.folder = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(16)
        root.addLayout(self._build_stepper())

        self.pages = QStackedWidget()
        self.pages.addWidget(self._page_permission())
        self.pages.addWidget(self._page_browser())
        self.pages.addWidget(self._page_install())
        self.pages.addWidget(self._page_done())
        root.addWidget(self.pages, 1)

        line = QFrame()
        line.setObjectName("wizardLine")
        line.setFixedHeight(1)
        root.addWidget(line)
        btns = QHBoxLayout()
        self.back_btn = QPushButton("Geri")
        self.back_btn.clicked.connect(self._back)
        self.cancel_btn = QPushButton("Vazgeç")
        self.cancel_btn.clicked.connect(self.reject)
        self.next_btn = QPushButton()
        self.next_btn.setObjectName("primary")
        self.next_btn.setMinimumWidth(180)
        self.next_btn.clicked.connect(self._next)
        btns.addWidget(self.back_btn)
        btns.addStretch()
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.next_btn)
        root.addLayout(btns)
        self._go(0)

    # ------------------------------------------------------------ yapı
    def _build_stepper(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setSpacing(8)
        self.step_dots, self.step_labels = [], []
        for i, name in enumerate(STEPS):
            dot = QLabel(str(i + 1))
            dot.setObjectName("wizDot")
            dot.setFixedSize(26, 26)
            dot.setAlignment(Qt.AlignCenter)
            lbl = QLabel(name)
            lbl.setObjectName("wizLabel")
            lay.addWidget(dot)
            lay.addWidget(lbl)
            if i < len(STEPS) - 1:
                bar = QFrame()
                bar.setObjectName("wizBar")
                bar.setFixedHeight(2)
                lay.addWidget(bar, 1)
            self.step_dots.append(dot)
            self.step_labels.append(lbl)
        return lay

    def _page_permission(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(pixmap("puzzle-outline", 40, ACCENT))
        texts = QVBoxLayout()
        texts.setSpacing(2)
        t = QLabel("BYK Music tarayıcı eklentisi")
        t.setObjectName("h1")
        s = QLabel("Birkaç adımda kurulur; sizi adım adım yönlendireceğiz.")
        s.setObjectName("muted")
        texts.addWidget(t)
        texts.addWidget(s)
        head.addWidget(ic)
        head.addSpacing(6)
        head.addLayout(texts, 1)
        lay.addLayout(head)

        if self.installed.get("version"):
            name = BROWSERS.get(self.installed.get("browser"), ("Tarayıcı",))[0]
            done = QLabel(f"✓  Eklenti zaten kurulu: <b>{name}</b> · v{self.installed['version']}. "
                          "Başka bir tarayıcıya kurmak için devam edebilirsiniz.")
            done.setObjectName("okNote")
            done.setWordWrap(True)
            lay.addWidget(done)

        sub = QLabel("EKLENTİ NELER KAZANDIRIR?")
        sub.setObjectName("fieldLabel")
        lay.addWidget(sub)
        for text in ("Videonun altında <b>MP3 / MP4</b> indirme düğmesi",
                     "YouTube oturumunuzu <b>tek tıkla</b> aktarma (beğenilenler ve listeleriniz için)",
                     "Açtığınız videonun <b>anında ve kesin</b> algılanması"):
            lay.addWidget(_row("check-circle", SUCCESS, text))

        sub2 = QLabel("İZİN VERDİĞİNİZDE BYK MUSIC")
        sub2.setObjectName("fieldLabel")
        lay.addSpacing(4)
        lay.addWidget(sub2)
        for text in ("Eklenti dosyalarını hazırlar ve eklenti klasörünü açar",
                     "Seçtiğiniz tarayıcıyı öne getirir ve <b>uzantılar sayfasının adresini</b> panoya kopyalar",
                     "Kalan birkaç adımı ekranda tek tek gösterir; kurulumu kendiliğinden algılar"):
            lay.addWidget(_row("gesture-tap", ACCENT, text))
        lay.addStretch()
        note = QLabel("Tarayıcılar güvenlik gereği eklentilerin programlar tarafından sessizce kurulmasına izin "
                      "vermez; son adımı siz onaylarsınız. Tarayıcı ayarlarınız değiştirilmez.")
        note.setObjectName("small")
        note.setWordWrap(True)
        lay.addWidget(note)
        return w

    def _page_browser(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        t = QLabel("Hangi tarayıcıya kurulsun?")
        t.setObjectName("h2")
        s = QLabel("YouTube'u izlediğiniz tarayıcıyı seçin. Yalnızca bu bilgisayarda bulunan tarayıcılar listelenir.")
        s.setObjectName("muted")
        s.setWordWrap(True)
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addSpacing(4)
        self.browser_group = QButtonGroup(self)
        self.browser_group.setExclusive(True)
        found = available_browsers()
        for key, label in found:
            b = QPushButton(f"  {label}")
            b.setObjectName("browserCard")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            set_icon(b, BROWSER_ICONS.get(key, "web"), ACCENT, 22)
            b.setProperty("key", key)
            self.browser_group.addButton(b)
            lay.addWidget(b)
        if found:
            pref = self.installed.get("browser")
            first = next((b for b in self.browser_group.buttons()
                          if b.property("key") != pref), self.browser_group.buttons()[0])
            first.setChecked(True)
        else:
            none = QLabel("Desteklenen bir tarayıcı bulunamadı (Chrome, Edge, Brave, Opera, Vivaldi ya da Firefox).")
            none.setObjectName("muted")
            none.setWordWrap(True)
            lay.addWidget(none)
        lay.addStretch()
        return w

    def _page_install(self) -> QWidget:
        w = QWidget()
        self.install_lay = QVBoxLayout(w)
        self.install_lay.setContentsMargins(0, 0, 0, 0)
        self.install_lay.setSpacing(10)
        return w

    def _fill_install(self):
        lay = self.install_lay
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        name, address = BROWSERS[self.browser]
        firefox = self.browser == "firefox"

        t = QLabel(f"{name} için son adımlar")
        t.setObjectName("h2")
        lay.addWidget(t)

        # uzantılar sayfasının adresi: büyük, kopyalanabilir kutu
        addr = QFrame()
        addr.setObjectName("addressBox")
        al = QHBoxLayout(addr)
        al.setContentsMargins(14, 10, 10, 10)
        al.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(pixmap("web", 20, ACCENT))
        texts = QVBoxLayout()
        texts.setSpacing(2)
        k = QLabel("UZANTILAR SAYFASININ ADRESİ  ·  PANOYA KOPYALANDI")
        k.setObjectName("fieldLabel")
        v = QLabel(address)
        v.setObjectName("addressText")
        v.setTextInteractionFlags(Qt.TextSelectableByMouse)
        texts.addWidget(k)
        texts.addWidget(v)
        copy_addr = QPushButton("Kopyala")
        copy_addr.setObjectName("smallBtn")
        set_icon(copy_addr, "content-copy", size=14)
        copy_addr.clicked.connect(lambda: self._copy(address, copy_addr))
        al.addWidget(ic)
        al.addLayout(texts, 1)
        al.addWidget(copy_addr)
        lay.addWidget(addr)

        sub = QLabel("ADIM ADIM")
        sub.setObjectName("fieldLabel")
        lay.addWidget(sub)
        open_keys = "⌘L" if sys.platform == "darwin" else "Ctrl+L"
        paste_keys = "⌘V" if sys.platform == "darwin" else "Ctrl+V"
        first = (f"{name} penceresinde adres çubuğuna tıklayın (<b>{open_keys}</b>), adresi yapıştırın "
                 f"(<b>{paste_keys}</b>) ve <b>Enter</b>'a basın.")
        if firefox:
            steps = [first,
                     "Açılan sayfada <b>Geçici Eklenti Yükle…</b> düğmesine tıklayın.",
                     "Yanında açılan <b>browser-extension</b> klasöründeki <b>manifest.json</b> dosyasını seçin.",
                     "Not: Firefox geçici eklentileri tarayıcı kapanınca kaldırır; Chrome ya da Edge önerilir."]
        else:
            steps = [first,
                     "Sayfanın sağ üst köşesindeki <b>Geliştirici modu</b> anahtarını açın.",
                     "Yanında açılan <b>browser-extension</b> klasörünü tarayıcı sayfasının üzerine "
                     "<b>sürükleyip bırakın</b>. Sürükleyemezseniz <b>Paketlenmemiş öğe yükle</b> düğmesine "
                     "tıklayıp klasörü seçin.",
                     "İsterseniz araç çubuğundaki yapboz simgesinden BYK Music'i sabitleyin."]
        for i, html in enumerate(steps, 1):
            lay.addWidget(_numbered(i, html))

        quick = QHBoxLayout()
        reopen = QPushButton("Tarayıcıyı öne getir")
        set_icon(reopen, BROWSER_ICONS.get(self.browser, "web"), size=14)
        reopen.clicked.connect(lambda: open_extensions_page(self.browser))
        folder = QPushButton("Klasörü göster")
        set_icon(folder, "folder-open-outline", size=14)
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder))))
        copy_path = QPushButton("Klasör yolunu kopyala")
        set_icon(copy_path, "content-copy", size=14)
        copy_path.clicked.connect(lambda: self._copy(str(self.folder), copy_path))
        for b in (reopen, folder, copy_path):
            b.setObjectName("smallBtn")
            quick.addWidget(b)
        quick.addStretch()
        lay.addLayout(quick)

        note = QLabel("Tarayıcılar güvenlik gereği uzantılar sayfasının başka programlarca açılmasına izin vermez; "
                      "bu yüzden adresi sizin yapıştırmanız gerekir.")
        note.setObjectName("small")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch()

        wait = QHBoxLayout()
        self.spinner = Spinner(20)
        self.spinner.start()
        wl = QLabel("Eklentinin yüklenmesi bekleniyor… Yüklendiği anda bu pencere kendiliğinden ilerler.")
        wl.setObjectName("small")
        wl.setWordWrap(True)
        wait.addWidget(self.spinner)
        wait.addWidget(wl, 1)
        lay.addLayout(wait)

    def _copy(self, text: str, button: QPushButton):
        QGuiApplication.clipboard().setText(text)
        old = button.text()
        button.setText("Kopyalandı ✓")
        QTimer.singleShot(1500, lambda: button.setText(old))

    def _page_done(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignTop)
        ic = QLabel()
        ic.setPixmap(pixmap("check-decagram", 56, SUCCESS))
        ic.setAlignment(Qt.AlignCenter)
        self.done_title = QLabel("Eklenti kuruldu")
        self.done_title.setObjectName("h1")
        self.done_title.setAlignment(Qt.AlignCenter)
        self.done_sub = QLabel()
        self.done_sub.setObjectName("muted")
        self.done_sub.setAlignment(Qt.AlignCenter)
        self.done_sub.setWordWrap(True)
        lay.addWidget(ic)
        lay.addWidget(self.done_title)
        lay.addWidget(self.done_sub)
        lay.addSpacing(10)
        for text in ("YouTube'da bir video açın: videonun altında <b>MP3 / MP4</b> düğmesi görünür.",
                     "Beğendiğiniz videolar ve listeleriniz için eklenti simgesine tıklayıp "
                     "<b>Oturumu BYK Music'e aktar</b> düğmesine basın.",
                     "Eklenti, BYK Music güncellendiğinde kendini otomatik olarak günceller."):
            lay.addWidget(_row("check-circle", SUCCESS, text))
        lay.addStretch()
        return w

    # ------------------------------------------------------------ akış
    def _go(self, idx: int):
        self.pages.setCurrentIndex(idx)
        for i, (dot, lbl) in enumerate(zip(self.step_dots, self.step_labels)):
            state = "done" if i < idx else "active" if i == idx else ""
            dot.setText("✓" if i < idx else str(i + 1))
            for widget in (dot, lbl):
                widget.setProperty("state", state)
                repolish(widget)
        self.back_btn.setVisible(idx in (1, 2))
        self.cancel_btn.setVisible(idx < 3)
        self.next_btn.setEnabled(True)
        if idx == 0:
            self.next_btn.setText("İzin Ver ve Başla")
            set_icon(self.next_btn, "check", "#FFFFFF")
        elif idx == 1:
            self.next_btn.setText("Devam")
            set_icon(self.next_btn, "arrow-right", "#FFFFFF")
            self.next_btn.setEnabled(bool(self.browser_group.buttons()))
        elif idx == 2:
            self.next_btn.setText("Kurdum, bitir")
            set_icon(self.next_btn, "check", "#FFFFFF")
        else:
            self.next_btn.setText("Oturumu Aktarmaya Geç")
            set_icon(self.next_btn, "youtube", "#FFFFFF")
            self.cancel_btn.setVisible(True)
            self.cancel_btn.setText("Bitti")

    def _next(self):
        idx = self.pages.currentIndex()
        if idx == 0:
            if self.ensure_bridge:
                self.ensure_bridge()
            self._go(1)
        elif idx == 1:
            checked = self.browser_group.checkedButton()
            if not checked:
                return
            self.browser = checked.property("key")
            self.folder = sync_extension_files()
            open_extensions_page(self.browser)  # tarayıcıyı öne getirir (iç sayfa engellenebilir)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder)))
            QGuiApplication.clipboard().setText(BROWSERS[self.browser][1])
            self._fill_install()
            self._go(2)
            self.raise_()
        elif idx == 2:
            self._finish(confirmed=False)
        else:
            self.open_account.emit()
            self.accept()

    def _back(self):
        self._go(max(0, self.pages.currentIndex() - 1))

    def _finish(self, confirmed: bool, info: dict | None = None):
        name = BROWSERS.get((info or {}).get("browser") or self.browser, ("Tarayıcı",))[0]
        if confirmed:
            self.done_title.setText("Eklenti kuruldu ve bağlandı")
            self.done_sub.setText(f"{name} · v{info.get('version', '')} — BYK Music ile iletişim kuruyor.")
        else:
            self.done_title.setText("Kurulum tamamlandı")
            self.done_sub.setText("Eklenti henüz bağlantı kurmadı. Tarayıcıda bir YouTube videosu açtığınızda "
                                  "otomatik olarak bağlanacaktır.")
        if hasattr(self, "spinner"):
            self.spinner.stop()
        self._go(3)

    def on_hello(self, info: dict):
        """Eklenti yüklendiğinde (köprü üzerinden) çağrılır."""
        if self.pages.currentIndex() in (1, 2):
            self._finish(confirmed=True, info=info)
            self.raise_()
            self.activateWindow()

