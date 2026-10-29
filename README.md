# BYK Music

**YouTube MP3 & MP4 İndirici** · Windows ve macOS

Geliştirici: **Metin Faruk Bıyık** · [biyik.dev](https://biyik.dev) · mb.metinbiyik@gmail.com

---

## Özellikler

- Tek video ya da oynatma listesi bağlantısı; listedeki parçaları görüp **istediklerini seçerek** indirme
- **MP3** (128–320 kbps, kapak resmi ve etiket bilgisi) ve **MP4** (360p – 4K)
- Biçim, kalite ve kayıt klasörü seçimi üst çubukta
- Satır bazında durum rozetleri, ilerleme çubukları, genel ilerleme, durdurma ve hatalıları yeniden deneme
- Uygulama içi bildirimler ve sistem bildirimleri (indirme başladı / tamamlandı)
- İndirme geçmişi, listede arama, panodaki YouTube bağlantısını otomatik algılama
- Uygulama içinden geliştiriciye **e-posta** ya da **WhatsApp** ile ulaşma
- **Otomatik güncelleme:** yeni sürüm arka planda indirilir ve kurulur
- ffmpeg uygulamayla birlikte gelir; ek kurulum gerekmez

## Kurulum

[Son sürümü indirin](https://github.com/metinfarukbiyik/byk-music/releases/latest):

| Sistem  | Dosya                         | Not |
|---------|-------------------------------|-----|
| Windows | `BYKMusic-Windows-Setup.exe`  | `C:\Program Files\BYK Music` altına kurulur; Denetim Masası > Programlar'da yayıncı **biyik.dev** olarak görünür. |
| macOS   | `BYKMusic-macOS.dmg`          | Uygulamayı *Applications* klasörüne sürükleyin. |

## Sürüm yayınlama

`main` dalına yapılan her push, GitHub Actions ile otomatik olarak:

1. Sürüm numarasını belirler (`byk_music/__init__.py` içindeki `ana.ara` + derleme numarası, örn. `1.0.12`)
2. Windows kurulum programını (Inno Setup) ve macOS uygulamasını derler
3. Hepsini yeni bir GitHub Release olarak yayınlar

Kurulu uygulamalar açılışta ve açıkken saatte bir yeni sürümü denetler, bildirim gösterir,
güncellemeyi indirir ve kurar. Ana/ara sürümü yükseltmek için `byk_music/__init__.py` dosyasını düzenleyin
(örn. `1.1.0`).

### Kod imzalama (Windows)

İmzasız uygulamalarda Windows SmartScreen "bilinmeyen yayıncı" uyarısı gösterir. Bir kod imzalama
sertifikanız olduğunda deponun **Settings → Secrets and variables → Actions** bölümüne ekleyin:

- `WINDOWS_CERT_PFX`: `.pfx` dosyasının base64 hali
- `WINDOWS_CERT_PASSWORD`: `.pfx` parolası

Bunlar tanımlandığında uygulama ve kurulum programı otomatik olarak imzalanır.

## Geliştirme

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Simgeleri yeniden üretmek için: `pip install -r requirements-dev.txt && python packaging/make_icons.py`

## Yapı

```
byk_music/
  config.py        uygulama, yayıncı ve geliştirici bilgileri (tek kaynak)
  core/            indirme motoru (yt-dlp), ayarlar, geçmiş, güncelleyici
  ui/              ana pencere, açılış ekranı, bildirimler, iletişim, geliştirici penceresi
packaging/         Windows kurulum programı, sürüm bilgisi, imzalama, simge üretimi
.github/workflows/ otomatik derleme ve yayınlama
```

---

© 2026 Metin Faruk Bıyık (biyik.dev). Tüm hakları saklıdır.
