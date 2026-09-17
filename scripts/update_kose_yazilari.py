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

Öne çıkan (featured) kutu için ayrıca: eğer yazı Habertürk'te kendi içinde
birden fazla alt başlığa (h3) bölünmüşse - yani tek bir konu değil, birkaç
ayrı konuyu ele alıyorsa - her alt başlık kendi kısa özetiyle ayrı bir
madde olarak gösterilir (col-featured-points). Yazı tek parça/tek konuysa
(alt başlık yoksa) sadece tek paragraflık lede metni kullanılır, madde
listesi eklenmez.

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
    r'(<li class="col-item">\s*<span class="col-date">([^<]+)</span>.*?</li>)',
    re.DOTALL,
)

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
    text = re.sub(r"<[^>]+>", " ", raw)
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


def extract_points(article_html: str, max_points: int = 4):
    """Yazı Habertürk'te birden fazla alt başlığa (h3) bölünmüşse, her
    alt başlığı kendi kısa özetiyle (o başlıktan sonraki ilk paragrafın
    ilk cümlesi) birlikte döndürür. Alt başlık yoksa boş liste döner ve
    featured kutusu tek paragraflık lede ile yetinir."""
    body = article_html.split(POINTS_STOP_MARKER, 1)[0]
    points = []
    for chunk in body.split("<h3")[1:]:
        close = chunk.find("</h3>")
        if close == -1:
            continue
        # h3 acilis etiketinin kalan kismini (ör. class="...") atla
        tag_end = chunk.find(">")
        if tag_end == -1 or tag_end > close:
            continue
        heading = strip_tags(chunk[tag_end + 1: close])
        if not heading:
            continue
        rest = chunk[close + 5: close + 5 + 2000]
        pm = re.search(r"<p[^>]*>(.*?)</p>", rest, re.DOTALL)
        if not pm:
            continue
        summary = first_sentence(html.unescape(pm.group(1)))
        if not summary:
            continue
        points.append({"heading": heading, "summary": summary})
        if len(points) >= max_points:
            break
    return points


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
        f'{share_row(item["title"], item["url"], "        ")}\n'
        '        </div>\n'
        '      </li>'
    )


def build_points_list(points: list) -> str:
    if not points:
        return ""
    lines = "\n".join(
        f'        <li><strong>{esc(p["heading"])}:</strong> {esc(p["summary"])}</li>'
        for p in points
    )
    return f'      <ul class="col-featured-points">\n{lines}\n      </ul>\n'


def build_featured(item: dict) -> str:
    title = esc(item["title"])
    points_html = build_points_list(item.get("points") or [])
    return (
        '<div class="col-featured">\n'
        f'      <span class="col-date">{item["date"]}</span>\n'
        f'      <h3 class="col-featured-title"><a href="{item["url"]}" target="_blank" rel="noopener">{title}</a></h3>\n'
        f'      <p class="col-featured-lede">{esc(item["excerpt"])}</p>\n'
        f'{points_html}'
        f'      <a class="section-more" href="{item["url"]}" target="_blank" rel="noopener">Yazının tamamı → Habertürk</a>\n'
        f'{share_row(item["title"], item["url"], "      ")}\n'
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
    elif "points" not in featured:
        # Featured slotuna cikan yazi bu calistirmada yeni eklenmemis
        # (ör. daha once eksik kalmis, arsive simdi eklenen bir yazi bu
        # calistirmada featured olmadi ama ileride olabilir) - alt baslik
        # kontrolu icin sayfasini tazeden okuyalim.
        try:
            page_html = fetch(featured["url"])
            featured = {
                **featured,
                "excerpt": first_sentence(extract_og_description(page_html)) or featured["excerpt"],
                "points": extract_points(page_html),
            }
        except Exception as exc:
            print(f"Uyari: featured yazi icin sayfa tazelenemedi ({featured['url']}): {exc}")
            featured = {**featured, "points": []}

    featured_html = build_featured(featured)
    list_items_html = "\n".join(build_list_item(it) for it in top3[1:3])
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
    INDEX_HTML.write_text(content, encoding="utf-8")
    return True


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
        print("Zaten güncel, yeni köşe yazısı yok.")
        return 0

    new_items = []
    for art in new_articles:
        excerpt = art["title"]
        points = []
        try:
            page_html = fetch(art["url"])
            desc = extract_og_description(page_html)
            excerpt = first_sentence(desc) or art["title"]
            points = extract_points(page_html)
        except Exception as exc:
            print(f"Uyari: yazı sayfası okunamadı ({art['url']}): {exc}")
        new_items.append({**art, "excerpt": excerpt, "points": points})

    ok_archive = update_archive_page(new_items)
    ok_home = update_homepage(new_items)
    if not (ok_archive and ok_home):
        return 1

    print(f"{len(new_items)} yeni köşe yazısı eklendi:")
    for it in new_items:
        print(f" - {it['date']}  {it['title']}  ({it['url']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
