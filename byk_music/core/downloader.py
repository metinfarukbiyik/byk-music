import logging
import queue
import re
import shutil
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import yt_dlp
from PySide6.QtCore import QThread, Signal
from yt_dlp.utils import sanitize_filename

from .naming import CleanTitlePP, SetTitlePP

log = logging.getLogger("byk.downloader")


class Cancelled(Exception):
    pass


class _YDLLogger:
    def debug(self, msg):
        if not msg.startswith("[debug]"):
            log.debug(msg)

    def info(self, msg):
        log.info(msg)

    def warning(self, msg):
        log.warning(msg)

    def error(self, msg):
        log.error(msg)


def ffmpeg_path() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def fmt_duration(seconds) -> str:
    if not seconds:
        return "--:--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_size(num) -> str:
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def extract_items(url: str, base_opts: dict) -> dict:
    """Bağlantıdaki tek videoyu ya da listedeki tüm videoları (indirmeden) listeler."""
    opts = {
        **base_opts,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "logger": _YDLLogger(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise ValueError("Bağlantıdan bilgi alınamadı.")

    entries = info.get("entries")
    is_playlist = entries is not None
    items = []
    for e in (entries if is_playlist else [info]):
        if not e:
            continue
        link = e.get("webpage_url") or e.get("url") or ""
        if not link.startswith("http") and e.get("id"):
            link = f"https://www.youtube.com/watch?v={e['id']}"
        items.append({
            "title": e.get("title") or e.get("id") or "(başlıksız)",
            "url": link,
            "duration": e.get("duration"),
            "uploader": e.get("uploader") or e.get("channel") or "",
        })
    return {"is_playlist": is_playlist, "title": info.get("title") or "", "items": items}


class InfoWorker(QThread):
    """Tek bir bağlantıyı çözümler (liste sayfasının yerine geçer)."""

    result = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str, base_opts: dict | None = None):
        super().__init__()
        self.url = url
        self.base_opts = base_opts or {}

    def run(self):
        try:
            self.result.emit(extract_items(self.url, self.base_opts))
        except Exception as exc:  # yt-dlp çok çeşitli hatalar fırlatır
            log.exception("Bilgi alınamadı")
            self.failed.emit(_clean_error(exc))


class MultiInfoWorker(QThread):
    """Birden fazla bağlantıyı paralel çözümler; her sonuç geldikçe bildirir."""

    resolved = Signal(object, dict)   # anahtar, extract_items sonucu
    failed = Signal(object, str)      # anahtar, hata

    def __init__(self, tasks: list[tuple[object, str]], base_opts: dict | None = None, workers: int = 4):
        super().__init__()
        self.tasks = tasks
        self.base_opts = base_opts or {}
        self.workers = workers

    def run(self):
        def one(key, url):
            try:
                self.resolved.emit(key, extract_items(url, self.base_opts))
            except Exception as exc:
                log.warning("Bilgi alınamadı (%s): %s", url, exc)
                self.failed.emit(key, _clean_error(exc))

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for key, url in self.tasks:
                pool.submit(one, key, url)


def _clean_error(exc: Exception) -> str:
    text = str(exc).replace("ERROR: ", "").strip() or exc.__class__.__name__
    low = text.lower()
    missing = re.search(r"could not find (\w+) cookies database", low)
    if missing:
        return (f"{missing.group(1).capitalize()} tarayıcısında kayıtlı bir profil bulunamadı. "
                "Tarayıcı eklentisiyle oturum aktarmayı ya da başka bir tarayıcı seçmeyi deneyin.")
    if "could not copy" in low and "cookie" in low:
        return ("Tarayıcı açıkken çerezleri okunamadı. Tarayıcıyı tamamen kapatıp yeniden deneyin "
                "ya da “Eklenti ile aktar” yöntemini kullanın.")
    if "failed to decrypt" in low or "app-bound" in low:
        return ("Bu tarayıcı çerezlerini şifreli tuttuğu için doğrudan okunamıyor. "
                "“Eklenti ile aktar” yöntemini kullanın.")
    if "sign in to confirm" in low or "login required" in low or "private" in low:
        return "Bu içerik için YouTube oturumu gerekiyor. Hesap sayfasından bağlanın."
    if "proxy" in low or "tunnel connection failed" in low:
        return f"Proxy bağlantısı kurulamadı: {text[:160]}"
    return text


class DownloadWorker(QThread):
    """İndirme kuyruğu: aynı anda en fazla `workers` öğe indirilir.

    İndirme sürerken add_jobs() ile yeni işler eklenebilir, set_workers() ile eşzamanlı
    indirme sayısı değiştirilebilir. Kuyruk boşalıp tüm işler bitince finished_all yayınlanır.
    """

    progress = Signal(int, float, str)   # satır, yüzde, açıklama
    state = Signal(int, str, str)        # satır, durum (active/processing/done/error/cancelled), mesaj
    saved = Signal(int, str)             # satır, son dosya yolu
    finished_all = Signal()

    def __init__(self, jobs: list[dict], opts: dict, base_opts: dict | None = None, workers: int = 3):
        super().__init__()
        self.opts = opts
        self.base_opts = base_opts or {}
        self.workers = max(1, workers)
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._closed = False
        self._cancel = False
        for job in jobs:
            self._queue.put(job)

    def add_jobs(self, jobs: list[dict]) -> bool:
        """Çalışan kuyruğa iş ekler; kuyruk kapanmışsa False döner."""
        with self._lock:
            if self._closed or self._cancel:
                return False
            for job in jobs:
                self._queue.put(job)
            return True

    def set_workers(self, n: int):
        self.workers = max(1, min(int(n), 8))

    def cancel(self):
        self._cancel = True

    def _build_opts(self, job: dict, ctx: dict) -> dict:
        """job: {row, url, index, format, name?, playlist_title?, clean?} — ayarlar iş başına."""
        o = self.opts
        row = job["row"]
        playlist_title = job.get("playlist_title")
        out_dir = Path(o["download_dir"])
        if playlist_title and o["playlist_folder"]:
            out_dir = out_dir / sanitize_filename(playlist_title)
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"{job['index']:02d} - " if playlist_title and o["number_prefix"] else ""
        fmt_kind = job.get("format") or o["format"]

        def hook(d):
            if self._cancel:
                raise Cancelled()
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                pct = done * 100 / total if total else 0
                speed = d.get("speed")
                eta = d.get("eta")
                txt = f"{pct:.0f}%  {fmt_size(done)}/{fmt_size(total)}"
                if speed:
                    txt += f"  •  {fmt_size(speed)}/s"
                if eta is not None:
                    txt += f"  •  {int(eta)} sn"
                self.progress.emit(row, pct, txt)
            elif d["status"] == "finished":
                ctx["path"] = d.get("filename")
                self.progress.emit(row, 100, "İndirme bitti")

        def pp_hook(d):
            if d["status"] == "started":
                self.state.emit(row, "processing", "Dönüştürülüyor…")
            elif d["status"] == "finished":
                path = (d.get("info_dict") or {}).get("filepath")
                if path:
                    ctx["path"] = path

        opts = {
            **self.base_opts,
            "outtmpl": str(out_dir / f"{prefix}%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": False,
            "windowsfilenames": True,
            "progress_hooks": [hook],
            "postprocessor_hooks": [pp_hook],
            "logger": _YDLLogger(),
            "retries": 5,
            "fragment_retries": 5,
        }
        ff = ffmpeg_path()
        if ff:
            opts["ffmpeg_location"] = ff

        if fmt_kind == "mp3":
            opts["format"] = "bestaudio/best"
            pps = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                    "preferredquality": str(o["audio_quality"])},
                   {"key": "FFmpegMetadata", "add_metadata": True}]
            if o["embed_thumbnail"]:
                opts["writethumbnail"] = True
                pps.insert(0, {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
                pps.append({"key": "EmbedThumbnail"})
            opts["postprocessors"] = pps
        else:
            h = o["video_quality"]
            if h == "best":
                fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            else:
                fmt = (f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
                       f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best")
            opts["format"] = fmt
            opts["merge_output_format"] = "mp4"
            opts["postprocessors"] = [{"key": "FFmpegMetadata", "add_metadata": True}]
        return opts

    def _run_job(self, job: dict):
        row = job["row"]
        if self._cancel:
            self.state.emit(row, "cancelled", "İptal edildi")
            return
        self.state.emit(row, "active", "Başlıyor…")
        ctx = {"path": None}
        try:
            with yt_dlp.YoutubeDL(self._build_opts(job, ctx)) as ydl:
                if job.get("name"):
                    ydl.add_post_processor(SetTitlePP(job["name"]), when="pre_process")
                elif job.get("clean"):
                    ydl.add_post_processor(CleanTitlePP(), when="pre_process")
                ydl.download([job["url"]])
            if ctx["path"]:
                self.saved.emit(row, ctx["path"])
            self.state.emit(row, "done", "Tamamlandı")
        except Cancelled:
            self.state.emit(row, "cancelled", "İptal edildi")
        except Exception as exc:
            if self._cancel:
                self.state.emit(row, "cancelled", "İptal edildi")
            else:
                log.exception("İndirme hatası: %s", job["url"])
                self.state.emit(row, "error", _clean_error(exc)[:200])

    def run(self):
        running = set()
        with ThreadPoolExecutor(max_workers=8) as pool:
            while True:
                while len(running) < self.workers and not self._cancel:
                    try:
                        job = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    running.add(pool.submit(self._run_job, job))
                if self._cancel:
                    self._drain_cancelled()
                if running:
                    _, running = wait(running, timeout=0.25, return_when=FIRST_COMPLETED)
                    continue
                with self._lock:
                    if self._queue.empty():
                        self._closed = True
                        break
        self.finished_all.emit()

    def _drain_cancelled(self):
        while True:
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                return
            self.state.emit(job["row"], "cancelled", "İptal edildi")
