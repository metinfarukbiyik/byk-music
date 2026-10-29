"""YouTube bağlantılarının türünü belirler.

watch?v=X&list=RD…  YouTube'un otomatik "Mix / Radyo" listesidir; gerçek bir liste değildir ve
sonsuz öneri içerir. Bu durumda yalnızca video alınır. Gerçek bir oynatma listesiyle birlikte gelen
video bağlantılarında kullanıcıya hangisini istediği sorulur.
"""
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass
class LinkInfo:
    kind: str                 # video | playlist | both | mix | other
    video_url: str = ""
    playlist_url: str = ""

    @property
    def fetch_url(self) -> str:
        return self.playlist_url if self.kind == "playlist" else self.video_url or self.playlist_url


def is_mix(list_id: str) -> bool:
    # RD… otomatik karışık listeler; RDCLAK… ise YouTube Music'in gerçek albüm/liste kimlikleri
    return list_id.startswith("RD") and not list_id.startswith("RDCLAK")


def analyze(url: str) -> LinkInfo:
    u = urlparse(url.strip())
    host = (u.hostname or "").lower()
    q = parse_qs(u.query)
    video = (q.get("v") or [""])[0]
    list_id = (q.get("list") or [""])[0]
    if host.endswith("youtu.be"):
        video = u.path.strip("/").split("/")[0]
    elif u.path.startswith("/shorts/"):
        video = u.path.split("/")[2] if len(u.path.split("/")) > 2 else ""

    base = "https://music.youtube.com" if host.startswith("music.") else "https://www.youtube.com"
    video_url = f"{base}/watch?v={video}" if video else ""
    playlist_url = f"{base}/playlist?list={list_id}" if list_id else ""

    if u.path.startswith("/playlist") and list_id:
        return LinkInfo("playlist", playlist_url=playlist_url)
    if video and list_id:
        if is_mix(list_id) or "start_radio" in q:
            return LinkInfo("mix", video_url=video_url)
        return LinkInfo("both", video_url=video_url, playlist_url=playlist_url)
    if video:
        return LinkInfo("video", video_url=video_url)
    return LinkInfo("other", video_url=url.strip())
