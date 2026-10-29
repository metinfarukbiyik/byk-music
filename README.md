# BYK Music

**YouTube MP3 & MP4 İndirici** · Windows ve macOS

Geliştirici: **Metin Faruk Bıyık** · [biyik.dev](https://biyik.dev) · metin@biyik.dev

---

## Özellikler

- Tek video ya da oynatma listesi bağlantısı; listedeki parçaları görüp **istediklerini seçerek** indirme
- **MP3** (128–320 kbps, kapak resmi ve etiket bilgisi) ve **MP4** (360p – 4K)
- Biçim, kalite ve kayıt klasörü seçimi üst çubukta
- Satır bazında durum rozetleri, ilerleme çubukları, genel ilerleme, durdurma ve hatalıları yeniden deneme
- Uygulama içi bildirimler ve sistem bildirimleri (indirme başladı / tamamlandı)
- İndirme geçmişi, listede arama, panodaki YouTube bağlantısını otomatik algılama
- **Dosya adı düzenleme:** "(Official Video)", "[HD]", "#etiket" gibi kalıplar otomatik temizlenir; ad indirmeden önce
  listede çift tıklanarak değiştirilebilir ve MP3 etiketine (sanatçı / başlık) yazılır
- **Akıllı bağlantı algılama:** YouTube'un otomatik "Mix / Radyo" listeleri (`&list=RD…`) yerine yalnızca video alınır;
  gerçek bir liste içeren video bağlantılarında "yalnızca video / tüm liste" seçimi sunulur
- **YouTube Hesabım:** tarayıcı oturumu ya da cookies.txt ile bağlanıp beğenilen videolar, "Daha sonra izle" ve
  oynatma listelerinize erişim (uygulama parola görmez ve saklamaz)
- **Tarayıcı eklentisi ve indirme balonu:** YouTube'da açılan video algılanır, ekranın kenarında MP3 / MP4 indirme
  balonu çıkar; bağlantı kopyalamadan listeye eklenip indirilir
- **Proxy desteği:** sistem ayarı, doğrudan bağlantı ya da özel HTTP / HTTPS / SOCKS5 proxy
- Uygulama içinden geliştiriciye **e-posta** ya da **WhatsApp** ile ulaşma
- **Otomatik güncelleme:** yeni sürüm arka planda indirilir ve kurulur
- ffmpeg uygulamayla birlikte gelir; ek kurulum gerekmez

## Kurulum

[Son sürümü indirin](https://github.com/metinfarukbiyik/byk-music/releases/latest):

| Sistem  | Dosya                         | Not |
|---------|-------------------------------|-----|
| Windows | `BYKMusic-Windows-Setup.exe`  | `C:\Program Files\BYK Music` altına kurulur; Denetim Masası > Programlar'da yayıncı **biyik.dev** olarak görünür. |
| macOS   | `BYKMusic-macOS.dmg`          | Uygulamayı *Applications* klasörüne sürükleyin. |
| Tarayıcı | `BYKMusic-Browser-Extension.zip` | Uygulamada **Ayarlar → Tarayıcı entegrasyonu → Eklentiyi Kur** adımlarını izleyin. |

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
  ui/              ana pencere, açılış ekranı, bildirimler, hesap, iletişim, indirme balonu
browser-extension/ Chrome / Edge / Firefox eklentisi (127.0.0.1 üzerinden uygulamayla konuşur)
packaging/         Windows kurulum programı, sürüm bilgisi, imzalama, simge üretimi
.github/workflows/ otomatik derleme ve yayınlama
```

---

© 2026 Metin Faruk Bıyık (biyik.dev). Tüm hakları saklıdır.
