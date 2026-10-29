"""YouTube hesabı: kullanıcının tarayıcı oturumu üzerinden kitaplık listelerini okur."""
import logging

import yt_dlp
from PySide6.QtCore import QThread, Signal

from .downloader import _YDLLogger, _clean_error

log = logging.getLogger("byk.account")

LIKED_URL = "https://www.youtube.com/playlist?list=LL"
WATCH_LATER_URL = "https://www.youtube.com/playlist?list=WL"
PLAYLISTS_URL = "https://www.youtube.com/feed/playlists"


def _extract(url: str, base_opts: dict, limit: int | None = None) -> dict:
    opts = {**base_opts, "quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
            "skip_download": True, "logger": _YDLLogger()}
    if limit:
        opts["playlistend"] = limit
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


class LibraryWorker(QThread):
    """Oturumu doğrular ve kitaplığı (beğenilenler, daha sonra izle, oynatma listeleri) getirir."""

    result = Signal(list)   # [{title, url, kind, count}]
    failed = Signal(str)

    def __init__(self, base_opts: dict):
        super().__init__()
        self.base_opts = base_opts

    def run(self):
        try:
            # Beğenilen videolar listesi yalnızca oturum açıkken erişilebilir: doğrulama için kullanılır.
            liked = _extract(LIKED_URL, self.base_opts, limit=1)
        except Exception as exc:
            log.warning("Oturum doğrulanamadı: %s", exc)
            self.failed.emit(_clean_error(exc))
            return

        items = [{"title": "Beğenilen videolar", "url": LIKED_URL, "kind": "liked",
                  "count": liked.get("playlist_count")}]
        for kind, title, url in (("later", "Daha sonra izle", WATCH_LATER_URL),):
            try:
                info = _extract(url, self.base_opts, limit=1)
                items.append({"title": title, "url": url, "kind": kind, "count": info.get("playlist_count")})
            except Exception as exc:
                log.info("%s alınamadı: %s", title, exc)
        try:
            feed = _extract(PLAYLISTS_URL, self.base_opts)
            for e in feed.get("entries") or []:
                if not e or not e.get("url"):
                    continue
                items.append({"title": e.get("title") or "(adsız liste)", "url": e["url"],
                              "kind": "playlist", "count": e.get("playlist_count")})
        except Exception as exc:
            log.info("Oynatma listeleri alınamadı: %s", exc)
        self.result.emit(items)
