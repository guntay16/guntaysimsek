#!/usr/bin/env python3
"""
guntaysimsek.com'daki "TV Yayınları — Airport" bölümlerini (anasayfa
hcard-row ve televizyon/index.html tv-list) Airport programının YouTube
oynatma listesiyle otomatik senkronize eder.

Kaynak (12 Kasım 2026'dan beri; kullanıcı: "Habertürk yerine tv programına
burayı link verelim"): AirportHT YouTube kanalının "Airport" oynatma listesi
(tam bölümler, "Konu | Airport -8 Kasım 2026" başlığıyla):
    https://www.youtube.com/playlist?list=PL7F3383DF1908AE23
Düz RSS akışı (son 15 bölüm), JS ve API anahtarı gerekmez:
    https://www.youtube.com/feeds/videos.xml?playlist_id=PL7F3383DF1908AE23

Kural: sadece YouTube'daki kendi başlık, tarih, bağlantı, kapak görseli ve
açıklamanın ilk paragrafı kullanılır - uydurma içerik yok. Bağlantılar
YouTube'daki bölüme (watch?v=...) gider.

Çalışma mantığı:
  1) Akıştaki bölümleri (video id, tarih, konu) çıkarır.
  2) Sitede Habertürk bağlantısıyla duran, akışta bulunan bölümlerin
     bağlantısını/kapağını YouTube'a çevirir (bir kerelik göç; akışta olmayan
     çok eski bölümler olduğu gibi kalır).
  3) Sitede tarihi bulunmayan yeni bölümleri iki dosyanın da listesinin EN
     BAŞINA ekler (hiçbir eski bölüm silinmez).
  4) Yeni bölüm yoksa ve en yeni bölüm çok eskiyse açık hata verir.

Pazartesi-Perşembe GitHub Actions tarafından çalıştırılır (bkz.
.github/workflows/airport-episodes.yml). Elle çalıştırmak için:
    python3 scripts/update_airport_episodes.py
"""
import html
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "main-site" / "index.html"
TV_HTML = REPO_ROOT / "main-site" / "televizyon" / "index.html"

PLAYLIST_ID = "PL7F3383DF1908AE23"
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?playlist_id={PLAYLIST_ID}"
PLAYLIST_URL = f"https://www.youtube.com/playlist?list={PLAYLIST_ID}"
UA = "Mozilla/5.0 (compatible; guntaysimsek-airport-bot/1.0)"

# Airport her Pazar 12:15'te yayinlaniyor, bu script her Pazartesi
# calisiyor; en yeni bilinen bolum bundan cok daha eskiyse (ör. iki
# haftadan fazla) bu genelde "bu hafta bolum yok" degil, tv.haberturk.com
# sayfa yapisinin degisip script'in artik hicbir yeni bolumu taniyamadigi
# anlamina gelir - 2026 Eylul'deki iki haftalik sessiz aksakligin bir
# daha fark edilmeden tekrarlanmamasi icin bu durum acik hata sayilir.
STALE_AFTER_DAYS = 10

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
EXISTING_DATE_RE = re.compile(r'<span class="tv-ep-date">(\d{4})\.(\d{2})\.(\d{2})</span>')

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


FEED_TITLE_RE = re.compile(r"^(.*?)\s*\|\s*Airport\s*-\s*(\d{1,2})\s+(\S+)\s+(\d{4})")


def thumb_url(video_id: str) -> str:
    """16:9 kapak: maxresdefault varsa o, yoksa mqdefault."""
    best = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    try:
        req = Request(best, headers={"User-Agent": UA}, method="HEAD")
        with urlopen(req, timeout=20) as resp:
            if resp.status == 200:
                return best
    except Exception:
        pass
    return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"


def parse_feed(feed_xml: str) -> list:
    """Oynatma listesi akışından bölümleri (en yeniden en eskiye) çıkarır;
    'Konu | Airport -8 Kasım 2026' kalıbına uymayanlar atlanır."""
    episodes = []
    for entry in re.findall(r"<entry>(.*?)</entry>", feed_xml, re.DOTALL):
        vid = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", entry)
        title = re.search(r"<title>([^<]+)</title>", entry)
        if not vid or not title:
            continue
        tm = FEED_TITLE_RE.match(html.unescape(title.group(1)).strip())
        if not tm:
            continue
        subject, day, monname, year = tm.groups()
        mon = TR_MONTHS.get(monname.lower())
        if not mon:
            continue
        desc_m = re.search(r"<media:description>(.*?)</media:description>", entry, re.DOTALL)
        desc = ""
        if desc_m:
            first = html.unescape(desc_m.group(1)).strip().split("\n\n")[0]
            desc = re.sub(r"\s+", " ", first).strip()
        episodes.append({
            "id": vid.group(1),
            "url": f"https://www.youtube.com/watch?v={vid.group(1)}",
            "date": f"{year}.{int(mon):02d}.{int(day):02d}",
            "subject": subject.strip(),
            "img": None,
            "desc": desc,
        })
    episodes.sort(key=lambda e: e["date"], reverse=True)
    return episodes


def migrate_links(path: Path, block_re: re.Pattern, date_re: re.Pattern, episodes: list) -> int:
    """Habertürk bağlantılı mevcut kartları, akışta bulunan bölümler için
    YouTube bağlantısı ve kapağına çevirir."""
    content = path.read_text(encoding="utf-8")
    by_date = {e["date"]: e for e in episodes}
    changed = 0
    for m in list(block_re.finditer(content)):
        block = m.group(0)
        dm = date_re.search(block)
        old = re.search(r'https://www\.haberturk\.com/video/programlar/izle/airport-[^"\s&]+', block)
        if not dm or not old:
            continue
        ep = by_date.get(f"{dm.group(1)}.{dm.group(2)}.{dm.group(3)}")
        if not ep:
            continue
        new_block = block.replace(old.group(0), ep["url"])
        new_block = new_block.replace(quote(old.group(0), safe="/"), quote(ep["url"], safe="/"))
        new_block = re.sub(r'https://mo\.ciner\.com\.tr/[^"]+?\.jpg', thumb_url(ep["id"]), new_block)
        if new_block != block:
            content = content.replace(block, new_block, 1)
            changed += 1
    if changed:
        path.write_text(content, encoding="utf-8")
    return changed


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


HCARD_BLOCK_RE = re.compile(r'<a class="hcard"[^>]*>.*?</a>\n', re.DOTALL)
TV_BLOCK_RE = re.compile(r'<li class="tv-ep">.*?</li>\n', re.DOTALL)
HCARD_DATE_RE = re.compile(r'<span class="hcard-date">(\d{4})\.(\d{2})\.(\d{2})</span>')


def insert_sorted(path: Path, block_re: re.Pattern, date_re: re.Pattern,
                  marker_re: re.Pattern, new_html: str, ep_date: str) -> bool:
    """Yeni bölüm kartını tarih sırasına göre yerleştirir: kendinden daha
    eski ilk kartın önüne; hepsi daha yeniyse listenin sonuna (daha önce
    eksik kalmış eski bir bölüm yanlışlıkla en üste çıkmasın)."""
    content = path.read_text(encoding="utf-8")
    mk = marker_re.search(content)
    if not mk:
        print(f"Hata: {path} icinde beklenen blok bulunamadi.")
        return False
    pos = None
    for m in block_re.finditer(content, mk.end(1)):
        dm = date_re.search(m.group(0))
        if dm and f"{dm.group(1)}.{dm.group(2)}.{dm.group(3)}" < ep_date:
            pos = m.start()
            break
    if pos is None:   # hepsinden eski: son kartın sonuna
        last = None
        for last in block_re.finditer(content, mk.end(1)):
            pass
        pos = last.end() if last else mk.end(1)
    content = content[:pos] + new_html + content[pos:]
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    episodes = parse_feed(fetch(FEED_URL))
    if not episodes:
        print("Uyari: YouTube oynatma listesinden hiç Airport bölümü çıkarılamadı.")
        return 1
    for ep in episodes:
        ep["img"] = thumb_url(ep["id"])

    # bir kerelik göç: Habertürk bağlantıları -> YouTube
    moved = migrate_links(INDEX_HTML, HCARD_BLOCK_RE, HCARD_DATE_RE, episodes)
    moved += migrate_links(TV_HTML, TV_BLOCK_RE, EXISTING_DATE_RE, episodes)
    if moved:
        print(f"{moved} mevcut bölüm kartı YouTube bağlantısına çevrildi.")

    known_content = TV_HTML.read_text(encoding="utf-8")
    existing_dates = {f"{y}.{m}.{d}" for y, m, d in EXISTING_DATE_RE.findall(known_content)}

    new_episodes = [e for e in episodes if e["date"] not in existing_dates]
    if not new_episodes:
        date_matches = EXISTING_DATE_RE.findall(known_content)
        if not date_matches:
            print("Uyari: televizyon/index.html icinde hic bolum tarihi bulunamadi.")
            return 0
        newest = max(date(int(y), int(m), int(d)) for y, m, d in date_matches)
        age_days = (date.today() - newest).days
        if age_days > STALE_AFTER_DAYS:
            print(f"Hata: sitedeki en yeni Airport bölümü {age_days} gündür güncellenmedi "
                  f"(son bilinen bölüm: {newest.isoformat()}). YouTube oynatma listesi "
                  f"({PLAYLIST_URL}) tarandı ama hiç yeni bölüm bulunamadı - liste ya da "
                  "başlık biçimi değişmiş olabilir, kontrol gerekiyor.")
            return 1
        print(f"Zaten güncel, yeni Airport bölümü yok (son bölüm {age_days} gün önce, "
              f"eşik {STALE_AFTER_DAYS} gün).")
        return 0

    new_episodes.sort(key=lambda e: e["date"])   # eskiden yeniye; her biri kendi sırasına girer
    for ep in new_episodes:
        ok_home = insert_sorted(INDEX_HTML, HCARD_BLOCK_RE, HCARD_DATE_RE, HCARD_ROW_RE,
                                build_hcard(ep), ep["date"])
        ok_tv = insert_sorted(TV_HTML, TV_BLOCK_RE, EXISTING_DATE_RE, TV_LIST_RE,
                              build_tv_ep(ep, ep["desc"]), ep["date"])
        if not (ok_home and ok_tv):
            return 1

    print(f"{len(new_episodes)} yeni Airport bölümü eklendi:")
    for e in sorted(new_episodes, key=lambda e: e["date"], reverse=True):
        print(f" - {e['date']}  {e['subject']}  ({e['url']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
