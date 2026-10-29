"""Derleme öncesi hazırlık (GitHub Actions tarafından çağrılır).

  python packaging/prepare.py <sürüm>

- byk_music/__init__.py içindeki sürümü günceller
- build/version_info.txt dosyasını (Windows dosya özellikleri) üretir
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from byk_music.config import APP_NAME, APP_TAGLINE, COPYRIGHT, PUBLISHER  # noqa: E402

version = sys.argv[1].lstrip("v")
nums = [int(n) for n in version.split(".")] + [0, 0, 0, 0]
vtuple = tuple(nums[:4])

(ROOT / "byk_music" / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")

strings = {
    "CompanyName": PUBLISHER,
    "FileDescription": f"{APP_NAME} – {APP_TAGLINE}",
    "FileVersion": version,
    "InternalName": "BYKMusic",
    "LegalCopyright": COPYRIGHT,
    "OriginalFilename": "BYKMusic.exe",
    "ProductName": APP_NAME,
    "ProductVersion": version,
}
table = ",\n          ".join(f"StringStruct({k!r}, {v!r})" for k, v in strings.items())
build = ROOT / "build"
build.mkdir(exist_ok=True)
(build / "version_info.txt").write_text(f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={vtuple}, prodvers={vtuple}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041F04B0', [
          {table}])]),
    VarFileInfo([VarStruct('Translation', [1055, 1200])])
  ]
)
""", encoding="utf-8")
print(f"Sürüm {version} hazırlandı")
