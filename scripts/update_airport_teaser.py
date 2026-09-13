#!/usr/bin/env python3
"""
guntaysimsek.com anasayfasindaki "Bu Hafta Airport'ta" tanitim kutusunu
haber.aero'daki en guncel Airport icerigiyle otomatik gunceller.

Kural: kutu HER ZAMAN haber.aero'nun kendi icerigini (baslik, gorsel, link)
kullanir. Hicbir zaman siteye ozel/genel bir gorsele (ör. Güntay Şimşek'in
kendi portresi) ya da uydurma bir baslik/linke dusulmez - boyle bir yontem
yok.

Iki farkli sinyal aranir, hangisi bulunursa o haberin kendi baslik/gorsel/
linki kullanilir:
  1) Dedicated ozel haber: basligi "Airport'ta bu hafta: ..." seklinde olan,
     o haftaya ozel konuyu tasiyan bir haber.aero yazisi.
  2) Genel tanitim cumlesi: haber.aero'nun konuyla ilgisiz bircok haberinin
     SONUNA hafta sonuna dogru ekledigi, sabit kalipli tanitim notu:
       "Airport, en ozel konu ve konuklariyla <tarih> Pazar, saat 12.15'te
        Haberturk TV ekranlarinda olacak."
     Bu not sadece BASLIKTA degil, haberin ICERIGINDE gectigi icin
     basliktan degil, tam metinden aranmasi gerekiyor. Boyle bir haber
     bulunursa, o haberin KENDI basligi/gorseli/linki kullanilir (haberin
     konusu Airport'la ilgisiz olsa bile - ornegin ucakta powerbank
     kurallari hakkinda bir haber olabilir); kutunun aciklama satirina ise
     bu tanitim cumlesi yazilir, boylece kutu neden bu habere baglandigini
     acikliyor.

Oncelik dedicated habere verilir; o bulunamazsa genel tanitim cumlesine
dusulur. Ikisi de yoksa kutu degistirilmez.

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
MAX_CONTENT_SCAN = 20

GENERIC_PROMO_RE = re.compile(
    r"Airport,?\s+en\s+özel\s+konu\s+(?:ve\s+)?konuklar[ıi]yla\s+"
    r"(\d{1,2}\s+\w+)\s+Pazar,?\s+saat\s+12[.:]15[^.]*\.",
    re.IGNORECASE,
)


def fetch(url: str, timeout: int = 20) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_tags(raw_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def first_sentence(description_html: str, max_len: int = 220) -> str:
    text = strip_tags(description_html)
    text = re.sub(r"\[\S*\.\.\.\S*\]|\[…\]", "", text)
    match = re.search(r"^(.{20,%d}?[.!?])(\s|$)" % max_len, text)
    sentence = match.group(1) if match else text[:max_len].rsplit(" ", 1)[0] + "…"
    return sentence.strip()


def extract_og_image(page_html: str) -> str | None:
    match = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        page_html,
    )
    return match.group(1) if match else None


def extract_title(page_html: str) -> str | None:
    match = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        page_html,
    )
    if match:
        # og:title genelde " - Havacilik, Savunma, ..." site adiyla biter.
        return html.unescape(match.group(1)).split(" - ")[0].strip()
    return None


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
    r'<a class="airport-teaser" href="[^"]*" target="_blank" rel="noopener">.*?</a>',
    re.DOTALL,
)


def build_teaser_block(href: str, img_src: str, alt: str, title: str, desc: str) -> str:
    return (
        f'<a class="airport-teaser" href="{href}" target="_blank" rel="noopener">\n'
        f'      <div class="airport-teaser-photo"><img src="{img_src}" alt="{alt}"></div>\n'
        f'      <div class="airport-teaser-body">\n'
        f'        <span class="airport-teaser-label">Bu Hafta Airport\'ta</span>\n'
        f'        <h3 class="airport-teaser-title">{title}</h3>\n'
        f'        <p class="airport-teaser-desc">{desc}</p>\n'
        f'        <span class="airport-teaser-more">Habere git → haber.aero</span>\n'
        f'      </div>\n'
        f'    </a>'
    )


def find_dedicated_item(feed_xml: bytes):
    """Basligi 'Airport'ta bu hafta ...' olan dedicated haberi arar."""
    root = ET.fromstring(feed_xml)
    for item in root.iter("item"):
        title_raw = (item.findtext("title") or "").strip()
        title = html.unescape(title_raw)
        low = title.lower()
        if "airport" in low and "bu hafta" in low:
            link = (item.findtext("link") or "").strip()
            desc_raw = item.findtext("description") or ""
            return {
                "link": link,
                "title": re.sub(r"^Airport.{0,3}ta bu hafta:\s*", "", title, flags=re.IGNORECASE),
                "desc": first_sentence(desc_raw),
            }
    return None


def find_generic_promo_item(feed_xml: bytes, max_items: int = MAX_CONTENT_SCAN):
    """Basliginda gecmese bile, herhangi bir haberin ICERIGINDE gecen sabit
    Airport tanitim cumlesini arar ve o haberin KENDI baslik/gorselini
    dondurur (fallback gorsel/baslik kullanilmaz)."""
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
            page_bytes = fetch(link)
        except Exception:
            continue
        page_html = page_bytes.decode("utf-8", errors="ignore")
        text = strip_tags(page_html)
        m = GENERIC_PROMO_RE.search(text)
        if not m:
            continue
        og_image = extract_og_image(page_html)
        title = extract_title(page_html) or html.unescape((item.findtext("title") or "").strip())
        if not og_image:
            continue
        return {
            "link": link,
            "title": title,
            "desc": m.group(0).strip(),
            "og_image": og_image,
        }
    return None


def apply_update(index_content: str, existing_match, link: str, title: str, desc: str, og_image_bytes: bytes | None, og_image_url: str | None) -> str | None:
    if f'href="{link}"' in existing_match.group(0):
        return None  # zaten guncel

    slug = slug_from_link(link)
    image_path = IMAGES_DIR / f"{slug}.jpg"
    if og_image_bytes is None:
        assert og_image_url is not None
        og_image_bytes = fetch(og_image_url)
    save_resized_image(og_image_bytes, image_path)

    new_block = build_teaser_block(
        href=link,
        img_src=f"images/{image_path.name}",
        alt=title,
        title=title,
        desc=desc,
    )
    return new_block


def main() -> int:
    feed_xml = fetch(FEED_URL)
    index_content = INDEX_HTML.read_text(encoding="utf-8")
    existing_match = TEASER_BLOCK_RE.search(index_content)
    if not existing_match:
        print("Hata: main-site/index.html icinde airport-teaser bloğu bulunamadi.")
        return 1

    # 1) Once dedicated "Airport'ta bu hafta: ..." haberini dene.
    item = find_dedicated_item(feed_xml)
    if item:
        og_image = extract_og_image(fetch(item["link"]).decode("utf-8", errors="ignore"))
        if not og_image:
            print("Uyari: dedicated haberde og:image bulunamadi, gorsel guncellenmeyecek.")
            return 1
        new_block = apply_update(index_content, existing_match, item["link"], item["title"], item["desc"], None, og_image)
        if new_block is None:
            print(f"Zaten guncel (dedicated): {item['title']}")
            return 0
        new_content = index_content[: existing_match.start()] + new_block + index_content[existing_match.end():]
        INDEX_HTML.write_text(new_content, encoding="utf-8")
        print(f"Guncellendi (dedicated): {item['title']}")
        print(f"Link: {item['link']}")
        return 0

    # 2) Dedicated haber yoksa, herhangi bir haberin ICERIGINDE gecen genel
    #    tanitim cumlesini ara. Bulunan haberin KENDI basligi/gorseli kullanilir.
    promo_item = find_generic_promo_item(feed_xml)
    if not promo_item:
        print("Uyari: haber.aero feed'inde ne dedicated 'Airport'ta bu hafta' haberi "
              "ne de genel tanitim cumlesi bulunamadi.")
        return 0

    new_block = apply_update(
        index_content, existing_match,
        promo_item["link"], promo_item["title"], promo_item["desc"],
        None, promo_item["og_image"],
    )
    if new_block is None:
        print(f"Zaten guncel (genel tanitim, kaynak: {promo_item['link']})")
        return 0

    new_content = index_content[: existing_match.start()] + new_block + index_content[existing_match.end():]
    INDEX_HTML.write_text(new_content, encoding="utf-8")
    print(f"Guncellendi (genel tanitim cumlesi uzerinden, kaynak: {promo_item['link']}):")
    print(f"Baslik: {promo_item['title']}")
    print(f"Aciklama: {promo_item['desc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
