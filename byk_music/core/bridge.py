"""Tarayıcı eklentisi köprüsü.

Yalnızca 127.0.0.1 üzerinde dinleyen küçük bir HTTP sunucusu. Dış ağa açık olmadığı için
güvenlik duvarı izni gerektirmez. Yalnızca tarayıcı eklentilerinden (chrome-extension://,
moz-extension://) gelen ve YouTube bağlantısı içeren istekleri kabul eder.

  GET  /ping    -> {"app": ..., "version": ...}
  POST /detect  {"url", "title"}            -> kullanıcı YouTube'da bir video açtı
  POST /add     {"url", "title", "format"}  -> kullanıcı "indir"e bastı
"""
import json
import logging
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QObject, Signal

from .. import __version__
from ..config import APP_NAME

log = logging.getLogger("byk.bridge")

PORT = 47815
YT_URL = re.compile(r"^https://((www|m|music)\.)?youtube\.com/(watch\?|shorts/|playlist\?)[\w\-=&?/%.]+$"
                    r"|^https://youtu\.be/[\w\-]+(\?[\w\-=&%.]*)?$")
ALLOWED_ORIGINS = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


class BrowserBridge(QObject):
    detected = Signal(dict)
    add_requested = Signal(dict)

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
                try:
                    length = min(int(self.headers.get("Content-Length", 0)), 16384)
                    data = json.loads(self.rfile.read(length) or b"{}")
                except (ValueError, OSError):
                    self._reply(400, {"error": "bad request"})
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
