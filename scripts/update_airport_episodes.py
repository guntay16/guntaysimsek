#!/usr/bin/env python3
"""
guntaysimsek.com'daki "TV Yayınları — Airport" bölümlerini (anasayfa
hcard-row ve televizyon/index.html tv-list) tv.haberturk.com'daki gerçek
Airport program sayfasıyla otomatik senkronize eder.

Kaynak: https://tv.haberturk.com/program/airport/147
(Airport programının kendi sayfası - hem en yeni (öne çıkan) bölümü hem de
son bölümlerin bir listesini sunucu tarafında render edilmiş düz HTML
olarak içerir, JS çalıştırmaya gerek yok.)

Kural: sadece Habertürk'ün kendi başlığı, kendi tarihi, kendi linki, kendi
kapak görseli ve (bölüm sayfasındaki) kendi konuk tanıtım cümlesinden
türetilen içerik kullanılır - uydurma içerik yok.

Calisma mantigi:
  1) Program sayfasından bölüm listesini (id, tarih, başlık, kapak görseli)
     çıkarır - hem "öne çıkan" en yeni bölüm hem de altındaki bölüm
     şeridi aynı <a title="Airport - ..." href=".../airport-...-/ID"> kalıbını
     kullandığı için tek bir taramayla ikisi de yakalanır.
  2) main-site/televizyon/index.html içinde henüz bulunmayan (yeni) bölümleri
     tespit eder (id, video URL'sindeki son sayı).
  3) Yeni bölüm yoksa hiçbir şey değiştirmez.
  4) Yeni bölüm(ler) varsa, her biri için kendi video sayfasından
     ("cms-container" içindeki konuk tanıtım cümlesi) kısa açıklama çeker
     ve iki dosyanın da listesinin EN BAŞINA ekler (hiçbir eski bölüm
     silinmez, sıralama en yeniden en eskiye).

Her pazartesi GitHub Actions tarafından çalıştırılır (bkz.
.github/workflows/airport-episodes.yml). Elle çalıştırmak için:
    python3 scripts/update_airport_episodes.py
"""
import html
import re
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "main-site" / "index.html"
TV_HTML = REPO_ROOT / "main-site" / "televizyon" / "index.html"

PROGRAM_URL = "https://tv.haberturk.com/program/airport/147"
UA = "Mozilla/5.0 (compatible; guntaysimsek-airport-bot/1.0)"

TAG_RE = re.compile(r"<a\b[^>]*>")
HREF_RE = re.compile(r'href="([^"]+)"')
TITLE_RE = re.compile(r'title="([^"]+)"')
IMG_RE = re.compile(r'src="(https://mo\.ciner\.com\.tr/[^"]+?\.jpg)"')
EP_ID_RE = re.compile(r"/(\d+)$")

TITLE_PARSE_RE = re.compile(r"^Airport\s*-\s*(\d{1,2})\s+(\S+)\s+(\d{4})\s*\((.+)\)\s*$")

TR_MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4,
    "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7,
    "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
    "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
}

EXISTING_ID_RE = re.compile(r"video/programlar/izle/airport-[^\"]+/(\d+)\"")

CMS_DESC_RE = re.compile(
    r'<div class="cms-container">\s*<p><span>(.*?)</span></p>', re.DOTALL
)

HCARD_ROW_RE = re.compile(r'(<div class="hcard-row">\n)', re.DOTALL)
TV_LIST_RE = re.compile(r'(<ul class="tv-list">\n)', re.DOTALL)


def fetch(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def parse_program_page(page_html: str) -> list:
    """Program sayfasındaki tüm bölüm linklerini (öne çıkan + şerit) tarih
    sırasına gerek kalmadan çıkarır, en yeniden en eskiye sıralı döner."""
    seen_ids = set()
    episodes = []
    for m in TAG_RE.finditer(page_html):
        tag = m.group(0)
        if "video/programlar/izle/airport-" not in tag:
            continue
        href_m = HREF_RE.search(tag)
        title_m = TITLE_RE.search(tag)
        if not href_m or not title_m:
            continue
        href = href_m.group(1)
        ep_id_m = EP_ID_RE.search(href)
        if not ep_id_m:
            continue
        ep_id = ep_id_m.group(1)
        if ep_id in seen_ids:
            continue
        title = html.unescape(title_m.group(1))
        tm = TITLE_PARSE_RE.match(title)
        if not tm:
            continue
        day, monname, year, subject = tm.groups()
        mon = TR_MONTHS.get(monname.lower())
        if not mon:
            continue
        seen_ids.add(ep_id)
        img_m = IMG_RE.search(page_html, m.end(), m.end() + 800)
        episodes.append({
            "id": ep_id,
            "url": href,
            "date": f"{year}.{int(mon):02d}.{int(day):02d}",
            "subject": subject.strip(),
            "img": img_m.group(1) if img_m else None,
        })
    episodes.sort(key=lambda e: e["date"], reverse=True)
    return episodes


def episode_desc(episode: dict) -> str:
    try:
        page_html = fetch(episode["url"])
    except Exception as exc:
        print(f"Uyari: bölüm sayfası okunamadı ({episode['url']}): {exc}")
        return ""
    m = CMS_DESC_RE.search(page_html)
    if not m:
        return ""
    return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()


def build_hcard(ep: dict) -> str:
    subject = esc(ep["subject"])
    img = ep["img"] or ""
    return (
        '      <a class="hcard" href="{url}" target="_blank" rel="noopener">\n'
        '        <div class="hcard-photo"><img src="{img}" alt="{subject}" loading="lazy"></div>\n'
        '        <div class="hcard-body">\n'
        '          <span class="hcard-date">{date}</span>\n'
        '          <h3 class="hcard-title">{subject}</h3>\n'
        '        </div>\n'
        '      </a>\n'
    ).format(url=ep["url"], img=img, subject=subject, date=ep["date"])


def build_tv_ep(ep: dict, desc: str) -> str:
    subject = esc(ep["subject"])
    img = ep["img"] or ""
    desc_esc = esc(desc) if desc else ""
    share_text = quote(f"{ep['subject']} — Airport", safe="")
    share_url = quote(ep["url"], safe="/")
    return (
        '      <li class="tv-ep">\n'
        '        <a class="tv-ep-link" href="{url}" target="_blank" rel="noopener">\n'
        '          <div class="tv-ep-thumb"><img src="{img}" alt="{subject}" loading="lazy"></div>\n'
        '          <div>\n'
        '            <span class="tv-ep-date">{date}</span>\n'
        '            <h3 class="tv-ep-title">{subject}</h3>\n'
        '            <p class="tv-ep-desc">{desc}</p>\n'
        '          </div>\n'
        '        </a>\n'
        '              <div class="share-row">\n'
        '          <span class="share-label">Paylaş:</span>\n'
        '          <a href="https://twitter.com/intent/tweet?text={share_text}&url={share_url}" target="_blank" rel="noopener">X</a>\n'
        '          <a href="https://wa.me/?text={share_text}%20{share_url}" target="_blank" rel="noopener">WhatsApp</a>\n'
        '          <button type="button" class="copy-link" data-url="{url}">Kopyala</button>\n'
        '        </div>\n'
        '      </li>\n'
    ).format(url=ep["url"], img=img, subject=subject, date=ep["date"], desc=desc_esc,
              share_text=share_text, share_url=share_url)


def prepend_block(path: Path, marker_re: re.Pattern, new_html: str) -> bool:
    content = path.read_text(encoding="utf-8")
    m = marker_re.search(content)
    if not m:
        print(f"Hata: {path} icinde beklenen blok bulunamadi.")
        return False
    content = content[: m.end(1)] + new_html + content[m.end(1):]
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    page_html = fetch(PROGRAM_URL)
    episodes = parse_program_page(page_html)
    if not episodes:
        print("Uyari: program sayfasından hiç bölüm çıkarılamadı.")
        return 1

    known_content = TV_HTML.read_text(encoding="utf-8")
    existing_ids = set(EXISTING_ID_RE.findall(known_content))

    new_episodes = [e for e in episodes if e["id"] not in existing_ids]
    if not new_episodes:
        print("Zaten güncel, yeni Airport bölümü yok.")
        return 0

    # en eskisinden en yenisine dogru eklemek, iki dosyada da en basa
    # dogru sirada (en yeni en ustte) yerlesmesini saglar
    new_episodes.sort(key=lambda e: e["date"])

    hcard_html = ""
    tv_html = ""
    for ep in new_episodes:
        desc = episode_desc(ep)
        hcard_html = build_hcard(ep) + hcard_html
        tv_html = build_tv_ep(ep, desc) + tv_html

    ok_home = prepend_block(INDEX_HTML, HCARD_ROW_RE, hcard_html)
    ok_tv = prepend_block(TV_HTML, TV_LIST_RE, tv_html)
    if not (ok_home and ok_tv):
        return 1

    print(f"{len(new_episodes)} yeni Airport bölümü eklendi:")
    for e in sorted(new_episodes, key=lambda e: e["date"], reverse=True):
        print(f" - {e['date']}  {e['subject']}  ({e['url']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
