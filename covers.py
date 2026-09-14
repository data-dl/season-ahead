"""Cache every jacket as a small WebP data URI in data/covers.json.

The hosted copy of the dashboard cannot load images from the presses' own
CDNs, so the jackets have to travel inside the page. At 96px they cost about
2.2 KB each and stay crisp at the size the list draws them; the reading pane
asks the press for a full-resolution jacket on top and quietly falls back to
this one when it cannot have it.

Incremental: only ISBNs missing from the cache are fetched, so a refresh that
adds thirty titles costs thirty requests, not eleven hundred.
"""

from __future__ import annotations

import base64
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

import presses as P

HERE = Path(__file__).resolve().parent
BOOKS = HERE / "data" / "books.json"
CACHE = HERE / "data" / "covers.json"

WIDTH = 96
QUALITY = 58
# Some presses serve a house placeholder for titles without a jacket yet.
# They are all but identical, so anything that encodes this small is one.
PLACEHOLDER_BYTES = 700


def fetch_one(book):
    key = book["press"] + ":" + book["isbn"]
    # Chicago records carry their own URL, since its jacket paths are keyed by
    # an ISBN that is not always the one you buy.
    tpl = P.PRESSES[book["press"]].get("cover") or ""
    url = book.get("cover") or (
        tpl.replace("{isbn}", book["isbn"]).replace("{w}", "300") if tpl else "")
    if not url:
        return key, None
    r = P.get(url, tries=2)
    if r is None or not r.headers.get("content-type", "").startswith("image"):
        return key, None
    try:
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:                                        # noqa: BLE001
        return key, None
    if im.width < 40 or im.height < 40:
        return key, None
    im.thumbnail((WIDTH, WIDTH * 3), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=QUALITY, method=6)
    data = buf.getvalue()
    if len(data) < PLACEHOLDER_BYTES:
        return key, None
    return key, "data:image/webp;base64," + base64.b64encode(data).decode("ascii")


def main():
    if not BOOKS.exists():
        print("no data yet — run scrape.py first")
        return 1
    books = json.loads(BOOKS.read_text(encoding="utf-8"))["books"]

    cache = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    live = {b["press"] + ":" + b["isbn"] for b in books}
    dropped = [k for k in cache if k not in live]
    for k in dropped:
        del cache[k]

    todo = [b for b in books if (b["press"] + ":" + b["isbn"]) not in cache]
    print(f"{len(cache)} cached, {len(dropped)} dropped, {len(todo)} to fetch")

    done = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        for key, uri in ex.map(fetch_one, todo):
            done += 1
            cache[key] = uri            # None records "this press has no jacket"
            if done % 50 == 0 or done == len(todo):
                print(f"    {done}/{len(todo)}")

    CACHE.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    have = sum(1 for v in cache.values() if v)
    size = sum(len(v) for v in cache.values() if v) / 1e6
    print(f"{have} jackets of {len(cache)} titles, {size:.1f} MB -> {CACHE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
