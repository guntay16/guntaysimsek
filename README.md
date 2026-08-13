# guntaysimsek-web

Güntay Şimşek'in iki web sitesi için proje deposu:

- **main-site/** → [guntaysimsek.com](https://guntaysimsek.com) — kişisel/gazetecilik sitesi (çok sayfalı)
- **photo-site/** → [guntaysimsekphoto.com](https://guntaysimsekphoto.com) — fotoğraf galerisi

Her iki site de derleme (build) adımı gerektirmeyen düz HTML/CSS/JS'tir. Node.js, bir framework ya da paket yöneticisi gerekmez — bu makinede zaten kurulu değiller ve ihtiyaç da yok.

## Proje yapısı

```
guntaysimsek-web/
├── main-site/
│   ├── index.html              → /
│   ├── kose-yazilari/index.html → /kose-yazilari/
│   ├── televizyon/index.html    → /televizyon/
│   ├── fotograf/index.html      → /fotograf/  (galeriye link verir)
│   ├── hakkinda/index.html      → /hakkinda/
│   ├── iletisim/index.html      → /iletisim/
│   ├── css/style.css
│   ├── images/                  (6 görsel — eskiden base64 idi, artık ayrı dosya)
│   └── netlify.toml
└── photo-site/
    ├── index.html                (filtrelenebilir galeri + lightbox)
    ├── css/style.css
    ├── js/gallery.js             (photos.json'u okuyup grid'i oluşturur)
    ├── photos.json               (44 fotoğrafın kategori/başlık/yol bilgisi)
    ├── images/thumbs/            (44 küçük boy görsel)
    ├── images/full/              (44 orijinal/lightbox boy görsel)
    └── netlify.toml
```

Her sayfa klasör + `index.html` düzeninde (`/hakkinda/index.html` gibi) — bu sayede GitHub Pages, Netlify ve Vercel'in hiçbiri için ekstra "redirect" kuralı yazmaya gerek kalmadan temiz URL'ler (`/hakkinda/`) çalışır.

**Neden değişti:** Prototiplerde her iki site de görselleri sayfanın `<script>`/`<img>` içine base64 olarak gömüyordu (fotoğraf sitesinde tek satır ~7,8 MB'tı). Şimdi görseller gerçek `.jpg` dosyaları; tarayıcı onları ayrı indirir, önbelleğe alır ve sayfa ilk yüklemede çok daha hafif olur.

## Yerel önizleme

Tarayıcıda `file://` ile açarsan fotoğraf sitesindeki `fetch('/photos.json')` CORS nedeniyle çalışmaz. Basit bir yerel sunucu yeterli:

```bash
cd guntaysimsek-web/main-site && python3 -m http.server 8000
```
```bash
cd guntaysimsek-web/photo-site && python3 -m http.server 8001
```

Sonra `http://localhost:8000` ve `http://localhost:8001` adreslerini aç.

## Yayına almadan önce

- `main-site/iletisim/index.html` içindeki E-posta / X / LinkedIn linkleri hâlâ `#` — gerçek adreslerinizle değiştirin (kod içinde `TODO` yorumu var).
- Televizyon bölümündeki küçük resimler hâlâ `mo.ciner.com.tr` üzerinden hotlink — isterseniz bunları da indirip `main-site/images/`'e taşıyabiliriz.

## Git ile versiyon kontrolü

Bu depo zaten yerel bir git deposu olarak başlatıldı ve ilk commit atıldı (`git log` ile görebilirsiniz). GitHub'a bağlamak için:

```bash
cd guntaysimsek-web
git remote add origin https://github.com/<kullanici-adiniz>/guntaysimsek-web.git
git branch -M main
git push -u origin main
```

(Önce GitHub'da boş bir `guntaysimsek-web` deposu oluşturmanız gerekir — github.com/new)

## Netlify'a deploy

İki site, tek GitHub reposu, iki ayrı Netlify sitesi (her biri kendi özel domainine sahip):

### A) Git tabanlı deploy (önerilen — her push'ta otomatik günceller)

1. [app.netlify.com](https://app.netlify.com) → **Add new site → Import an existing project** → GitHub'ı seçip `guntaysimsek-web` reposunu bağla.
2. **Base directory:** `main-site`, **Build command:** (boş bırak), **Publish directory:** `main-site`
3. Deploy'u tamamla. Aynı adımları tekrarlayıp ikinci bir site daha oluştur, bu kez **Base directory:** `photo-site`.
4. Her Netlify sitesinde **Site configuration → Domain management → Add a domain**:
   - main-site projesine: `guntaysimsek.com`
   - photo-site projesine: `guntaysimsekphoto.com`
5. Netlify sana her domain için DNS kayıtları verecek (genelde bir `A` kaydı Netlify'ın load balancer IP'sine, ya da domaini doğrudan Netlify DNS'ine yönlendirme seçeneği). Bu kayıtları domainlerin kayıtlı olduğu sağlayıcının (GoDaddy, Namecheap, Turkticaret vb.) DNS panelinden ekleyin. DNS yayılması birkaç dakika–birkaç saat sürebilir.
6. Netlify, domain doğrulandıktan sonra ücretsiz Let's Encrypt SSL sertifikasını otomatik kurar.

### B) Sürükle-bırak deploy (hızlı, tek seferlik — CLI/hesap bağlamadan)

[app.netlify.com/drop](https://app.netlify.com/drop) adresine `main-site` klasörünü, ayrı bir sekmede de `photo-site` klasörünü sürükleyip bırakman yeterli. Git entegrasyonu olmadığı için içerik güncellendiğinde manuel tekrar sürüklemen gerekir — sürekli güncellenen bir site için A seçeneği daha uygun.

## Notlar

- Bu ortamda (yerel terminal) Node.js, GitHub CLI (`gh`), Netlify CLI ve Homebrew kurulu değil — bu yüzden GitHub repo oluşturma, push ve Netlify hesap/domain bağlama adımlarını yukarıdaki komut ve arayüzlerle siz tamamlamalısınız. İsterseniz bu adımları birlikte, adım adım da yürütebiliriz.
- Domain DNS ayarları kayıt yaptırdığınız sağlayıcıya özgüdür; hangi sağlayıcıyı kullandığınızı söylerseniz o sağlayıcıya özel ekran görüntülü adımlar çıkarabilirim.
