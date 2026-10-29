"""assets/ altındaki uygulama simgelerini (png, ico, icns) üretir.

Kullanım:  python packaging/make_icons.py   (PySide6 ve Pillow gerekir)
"""
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtGui import QGuiApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from byk_music.ui.styles import app_icon  # noqa: E402

app = QGuiApplication(["", "-platform", "offscreen"])
out = ROOT / "assets"
out.mkdir(exist_ok=True)
png = out / "icon.png"
app_icon(1024).pixmap(1024, 1024).save(str(png))
img = Image.open(png)
img.save(out / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
img.save(out / "icon.icns")
print("Simgeler üretildi:", ", ".join(p.name for p in sorted(out.iterdir())))
