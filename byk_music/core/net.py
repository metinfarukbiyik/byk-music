"""Ağ ayarları: proxy ve YouTube oturumu (tarayıcı çerezleri) tek yerden yönetilir.

Uygulama hiçbir zaman kullanıcı adı ya da parola görmez veya saklamaz; YouTube oturumu,
kullanıcının kendi tarayıcısında açık olan oturumun çerezleri okunarak kullanılır.
"""
import os
import sys
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QThread, Signal

BROWSERS = [("Google Chrome", "chrome"), ("Microsoft Edge", "edge"), ("Firefox", "firefox"),
            ("Brave", "brave"), ("Opera", "opera"), ("Vivaldi", "vivaldi"), ("Chromium", "chromium"),
            ("Safari", "safari")]


def _browser_dirs() -> dict[str, list[Path]]:
    home = Path.home()
    if sys.platform.startswith("win"):
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        roaming = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return {
            "chrome": [local / "Google" / "Chrome" / "User Data"],
            "edge": [local / "Microsoft" / "Edge" / "User Data"],
            "firefox": [roaming / "Mozilla" / "Firefox" / "Profiles"],
            "brave": [local / "BraveSoftware" / "Brave-Browser" / "User Data"],
            "opera": [roaming / "Opera Software" / "Opera Stable"],
            "vivaldi": [local / "Vivaldi" / "User Data"],
            "chromium": [local / "Chromium" / "User Data"],
        }
    support = home / "Library" / "Application Support"
    return {
        "chrome": [support / "Google" / "Chrome"],
        "edge": [support / "Microsoft Edge"],
        "firefox": [support / "Firefox" / "Profiles"],
        "brave": [support / "BraveSoftware" / "Brave-Browser"],
        "opera": [support / "com.operasoftware.Opera"],
        "vivaldi": [support / "Vivaldi"],
        "chromium": [support / "Chromium"],
        "safari": [home / "Library" / "Containers" / "com.apple.Safari", home / "Library" / "Cookies"],
    }


def installed_browsers() -> list[tuple[str, str]]:
    """Bu bilgisayarda profili bulunan tarayıcılar."""
    dirs = _browser_dirs()
    return [(label, key) for label, key in BROWSERS if any(p.exists() for p in dirs.get(key, []))]


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
    elif with_account and settings["account_source"] == "extension":
        from .bridge import cookie_file  # döngüsel içe aktarmayı önlemek için burada
        opts["cookiefile"] = str(cookie_file())
    elif with_account and settings["account_source"] == "file" and settings["cookies_file"]:
        opts["cookiefile"] = settings["cookies_file"]
    return opts


def account_opts(settings) -> dict:
    """Yalnızca YouTube oturumu seçenekleri (çerezler)."""
    base = ydl_base_opts(settings, with_account=False)
    return {k: v for k, v in ydl_base_opts(settings).items() if k not in base}


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
