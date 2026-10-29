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

    def remove(self, entries: list[dict]) -> list[tuple[int, dict]]:
        """Kayıtları siler; geri almak için (konum, kayıt) listesini döndürür."""
        ids = {id(e) for e in entries}
        removed = [(i, e) for i, e in enumerate(self.items) if id(e) in ids]
        self.items = [e for e in self.items if id(e) not in ids]
        self.save()
        return removed

    def restore(self, removed: list[tuple[int, dict]]):
        for index, entry in sorted(removed, key=lambda x: x[0]):
            self.items.insert(min(index, len(self.items)), entry)
        self.save()

    def save(self):
        try:
            self._file.write_text(json.dumps(self.items, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


TRASH_NAME = "Çöp Kutusu" if sys.platform == "darwin" else "Geri Dönüşüm Kutusu"


def move_to_trash(path: str) -> bool:
    """Dosyayı kalıcı silmek yerine Geri Dönüşüm Kutusu'na / Çöp Kutusu'na taşır."""
    from PySide6.QtCore import QFile
    return Path(path).exists() and QFile(path).moveToTrash()  # statik sürüm (bool, yol) demeti döndürür


def reveal_in_folder(path: str):
    """Dosyayı Finder / Gezgin içinde seçili olarak gösterir."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    elif sys.platform.startswith("win"):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        subprocess.Popen(["xdg-open", str(Path(path).parent)])
