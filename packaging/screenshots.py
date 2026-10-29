"""README için tanıtım görseli ve ekran görüntülerini üretir (docs/).

  QT_SCALE_FACTOR=2 python packaging/screenshots.py <sürüm>

Ekranlar örnek verilerle, ağa çıkmadan ve hiçbir ayar ya da dosya değiştirilmeden çizilir.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import byk_music  # noqa: E402

byk_music.__version__ = (sys.argv[1] if len(sys.argv) > 1 else byk_music.__version__).lstrip("v")

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])
app.setApplicationName("BYK Music")
app.setOrganizationName("BYK")
app.setStyle("Fusion")

from byk_music.core.settings import Settings, config_dir  # noqa: E402
from byk_music.ui.styles import app_icon, build_qss, light_palette  # noqa: E402

app.setPalette(light_palette())
app.setStyleSheet(build_qss(config_dir() / "assets"))

from byk_music.ui import extension_wizard as wz  # noqa: E402
from byk_music.ui.bubble import DetectBubble  # noqa: E402
from byk_music.ui.dev_dialog import LogBuffer  # noqa: E402
from byk_music.ui.main_window import MainWindow  # noqa: E402
from byk_music.ui.multilink import MultiLinkDialog  # noqa: E402
from byk_music.ui.update_dialog import UpdateDialog  # noqa: E402

OUT = ROOT / "docs"
SHOTS = OUT / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)
VERSION = byk_music.__version__

SONGS = [("Tarkan - Şımarık", 232), ("Sezen Aksu - Gülümse", 268), ("Barış Manço - Dağlar Dağlar", 301),
         ("MFÖ - Ele Güne Karşı", 245), ("Sertab Erener - Everyway That I Can", 183),
         ("Müslüm Gürses - Nilüfer", 254), ("Ajda Pekkan - Bambaşka Biri", 221)]


def save(widget, name: str):
    for _ in range(20):  # yerleşimin oturması için
        app.processEvents()
    widget.grab().save(str(SHOTS / f"{name}.png"))
    print("✓", name)


def banner():
    """README başlığındaki renkli tanıtım görseli."""
    w, h = 1280, 380
    scale = app.primaryScreen().devicePixelRatio()
    pm = QPixmap(int(w * scale), int(h * scale))
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(0, 0, w, h)
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor("#0F1B2D"))
    g.setColorAt(0.6, QColor("#1B2F55"))
    g.setColorAt(1, QColor("#1F4FD8"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(r, 28, 28)
    p.setBrush(QColor(255, 255, 255, 12))
    p.drawEllipse(QPointF(w - 120, 40), 260, 260)
    p.drawEllipse(QPointF(140, h + 40), 180, 180)
    icon = app_icon().pixmap(256, 256)
    p.drawPixmap(QRectF(110, 104, 172, 172), icon, QRectF(icon.rect()))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(68)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(QRectF(330, 98, 900, 84), Qt.AlignLeft | Qt.AlignVCenter, "BYK Music")
    f.setBold(False)
    f.setPixelSize(28)
    p.setFont(f)
    p.setPen(QColor("#C9D6F2"))
    p.drawText(QRectF(334, 178, 900, 40), Qt.AlignLeft | Qt.AlignVCenter, "YouTube MP3 & MP4 İndirici")
    f.setBold(True)
    f.setPixelSize(18)
    p.setFont(f)
    x = 334
    for text, color in (("MP3 · MP4", "#3B6CF0"), ("Windows · macOS", "#12B76A"), ("Otomatik güncelleme", "#7A5AF8"),
                        ("Türkçe", "#F79009")):
        tw = p.fontMetrics().horizontalAdvance(text) + 32
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(x, 244, tw, 38), 19, 19)
        p.setPen(QColor("white"))
        p.drawText(QRectF(x, 244, tw, 38), Qt.AlignCenter, text)
        x += tw + 12
    p.end()
    pm.save(str(OUT / "banner.png"))
    print("✓ banner")


def main():
    banner()
    s = Settings()
    s.save = lambda: None
    for k, v in (("auto_update", False), ("clipboard_watch", False), ("browser_bridge", True),
                 ("window_watch", True), ("format", "mp3"), ("account_source", ""),
                 ("download_dir", str(Path.home().parent / "kullanici" / "Müzik" / "BYK Music")),
                 ("extension_seen", {"version": "1.4.0", "browser": "chrome"})):
        s[k] = v
    w = MainWindow(s, LogBuffer())
    w.history.save = lambda: None
    w.history.add = lambda *a: None
    w.notify = lambda *a, **k: None
    w.resize(1240, 780)
    w.show()

    # --- indirme listesi: farklı durumlar ve biçimler
    items = [{"title": t, "url": f"https://www.youtube.com/watch?v=ornek{i}", "duration": d, "uploader": ""}
             for i, (t, d) in enumerate(SONGS)]
    w._on_info({"is_playlist": True, "title": "Türkçe Pop Klasikleri", "items": items})
    w.dl_worker = object()
    w._batch = [0, 1, 2, 3, 4]
    w._set_busy(True)
    for r in (0, 1):
        w.rows[r]["path"] = f"/{items[r]['title']}.mp3"
        w._set_row_state(r, "done")
    w.playlist["items"][2]["format"] = "mp4"
    w.playlist["items"][2]["single"] = True
    w._set_row_state(2, "active")
    w._on_progress(2, 64, "64%  41.2 MB/64.5 MB  •  6.8 MB/s  •  3 sn")
    w._set_row_state(3, "processing", "Dönüştürülüyor…")
    w._set_row_state(4, "queued", "Sırada")
    w.table.item(6, 0).setCheckState(Qt.Unchecked)
    w._update_overall()
    save(w, "indir")
    w.dl_worker = None
    w._set_busy(False)
    w._set_status("Hazır", "neutral")
    w.nav[0].set_badge(None)

    # --- yükleme görünümü
    w.loading.start("Bağlantı çözümleniyor", "Bilgiler YouTube'dan alınıyor · https://www.youtube.com/playlist?list=…")
    w.list_stack.setCurrentWidget(w.loading)
    QTimer.singleShot(0, lambda: None)
    for _ in range(30):
        app.processEvents()
    w.loading.stop()
    w.list_stack.setCurrentWidget(w.table)

    # --- geçmiş
    from datetime import datetime, timedelta
    now = datetime(2026, 10, 29, 14, 30)
    w.history.items = [{"title": t, "url": "u", "path": str(Path(__file__)) if i < 5 else "/yok",
                        "format": "mp4" if i in (1, 4) else "mp3",
                        "date": (now - timedelta(minutes=17 * i)).isoformat(timespec="seconds")}
                       for i, (t, _) in enumerate(SONGS)]
    w._goto(1)
    w.hist_table.item(1, 0).setCheckState(Qt.Checked)
    w.hist_table.item(3, 0).setCheckState(Qt.Checked)
    save(w, "gecmis")


    # --- hesap, ayarlar, iletişim
    w._goto(2)
    save(w, "hesap")
    w._goto(3)
    save(w, "ayarlar")
    w._goto(4)
    save(w, "iletisim")
    w._goto(0)

    # --- çoklu bağlantı
    d = MultiLinkDialog(w, "https://www.youtube.com/watch?v=ornek1\nhttps://youtu.be/ornek2\n"
                           "https://www.youtube.com/playlist?list=PLornek3")
    d.show()
    save(d, "coklu-baglanti")
    d.close()

    # --- indirme balonu
    b = DetectBubble()
    b.show_item({"url": "https://www.youtube.com/watch?v=ornek", "title": "Barış Manço - Dağlar Dağlar",
                 "kind": "video"}, "mp3")
    b.setWindowOpacity(1.0)
    save(b, "balon")
    b.close()

    # --- güncelleme penceresi
    notes = ("### Güncellemeler artık size soruluyor\n- Şimdi Kur ya da Daha Sonra Kur seçebilirsiniz\n"
             "- Arada birden fazla sürüm çıkmışsa doğrudan en son sürüm kurulur\n"
             "### Geçmişte toplu silme\n- Kayıtlar işaretlenip toplu silinebilir\n"
             "- İstenirse dosyalar Geri Dönüşüm Kutusu'na taşınır")
    u = UpdateDialog({"version": VERSION, "notes": notes, "page": "", "url": "", "name": "", "size": 72_600_000},
                     "1.1.8")
    u.show()
    save(u, "guncelleme")
    u.close()

    # --- eklenti sihirbazı
    wz.open_extensions_page = lambda key: True
    wz.QDesktopServices.openUrl = staticmethod(lambda url: True)
    wz.available_browsers = lambda: [("chrome", "Google Chrome"), ("edge", "Microsoft Edge"), ("firefox", "Firefox")]
    clip = app.clipboard().text()
    x = wz.ExtensionWizard(w, {})
    x.show()
    x._next()
    x._next()
    save(x, "eklenti-sihirbazi")
    x.close()
    app.clipboard().setText(clip)
    w.close()


if __name__ == "__main__":
    main()
