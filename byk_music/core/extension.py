"""Tarayıcı eklentisinin dosyalarını hazırlama, tarayıcıyı bulma ve uzantılar sayfasını açma.

Tarayıcılar güvenlik gereği mağaza dışı eklentilerin bir program tarafından sessizce kurulmasına izin
vermez. Bu yüzden kurulum sihirbazı dosyaları hazırlar, uzantılar sayfasını açar ve kullanıcıya son
adımı (klasörü sayfaya bırakmak) gösterir. Eklenti yüklenince uygulamaya kendisi haber verir.
"""
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .settings import config_dir

log = logging.getLogger("byk.extension")

# tarayıcı anahtarı: (görünen ad, uzantılar sayfası)
BROWSERS = {
    "chrome": ("Google Chrome", "chrome://extensions"),
    "edge": ("Microsoft Edge", "edge://extensions"),
    "brave": ("Brave", "brave://extensions"),
    "opera": ("Opera", "opera://extensions"),
    "vivaldi": ("Vivaldi", "vivaldi://extensions"),
    "chromium": ("Chromium", "chrome://extensions"),
    "firefox": ("Firefox", "about:debugging#/runtime/this-firefox"),
}
_WIN_EXE = {"chrome": "chrome.exe", "edge": "msedge.exe", "brave": "brave.exe", "opera": "opera.exe",
            "vivaldi": "vivaldi.exe", "chromium": "chrome.exe", "firefox": "firefox.exe"}
_MAC_APP = {"chrome": "Google Chrome", "edge": "Microsoft Edge", "brave": "Brave Browser", "opera": "Opera",
            "vivaldi": "Vivaldi", "chromium": "Chromium", "firefox": "Firefox"}


# ------------------------------------------------------------ eklenti dosyaları
def extension_source() -> Path:
    """Uygulamayla birlikte gelen eklenti klasörü."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "browser-extension"


def extension_dir() -> Path:
    """Tarayıcının yüklediği kalıcı eklenti klasörü (uygulama güncellense de yolu değişmez)."""
    return config_dir() / "browser-extension"


def _manifest_version(folder: Path) -> str:
    try:
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return ""


def bundled_version() -> str:
    return _manifest_version(extension_source())


def sync_extension_files() -> Path | None:
    """Kalıcı klasördeki eklenti dosyalarını uygulamayla gelen sürüme getirir.
    Eklenti, sürümün değiştiğini görünce kendini yeniden yükler."""
    src, dest = extension_source(), extension_dir()
    if not src.exists():
        return None
    if _manifest_version(dest) != _manifest_version(src):
        shutil.copytree(src, dest, dirs_exist_ok=True)
        log.info("Eklenti dosyaları güncellendi: %s", _manifest_version(src))
    return dest


# ---------------------------------------------------------------- tarayıcılar
def _win_exe(key: str) -> str | None:
    exe = _WIN_EXE[key]
    try:
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                    path = winreg.QueryValue(k, None)
                    if path and Path(path).exists() and (key != "chromium" or "Chromium" in path):
                        return path
            except OSError:
                pass
    except ImportError:
        pass
    env = os.environ
    pf, pf86, local = env.get("ProgramFiles", ""), env.get("ProgramFiles(x86)", ""), env.get("LOCALAPPDATA", "")
    candidates = {
        "chrome": [rf"{pf}\Google\Chrome\Application\chrome.exe", rf"{pf86}\Google\Chrome\Application\chrome.exe",
                   rf"{local}\Google\Chrome\Application\chrome.exe"],
        "edge": [rf"{pf86}\Microsoft\Edge\Application\msedge.exe", rf"{pf}\Microsoft\Edge\Application\msedge.exe"],
        "brave": [rf"{pf}\BraveSoftware\Brave-Browser\Application\brave.exe",
                  rf"{local}\BraveSoftware\Brave-Browser\Application\brave.exe"],
        "opera": [rf"{local}\Programs\Opera\opera.exe", rf"{local}\Programs\Opera\launcher.exe"],
        "vivaldi": [rf"{local}\Vivaldi\Application\vivaldi.exe", rf"{pf}\Vivaldi\Application\vivaldi.exe"],
        "chromium": [rf"{local}\Chromium\Application\chrome.exe"],
        "firefox": [rf"{pf}\Mozilla Firefox\firefox.exe", rf"{pf86}\Mozilla Firefox\firefox.exe"],
    }[key]
    return next((c for c in candidates if c and Path(c).exists()), None)


def _mac_app(key: str) -> str | None:
    name = _MAC_APP[key]
    for base in (Path("/Applications"), Path.home() / "Applications"):
        if (base / f"{name}.app").exists():
            return name
    return None


def available_browsers() -> list[tuple[str, str]]:
    """Eklenti kurulabilecek ve bu bilgisayarda bulunan tarayıcılar: [(anahtar, ad)]."""
    found = []
    for key, (label, _) in BROWSERS.items():
        ok = _win_exe(key) if sys.platform.startswith("win") else _mac_app(key) if sys.platform == "darwin" else None
        if ok:
            found.append((key, label))
    return found


def open_extensions_page(key: str) -> bool:
    """Seçilen tarayıcıda uzantılar sayfasını açar."""
    url = BROWSERS[key][1]
    try:
        if sys.platform.startswith("win"):
            exe = _win_exe(key)
            if not exe:
                return False
            # Tarayıcı kapalıysa sayfa açılır; açıksa tarayıcılar iç sayfaları dışarıdan açmaya izin
            # vermediğinden yalnızca yeni pencere gelir (adres sihirbazda panoya kopyalanır).
            subprocess.Popen([exe, "--new-window", url] if key != "firefox" else [exe, url], close_fds=True)
            return True
        if sys.platform == "darwin":
            app = _mac_app(key)
            if not app:
                return False
            script = f'tell application "{app}"\nactivate\nopen location "{url}"\nend tell'
            if subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10).returncode == 0:
                return True
            subprocess.Popen(["open", "-a", app, url])
            return True
    except Exception as exc:
        log.warning("Uzantılar sayfası açılamadı (%s): %s", key, exc)
    return False


def browser_from_user_agent(ua: str) -> str:
    ua = ua or ""
    if "Firefox/" in ua:
        return "firefox"
    if "Edg/" in ua:
        return "edge"
    if "OPR/" in ua:
        return "opera"
    if "Vivaldi" in ua:
        return "vivaldi"
    return "chrome"
