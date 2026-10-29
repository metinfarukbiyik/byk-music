import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .settings import config_dir

MAX_ITEMS = 1000


class History:
    """İndirilen dosyaların kaydı (history.json)."""

    def __init__(self):
        self._file = config_dir() / "history.json"
        try:
            self.items: list[dict] = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.items = []

    def add(self, title: str, url: str, path: str, fmt: str):
        self.items.insert(0, {
            "title": title, "url": url, "path": path, "format": fmt,
            "date": datetime.now().isoformat(timespec="seconds"),
        })
        del self.items[MAX_ITEMS:]
        self.save()

    def clear(self):
        self.items = []
        self.save()

    def save(self):
        try:
            self._file.write_text(json.dumps(self.items, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def reveal_in_folder(path: str):
    """Dosyayı Finder / Gezgin içinde seçili olarak gösterir."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    elif sys.platform.startswith("win"):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        subprocess.Popen(["xdg-open", str(Path(path).parent)])
