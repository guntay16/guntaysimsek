#!/usr/bin/env python3
"""
guntaysimsek.com'daki "Son Köşe Yazıları" (anasayfa) ve "Köşe Yazıları"
(kose-yazilari/) bölümlerini Habertürk.com'daki gerçek yazar arşiviyle
otomatik senkronize eder.

Kaynak: https://www.haberturk.com/ozel-icerikler/guntay-simsek-1019
(Güntay Şimşek'in Habertürk yazar arşiv sayfası - sunucu tarafında render
edilen HTML, JS calistirmaya gerek yok, duz HTTP GET ile okunabiliyor.)

Kural: sadece Habertürk'ün kendi başlığı, kendi tarihi, kendi linki ve
kendi özet metninden (og:description) türetilen tek cümlelik özet
kullanılır - uydurma içerik yok.

Öne çıkan (featured) kutu için ayrıca (kalıcı kural, Ekim 2026):
  - Yazı Habertürk'te birden fazla ara başlığa (h2/h3) bölünmüşse - yani
    tek bir konu değil, birkaç ayrı konuyu ele alıyorsa - HER ara başlık
    için ayrı bir alan (col-section kartı) açılır. Günün ana yazısı
    (başlıksız ilk bölüm) başlıkta kalır: kapak fotoğrafı (og:image) ve
    kendi özetiyle (col-featured-main). Diğer ara başlıklar onun ALTINDA
    ayrı kartlar olur; her karta Habertürk'te o başlığın hemen üstünde
    duran fotoğraf ve o bölümün ilk paragrafından alınan cümleler konur. Fotoğraflar main-site/images/kose/ altına indirilir (hotlink
    yok).
  - Yazı tek başlık altında tek bir konuyu ele alıyorsa, yazının önemli
    bölümleri (baş/orta/son kısımlardan en çok vurgulanan paragraflar)
    ayrı ayrı madde olarak gösterilir (col-featured-points).
  - Özet satırı hiçbir zaman başlığın tekrarı olmaz. Yazı sayfası
    okunamazsa (ör. yayından hemen sonra) sonraki çalıştırmalar eksik
    kalan featured kutusunu ve arşivdeki başlık-tekrarı özetleri onarır.

Calisma mantigi:
  1) Arşiv sayfasından yazı listesini (id, başlık, tarih) yeniden-eskiye
     sırayla çıkar.
  2) main-site/kose-yazilari/index.html içinde henüz bulunmayan (yeni)
     yazıları tespit eder.
  3) Yeni yazı yoksa hiçbir şey değiştirmez.
  4) Yeni yazı varsa:
     - kose-yazilari/index.html: yeni yazı(lar) listenin EN BAŞINA eklenir
       (arşiv sayfası olduğu için hiçbir eski yazı silinmez).
     - main-site/index.html "Son Köşe Yazıları": en güncel yazı öne
       çıkan (featured) kutuya taşınır; önceki featured ve liste
       öğeleri bir alt sıraya kayar, en eski gösterilen öğe listeden
       düşer (bu bölüm sadece en güncel 3 yazıyı gösteriyor).

Her gün GitHub Actions tarafından çalıştırılır (bkz.
.github/workflows/kose-yazilari.yml). Elle çalıştırmak için:
    python3 scripts/update_kose_yazilari.py
"""
import html
import re
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "main-site" / "index.html"
ARCHIVE_HTML = REPO_ROOT / "main-site" / "kose-yazilari" / "index.html"

ARCHIVE_URL = "https://www.haberturk.com/ozel-icerikler/guntay-simsek-1019"
BASE_URL = "https://www.haberturk.com"
UA = "Mozilla/5.0 (compatible; guntaysimsek-kose-yazilari-bot/1.0)"

ARTICLE_LIST_RE = re.compile(
    r'<a href="(/ozel-icerikler/guntay-simsek-1019/(\d+)-[a-z0-9-]+)" title="([^"]+)">'
    r'.*?<b>Giri.: </b>\s*(\d{4})-(\d{2})-(\d{2})',
    re.DOTALL,
)

EXISTING_ID_RE = re.compile(r"ozel-icerikler/guntay-simsek-1019/(\d+)-")

# Arşiv sayfasındaki mevcut <li class="col-item">...</li> bloklarını,
# tarihiyle birlikte tek tek yakalar (yeniden ekleme sırasında tüm liste
# gerçek tarihe göre yeniden sıralanabilsin diye).
ENTRY_RE = re.compile(
    # Oge, kendi girintisindeki (6 bosluk) </li> ile biter; alt baslik
    # listesindeki ic ice <li>'ler daha derin girintili.
    r'(<li class="col-item">\s*<span class="col-date">([^<]+)</span>.*?\n {6}</li>)',
    re.DOTALL,
)

TICKER_NEW_RE = re.compile(r'(<span class="ticker-tag">YENİ YAZI</span>)[^<]*</span>')

LIST_BLOCK_RE = re.compile(r'<ul class="col-list">\n(.*?)\n    </ul>', re.DOTALL)

SECTION_RE = re.compile(
    r'<div class="col-featured">.*?'
    r'<a class="section-more" href="kose-yazilari/">Tüm Köşe Yazıları →</a>',
    re.DOTALL,
)

OLD_FEATURED_RE = re.compile(
    r'<span class="col-date">([^<]+)</span>\s*'
    r'<h3 class="col-featured-title"><a href="([^"]+)"[^>]*>([^<]+)</a></h3>\s*'
    r'<p class="col-featured-lede">([^<]+)</p>',
    re.DOTALL,
)

OLD_LIST_ITEM_RE = re.compile(
    r'<span class="col-date">([^<]+)</span>\s*<div>\s*'
    r'<h3 class="col-headline"><a href="([^"]+)"[^>]*>([^<]+)</a></h3>\s*'
    r'<p class="col-excerpt">([^<]+)</p>',
    re.DOTALL,
)


def fetch(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def strip_tags(raw: str) -> str:
    # Satir ici vurgu etiketleri bosluksuz silinir ("<strong>Çin</strong>'e"
    # -> "Çin'e"), digerleri bosluga donusur.
    text = re.sub(r"</?(?:strong|b|em|i|u|a|span)\b[^>]*>", "", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_og_description(page_html: str) -> str:
    m = re.search(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        page_html,
    )
    if not m:
        return ""
    return html.unescape(m.group(1))


def og_description(article_url: str) -> str:
    return extract_og_description(fetch(article_url))


def first_sentence(text: str, max_len: int = 260) -> str:
    text = strip_tags(text)
    m = re.search(r"^(.{20,%d}?[.!?])(\s|$)" % max_len, text)
    if m:
        return m.group(1).strip()
    return (text[:max_len].rsplit(" ", 1)[0] + "…") if text else ""


POINTS_STOP_MARKER = "Diğer Yazılar"
BODY_START_MARKER = 'property="articleBody"'
MAX_HEADING_LEN = 80
IMAGES_DIR = REPO_ROOT / "main-site" / "images" / "kose"
IMAGES_URL_PREFIX = "/images/kose/"

# Habertürk yazı gövdesindeki sıralı öğeler: fotoğraf (widget-image),
# ara başlık (h2/h3) ve paragraf.
BODY_TOKEN_RE = re.compile(
    r'<div class="widget-image[^>]*>\s*<img[^>]*?data-big-src="(?P<img>[^"]+)"'
    r'|<h(?P<hl>[23])[^>]*>(?P<head>.*?)</h(?P=hl)>'
    r'|<p[^>]*>(?P<para>.*?)</p>',
    re.DOTALL,
)


def extract_og_image(page_html: str) -> str:
    m = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        page_html,
    )
    return html.unescape(m.group(1)) if m else ""


def lead_sentences(text: str, max_len: int = 320) -> str:
    """Paragrafin ilk cumlelerini (toplam max_len karakteri asmadan, en az
    bir cumle) dondurur - yazarin kendi ifadesi, uydurma yok."""
    text = strip_tags(text)
    sentences = re.findall(r".+?[.!?…](?=\s|$)|.+$", text)
    out = ""
    for sent in sentences:
        sent = sent.strip()
        if out and len(out) + 1 + len(sent) > max_len:
            break
        out = f"{out} {sent}".strip()
    if len(out) > max_len + 120:
        out = out[:max_len].rsplit(" ", 1)[0] + "…"
    return out


def article_body(article_html: str) -> str:
    body = article_html.split(POINTS_STOP_MARKER, 1)[0]
    start = body.find(BODY_START_MARKER)
    return body[start:] if start != -1 else body


def extract_sections(article_html: str, title: str):
    """Yazıyı ara başlıklarına göre bölümlere ayırır. Her bölüm: başlık,
    fotoğraf URL'si (varsa) ve paragrafları. Ara başlıktan önceki ilk
    bölüm yazının ana başlığını ve kapak fotoğrafını (og:image) alır.
    Habertürk'te bir ara başlığın fotoğrafı başlığın hemen ÜSTÜNDE durur."""
    sections = [{"heading": title.strip(), "image": extract_og_image(article_html),
                 "paras": [], "raw": []}]
    pending_img = None
    for m in BODY_TOKEN_RE.finditer(article_body(article_html)):
        if m.group("img"):
            pending_img = html.unescape(m.group("img"))
        elif m.group("head") is not None:
            heading = strip_tags(m.group("head"))
            # Habertürk vurgulu alinti cumlelerini de ayni baslik
            # etiketiyle isaretliyor; nokta ile biten ya da cok uzun
            # "basliklar" ara baslik sayilmaz.
            if heading and not heading.endswith(".") and len(heading) <= MAX_HEADING_LEN:
                sections.append({"heading": heading, "image": pending_img,
                                 "paras": [], "raw": []})
            pending_img = None
        else:
            text = strip_tags(m.group("para"))
            if not text or set(text) <= set("*-–— "):
                continue
            sections[-1]["paras"].append(text)
            sections[-1]["raw"].append(m.group("para"))
    return [s for s in sections if s["paras"]]


def key_points(paras: list, raws: list, max_points: int = 3):
    """Tek konulu (ara başlıksız) yazıda önemli bölümleri seçer: ilk
    paragraf (lede) haric kalanlari bas/orta/son diye esit parçalara böler
    ve her parçadan en çok vurgulanan (<strong>) paragrafı alır."""
    rest = list(range(1, len(paras)))
    if not rest:
        return []
    n = min(max_points, len(rest))
    chunks = [rest[i * len(rest) // n:(i + 1) * len(rest) // n] for i in range(n)]
    picks = []
    for chunk in chunks:
        if chunk:
            best = max(chunk, key=lambda i: (raws[i].count("<strong"), -i))
            picks.append(best)
    return [{"summary": lead_sentences(paras[i], 260)} for i in picks]


def safe_image_name(art_id: str, index: int) -> str:
    return f"{art_id}-{index + 1}.jpg"


def download_image(url: str, art_id: str, index: int) -> str:
    """Fotoğrafı main-site/images/kose/ altına indirir ve sayfada
    kullanılacak göreli yolu döndürür. Başarısızsa boş string."""
    if not url:
        return ""
    # static.domer.tr gorselleri genislik parametresiyle sunuluyor;
    # anasayfa karti icin 960px yeterli.
    url = re.sub(r"/\d+x0$", "/960x0", url)
    name = safe_image_name(art_id, index)
    target = IMAGES_DIR / name
    if not target.exists():
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=30) as resp:
                data = resp.read()
            if len(data) < 2000:
                return ""
            IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except Exception as exc:
            print(f"Uyari: fotograf indirilemedi ({url}): {exc}")
            return ""
    return IMAGES_URL_PREFIX + name


def analyze_article(page_html: str, art: dict, main_image: bool = True) -> dict:
    """Yazı sayfasından özet, ara başlık kartları (sections) ve - tek
    konulu yazıda - önemli bölüm maddelerini (points) çıkarır."""
    sections = extract_sections(page_html, art["title"])
    excerpt = first_sentence(extract_og_description(page_html))
    if (not excerpt or excerpt.strip() == art["title"].strip()) and sections:
        excerpt = first_sentence(sections[0]["paras"][0])
    result = {"excerpt": excerpt or art["title"], "sections": [], "points": []}
    if len(sections) > 1:
        for idx, sec in enumerate(sections):
            result["sections"].append({
                "heading": sec["heading"],
                "summary": lead_sentences(sec["paras"][0], 420 if idx == 0 else 320),
                "image": download_image(sec["image"], art["id"], idx)
                if (idx or main_image) else "",
            })
    elif sections:
        result["points"] = key_points(sections[0]["paras"], sections[0]["raw"])
    return result


def fetch_article(url: str, attempts: int = 3) -> str:
    last_exc = None
    for _ in range(attempts):
        try:
            page = fetch(url, timeout=30)
            if BODY_START_MARKER in page:
                return page
        except Exception as exc:  # noqa: PERF203
            last_exc = exc
    raise RuntimeError(f"yazi govdesi okunamadi: {last_exc}")


def parse_archive(archive_html: str):
    """Habertürk arşiv sayfasından yazıları yeniden-eskiye sırayla çıkarır."""
    items = []
    seen = set()
    for m in ARTICLE_LIST_RE.finditer(archive_html):
        rel_path, art_id, title_raw, y, mo, d = m.groups()
        if art_id in seen:
            continue
        seen.add(art_id)
        items.append({
            "id": art_id,
            "url": BASE_URL + rel_path,
            "title": html.unescape(title_raw),
            "date": f"{y}.{mo}.{d}",
        })
    return items


def share_row(title: str, url: str, indent: str) -> str:
    enc_title = quote(title, safe="")
    enc_url = quote(url, safe="/")
    return (
        f'{indent}<div class="share-row">\n'
        f'{indent}  <span class="share-label">Paylaş:</span>\n'
        f'{indent}  <a href="https://twitter.com/intent/tweet?text={enc_title}&url={enc_url}" target="_blank" rel="noopener">X</a>\n'
        f'{indent}  <a href="https://wa.me/?text={enc_title}%20{url}" target="_blank" rel="noopener">WhatsApp</a>\n'
        f'{indent}  <button type="button" class="copy-link" data-url="{url}">Kopyala</button>\n'
        f'{indent}</div>'
    )


def build_list_item(item: dict) -> str:
    title = esc(item["title"])
    return (
        '      <li class="col-item">\n'
        f'        <span class="col-date">{item["date"]}</span>\n'
        '        <div>\n'
        f'          <h3 class="col-headline"><a href="{item["url"]}" target="_blank" rel="noopener">{title}</a></h3>\n'
        f'          <p class="col-excerpt">{esc(item["excerpt"])}</p>\n'
        f'{build_subtopics(item.get("sections") or [], item["url"])}'
        f'{share_row(item["title"], item["url"], "        ")}\n'
        '        </div>\n'
        '      </li>'
    )


def build_subtopics(sections: list, url: str) -> str:
    """Liste/arsiv ogesinde ana yazinin altindaki diger ara basliklar
    (fotografli kucuk satirlar). Ilk bolum ana yazinin kendisi oldugu icin
    atlanir."""
    subs = sections[1:]
    if not subs:
        return ""
    rows = []
    for sec in subs:
        img = (
            f'              <img src="{sec["image"]}" alt="{html.escape(sec["heading"])}" loading="lazy">\n'
            if sec.get("image") else ""
        )
        rows.append(
            '            <li class="col-subtopic">\n'
            f'{img}'
            '              <div>\n'
            f'                <h4 class="col-subtopic-title"><a href="{url}" target="_blank" rel="noopener">{esc(sec["heading"])}</a></h4>\n'
            f'                <p class="col-subtopic-text">{esc(first_sentence(sec["summary"], 220))}</p>\n'
            '              </div>\n'
            '            </li>'
        )
    return '          <ul class="col-subtopics">\n' + "\n".join(rows) + '\n          </ul>\n'


def build_points_list(points: list) -> str:
    """Tek konulu yazinin onemli bolumleri (madde listesi)."""
    if not points:
        return ""
    lines = "\n".join(
        f'        <li>{esc(p["summary"])}</li>' for p in points
    )
    return f'      <ul class="col-featured-points">\n{lines}\n      </ul>\n'


def build_sections(sections: list, url: str) -> str:
    """Ara basliklara bolunmus yazida her baslik icin ayri kart."""
    if not sections:
        return ""
    cards = []
    for idx, sec in enumerate(sections, 1):
        img = (
            f'          <img src="{sec["image"]}" alt="{html.escape(sec["heading"])}" loading="lazy">\n'
            if sec.get("image") else ""
        )
        cards.append(
            '        <li class="col-section">\n'
            f'{img}'
            f'          <span class="col-section-num">{idx:02d}</span>\n'
            f'          <h4 class="col-section-title"><a href="{url}" target="_blank" rel="noopener">{esc(sec["heading"])}</a></h4>\n'
            f'          <p class="col-section-text">{esc(sec["summary"])}</p>\n'
            '        </li>'
        )
    return '      <ul class="col-sections">\n' + "\n".join(cards) + '\n      </ul>\n'


def build_featured(item: dict) -> str:
    title = esc(item["title"].strip())
    sections = item.get("sections") or []
    if sections:
        # Gunun ana yazisi baslikta kalir (kendi fotografi ve ozetiyle);
        # diger ara basliklar onun altinda ayri kartlar olarak yer alir.
        main = sections[0]
        img = (
            f'        <img src="{main["image"]}" alt="{html.escape(main["heading"])}" loading="lazy">\n'
            if main.get("image") else ""
        )
        body_html = (
            '      <div class="col-featured-main">\n'
            f'{img}'
            f'        <p class="col-featured-lede">{esc(main["summary"])}</p>\n'
            '      </div>\n'
            f'{build_sections(sections[1:], item["url"])}'
        )
    else:
        body_html = (
            f'      <p class="col-featured-lede">{esc(item["excerpt"])}</p>\n'
            f'{build_points_list(item.get("points") or [])}'
        )
    return (
        '<div class="col-featured">\n'
        f'      <span class="col-date">{item["date"]}</span>\n'
        f'      <h3 class="col-featured-title"><a href="{item["url"]}" target="_blank" rel="noopener">{title}</a></h3>\n'
        f'{body_html}'
        f'      <a class="section-more" href="{item["url"]}" target="_blank" rel="noopener">Yazının tamamı → Habertürk</a>\n'
        f'{share_row(item["title"].strip(), item["url"], "      ")}\n'
        '    </div>'
    )


def update_archive_page(new_items: list) -> bool:
    """Yeni yazilari arsive ekler ve TUM listeyi (eskiler + yeniler) gercek
    tarihe gore yeniden buyukten-kucuge sıralar. Sadece en basa eklemek,
    daha once eksik kalmis eski bir yazi (backlog) tespit edildiginde onu
    yanlislikla en guncel yaziymis gibi goruntuler - bu yuzden her
    calistirmada tum liste tarihe gore yeniden kuruluyor."""
    content = ARCHIVE_HTML.read_text(encoding="utf-8")
    match = LIST_BLOCK_RE.search(content)
    if not match:
        print("Hata: kose-yazilari/index.html icinde col-list bulunamadi.")
        return False
    existing_entries = [
        (m.group(2).strip(), m.group(1)) for m in ENTRY_RE.finditer(match.group(1))
    ]
    new_entries = [(it["date"], build_list_item(it)) for it in new_items]
    all_entries = existing_entries + new_entries
    all_entries.sort(key=lambda e: e[0], reverse=True)
    normalized_blocks = [
        block if block.startswith("      <li") else "      " + block
        for _, block in all_entries
    ]
    new_list_html = "\n".join(normalized_blocks)
    content = content[: match.start(1)] + new_list_html + content[match.end(1):]
    ARCHIVE_HTML.write_text(content, encoding="utf-8")
    return True


def update_homepage(new_items: list) -> bool:
    """Anasayfadaki 'Son Köşe Yazıları' önizlemesini, GÜNCEL VE TAM ARŞİV
    dosyasından (kose-yazilari/index.html - bu fonksiyon her zaman
    update_archive_page'den SONRA çağrılmalı) türetir. Anasayfadaki eski
    kutunun kendi içeriğine güvenilmez: arşiv tek doğruluk kaynağıdır,
    böylece daha önce eksik kalmış eski bir yazı (backlog) tespit edilip
    arşive eklendiğinde bile, gerçekten en güncel olan yazı anasayfada
    yanlışlıkla ikinci plana düşmez.
    """
    archive_content = ARCHIVE_HTML.read_text(encoding="utf-8")
    entries = [
        {
            "date": m.group(1).strip(),
            "url": m.group(2),
            "title": html.unescape(m.group(3)),
            "excerpt": html.unescape(m.group(4)),
        }
        for m in OLD_LIST_ITEM_RE.finditer(archive_content)
    ]
    if not entries:
        print("Hata: kose-yazilari/index.html icinde hic yazi bulunamadi.")
        return False

    # entries zaten update_archive_page tarafindan tarihe gore siralanmis
    # durumda (buyukten kucuge); yine de garanti olsun diye tekrar sirala.
    entries.sort(key=lambda it: it["date"], reverse=True)
    top3 = entries[:3]

    new_by_url = {it["url"]: it for it in new_items}
    featured = top3[0]
    if featured["url"] in new_by_url:
        featured = new_by_url[featured["url"]]
    elif "sections" not in featured:
        # Featured slotundaki yazi bu calistirmada yeni eklenmemis (ör.
        # eksik kalmis bir featured kutusu onariliyor) - ara baslik ve
        # fotograflar icin sayfasini tazeden okuyalim.
        try:
            art = {**featured, "id": EXISTING_ID_RE.search(featured["url"]).group(1)}
            featured = {**featured, **analyze_article(fetch_article(featured["url"]), art)}
        except Exception as exc:
            print(f"Uyari: featured yazi icin sayfa tazelenemedi ({featured['url']}): {exc}")
            featured = {**featured, "sections": [], "points": []}

    featured_html = build_featured(featured)
    # Liste ogeleri arsivdeki hazir bloklardan alinir (ara basliklari ve
    # fotograflariyla birlikte).
    raw_blocks = {}
    for m in ENTRY_RE.finditer(archive_content):
        um = re.search(r'<h3 class="col-headline"><a href="([^"]+)"', m.group(1))
        if um:
            raw_blocks[um.group(1)] = m.group(1)
    list_items_html = "\n".join(
        "      " + raw_blocks[it["url"]].lstrip() if it["url"] in raw_blocks else build_list_item(it)
        for it in top3[1:3]
    )
    content = INDEX_HTML.read_text(encoding="utf-8")
    match = SECTION_RE.search(content)
    if not match:
        print("Hata: main-site/index.html icinde 'Son Köşe Yazıları' bölümü bulunamadi.")
        return False
    new_section = (
        f"{featured_html}\n\n"
        f'    <ul class="col-list">\n{list_items_html}\n    </ul>\n'
        '    <a class="section-more" href="kose-yazilari/">Tüm Köşe Yazıları →</a>'
    )
    content = content[: match.start()] + new_section + content[match.end():]
    # Sayfa ustundeki kayan "YENI YAZI" bandi her zaman en guncel yazinin
    # basligini gostermeli (band kesintisiz donsun diye iki kez tekrarlanir).
    content = TICKER_NEW_RE.sub(
        lambda m: m.group(1) + esc(featured["title"]) + "</span>", content
    )
    INDEX_HTML.write_text(content, encoding="utf-8")
    return True


def sync_ticker() -> bool:
    """Kayan YENI YAZI bandi, anasayfadaki öne çıkan yazının başlığından
    farklıysa eşitler; değişiklik yapıldıysa True döner."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    m = re.search(r'<h3 class="col-featured-title"><a [^>]*>([^<]+)</a></h3>', content)
    if not m:
        return False
    title = m.group(1)  # HTML'de zaten kacirilmis hali
    new = TICKER_NEW_RE.sub(lambda t: t.group(1) + title + "</span>", content)
    if new == content:
        return False
    INDEX_HTML.write_text(new, encoding="utf-8")
    return True


def featured_needs_repair() -> bool:
    """Anasayfadaki featured kutusu ara baslik kartlari/maddeler olmadan
    ya da basligi tekrar eden bir ozetle kalmissa True (ör. bot yaziyi
    yayindan hemen sonra okuyamadiysa)."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    match = SECTION_RE.search(content)
    if not match:
        return False
    block = match.group(0).split('<ul class="col-list">', 1)[0]
    if 'class="col-sections"' in block or 'class="col-featured-points"' in block:
        return False
    return True


def repair_archive_excerpts(limit: int = 5) -> None:
    """Arsivde ozeti basligin tekrari olan son yazilarin ozetini onarir."""
    content = ARCHIVE_HTML.read_text(encoding="utf-8")
    changed = False
    for m in list(OLD_LIST_ITEM_RE.finditer(content))[:limit]:
        title, excerpt = html.unescape(m.group(3)).strip(), html.unescape(m.group(4)).strip()
        if excerpt != title:
            continue
        try:
            art = {"id": EXISTING_ID_RE.search(m.group(2)).group(1), "title": title}
            new_excerpt = analyze_article(fetch_article(m.group(2)), art)["excerpt"]
        except Exception as exc:
            print(f"Uyari: ozet onarilamadi ({m.group(2)}): {exc}")
            continue
        if new_excerpt and new_excerpt != title:
            old = f'<p class="col-excerpt">{m.group(4)}</p>'
            content = content.replace(old, f'<p class="col-excerpt">{esc(new_excerpt)}</p>', 1)
            changed = True
    if changed:
        ARCHIVE_HTML.write_text(content, encoding="utf-8")


def backfill_subtopics() -> int:
    """Tek seferlik: arsivdeki ara baslik listesi olmayan yazilari Habertürk'ten
    tarar; birden fazla ara basligi olanlara fotografli alt basliklari ekler."""
    content = ARCHIVE_HTML.read_text(encoding="utf-8")
    added = 0
    for m in list(ENTRY_RE.finditer(content)):
        block = m.group(1)
        if 'class="col-subtopics"' in block:
            continue
        um = re.search(r'<h3 class="col-headline"><a href="([^"]+)"[^>]*>([^<]+)</a>', block)
        if not um:
            continue
        url, title = um.group(1), html.unescape(um.group(2))
        try:
            art = {"id": EXISTING_ID_RE.search(url).group(1), "title": title}
            info = analyze_article(fetch_article(url), art, main_image=False)
        except Exception as exc:
            print(f"Uyari: {url} okunamadi: {exc}")
            continue
        subs_html = build_subtopics(info["sections"], url)
        if not subs_html:
            continue
        new_block = re.sub(r'(<p class="col-excerpt">.*?</p>\n)', lambda x: x.group(1) + subs_html,
                           block, count=1, flags=re.DOTALL)
        content = content.replace(block, new_block, 1)
        added += 1
        print(f" + {title}: {len(info['sections']) - 1} ara baslik")
    ARCHIVE_HTML.write_text(content, encoding="utf-8")
    print(f"{added} yaziya ara basliklar eklendi.")
    return 0


def main() -> int:
    archive_html = fetch(ARCHIVE_URL)
    articles = parse_archive(archive_html)
    if not articles:
        print("Uyari: Habertürk arşiv sayfasından hiç yazı çıkarılamadı.")
        return 1

    known_content = ARCHIVE_HTML.read_text(encoding="utf-8")
    existing_ids = set(EXISTING_ID_RE.findall(known_content))

    new_articles = [a for a in articles if a["id"] not in existing_ids]
    if not new_articles:
        if featured_needs_repair():
            print("Yeni yazı yok; eksik kalan öne çıkan kutu/özetler onarılıyor.")
            repair_archive_excerpts()
            return 0 if update_homepage([]) else 1
        if sync_ticker():
            print("Yeni yazı yok; kayan YENİ YAZI bandı en güncel başlığa eşitlendi.")
            return 0
        print("Zaten güncel, yeni köşe yazısı yok.")
        return 0

    new_items = []
    for art in new_articles:
        info = {"excerpt": art["title"], "sections": [], "points": []}
        try:
            info = analyze_article(fetch_article(art["url"]), art)
        except Exception as exc:
            print(f"Uyari: yazı sayfası okunamadı ({art['url']}): {exc}")
        new_items.append({**art, **info})

    ok_archive = update_archive_page(new_items)
    ok_home = update_homepage(new_items)
    if not (ok_archive and ok_home):
        return 1

    print(f"{len(new_items)} yeni köşe yazısı eklendi:")
    for it in new_items:
        print(f" - {it['date']}  {it['title']}  ({it['url']})")
    return 0


if __name__ == "__main__":
    if "--backfill" in sys.argv:
        sys.exit(backfill_subtopics() or (0 if update_homepage([]) else 1))
    sys.exit(main())
