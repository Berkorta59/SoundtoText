# SoundtoText — yerel Whisper transkripsiyonu

Windows ve Linux için Türkçe arayüzlü masaüstü uygulaması. Faster-Whisper modeli bilgisayarda çalışır; ses/video içerikleri bir transkripsiyon servisine yüklenmez. İlk model indirmesi internet gerektirir; model indirildikten sonra uygulama çevrimdışı kullanılabilir.

## Kurulum

Gereksinimler: Python 3.10–3.14 (3.12 önerilir), ilk paket/model indirmesi için internet ve model boyutuna yetecek disk alanı. GPU zorunlu değildir. Ses dönüştürücü FFmpeg Python paketinde sağlanır; ayrıca sistem FFmpeg kurmak gerekmez.

**Windows:** `install.bat` dosyasını çalıştırın, ardından `run.bat`.

**Linux:** `./install.sh`, ardından `./run.sh`. Çalıştırma izni gerekirse `chmod +x install.sh run.sh` kullanın. Dağıtımın Qt platform bağımlılıkları eksikse sistem paket yöneticinizle Qt6 XCB/Wayland kütüphanelerini kurun.

Model ilk kez kullanılınca otomatik olarak indirilir. Kurulum sonrası indirilen model dosyaları yerel önbellekte tutulur. Model önbelleği Windows'ta `%LOCALAPPDATA%\SoundtoText\models`, Linux'ta `~/.cache/SoundtoText/models` konumundadır. Çevrimdışı ilk çalıştırmadan önce modelin indirilmiş olması gerekir. Varsayılan `base` model makul bellek ve hız dengesi sunar; `small`, `medium` ve `large-v3` daha fazla disk, bellek ve işlem süresi gerektirir. Uygulama GPU seçeneğini yalnızca CUDA aygıtı algılandığında etkinleştirir.

## Özellikler

- MP3, WAV, M4A, AAC, FLAC, OGG, OPUS, WMA ve MP4, MKV, MOV, AVI, WEBM, M4V dosyaları.
- Sürükle-bırak, çoklu dosya kuyruğu, durum/ilerleme, güvenli iptal ve dosya başına hata yönetimi.
- Otomatik dil algılama, Türkçe ve İngilizce seçimi, transkripsiyon veya İngilizceye çeviri.
- Düzenlenebilir ve aranabilir sonuç; TXT, SRT, VTT, JSON ve CSV dışa aktarımı.
- Koyu/açık tema, kalıcı ayarlar ve işlem günlüğü.
- Model bellekte oturum boyunca tekrar kullanılır; video dahil medya geçici mono 16 kHz WAV'a dönüştürülüp işlenir. Geçici ses işlem bitince silinir; kaynak dosyalar değiştirilmez.
- Konuşmacı ayrıştırma mevcut değildir ve arayüzde etkin bir özellik olarak sunulmaz.

## Sorun giderme

- **Model indirilemiyor:** İlk indirme internet bağlantısı ve model boyutuna yetecek disk alanı ister. İndirildikten sonra aynı model tekrar indirilmez.
- **Bellek/işlem yavaşlığı:** `tiny` veya `base` seçin; CUDA aygıtı yoksa CPU kullanılır. Daha büyük modeller çok daha fazla bellek ve süre ister.
- **`cublas64_12.dll` bulunamıyor:** Otomatik aygıt seçimi CUDA başlatılamazsa CPU `int8` moduna geçip transkripsiyonu yeniden dener. CUDA'yı elle seçtiyseniz `Ayarlar > İşlem aygıtı > Otomatik` seçin veya CUDA 12 uyumlu NVIDIA çalışma kitaplıklarını kurun.
- **Dosya açılamıyor:** Dosya uzantısı desteklenmeli ve dosyada ses kanalı bulunmalıdır. Bozuk/şifreli dosyalar hata olarak bildirilir.
- **Linux GUI açılmıyor:** Dağıtımınıza uygun Qt6 platform eklentisini (çoğunlukla XCB veya Wayland) yükleyin.
- **Teknik günlük:** Uygulama olayları `soundtotext.log` dosyasına yazılır; transkript içeriği günlüğe eklenmez.

## Geliştirme ve test

```text
python -m pip install -r requirements-dev.txt
python -m pytest
```

PyInstaller paketlemesi henüz yapılandırılmadı/doğrulanmadı. Gerçek ses tanıma kalitesi seçilen model ve kayıt kalitesine bağlıdır; otomatik testlerde uzaktaki bir hizmet veya model indirme kullanılmaz.
