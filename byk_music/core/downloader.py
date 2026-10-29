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


ACCOUNT_LISTS = ("list=LL", "list=WL", "list=LM")   # yalnızca oturumla erişilebilen listeler
AUTH_HINTS = ("sign in", "login required", "private", "age", "members-only", "confirm you",
              "does not exist", "unavailable")


def _extract_once(url: str, opts: dict) -> dict:
    """Yalnızca başlık, süre ve kanal bilgisini okur; video biçimi seçmez (process=False).
    Biçim seçimi indirme sırasında yapılır; böylece listeleme biçim hatasına takılmaz."""
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False, process=False)
        for _ in range(3):  # youtu.be gibi yönlendirmeleri izle
            if info and info.get("_type") in ("url", "url_transparent") and info.get("url"):
                info = ydl.extract_info(info["url"], download=False, process=False)
            else:
                break
        if info and info.get("entries") is not None:
            info["entries"] = list(info["entries"])
    return info


def extract_items(url: str, base_opts: dict, account_opts: dict | None = None) -> dict:
    """Bağlantıdaki tek videoyu ya da listedeki tüm videoları (indirmeden) listeler.
    Önce oturumsuz denenir; içerik oturum gerektiriyorsa YouTube hesabıyla yeniden denenir."""
    opts = {
        **base_opts,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignore_no_formats_error": True,
        "logger": _YDLLogger(),
    }
    with_account = {**opts, **(account_opts or {})}
    attempts = [with_account] if account_opts and any(k in url for k in ACCOUNT_LISTS) else [opts]
    if account_opts and attempts[0] is opts:
        attempts.append(with_account)
    info, last_exc = None, None
    for i, attempt in enumerate(attempts):
        try:
            info = _extract_once(url, attempt)
            if info:
                break
        except Exception as exc:
            last_exc = exc
            retry = i + 1 < len(attempts) and any(k in str(exc).lower() for k in AUTH_HINTS)
            if not retry:
                raise
            log.info("Oturumsuz listelenemedi, YouTube hesabıyla deneniyor: %s", exc)
    if not info:
        raise last_exc or ValueError("Bağlantıdan bilgi alınamadı.")

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

    def __init__(self, url: str, base_opts: dict | None = None, account_opts: dict | None = None):
        super().__init__()
        self.url = url
        self.base_opts = base_opts or {}
        self.account_opts = account_opts or {}

    def run(self):
        try:
            self.result.emit(extract_items(self.url, self.base_opts, self.account_opts))
        except Exception as exc:  # yt-dlp çok çeşitli hatalar fırlatır
            log.exception("Bilgi alınamadı")
            self.failed.emit(_clean_error(exc))


class MultiInfoWorker(QThread):
    """Birden fazla bağlantıyı paralel çözümler; her sonuç geldikçe bildirir."""

    resolved = Signal(object, dict)   # anahtar, extract_items sonucu
    failed = Signal(object, str)      # anahtar, hata

    def __init__(self, tasks: list[tuple[object, str]], base_opts: dict | None = None, workers: int = 4,
                 account_opts: dict | None = None):
        super().__init__()
        self.tasks = tasks
        self.base_opts = base_opts or {}
        self.account_opts = account_opts or {}
        self.workers = workers

    def run(self):
        def one(key, url):
            try:
                self.resolved.emit(key, extract_items(url, self.base_opts, self.account_opts))
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
    if "sign in to confirm you" in low and "bot" in low:
        return ("YouTube bu bağlantıdan doğrulama istedi. YouTube Hesabım sayfasından oturumu bağlayıp "
                "yeniden deneyin.")
    if "sign in to confirm your age" in low or "age-restricted" in low:
        return "Bu video yaş sınırlı; indirmek için YouTube Hesabım sayfasından oturumu bağlayın."
    if "sign in to confirm" in low or "login required" in low or "private" in low:
        return "Bu içerik için YouTube oturumu gerekiyor. Hesap sayfasından bağlanın."
    if "requested format is not available" in low:
        return ("YouTube bu video için indirilebilir bir biçim sunmadı. YouTube hesabı bağlıysa "
                "YouTube Hesabım sayfasından bağlantıyı kesip yeniden deneyin.")
    if "ffmpeg" in low and ("not found" in low or "not installed" in low):
        return "Dönüştürme aracı (ffmpeg) bulunamadı. Uygulamayı yeniden kurmayı deneyin."
    if "http error 403" in low:
        return "YouTube indirmeyi geçici olarak reddetti (403). Birkaç dakika sonra yeniden deneyin."
    if "unable to download" in low and ("timed out" in low or "connection" in low):
        return "Bağlantı hatası: YouTube'a ulaşılamadı. İnternet / proxy ayarlarınızı kontrol edin."
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

    def __init__(self, jobs: list[dict], opts: dict, base_opts: dict | None = None, workers: int = 3,
                 account_opts: dict | None = None):
        """base_opts: proxy gibi her istekte kullanılan seçenekler; account_opts: YouTube oturumu
        (yalnızca içerik giriş gerektirdiğinde kullanılır)."""
        super().__init__()
        self.opts = opts
        self.base_opts = base_opts or {}
        self.account_opts = account_opts or {}
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
            **(self.account_opts if job.get("use_account") else {}),
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
            opts["format"] = job.get("format_override") or "ba/b"
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
                fmt = "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
            else:
                fmt = (f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/bv*[height<={h}]+ba/"
                       f"b[height<={h}]/bv*+ba/b")
            opts["format"] = job.get("format_override") or fmt
            opts["merge_output_format"] = "mp4"
            opts["postprocessors"] = [{"key": "FFmpegMetadata", "add_metadata": True}]
        return opts

    def _attempt(self, job: dict, ctx: dict):
        with yt_dlp.YoutubeDL(self._build_opts(job, ctx)) as ydl:
            if job.get("name"):
                ydl.add_post_processor(SetTitlePP(job["name"]), when="pre_process")
            elif job.get("clean"):
                ydl.add_post_processor(CleanTitlePP(), when="pre_process")
            ydl.download([job["url"]])

    def _run_job(self, job: dict):
        """Bir öğeyi indirir. Başarısız olursa nedene göre farklı yollarla yeniden dener:
        - oturum gerekiyorsa YouTube hesabıyla,
        - oturumla sorun çıkıyorsa oturumsuz,
        - istenen biçim yoksa tek dosyalı en iyi biçimle."""
        row = job["row"]
        if self._cancel:
            self.state.emit(row, "cancelled", "İptal edildi")
            return
        self.state.emit(row, "active", "Başlıyor…")
        attempts = [dict(job, use_account=False)]
        last_exc = None
        while attempts:
            current = attempts.pop(0)
            ctx = {"path": None}
            try:
                self._attempt(current, ctx)
                if ctx["path"]:
                    self.saved.emit(row, ctx["path"])
                self.state.emit(row, "done", "Tamamlandı")
                return
            except Cancelled:
                self.state.emit(row, "cancelled", "İptal edildi")
                return
            except Exception as exc:
                if self._cancel:
                    self.state.emit(row, "cancelled", "İptal edildi")
                    return
                last_exc = exc
                low = str(exc).lower()
                log.warning("İndirme denemesi başarısız (%s): %s", job["url"], exc)
                needs_login = any(k in low for k in ("sign in", "login required", "private video", "age",
                                                     "members-only", "confirm you"))
                if needs_login and self.account_opts and not current.get("use_account"):
                    attempts.append(dict(current, use_account=True))
                    self.state.emit(row, "active", "YouTube hesabıyla yeniden deneniyor…")
                elif "requested format is not available" in low and not current.get("format_override"):
                    attempts.append(dict(current, format_override="b"))
                    self.state.emit(row, "active", "Farklı biçimle yeniden deneniyor…")
        log.error("İndirme hatası: %s", job["url"], exc_info=last_exc)
        self.state.emit(row, "error", _clean_error(last_exc)[:240])

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
