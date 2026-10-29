"""Video başlıklarından temiz dosya adı üretimi.

"Tarkan - Şımarık (Official Video) [HD] #pop" -> "Tarkan - Şımarık"
"""
import re

from yt_dlp.postprocessor import PostProcessor

# Parantez içinde geçtiğinde etiketin tamamen atılmasına yol açan sözcükler
TAG_WORDS = (
    r"official|video|audio|lyrics?|lyric video|visuali[sz]er|music video|mv|clip|klip|resmi|"
    r"şarkı sözleri|sözleri|altyazılı|hd|hq|4k|8k|1080p|720p|remaster(ed)?|explicit|"
    r"full album|teaser|trailer|studio version|"
    r"prod\.?|color coded|audio only|360|vevo|official audio|official video|official music video"
)
_BRACKETS = re.compile(r"\s*[\(\[\{【「]([^\)\]\}】」]*)[\)\]\}】」]")
_TAG_RE = re.compile(rf"\b({TAG_WORDS})\b", re.IGNORECASE)
_PIPE_TAIL = re.compile(r"\s*[|｜•·]\s*(?=[^|｜•·]*$).*$")
_HASHTAG = re.compile(r"\s*#[\wÀ-ɏ]+")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D]+")
_SPACES = re.compile(r"\s{2,}")
_QUALITY_TAIL = re.compile(r"(\s+(hd|hq|4k|8k|1080p|720p|2160p|m/v|mv))+\s*$", re.IGNORECASE)
_DASHES = re.compile(r"\s*[–—]\s*")


def clean_title(title: str) -> str:
    text = title or ""
    text = _EMOJI.sub("", text)
    text = _HASHTAG.sub("", text)
    # Etiket içeren parantezleri kaldır, "feat." gibi anlamlı olanları koru
    text = _BRACKETS.sub(lambda m: "" if _TAG_RE.search(m.group(1)) else m.group(0), text)
    # "Şarkı | Official Video" gibi dikey çizgiden sonraki etiket kısmı
    tail = _PIPE_TAIL.search(text)
    if tail and _TAG_RE.search(tail.group(0)):
        text = text[:tail.start()]
    # Parantezsiz sondaki etiketler: "Şarkı - Official Video", "Şarkı Lyrics"
    text = re.sub(rf"\s*[-–—:]\s*({TAG_WORDS})(\s+({TAG_WORDS}))*\s*$", "", text, flags=re.IGNORECASE)
    text = _QUALITY_TAIL.sub("", text)
    text = _DASHES.sub(" - ", text)
    text = _SPACES.sub(" ", text).strip(" -_.,|")
    return text or (title or "").strip()


def safe_filename(name: str) -> str:
    """Windows ve macOS'ta geçerli dosya adı."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", name)
    name = name.strip().rstrip(".")
    return name[:180] or "indirilen"


class SetTitlePP(PostProcessor):
    """İndirmeden önce başlığı kullanıcının belirlediği adla değiştirir.
    "Sanatçı - Şarkı" biçimindeyse sanatçı ve parça etiketleri de doldurulur."""

    def __init__(self, title: str):
        super().__init__()
        self._title = title

    def run(self, info):
        info["title"] = self._title
        if " - " in self._title:
            artist, track = self._title.split(" - ", 1)
            info["artist"] = artist.strip()
            info["track"] = track.strip()
        return [], info


class CleanTitlePP(PostProcessor):
    """Ad önceden belirlenmemişse YouTube başlığını etiketlerden temizler."""

    def run(self, info):
        info["title"] = clean_title(info.get("title") or "")
        return [], info
