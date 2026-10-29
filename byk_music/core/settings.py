import json
from pathlib import Path

from PySide6.QtCore import QStandardPaths

DEFAULTS = {
    "download_dir": str(Path.home() / "Downloads" / "BYK Music"),
    "format": "mp3",            # mp3 | mp4
    "audio_quality": "192",     # kbps
    "video_quality": "best",    # best | 2160 | 1440 | 1080 | 720 | 480 | 360
    "concurrent": 3,            # aynı anda indirilecek dosya sayısı (1-5)
    "playlist_folder": True,    # liste indirmelerinde alt klasör oluştur
    "number_prefix": False,     # liste sırasını dosya adına ekle
    "embed_thumbnail": True,    # MP3'e kapak resmi göm
    "auto_update": True,        # açılışta ve saatte bir güncelleme denetle
    "auto_install": True,       # güncellemeyi arka planda indirip kur
    "notify_system": True,      # pencere arka plandayken sistem bildirimi göster
    "clipboard_watch": True,    # panodaki YouTube bağlantısını otomatik algıla
    "clean_titles": True,       # dosya adlarındaki (Official Video), [HD] gibi etiketleri temizle
    "browser_bridge": True,     # tarayıcı eklentisinden gelen bağlantıları kabul et (yalnızca 127.0.0.1)
    "show_bubble": True,        # YouTube'da video algılanınca indirme balonu göster
    "extension_seen": {},       # en son bağlanan eklenti: {version, browser}
    "window_watch": True,       # eklenti olmadan tarayıcı penceresinden YouTube videosunu algıla
    "proxy_mode": "system",     # system | none | custom
    "proxy_url": "",            # http://kullanıcı:parola@sunucu:port  ya da  socks5://sunucu:port
    "account_source": "",       # "" (bağlı değil) | extension | browser | file
    "account_method": "extension",
    "account_browser": "chrome",
    "account_profile": "",
    "cookies_file": "",
}


def config_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    path = Path(base or Path.home() / ".byk-music")
    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings:
    def __init__(self):
        self._file = config_dir() / "settings.json"
        self._data = dict(DEFAULTS)
        try:
            self._data.update(json.loads(self._file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self._data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self._data[key] = value

    def save(self):
        try:
            self._file.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
