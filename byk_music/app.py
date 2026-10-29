import logging
import os
import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QApplication

from .config import APP_NAME
from .core.settings import Settings, config_dir
from .ui.dev_dialog import LogBuffer
from .ui.main_window import MainWindow
from .ui.splash import Splash
from .ui.styles import app_icon, build_qss, light_palette


def _setup_ssl():
    """Python'un sistem sertifikası bulamadığı durumlar (macOS, PyInstaller) için certifi kullan."""
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except ImportError:
        pass


def run() -> int:
    _setup_ssl()
    logbuf = LogBuffer()
    logging.basicConfig(level=logging.INFO, handlers=[logbuf])

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("BYK")
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setStyleSheet(build_qss(config_dir() / "assets"))

    splash = Splash()
    splash.start()
    app.processEvents()
    win = MainWindow(Settings(), logbuf)

    def show_main():
        win.setWindowOpacity(0.0)
        win.show()
        win.raise_()
        win.activateWindow()
        fade = QPropertyAnimation(win, b"windowOpacity", win)
        fade.setDuration(450)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        fade.start()
        QTimer.singleShot(600, win.after_show)

    splash.finished.connect(show_main)
    return app.exec()
