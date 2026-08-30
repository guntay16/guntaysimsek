#!/usr/bin/env python3
"""
guntaysimsek.com anasayfasindaki "Bu Hafta Airport'ta" tanitim kutusunu
haber.aero'daki en guncel "Airport'ta bu hafta" haberiyle otomatik gunceller.

Haftada bir kez GitHub Actions tarafindan calistirilir (bkz.
.github/workflows/airport-teaser.yml). Elle calistirmak icin:
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


def fetch(url: str, timeout: int = 20) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def find_latest_airport_item(feed_xml: bytes):
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


def first_sentence(description_html: str, max_len: int = 220) -> str:
    text = re.sub(r"<[^>]+>", " ", description_html)
    text = html.unescape(text)
    text = re.sub(r"\[\S*\.\.\.\S*\]|\[…\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
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


def main() -> int:
    feed_xml = fetch(FEED_URL)
    item = find_latest_airport_item(feed_xml)
    if not item:
        print("Uyari: haber.aero feed'inde 'Airport'ta bu hafta' haberi bulunamadi.")
        return 0

    index_content = INDEX_HTML.read_text(encoding="utf-8")
    existing_match = TEASER_BLOCK_RE.search(index_content)
    if existing_match and f'href="{item["link"]}"' in existing_match.group(0):
        print(f"Zaten guncel: {item['title']}")
        return 0

    og_image = extract_og_image(item["link"])
    if not og_image:
        print("Uyari: makalede og:image bulunamadi, gorsel guncellenmeyecek.")
        return 1

    slug = slug_from_link(item["link"])
    image_path = IMAGES_DIR / f"{slug}.jpg"
    image_bytes = fetch(og_image)
    save_resized_image(image_bytes, image_path)

    # Baslikta "Airport'ta bu hafta: " on eki varsa kaldir - kutuda zaten
    # "Bu Hafta Airport'ta" etiketi ayrica gosteriliyor.
    title = re.sub(r"^Airport.{0,3}ta bu hafta:\s*", "", item["title"], flags=re.IGNORECASE)
    desc = first_sentence(item["description_html"])

    new_block = build_teaser_block(
        href=item["link"],
        img_src=f"images/{image_path.name}",
        alt=title,
        title=title,
        desc=desc,
    )

    if not existing_match:
        print("Hata: main-site/index.html icinde airport-teaser bloğu bulunamadi.")
        return 1

    new_content = index_content[: existing_match.start()] + new_block + index_content[existing_match.end() :]
    INDEX_HTML.write_text(new_content, encoding="utf-8")

    print(f"Guncellendi: {title}")
    print(f"Link: {item['link']}")
    print(f"Gorsel: {image_path.relative_to(REPO_ROOT)}")
    print(f"Aciklama: {desc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
