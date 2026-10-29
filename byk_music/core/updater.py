"""GitHub Releases üzerinden otomatik güncelleme.

Release varlıkları (assets) adında platform adı geçmelidir:
  BYKMusic-Windows-Setup.exe  ->  Windows kurulum programı (Inno Setup)
  BYKMusic-macOS.zip          ->  macOS (.app içerir)
"""
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .. import __version__
from ..config import GITHUB_OWNER, GITHUB_REPO

log = logging.getLogger("byk.updater")
API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


def parse_version(text: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:4]) or (0,)


def platform_key() -> str:
    return "windows" if sys.platform.startswith("win") else "macos" if sys.platform == "darwin" else "linux"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


class UpdateCheckWorker(QThread):
    available = Signal(dict)   # {version, notes, url, name, size}
    up_to_date = Signal()
    failed = Signal(str)

    def __init__(self, opener: urllib.request.OpenerDirector | None = None):
        super().__init__()
        self.opener = opener or urllib.request.build_opener()

    def run(self):
        try:
            req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                                       "User-Agent": "BYKMusic-Updater"})
            with self.opener.open(req, timeout=15) as resp:
                data = json.load(resp)
        except Exception as exc:
            log.warning("Güncelleme denetimi başarısız: %s", exc)
            self.failed.emit(str(exc))
            return

        latest = data.get("tag_name", "")
        if parse_version(latest) <= parse_version(__version__):
            self.up_to_date.emit()
            return
        key = platform_key()
        ext = {"windows": ".exe", "macos": ".zip"}.get(key, "")
        asset = next((a for a in data.get("assets", [])
                      if key in a["name"].lower() and a["name"].lower().endswith(ext)), None)
        self.available.emit({
            "version": latest.lstrip("v"),
            "notes": data.get("body") or "",
            "page": data.get("html_url") or RELEASES_PAGE,
            "url": asset["browser_download_url"] if asset else "",
            "name": asset["name"] if asset else "",
            "size": asset["size"] if asset else 0,
        })


class UpdateDownloadWorker(QThread):
    progress = Signal(int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, name: str, opener: urllib.request.OpenerDirector | None = None):
        super().__init__()
        self.url, self.name = url, name
        self.opener = opener or urllib.request.build_opener()

    def run(self):
        try:
            dest = Path(tempfile.mkdtemp(prefix="bykmusic-update-")) / self.name
            req = urllib.request.Request(self.url, headers={"User-Agent": "BYKMusic-Updater"})
            with self.opener.open(req, timeout=30) as resp, open(dest, "wb") as fh:
                total = int(resp.headers.get("Content-Length") or 0)
                got = 0
                while chunk := resp.read(1 << 16):
                    fh.write(chunk)
                    got += len(chunk)
                    if total:
                        self.progress.emit(int(got * 100 / total))
            self.done.emit(str(dest))
        except Exception as exc:
            log.exception("Güncelleme indirilemedi")
            self.failed.emit(str(exc))


def install_update(downloaded: str, relaunch: bool = True) -> bool:
    """İndirilen güncellemeyi kurar. Başarılıysa True döner; çağıran uygulamayı kapatmalıdır.

    Windows: kurulum programı sessiz kipte çalışır, Program Files'taki kurulumu
    yerinde günceller (yönetici onayı için Windows UAC penceresi bir kez görünür).
    macOS: .app paketi uygulama kapandıktan sonra yenisiyle değiştirilir.
    """
    if not is_frozen():
        return False
    src = Path(downloaded)
    try:
        if sys.platform.startswith("win"):
            args = "/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS"
            if not relaunch:
                args += " /NORELAUNCH"
            os.startfile(str(src), "runas", args)
            return True
        if sys.platform == "darwin":
            pid = os.getpid()
            app = Path(sys.executable).resolve().parents[2]      # X.app
            stage = src.parent / "extracted"
            stage.mkdir(exist_ok=True)
            subprocess.run(["ditto", "-x", "-k", str(src), str(stage)], check=True)
            new_app = next(stage.glob("*.app"))
            sh = src.parent / "update.sh"
            sh.write_text(
                "#!/bin/bash\n"
                f"while kill -0 {pid} 2>/dev/null; do sleep 1; done\n"
                f"rm -rf \"{app}\"\n"
                f"mv \"{new_app}\" \"{app}\"\n"
                f"xattr -dr com.apple.quarantine \"{app}\" 2>/dev/null\n"
                + (f"open \"{app}\"\n" if relaunch else ""))
            sh.chmod(0o755)
            subprocess.Popen(["/bin/bash", str(sh)], start_new_session=True, close_fds=True)
            return True
    except Exception:
        log.exception("Güncelleme kurulamadı")
    return False
