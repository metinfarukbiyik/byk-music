"""Ağ ayarları: proxy ve YouTube oturumu (tarayıcı çerezleri) tek yerden yönetilir.

Uygulama hiçbir zaman kullanıcı adı ya da parola görmez veya saklamaz; YouTube oturumu,
kullanıcının kendi tarayıcısında açık olan oturumun çerezleri okunarak kullanılır.
"""
import time
import urllib.request

from PySide6.QtCore import QThread, Signal

BROWSERS = [("Firefox", "firefox"), ("Google Chrome", "chrome"), ("Microsoft Edge", "edge"),
            ("Brave", "brave"), ("Opera", "opera"), ("Vivaldi", "vivaldi"), ("Chromium", "chromium"),
            ("Safari", "safari")]


def proxy_url(settings) -> str | None:
    """None: sistem ayarı, "": doğrudan bağlantı, diğer: özel proxy."""
    mode = settings["proxy_mode"]
    if mode == "none":
        return ""
    if mode == "custom" and settings["proxy_url"].strip():
        return settings["proxy_url"].strip()
    return None


def ydl_base_opts(settings, with_account: bool = True) -> dict:
    """yt-dlp'nin tüm çağrılarında ortak kullanılan seçenekler."""
    opts = {}
    proxy = proxy_url(settings)
    if proxy is not None:
        opts["proxy"] = proxy
    if with_account and settings["account_source"] == "browser":
        browser = settings["account_browser"]
        profile = settings["account_profile"].strip() or None
        opts["cookiesfrombrowser"] = (browser, profile, None, None)
    elif with_account and settings["account_source"] == "file" and settings["cookies_file"]:
        opts["cookiefile"] = settings["cookies_file"]
    return opts


def url_opener(settings) -> urllib.request.OpenerDirector:
    """Güncelleyici ve bağlantı testi için proxy ayarına uygun urllib açıcısı."""
    proxy = proxy_url(settings)
    if proxy is None:
        return urllib.request.build_opener()  # sistem / ortam proxy ayarları
    if proxy == "":
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))


class ConnectionTestWorker(QThread):
    """Proxy ayarıyla YouTube'a erişilebildiğini denetler."""

    done = Signal(bool, str)

    def __init__(self, opener: urllib.request.OpenerDirector):
        super().__init__()
        self.opener = opener

    def run(self):
        started = time.monotonic()
        try:
            req = urllib.request.Request("https://www.youtube.com/generate_204",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with self.opener.open(req, timeout=12) as resp:
                resp.read()
            self.done.emit(True, f"YouTube'a erişildi ({(time.monotonic() - started) * 1000:.0f} ms).")
        except Exception as exc:
            self.done.emit(False, str(exc)[:200])
