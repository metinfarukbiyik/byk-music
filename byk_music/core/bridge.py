"""Tarayıcı eklentisi köprüsü.

Yalnızca 127.0.0.1 üzerinde dinleyen küçük bir HTTP sunucusu. Dış ağa açık olmadığı için
güvenlik duvarı izni gerektirmez. Yalnızca tarayıcı eklentilerinden (chrome-extension://,
moz-extension://) gelen ve YouTube bağlantısı içeren istekleri kabul eder.

  GET  /ping    -> {"app": ..., "version": ...}
  POST /detect  {"url", "title"}            -> kullanıcı YouTube'da bir video açtı
  POST /add     {"url", "title", "format"}  -> kullanıcı "indir"e bastı
  POST /cookies {"cookies": [...]}          -> kullanıcı eklentiden YouTube oturumunu aktardı

Çerezler yalnızca kullanıcı eklentide "oturumu aktar" düğmesine bastığında gönderilir, yalnızca
youtube.com alan adına ait olanlar kabul edilir ve kullanıcının ayar klasörüne yalnızca kendisinin
okuyabileceği bir dosya olarak yazılır.
"""
import json
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .. import __version__
from ..config import APP_NAME
from .settings import config_dir

log = logging.getLogger("byk.bridge")

PORT = 47815
YT_URL = re.compile(r"^https://((www|m|music)\.)?youtube\.com/(watch\?|shorts/|playlist\?)[\w\-=&?/%.]+$"
                    r"|^https://youtu\.be/[\w\-]+(\?[\w\-=&%.]*)?$")
ALLOWED_ORIGINS = ("chrome-extension://", "moz-extension://", "safari-web-extension://")
COOKIE_FILE_NAME = "youtube-cookies.txt"
SESSION_COOKIES = ("SAPISID", "__Secure-3PAPISID", "LOGIN_INFO")


def cookie_file() -> Path:
    return config_dir() / COOKIE_FILE_NAME


def write_cookie_file(cookies: list) -> int:
    """Eklentiden gelen çerezleri Netscape (cookies.txt) biçiminde yazar; yazılan çerez sayısını döndürür."""
    lines = ["# Netscape HTTP Cookie File", "# BYK Music: tarayıcı eklentisinden aktarılan YouTube oturumu", ""]
    count = 0
    for c in cookies:
        domain = str(c.get("domain", ""))
        name, value = str(c.get("name", "")), str(c.get("value", ""))
        if not name or not domain.lstrip(".").endswith("youtube.com") or "\t" in name + value:
            continue
        include_sub = "FALSE" if c.get("hostOnly") else "TRUE"
        if include_sub == "TRUE" and not domain.startswith("."):
            domain = "." + domain
        expiry = int(c.get("expirationDate") or 0)
        secure = "TRUE" if c.get("secure") else "FALSE"
        prefix = "#HttpOnly_" if c.get("httpOnly") else ""
        lines.append("\t".join([prefix + domain, include_sub, str(c.get("path") or "/"), secure, str(expiry),
                                name, value]))
        count += 1
    path = cookie_file()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return count


class BrowserBridge(QObject):
    detected = Signal(dict)
    add_requested = Signal(dict)
    cookies_received = Signal(str, int)   # dosya yolu, çerez sayısı

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = None

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> bool:
        if self._server:
            return True
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, code: int, data: dict):
                body = json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _allowed(self) -> bool:
                origin = self.headers.get("Origin", "")
                return not origin or origin.startswith(ALLOWED_ORIGINS)

            def do_GET(self):
                if self.path == "/ping" and self._allowed():
                    self._reply(200, {"app": APP_NAME, "version": __version__})
                else:
                    self._reply(404, {"error": "not found"})

            def do_POST(self):
                if not self._allowed():
                    self._reply(403, {"error": "forbidden"})
                    return
                limit = 262144 if self.path == "/cookies" else 16384
                try:
                    length = min(int(self.headers.get("Content-Length", 0)), limit)
                    data = json.loads(self.rfile.read(length) or b"{}")
                except (ValueError, OSError):
                    self._reply(400, {"error": "bad request"})
                    return
                if self.path == "/cookies":
                    cookies = data.get("cookies")
                    if not isinstance(cookies, list):
                        self._reply(400, {"error": "bad request"})
                        return
                    # oturum açılmamışsa mevcut geçerli dosyanın üzerine yazma
                    if not any(isinstance(c, dict) and c.get("name") in SESSION_COOKIES for c in cookies):
                        self._reply(200, {"ok": False, "error": "not signed in"})
                        return
                    count = write_cookie_file([c for c in cookies if isinstance(c, dict)])
                    bridge.cookies_received.emit(str(cookie_file()), count)
                    self._reply(200, {"ok": True, "count": count})
                    return
                url = str(data.get("url", ""))
                if not YT_URL.match(url):
                    self._reply(400, {"error": "unsupported url"})
                    return
                fmt = data.get("format")
                item = {
                    "url": url,
                    "title": str(data.get("title", "")).strip()[:300],
                    "kind": "playlist" if "/playlist?" in url else "video",
                    "format": fmt if fmt in ("mp3", "mp4") else None,
                }
                if self.path == "/detect":
                    bridge.detected.emit(item)
                elif self.path == "/add":
                    bridge.add_requested.emit(item)
                else:
                    self._reply(404, {"error": "not found"})
                    return
                self._reply(200, {"ok": True})

        try:
            self._server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        except OSError as exc:
            log.warning("Tarayıcı köprüsü başlatılamadı (port %s): %s", PORT, exc)
            return False
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="browser-bridge", daemon=True).start()
        log.info("Tarayıcı köprüsü 127.0.0.1:%s üzerinde çalışıyor", PORT)
        return True

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
