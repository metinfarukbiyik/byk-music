import logging
import shutil
from pathlib import Path

import yt_dlp
from PySide6.QtCore import QThread, Signal
from yt_dlp.utils import sanitize_filename

from .naming import SetTitlePP

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


class InfoWorker(QThread):
    """Bağlantıdaki tek videoyu ya da listedeki tüm videoları (indirmeden) listeler."""

    result = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str, base_opts: dict | None = None):
        super().__init__()
        self.url = url
        self.base_opts = base_opts or {}

    def run(self):
        opts = {
            **self.base_opts,
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "logger": _YDLLogger(),
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
        except Exception as exc:  # yt-dlp çok çeşitli hatalar fırlatır
            log.exception("Bilgi alınamadı")
            self.failed.emit(_clean_error(exc))
            return
        if not info:
            self.failed.emit("Bağlantıdan bilgi alınamadı.")
            return

        entries = info.get("entries")
        is_playlist = entries is not None
        items = []
        for e in (entries if is_playlist else [info]):
            if not e:
                continue
            url = e.get("webpage_url") or e.get("url") or ""
            if not url.startswith("http") and e.get("id"):
                url = f"https://www.youtube.com/watch?v={e['id']}"
            items.append({
                "title": e.get("title") or e.get("id") or "(başlıksız)",
                "url": url,
                "duration": e.get("duration"),
                "uploader": e.get("uploader") or e.get("channel") or "",
            })
        self.result.emit({
            "is_playlist": is_playlist,
            "title": info.get("title") or "",
            "items": items,
        })


def _clean_error(exc: Exception) -> str:
    text = str(exc).replace("ERROR: ", "").strip() or exc.__class__.__name__
    low = text.lower()
    if "could not copy" in low and "cookie" in low:
        return "Tarayıcı çerezleri okunamadı. Tarayıcıyı tamamen kapatıp yeniden deneyin."
    if "failed to decrypt" in low or "app-bound" in low:
        return ("Bu tarayıcının çerezleri şifreli olduğu için okunamadı. "
                "Firefox kullanın ya da cookies.txt dosyası seçin.")
    if "sign in to confirm" in low or "login required" in low or "private" in low:
        return "Bu içerik için YouTube oturumu gerekiyor. Hesap sayfasından bağlanın."
    if "proxy" in low or "tunnel connection failed" in low:
        return f"Proxy bağlantısı kurulamadı: {text[:160]}"
    return text


class DownloadWorker(QThread):
    """Seçilen satırları sırayla indirir."""

    progress = Signal(int, float, str)   # satır, yüzde, açıklama
    state = Signal(int, str, str)        # satır, durum (active/processing/done/error/cancelled), mesaj
    saved = Signal(int, str)             # satır, son dosya yolu
    finished_all = Signal()

    def __init__(self, jobs: list[dict], opts: dict, base_opts: dict | None = None):
        """jobs: [{row, url, index}], opts: biçim/kalite/klasör ayarları, base_opts: proxy/oturum."""
        super().__init__()
        self.jobs = jobs
        self.opts = opts
        self.base_opts = base_opts or {}
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _build_opts(self, job: dict) -> dict:
        """job: {row, url, index, format?, name?, single?} — biçim ve ad iş başına değişebilir."""
        o = self.opts
        row = job["row"]
        in_playlist = o["is_playlist"] and not job.get("single")
        out_dir = Path(o["download_dir"])
        if in_playlist and o["playlist_folder"] and o["playlist_title"]:
            out_dir = out_dir / sanitize_filename(o["playlist_title"])
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"{job['index']:02d} - " if in_playlist and o["number_prefix"] else ""
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
                self._last_path = d.get("filename")
                self.progress.emit(row, 100, "İndirme bitti")

        def pp_hook(d):
            if d["status"] == "started":
                self.state.emit(row, "processing", "Dönüştürülüyor…")
            elif d["status"] == "finished":
                path = (d.get("info_dict") or {}).get("filepath")
                if path:
                    self._last_path = path

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

    def run(self):
        for job in self.jobs:
            row = job["row"]
            if self._cancel:
                self.state.emit(row, "cancelled", "İptal edildi")
                continue
            self.state.emit(row, "active", "Başlıyor…")
            self._last_path = None
            try:
                with yt_dlp.YoutubeDL(self._build_opts(job)) as ydl:
                    if job.get("name"):
                        ydl.add_post_processor(SetTitlePP(job["name"]), when="pre_process")
                    ydl.download([job["url"]])
                if self._last_path:
                    self.saved.emit(row, self._last_path)
                self.state.emit(row, "done", "Tamamlandı")
            except Cancelled:
                self.state.emit(row, "cancelled", "İptal edildi")
            except Exception as exc:
                if self._cancel:
                    self.state.emit(row, "cancelled", "İptal edildi")
                else:
                    log.exception("İndirme hatası: %s", job["url"])
                    self.state.emit(row, "error", _clean_error(exc)[:200])
        self.finished_all.emit()
