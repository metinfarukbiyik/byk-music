"""Eklenti gerektirmeden tarayıcıda açık YouTube videosunu algılar.

Windows: görünür tarayıcı pencerelerinin başlıkları okunur ("Şarkı - YouTube - Google Chrome").
         Başlıkla YouTube'da aranır; ilk sonuç başlıkla neredeyse aynıysa video kabul edilir.
         Böylece arama sonuçları ve kanal sayfaları yanlışlıkla algılanmaz.
macOS:   Chrome, Edge, Brave, Arc ve Safari'nin öndeki sekme adresi AppleScript ile okunur
         (macOS ilk kullanımda bir kez izin ister).

Okunan bilgi bilgisayardan çıkmaz; yalnızca Windows'ta video başlığı YouTube aramasında kullanılır.
"""
import logging
import re
import subprocess
import sys
import time
from difflib import SequenceMatcher

import yt_dlp
from PySide6.QtCore import QThread, Signal

from .downloader import _YDLLogger
from .links import analyze

log = logging.getLogger("byk.watcher")

POLL_SECONDS = 2.5
MAC_BROWSERS = {  # uygulama adı: (süreç adı, sekme ifadesi)
    "Google Chrome": ("Google Chrome", "active tab of front window"),
    "Microsoft Edge": ("Microsoft Edge", "active tab of front window"),
    "Brave Browser": ("Brave Browser", "active tab of front window"),
    "Arc": ("Arc", "active tab of front window"),
    "Safari": ("Safari", "current tab of front window"),
}
_TITLE_RE = re.compile(r"^(?:\(\d+\)\s*)?(?P<title>.+?) - YouTube(?: Music)?(?:\s|$)")


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text.casefold()).strip()


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def youtube_title_from_window(window_title: str) -> str | None:
    """'(3) Tarkan - Şımarık - YouTube - Google Chrome' -> 'Tarkan - Şımarık'"""
    m = _TITLE_RE.match(window_title.strip())
    if not m:
        return None
    title = m.group("title").strip()
    return title if title and title.casefold() != "youtube" else None


def _windows_titles() -> list[str]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    titles: list[str] = []

    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if " - YouTube" in buf.value:
                    titles.append(buf.value)
        return True

    user32.EnumWindows(proc_type(callback), 0)
    return titles


class BrowserWatcher(QThread):
    detected = Signal(dict)   # {url, title, kind, source}

    def __init__(self, base_opts_fn):
        super().__init__()
        self._base_opts_fn = base_opts_fn
        self._stop = False
        self._seen: set[str] = set()
        self._mac_denied: set[str] = set()

    def stop(self):
        self._stop = True

    def run(self):
        log.info("Tarayıcı izleyici başladı")
        while not self._stop:
            try:
                if sys.platform.startswith("win"):
                    self._scan_windows()
                elif sys.platform == "darwin":
                    self._scan_mac()
            except Exception as exc:
                log.debug("İzleme hatası: %s", exc)
            for _ in range(int(POLL_SECONDS * 10)):
                if self._stop:
                    return
                time.sleep(0.1)

    # ----------------------------------------------------------- Windows
    def _scan_windows(self):
        for window in _windows_titles():
            title = youtube_title_from_window(window)
            if not title or title in self._seen:
                continue
            self._seen.add(title)
            item = self._resolve_title(title)
            if item:
                self.detected.emit(item)

    def _resolve_title(self, title: str) -> dict | None:
        opts = {**self._base_opts_fn(), "quiet": True, "no_warnings": True, "extract_flat": True,
                "skip_download": True, "logger": _YDLLogger()}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch5:{title}", download=False) or {}
        except Exception as exc:
            log.info("Başlık aranamadı (%s): %s", title, exc)
            return None
        best = max(info.get("entries") or [], key=lambda e: similar(title, e.get("title") or ""), default=None)
        if not best or similar(title, best.get("title") or "") < 0.85:
            return None  # arama / kanal sayfası ya da emin olunamayan eşleşme
        return {"url": f"https://www.youtube.com/watch?v={best['id']}", "title": best.get("title") or title,
                "kind": "video", "format": None, "source": "window"}

    # ------------------------------------------------------------- macOS
    def _scan_mac(self):
        for app, (process, tab) in MAC_BROWSERS.items():
            if app in self._mac_denied:
                continue
            running = subprocess.run(["pgrep", "-x", process], capture_output=True).returncode == 0
            if not running:
                continue
            script = (f'tell application "{app}"\n'
                      f'  if (count of windows) is 0 then return ""\n'
                      f'  return (URL of {tab}) & linefeed & (name of {tab})\n'
                      f'end tell')
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                if "-1743" in res.stderr:  # kullanıcı izin vermedi
                    log.info("%s için otomasyon izni verilmedi; bu tarayıcı izlenmeyecek", app)
                    self._mac_denied.add(app)
                continue
            url, _, title = res.stdout.strip().partition("\n")
            link = analyze(url) if "youtube.com" in url or "youtu.be" in url else None
            if not link or link.kind not in ("video", "mix", "both"):
                continue
            if link.video_url in self._seen:
                continue
            self._seen.add(link.video_url)
            clean = re.sub(r"^\(\d+\)\s*", "", title).removesuffix(" - YouTube").strip()
            self.detected.emit({"url": link.video_url, "title": clean, "kind": "video", "format": None,
                                "source": "window"})
