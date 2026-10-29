"""Sürüme eklenen latest.json dosyasını üretir (GitHub Actions tarafından çağrılır).

  python packaging/release_manifest.py <sürüm> <sürüm-notları.md> <dosya-klasörü> > latest.json

Uygulama güncellemeyi bu dosyadan denetler; sürüm dosyaları API istek sınırına takılmaz.
"""
import json
import sys
from pathlib import Path

OWNER, REPO = "metinfarukbiyik", "byk-music"
version = sys.argv[1].lstrip("v")
notes = Path(sys.argv[2]).read_text(encoding="utf-8")
files = Path(sys.argv[3])
assets = {}
for key, name in (("windows", "BYKMusic-Windows-Setup.exe"), ("macos", "BYKMusic-macOS.zip")):
    f = files / name
    if f.exists():
        assets[key] = {"name": name, "size": f.stat().st_size}
print(json.dumps({
    "version": version,
    "tag": f"v{version}",
    "notes": notes,
    "page": f"https://github.com/{OWNER}/{REPO}/releases/tag/v{version}",
    "assets": assets,
}, ensure_ascii=False, indent=2))
