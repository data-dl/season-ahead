"""University of Chicago Press.

Chicago publishes no forthcoming feed, but every "browse by subject" page
ships the complete record for each book it lists inside a `books = eval([...])`
block: title, author, publisher, jacket path and a publication timestamp.
Walking the subject tree once and merging on URL therefore reconstructs the
whole catalogue — about 23,000 titles — and the timestamps make the
forthcoming slice a plain filter.

Two things make Chicago different from the other four:

  * It distributes for roughly a hundred other houses. The listing's `ucp`
    flag separates Chicago's own list from those, and the detail page names
    the house it is distributing for. The dashboard keeps them apart.
  * Prices and formats are loaded by the shopping cart's own JavaScript, so
    they are not on the page. Everything else is.

robots.txt asks for Crawl-delay: 2, which UC_DELAY honours.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import date, datetime
from pathlib import Path

import requests

from presses import blocks, clean, praise_pairs, session, soup

SITE = "https://press.uchicago.edu"
UC_DELAY = 2.0
INDEX = Path(__file__).resolve().parent / "data" / "uc_index.json"

_lock = threading.Lock()
_last = [0.0]


def get(url, tries=2):
    """One request every UC_DELAY seconds, whatever the caller's concurrency."""
    for _ in range(tries):
        with _lock:
            wait = UC_DELAY - (time.time() - _last[0])
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
        try:
            r = session.get(url, timeout=45)
            if r.status_code == 200:
                return r
            if r.status_code in (404, 410):
                return None
        except requests.RequestException:
            pass
    return None


def subject_pages(log=print):
    r = get(f"{SITE}/books/subject.html")
    if r is None:
        return []
    pages = sorted(set(re.findall(r'href="(/ucp/books/subject/[^"]+\.html)"', r.text)))
    log(f"    chicago: {len(pages)} subject pages to walk")
    return pages


def index(log=print, max_age_days=3):
    """The merged catalogue, cached — the walk is 250-odd polite requests."""
    if INDEX.exists():
        age_h = (time.time() - INDEX.stat().st_mtime) / 3600
        if age_h < max_age_days * 24:
            books = json.loads(INDEX.read_text(encoding="utf-8"))
            log(f"    chicago: {len(books)} books from the cached index ({age_h:.0f}h old)")
            return books

    books, done = {}, 0
    for path in subject_pages(log=log):
        r = get(SITE + path)
        done += 1
        if r is None:
            continue
        m = re.search(r"books\s*=\s*eval\(\s*(\[.*?\])\s*\);", r.text, re.S)
        if not m:
            continue
        try:
            rows = json.loads(m.group(1))
        except ValueError:
            continue
        for b in rows:
            if b.get("url"):
                books.setdefault(b["url"], b)
        if done % 40 == 0:
            log(f"    chicago: {done} pages, {len(books)} books")

    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(list(books.values()), separators=(",", ":")),
                     encoding="utf-8")
    log(f"    chicago: {len(books)} books indexed from {done} pages")
    return list(books.values())


def listing(cutoff: date, horizon: date, log=print):
    rows = []
    for b in index(log=log):
        ts = b.get("pubDate")
        if not isinstance(ts, (int, float)) or not 0 < ts < 4e12:
            continue
        try:
            d = datetime.fromtimestamp(ts / 1000).date()
        except (OverflowError, OSError, ValueError):
            continue
        if not cutoff <= d <= horizon:
            continue
        img = b.get("image") or ""
        cover = ""
        if img and "ImageNotAvailable" not in img:
            cover = f"{SITE}/.imaging/mte/ucp/thumbnail{img}"
        # The book page lists related titles' ISBNs too, so take this book's
        # from its own basket link, falling back to the jacket filename.
        m = (re.search(r"ISBN=(97[89]\d{10})", b.get("buy") or "")
             or re.search(r"(97[89]\d{10})", img))
        rows.append({
            "press": "chicago",
            "url": SITE + b["url"],
            "isbn": m.group(1) if m else "",
            "title": clean(b.get("title")),
            "authors": clean(b.get("author")),
            "pub_date": d.isoformat(),
            "cover": cover,
            "own_list": bool(b.get("ucp")),
        })
    own = sum(1 for r in rows if r["own_list"])
    log(f"    chicago: {len(rows)} in window — {own} on Chicago's own list, "
        f"{len(rows) - own} distributed for other houses")
    return rows


DETAILS = Path(__file__).resolve().parent / "data" / "uc_details.json"
DETAIL_TTL_DAYS = 14
_details = None
_details_lock = threading.Lock()


def _load_details():
    global _details
    if _details is None:
        try:
            _details = json.loads(DETAILS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _details = {}
    return _details


def save_details():
    d = _load_details()
    DETAILS.parent.mkdir(parents=True, exist_ok=True)
    DETAILS.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")


def detail(row):
    """Parsed record for one book, cached so a refresh only re-reads what aged.

    Seven hundred pages at one every two seconds is twenty-five minutes, which
    is too long to repeat for books whose copy has not changed. Records go
    stale after DETAIL_TTL_DAYS; blurbs mostly arrive near publication, so
    anything publishing within three months is re-read every time.
    """
    cache = _load_details()
    hit = cache.get(row["url"])
    if hit:
        age = (time.time() - hit.get("_at", 0)) / 86400
        near = (date.fromisoformat(row["pub_date"]) - date.today()).days < 90
        if age < DETAIL_TTL_DAYS and not near:
            rec = {k: v for k, v in hit.items() if k != "_at"}
            rec.update(pub_date=row["pub_date"], cover=row.get("cover", ""),
                       own_list=row.get("own_list", True))
            if row.get("isbn"):
                rec["isbn"] = row["isbn"]
            return rec

    rec = _fetch_detail(row)
    if rec:
        with _details_lock:
            cache[row["url"]] = dict(rec, _at=time.time())
    return rec


def _fetch_detail(row):
    r = get(row["url"])
    if r is None:
        return None
    s = soup(r.text)
    for junk in s.select("script, style, nav, header, footer"):
        junk.decompose()

    h1 = s.find("h1")
    title = clean(h1.get_text()) if h1 else row["title"]
    h2 = h1.find_next("h2") if h1 else None
    subtitle = clean(h2.get_text()) if h2 else ""

    author_el = s.select_one(".author-info")
    authors = clean(author_el.get_text(" ")) if author_el else row["authors"]

    # "Distributed for <Press>" names the house Chicago is warehousing for
    distributor = ""
    for lab in s.select("span.label"):
        if clean(lab.get_text()).lower().startswith("distributed for"):
            link = lab.find_next("a")
            if link:
                distributor = clean(link.get_text())
            break

    paras = blocks(s.select_one(".purchase-item-detail-summary"))
    tagline = ""
    if paras and len(paras[0]) < 300:
        tagline, paras = paras[0], paras[1:]

    rv = s.select_one("#anchor-reviews")
    praise = praise_pairs([
        (q.get_text(" "),
         (lambda a: a.get_text(" ") if a else "")(
             q.find_next("p", class_="blockquote-review-attribution")))
        for q in rv.select("blockquote.blockquote-review")]) if rv else []

    pages = trim = series = ""
    subjects = []
    det = s.select_one(".purchase-item-detail-details")
    if det:
        for para in det.find_all("p"):
            txt = clean(para.get_text(" "))
            if "subject-list" in (para.get("class") or []):
                subjects += [clean(a.get_text()) for a in para.select("a")]
            elif re.search(r"\d+ pages", txt):
                pages = re.search(r"(\d+) pages", txt).group(1)
                m = re.search(r"(\d+(?:\.\d+)? x \d+(?:\.\d+)?)", txt)
                trim = f"{m.group(1)} in" if m else ""
            elif txt and not series:
                series = txt

    # The listing's basket link is authoritative; the page also carries the
    # ISBNs of every related title it recommends.
    isbn = row.get("isbn") or ""
    if not isbn:
        widget = s.select_one(".purchase-item-detail-purchase-widget") or s
        found = re.findall(r"97[89]\d{10}", str(widget))
        isbn = found[0] if found else row["url"].rsplit("/", 1)[-1].replace(".html", "")

    return {
        "press": "chicago",
        "isbn": isbn,
        "title": title,
        "subtitle": subtitle,
        "authors": authors,
        "pub_date": row["pub_date"],
        "url": row["url"],
        "cover": row.get("cover", ""),
        "tagline": tagline,
        "description": "\n\n".join(paras),
        "bio": "",
        "praise": praise,
        "subjects": list(dict.fromkeys(subjects))[:6],
        "series": series,
        "format": "",
        "formats": [],
        "pages": pages,
        "price": "",
        "trim": trim,
        "own_list": row.get("own_list", True),
        "distributor": distributor,
    }
