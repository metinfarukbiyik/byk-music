"""Uygulama kimliği, yayıncı ve geliştirici bilgileri.

Buradaki değerler arayüzde, kurulum programında (Denetim Masası > Programlar)
ve Windows dosya özelliklerinde görünen bilgilerin tek kaynağıdır.
"""

APP_NAME = "BYK Music"
APP_TAGLINE = "YouTube MP3 & MP4 İndirici"
APP_ID = "dev.biyik.bykmusic"

PUBLISHER = "biyik.dev"
COPYRIGHT = "© 2026 Metin Faruk Bıyık (biyik.dev). Tüm hakları saklıdır."

# Otomatik güncelleme bu deponun Releases sayfasını izler.
GITHUB_OWNER = "metinfarukbiyik"
GITHUB_REPO = "byk-music"
REPO_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"

DEVELOPER = {
    "name": "Metin Faruk Bıyık",
    "brand": "biyik.dev",
    "title": "Yazılım Geliştirici",
    "email": "metin@biyik.dev",
    "website": "https://biyik.dev",
    "github": f"https://github.com/{GITHUB_OWNER}",
    # Uluslararası biçimde, yalnızca rakam: 90 5xx xxx xx xx -> "905xxxxxxxxx"
    "whatsapp": "",
    "about": (
        "BYK Music; YouTube müzik ve videolarını MP3 / MP4 olarak indirmek, "
        "oynatma listelerinden istenen parçaları seçip indirmek için geliştirilmiş "
        "Windows ve macOS uyumlu bir masaüstü uygulamasıdır."
    ),
}
