"""Shared HTTP plumbing and per-press scrapers.

Four presses, three different back ends:

  Princeton  Algolia index `books_published_date_desc` — the same public
             browse key the site's own search box uses, read out of
             drupalSettings.
  Harvard    server-rendered /forthcoming-books, 20 per page. Its AWS WAF
             turns away python-requests on TLS fingerprint alone, so Harvard
             is fetched through curl instead, one request at a time and two
             seconds apart. robots.txt allows the crawl; the WAF is stricter
             than the Crawl-delay it publishes, so curl() backs off further
             on its own if a challenge comes back.
  Yale, MIT  Supafolio storefronts on the same WordPress theme, so one parser
             covers both. `amount=` is uncapped, so the whole forthcoming
             window arrives in a single request.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")

# MIT's WAF rejects a bare User-Agent, so every request carries the full set.
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# `cover` is a template the dashboard fills in at the width it needs, so the
# page can ask each press's own image CDN for a thumbnail or a full jacket.
PRESSES = {
    "harvard":   {"name": "Harvard University Press", "short": "Harvard",
                  "site": "https://www.hup.harvard.edu",
                  "cover": "https://www.hup.harvard.edu/img/feeds/jackets/{isbn}.png?fm=jpg&q=80&fit=max&w={w}"},
    "mit":       {"name": "The MIT Press", "short": "MIT",
                  "site": "https://mitpress.mit.edu",
                  "cover": "https://mit-press-new-us.imgix.net/covers/{isbn}.jpg?auto=format&w={w}"},
    "princeton": {"name": "Princeton University Press", "short": "Princeton",
                  "site": "https://press.princeton.edu",
                  "cover": "https://pup-assets.imgix.net/onix/images/{isbn}.jpg?auto=format&w={w}"},
    "yale":      {"name": "Yale University Press", "short": "Yale",
                  "site": "https://yalebooks.yale.edu",
                  "cover": "https://yale-press-us.imgix.net/covers/{isbn}.jpg?auto=format&w={w}"},
    # Chicago's jacket paths are keyed by the jacket's own ISBN, which is not
    # always the ISBN you buy, so each Chicago record carries its own cover URL
    # and there is no template to fall back on. See chicago.py.
    "chicago":   {"name": "University of Chicago Press", "short": "Chicago",
                  "site": "https://press.uchicago.edu",
                  "cover": ""},
}

session = requests.Session()
session.headers.update(HEADERS)

# robots.txt asks for Crawl-delay: 1. In practice HUP's WAF starts serving a
# challenge page somewhere above that, so requests are strictly serialised at
# HUP_DELAY apart and the gap widens on its own if a challenge comes back.
HUP_DELAY = [2.0]
HUP_COOLDOWN = 45.0
_hup_lock = threading.Lock()
_hup_last = [0.0]


def get(url, tries=3, **kw):
    """GET with a couple of retries. Returns response or None."""
    for attempt in range(tries):
        try:
            r = session.get(url, timeout=45, **kw)
            if r.status_code == 200:
                return r
            if r.status_code in (404, 410):
                return None
        except requests.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


HUP_CACHE = Path(__file__).resolve().parent / "data" / "hup_cache"


def curl_cached(url, name, tries=2, log=None):
    """curl(), but a page already on disk is never fetched twice.

    Harvard's WAF allows only a few dozen page loads before it starts serving
    a challenge and needs a long rest, so the crawl has to survive being
    interrupted and resumed. Everything it manages to read is kept.
    """
    HUP_CACHE.mkdir(parents=True, exist_ok=True)
    f = HUP_CACHE / f"{name}.html"
    if f.exists() and f.stat().st_size > 2000:
        return f.read_text(encoding="utf-8", errors="replace")
    body = curl(url, tries=tries, log=log)
    if body:
        f.write_text(body, encoding="utf-8")
    return body


def curl(url, tries=3, log=None):
    """Fetch through curl. Harvard's WAF accepts curl but not requests."""
    for attempt in range(tries):
        with _hup_lock:                      # one request at a time, spaced out
            wait = HUP_DELAY[0] - (time.time() - _hup_last[0])
            if wait > 0:
                time.sleep(wait)
            try:
                p = subprocess.run(
                    ["curl", "-sSL", "--compressed", "-A", UA, "--max-time", "45", url],
                    capture_output=True, timeout=60)
                body = p.stdout.decode("utf-8", "replace")
            except (subprocess.TimeoutExpired, OSError):
                body = ""
            _hup_last[0] = time.time()

        if len(body) > 2000 and "awsWafCookieDomainList" not in body:
            return body
        if attempt == tries - 1:
            break                       # no retry follows, so do not sit waiting
        if "awsWafCookieDomainList" in body:
            # Challenged: wait it out and crawl more slowly from here on.
            HUP_DELAY[0] = min(6.0, HUP_DELAY[0] + 1.0)
            if log:
                log(f"    harvard asked us to slow down; pausing {HUP_COOLDOWN:.0f}s, "
                    f"then {HUP_DELAY[0]:.0f}s between requests")
            time.sleep(HUP_COOLDOWN)
        else:
            time.sleep(2.0 * (attempt + 1))
    return None


def soup(html):
    return BeautifulSoup(html, "lxml")


def clean(s):
    """Collapse whitespace, normalise the exotic spaces publishers love.

    Algolia hands back a bare string for a single-valued field and a list when
    a book has several, so coerce rather than assume.
    """
    if not s:
        return ""
    if isinstance(s, (list, tuple)):
        s = ", ".join(dict.fromkeys(str(x) for x in s if x))
    elif not isinstance(s, str):
        s = str(s)
    for ch in (" ", " ", " ", " "):
        s = s.replace(ch, " ")
    return re.sub(r"\s+", " ", s).strip()


def blocks(node):
    """Paragraph list from a node, handling both <p> and <br>-separated prose."""
    if node is None:
        return []
    for br in node.find_all("br"):
        br.replace_with("\n")
    tags = node.find_all(["p", "li", "blockquote"])
    raw = [t.get_text(" ") for t in tags] if tags else [node.get_text(" ")]
    out = []
    for chunk in raw:
        for piece in chunk.split("\n"):
            t = clean(piece)
            if t and (not out or out[-1] != t):
                out.append(t)
    return out


def parse_date(s):
    """Return ISO yyyy-mm-dd. Month-only dates land on the 1st."""
    s = clean(s)
    if not s:
        return ""
    s = re.sub(r"^(Pub Date|Published|Publication date|Sales Date)\s*:?\s*", "", s, flags=re.I)
    s = re.sub(r"^\w+day,\s*", "", s)            # "Tuesday, 15 Sep 2026"
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    if m:
        return m.group(0)
    for fmt in ("%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%d %b %Y", "%d %B %Y",
                "%B %Y", "%b %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def money(s):
    m = re.search(r"\$\s?([\d,]+\.\d{2}|[\d,]+)", s or "")
    return f"${m.group(1)}" if m else ""


def pool_map(fn, items, workers=6, log=print, label=""):
    def guarded(item):
        """One bad record must not abandon a twenty-minute crawl."""
        try:
            return fn(item)
        except Exception as exc:                       # noqa: BLE001
            log(f"    ! {label} skipped one: {type(exc).__name__}: {exc}")
            return None

    done, total, out = 0, len(items), []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(guarded, items):
            done += 1
            if res:
                out.append(res)
            if done % 25 == 0 or done == total:
                log(f"    {label} {done}/{total}")
    return out


# --------------------------------------------------------------------------
# Blurbs
# --------------------------------------------------------------------------
#
# Every press but Harvard says who is doing the recommending; they just say it
# in four different places. Chicago pairs the quote with a sibling attribution
# paragraph, MIT uses a <cite> (sometimes prefixed with a tilde) or a trailing
# dash, and Yale and Princeton run the attribution inline after an em dash.
# Harvard publishes bare blockquotes with no credit at all.

# The last dash on the line, when what follows is short enough to be a name
# rather than the rest of a sentence.
_ATTR = re.compile(r"\s*[—–]\s*(?=[^\s—–][^—–]{2,120}$)")


def split_praise(text, by=""):
    """Return (quote, attribution) for one blurb."""
    t = clean(text)
    by = clean(by).lstrip("~").strip(" -–—")
    if not by:
        hits = list(_ATTR.finditer(t))
        if hits:
            cut = hits[-1]
            head, tail = t[:cut.start()], t[cut.end():]
            # A real attribution is a credit line, not another sentence.
            if len(head) > 40 and tail.count(". ") <= 1:
                t, by = head, tail
    return t.strip().strip('"“” ').strip(), by.strip(" .,")


def praise_pairs(items):
    """[{q, by}] from (quote_text, attribution_text) pairs."""
    out, seen = [], set()
    for q, a in items:
        if not q or len(clean(q)) < 40:
            continue
        quote, by = split_praise(q, a or "")
        if len(quote) > 40 and quote not in seen:
            seen.add(quote)
            out.append({"q": quote, "by": by})
    return out[:10]


def praise_from(panel):
    """Blurbs out of a reviews panel, whichever way the press stacked them.

    MIT gives one <blockquote> per endorsement, sometimes with a <cite>. Yale
    runs all of them into a single <blockquote> separated by <br><br>. Reading
    the <br>-separated segments handles both.
    """
    if panel is None:
        return []
    items = []
    for bq in panel.find_all("blockquote") or [panel]:
        cite = bq.find("cite")
        if cite:
            cite.extract()
        segments = blocks(bq)
        if len(segments) == 1:
            items.append((segments[0], clean(cite.get_text(" ")) if cite else ""))
        else:
            items += [(seg, "") for seg in segments]
    return praise_pairs(items)


# --------------------------------------------------------------------------
# Princeton — Algolia
# --------------------------------------------------------------------------

ALGOLIA_APP = "OWWQ1C6EL0"
ALGOLIA_KEY = "765bd59e29c51e402d1362e72981b1cf"
ALGOLIA_URL = (f"https://{ALGOLIA_APP.lower()}-dsn.algolia.net"
               "/1/indexes/books_published_date_desc/query")


def princeton_list(cutoff: date, horizon: date, log=print):
    """Walk the date-sorted index until most of a page is behind the cutoff."""
    out, page = {}, 0
    while page < 12:
        r = session.post(
            ALGOLIA_URL,
            headers={"X-Algolia-Application-Id": ALGOLIA_APP,
                     "X-Algolia-API-Key": ALGOLIA_KEY,
                     "Content-Type": "application/json"},
            data=json.dumps({"query": "", "hitsPerPage": 200, "page": page}),
            timeout=45)
        r.raise_for_status()
        hits = r.json().get("hits", [])
        if not hits:
            break
        past = 0
        for h in hits:
            ts = h.get("book_published_date_us")
            if not ts:
                continue
            d = datetime.utcfromtimestamp(ts).date()
            if d > horizon:                # placeholder dates parked in 2041
                continue
            if d < cutoff:
                past += 1
                continue
            key = h.get("work_ref_id") or str(h.get("book_isbn"))
            better = bool(h.get("book_primary_edition")) or h.get("book_type") == "Hardcover"
            prev = out.get(key)
            if prev is None or (better and not prev.get("_better")):
                h["_better"], h["_date"] = better, d.isoformat()
                out[key] = h
        log(f"    princeton page {page}: {len(out)} in window")
        if past > len(hits) * 0.6:
            break
        page += 1
    return list(out.values())


def princeton_detail(hit):
    """Algolia already carries the promo copy; the page adds praise and specs."""
    isbn = str(hit.get("book_isbn"))
    contribs = hit.get("contrib_full_name")
    if isinstance(contribs, str):
        contribs = [contribs]
    tag = BeautifulSoup(hit.get("book_tagline") or "", "lxml")
    ovr = BeautifulSoup(hit.get("book_overview") or "", "lxml")

    rec = {
        "press": "princeton",
        "isbn": isbn,
        "title": clean(hit.get("book_title")),
        "subtitle": clean(hit.get("book_subtitle")),
        "authors": ", ".join(dict.fromkeys(contribs or [])),
        "pub_date": hit.get("_date", ""),
        "url": f"https://press.princeton.edu/isbn/{isbn}",
        "cover": f"https://pup-assets.imgix.net/onix/images/{isbn}.jpg",
        "tagline": clean(tag.get_text(" ")),
        "description": "\n\n".join(blocks(ovr)),
        "bio": "",
        "praise": [],
        "subjects": list(dict.fromkeys(hit.get("subjects") or []))[:6],
        "series": clean(hit.get("series")),
        "format": clean(hit.get("book_type")),
        "formats": [],
        "pages": "",
        "price": "",
        "trim": "",
    }
    if not rec["title"]:
        return None

    r = get(rec["url"])
    if r is None:
        return rec

    s = soup(r.text)
    for junk in s.select("script, style, nav, footer"):
        junk.decompose()

    rec["url"] = r.url
    rec["bio"] = "\n\n".join(blocks(s.select_one(".m-authors"))[:5])
    rec["praise"] = praise_pairs(
        [(t, "") for t in blocks(s.select_one(".o-blocks--reviews"))])

    text = clean(s.get_text(" "))
    m = re.search(r"Pages:\s*(\d+)", text)
    rec["pages"] = m.group(1) if m else ""
    rec["price"] = money(text)
    formats = [f for f in ("Hardcover", "Paperback", "Audio")
               if re.search(rf"\b{f}\b", text)]
    if "ebook" in text.lower():
        formats.append("Ebook")
    rec["formats"] = sorted(set(formats))
    m = re.search(r"Size:\s*([\d.]+ x [\d.]+ in\.)", text)
    rec["trim"] = m.group(1) if m else ""
    return rec


# --------------------------------------------------------------------------
# Harvard — server-rendered, fetched with curl
# --------------------------------------------------------------------------

def harvard_list(log=print):
    """HUP's pager is 1-indexed — page=0 and page=1 both return the first 20."""
    isbns, page, dry = [], 1, 0
    while page < 40 and dry < 2:
        body = curl_cached(f"https://www.hup.harvard.edu/forthcoming-books?sort=date&page={page}",
                           f"list-{page}", log=log)
        if not body:
            break
        found = re.findall(r"/books/(97\d{11})", body)
        new = [i for i in dict.fromkeys(found) if i not in isbns]
        dry = 0 if new else dry + 1
        isbns.extend(new)
        log(f"    harvard page {page}: {len(isbns)} titles")
        page += 1
    return isbns


def harvard_detail(isbn):
    body = curl_cached(f"https://www.hup.harvard.edu/books/{isbn}", isbn)
    if not body:
        return None
    s = soup(body)

    # Subject links live in /browse/. The nav and footer repeat the five
    # top-level subjects on every page; a book's own subjects appear once.
    # Read them before the chrome is stripped out.
    labels = [clean(a.get_text()) for a in s.select('a[href*="/browse/"]')]
    counts = Counter(labels)
    subjects = list(dict.fromkeys(l for l in labels if l and counts[l] == 1))[:6]

    for junk in s.select("script, style, nav, footer"):
        junk.decompose()

    h1 = s.find("h1")
    title = clean(h1.get_text()) if h1 else ""
    if not title:
        return None

    # product header: <h1>title</h1><p.f-body-01>subtitle</p><p.f-body-01.text-secondary>author</p>
    head_ps = h1.find_all_next("p", class_="f-body-01", limit=4)
    author_p = next((p for p in head_ps if "text-secondary" in (p.get("class") or [])), None)
    sub_p = next((p for p in head_ps if p is not author_p), None)
    subtitle = clean(sub_p.get_text(" ")) if sub_p else ""
    authors = clean(author_p.get_text(" ")) if author_p else ""
    if not authors:
        a = s.select_one('[itemprop="author"]')
        authors = clean(a.get_text()) if a else ""

    intro = s.select_one('[data-component="editorial:intro"]')
    tagline = clean(intro.get_text(" ")) if intro else ""

    body_el = s.select_one('[data-component="editorial:wysiwyg"]')
    description = "\n\n".join(blocks(body_el))

    bio, praise, details = "", [], []
    for sec in s.select('[data-component="pdp:section"]'):
        head = sec.find(["h2", "h3", "h4"])
        label = clean(head.get_text()).lower() if head else ""
        if label.startswith("author"):
            bio = "\n\n".join(b for b in blocks(sec) if b.lower() != "author")
        elif label.startswith("book details"):
            details = [b for b in blocks(sec) if b.lower() != "book details"]
        elif any(label.startswith(k) for k in ("review", "praise", "award", "accolade")):
            # HUP prints the endorsements without saying who gave them.
            praise.extend({"q": b, "by": ""} for b in blocks(sec) if len(b) > 60)

    pages = next((m.group(1) for d in details
                  if (m := re.match(r"^(\d+) pages", d))), "")
    trim = next((d for d in details if "inches" in d), "")

    flat = clean(s.get_text(" "))
    pub = parse_date((re.search(r"Publication date:\s*([\d/]+)", flat) or [None, ""])[1])
    formats = [f for f in ("Hardcover", "Paperback", "Ebook", "Audiobook")
               if re.search(rf"\b{f}\b", flat)]

    return {
        "press": "harvard",
        "isbn": isbn,
        "title": title,
        "subtitle": subtitle,
        "authors": authors,
        "pub_date": pub,
        "url": f"https://www.hup.harvard.edu/books/{isbn}",
        "cover": f"https://www.hup.harvard.edu/img/feeds/jackets/{isbn}.png?fm=jpg&q=80&fit=max&w=600",
        "tagline": tagline,
        "description": description,
        "bio": bio,
        "praise": praise[:8],
        "subjects": subjects,
        "series": "",
        "format": formats[0] if formats else "",
        "formats": formats,
        "pages": pages,
        "price": money(flat),
        "trim": trim,
    }


# --------------------------------------------------------------------------
# Yale and MIT — Supafolio, identical templates
# --------------------------------------------------------------------------

SUPA = {
    "yale": {"list": "https://yalebooks.yale.edu/search-results-list/",
             "site": "https://yalebooks.yale.edu",
             "cover": "https://yale-press-us.imgix.net/covers/{isbn}.jpg"},
    "mit":  {"list": "https://mitpress.mit.edu/search-result-list/",
             "site": "https://mitpress.mit.edu",
             "cover": "https://mit-press-new-us.imgix.net/covers/{isbn}.jpg"},
}


def supa_list(press, cutoff: date, horizon: date, amount=400, log=print):
    cfg = SUPA[press]
    r = get(f"{cfg['list']}?keyword=&order=publishdate-desc&amount={amount}")
    if r is None:
        return []
    s = soup(r.text)
    rows, seen = [], set()
    for wrap in s.select("div.book-wrapper"):
        def pick(sel):
            el = wrap.select_one(sel)
            return clean(el.get_text(" ")) if el else ""

        isbn = re.sub(r"\D", "", pick(".sp__the-isbn13"))
        a = wrap.select_one("a[href]")
        href = a["href"] if a else ""
        if not isbn:
            m = re.search(r"(97\d{11})", href)
            isbn = m.group(1) if m else ""
        if not isbn or isbn in seen:
            continue

        raw = (pick(".sp__the-sales-date").replace("Sales Date:", "")
               or pick(".sp__the-publication-date").replace("Pub Date:", ""))
        pub = parse_date(raw)
        if not pub:
            continue
        d = date.fromisoformat(pub)
        if d < cutoff or d > horizon:
            continue
        seen.add(isbn)
        rows.append({
            "press": press,
            "isbn": isbn,
            "url": (cfg["site"] + href) if href.startswith("/") else href,
            "title": pick("h3.sp__the-title") or pick(".sp__the-title"),
            "subtitle": pick(".sp__the-subtitle"),
            "authors": re.sub(r"^by\s+", "", pick(".sp__the-author"), flags=re.I),
            "pub_date": pub,
            "pages": re.sub(r"\D", "", pick(".sp__the-pages")),
            "price": money(pick(".sp__the-price")),
            "summary": pick(".sp__the-summary"),
            "series": pick(".sp__the-series").replace("Series:", "").strip(),
            "cover": cfg["cover"].format(isbn=isbn),
        })
    log(f"    {press}: {len(rows)} in window")
    return rows


def supa_detail(row):
    r = get(row["url"])
    if r is None:
        return None
    s = soup(r.text)
    for junk in s.select("script, style"):
        junk.decompose()

    # These templates open the description with the marketing hook in bold,
    # then the jacket copy. Lift the hook out so it can be set as a pull quote
    # instead of being printed twice.
    desc_el = s.select_one(".tabs__panel--description")
    lead = desc_el.find(["strong", "b"]) if desc_el else None
    hook = clean(lead.get_text(" ")) if lead else ""
    if not (20 < len(hook) < 400):
        hook = ""

    desc = blocks(desc_el)
    if not desc and row.get("summary"):
        desc = [row["summary"]]
    if not hook and desc and len(desc[0]) < 300:
        hook = desc[0]
    tagline = hook
    desc = [p for p in desc if p != hook and not p.startswith(hook[:60] or "\0")]

    bio = "\n\n".join(blocks(s.select_one(".tabs__panel--authors"))[:5])
    praise_el = (s.select_one(".tabs__panel--reviews")
                 or s.select_one(".tabs__panel--praise"))
    praise = praise_from(praise_el)

    crumbs = [clean(a.get_text()) for a in s.select(".book-wrapper__breadcrumbs a")]
    subjects = [c.title() if c.islower() else c for c in crumbs
                if c.lower() not in ("home", "books", "")][:6]

    formats = list(dict.fromkeys(
        clean(e.get_text()) for e in s.select(".sp__format") if clean(e.get_text())))
    trim = s.select_one(".sp__the-trim-size")

    out = dict(row)
    out.pop("summary", None)
    out.update({
        "tagline": tagline,
        "description": "\n\n".join(desc),
        "bio": bio,
        "praise": praise,
        "subjects": subjects,
        "format": formats[0] if formats else "",
        "formats": formats[:5],
        "trim": clean(trim.get_text()) if trim else "",
    })
    return out
