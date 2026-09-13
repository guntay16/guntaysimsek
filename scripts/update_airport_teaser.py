#!/usr/bin/env python3
"""
guntaysimsek.com anasayfasindaki "Bu Hafta Airport'ta" tanitim kutusunu
haber.aero'daki en guncel Airport icerigiyle otomatik gunceller.

Iki farkli sinyali arar:
  1) Dedicated ozel haber: basligi "Airport'ta bu hafta: ..." seklinde olan,
     o haftaya ozel konuyu/gorseli tasiyan bir haber.aero yazisi.
  2) Genel tanitim cumlesi: haber.aero'nun konuyla ilgisiz bircok haberinin
     SONUNA hafta sonuna dogru ekledigi, sabit kalipli tanitim notu:
       "Airport, en ozel konu ve konuklariyla <tarih> Pazar, saat 12.15'te
        Haberturk TV ekranlarinda olacak."
     Bu not sadece BASLIKTA degil, haberin ICERIGINDE gectigi icin
     basliktan degil, tam metinden aranmasi gerekiyor.

Oncelik dedicated habere verilir (kendi konusu/gorseli oldugu icin daha
zengin bir kutu olusturur); o bulunamazsa genel tanitim cumlesine dusulur.

Haftada bir kez degil GUNLUK olarak GitHub Actions tarafindan calistirilir
(bkz. .github/workflows/airport-teaser.yml) - bu sayede haber.aero'nun
genelde cuma/cumartesi yayinladigi icerik gecikmeden yakalanir. Elle
calistirmak icin:
    python3 scripts/update_airport_teaser.py
"""
import html
import io
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "main-site" / "index.html"
IMAGES_DIR = REPO_ROOT / "main-site" / "images"
FEED_URL = "https://haber.aero/feed/"
UA = "Mozilla/5.0 (compatible; guntaysimsek-airport-teaser-bot/1.0)"
FALLBACK_IMAGE = "images/portre.jpg"
GENERIC_MARKER = "<!-- airport-teaser:generic -->"

# Genel tanitim cumlesindeki tarihi de yakalar (ornek: "13 Eylul") ama asil
# amac cumlenin kendisini/ tarihi tekillestirici olarak kullanmak.
GENERIC_PROMO_RE = re.compile(
    r"Airport,?\s+en\s+özel\s+konu\s+(?:ve\s+)?konuklar[ıi]yla\s+"
    r"(\d{1,2}\s+\w+)\s+Pazar,?\s+saat\s+12[.:]15[^.]*\.",
    re.IGNORECASE,
)


def fetch(url: str, timeout: int = 20) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_tags(html_text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def find_latest_airport_item(feed_xml: bytes):
    """Basligi 'Airport'ta bu hafta ...' olan dedicated haberi arar."""
    root = ET.fromstring(feed_xml)
    for item in root.iter("item"):
        title_raw = (item.findtext("title") or "").strip()
        title = html.unescape(title_raw)
        low = title.lower()
        if "airport" in low and "bu hafta" in low:
            link = (item.findtext("link") or "").strip()
            desc_raw = item.findtext("description") or ""
            return {"title": title, "link": link, "description_html": desc_raw}
    return None


def find_generic_promo(feed_xml: bytes, max_items: int = 20):
    """Basliginda gecmese bile, herhangi bir haberin ICERIGINDE gecen
    sabit Airport tanitim cumlesini arar (haftada bir, genelde cuma/
    cumartesi yayinlanan haberlerin sonuna eklenir)."""
    root = ET.fromstring(feed_xml)
    checked = 0
    for item in root.iter("item"):
        if checked >= max_items:
            break
        link = (item.findtext("link") or "").strip()
        if not link:
            continue
        checked += 1
        try:
            page = fetch(link).decode("utf-8", errors="ignore")
        except Exception:
            continue
        text = strip_tags(page)
        m = GENERIC_PROMO_RE.search(text)
        if m:
            return {"sentence": m.group(0).strip(), "date_phrase": m.group(1), "source_link": link}
    return None


def first_sentence(description_html: str, max_len: int = 220) -> str:
    text = strip_tags(description_html)
    text = re.sub(r"\[\S*\.\.\.\S*\]|\[…\]", "", text)
    match = re.search(r"^(.{20,%d}?[.!?])(\s|$)" % max_len, text)
    sentence = match.group(1) if match else text[:max_len].rsplit(" ", 1)[0] + "…"
    return sentence.strip()


def extract_og_image(article_url: str) -> str | None:
    page = fetch(article_url).decode("utf-8", errors="ignore")
    match = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        page,
    )
    return match.group(1) if match else None


def slug_from_link(link: str) -> str:
    slug = link.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"[^a-z0-9\-]", "", slug.lower())
    return slug[:60] or "airport-bu-hafta"


def save_resized_image(image_bytes: bytes, dest: Path, max_width: int = 900) -> None:
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if img.width > max_width:
        new_height = int(img.height * max_width / img.width)
        img = img.resize((max_width, new_height), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=82, optimize=True)


TEASER_BLOCK_RE = re.compile(
    r'(?:<!-- airport-teaser:generic -->\n\s*)?'
    r'<a class="airport-teaser" href="[^"]*" target="_blank" rel="noopener">.*?</a>',
    re.DOTALL,
)


def build_teaser_block(href: str, img_src: str, alt: str, title: str, desc: str, more_label: str = "Habere git → haber.aero", generic: bool = False) -> str:
    block = (
        f'<a class="airport-teaser" href="{href}" target="_blank" rel="noopener">\n'
        f'      <div class="airport-teaser-photo"><img src="{img_src}" alt="{alt}"></div>\n'
        f'      <div class="airport-teaser-body">\n'
        f'        <span class="airport-teaser-label">Bu Hafta Airport\'ta</span>\n'
        f'        <h3 class="airport-teaser-title">{title}</h3>\n'
        f'        <p class="airport-teaser-desc">{desc}</p>\n'
        f'        <span class="airport-teaser-more">{more_label}</span>\n'
        f'      </div>\n'
        f'    </a>'
    )
    if generic:
        block = f'{GENERIC_MARKER}\n    {block}'
    return block


def main() -> int:
    feed_xml = fetch(FEED_URL)
    index_content = INDEX_HTML.read_text(encoding="utf-8")
    existing_match = TEASER_BLOCK_RE.search(index_content)
    if not existing_match:
        print("Hata: main-site/index.html icinde airport-teaser bloğu bulunamadi.")
        return 1

    # 1) Once dedicated "Airport'ta bu hafta: ..." habercisini dene.
    item = find_latest_airport_item(feed_xml)
    if item:
        if f'href="{item["link"]}"' in existing_match.group(0):
            print(f"Zaten guncel (dedicated): {item['title']}")
            return 0

        og_image = extract_og_image(item["link"])
        if not og_image:
            print("Uyari: makalede og:image bulunamadi, gorsel guncellenmeyecek.")
            return 1

        slug = slug_from_link(item["link"])
        image_path = IMAGES_DIR / f"{slug}.jpg"
        image_bytes = fetch(og_image)
        save_resized_image(image_bytes, image_path)

        title = re.sub(r"^Airport.{0,3}ta bu hafta:\s*", "", item["title"], flags=re.IGNORECASE)
        desc = first_sentence(item["description_html"])

        new_block = build_teaser_block(
            href=item["link"],
            img_src=f"images/{image_path.name}",
            alt=title,
            title=title,
            desc=desc,
        )
        new_content = index_content[: existing_match.start()] + new_block + index_content[existing_match.end():]
        INDEX_HTML.write_text(new_content, encoding="utf-8")
        print(f"Guncellendi (dedicated): {title}")
        print(f"Link: {item['link']}")
        print(f"Gorsel: {image_path.relative_to(REPO_ROOT)}")
        print(f"Aciklama: {desc}")
        return 0

    # 2) Dedicated haber yoksa, herhangi bir haberin ICERIGINDE gecen genel
    #    tanitim cumlesini ara (sadece basliga degil, tam metne bakar).
    promo = find_generic_promo(feed_xml)
    if not promo:
        print("Uyari: haber.aero feed'inde ne dedicated 'Airport'ta bu hafta' haberi "
              "ne de genel tanitim cumlesi bulunamadi.")
        return 0

    marker_needle = f"{GENERIC_MARKER}"
    if marker_needle in existing_match.group(0) and promo["date_phrase"] in existing_match.group(0):
        print(f"Zaten guncel (genel tanitim): {promo['sentence']}")
        return 0

    new_block = build_teaser_block(
        href="https://tv.haberturk.com/program/airport/147",
        img_src=FALLBACK_IMAGE,
        alt="Airport",
        title="En Özel Konu ve Konuklarıyla Ekranda",
        desc=promo["sentence"],
        more_label="Tüm Bölümler → Habertürk TV",
        generic=True,
    )
    new_content = index_content[: existing_match.start()] + new_block + index_content[existing_match.end():]
    INDEX_HTML.write_text(new_content, encoding="utf-8")
    print(f"Guncellendi (genel tanitim cumlesi, kaynak: {promo['source_link']}):")
    print(promo["sentence"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
