"""Pull the forthcoming lists from all five presses into data/books.json.

Window runs from 30 days back (so titles that landed last month still show as
"Just out") to 13 months ahead, which is as far as any of them have announced.
Run it again whenever you want fresh data; it is idempotent.

    python scrape.py                  every press
    python scrape.py chicago yale     only those, the rest kept from last run
    python scrape.py --retidy         re-run the cleanup over what is on disk
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import chicago as C
import presses as P

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "books.json"

BACK_DAYS = 30
AHEAD_DAYS = 400


# Each press keeps its own subject vocabulary. These buckets let one filter
# span all five. First match wins, so the order matters.
TOPIC_RULES = [
    ("Classics",            r"classic|ancient greek|ancient rome|ancient world|ancient histor|hellenis|latin literature"),
    ("Art & Architecture",  r"art|architect|photograph|design|museum|visual|craft"),
    ("History",             r"history|historical|medieval|ancient|antiquit|renaissance|war|empire|civil"),
    ("Philosophy",          r"philosoph|ethic|logic|metaphys|aesthetic"),
    ("Religion",            r"religio|theolog|bible|biblical|islam|jewish|judaism|buddh|christian"),
    ("Politics & Law",      r"politic|law|legal|government|constitut|public policy|internation|justice"),
    ("Economics & Business", r"econom|business|finance|financ|market|labor|labour|trade|management"),
    ("Science & Nature",    r"science|scien|biolog|physic|chemis|astronom|nature|environment|climate|ecolog|earth|geolog|evolution"),
    ("Technology & Computing", r"comput|technolog|engineer|artificial intelligence|\bai\b|data|robot|digital|information|software|internet|cyber"),
    ("Mind & Behaviour",    r"psycholog|neuro|cognitive|mind|brain|behavio"),
    ("Society & Culture",   r"sociolog|anthropolog|cultur|social|gender|race|media|urban|education|geograph|food"),
    ("Literature",          r"literat|poetry|poem|fiction|literary|language|linguist|writing|criticism"),
    ("Music & Performance", r"music|theat|theatre|dance|film|cinema|performance"),
    ("Life & Memoir",       r"biograph|memoir|autobiograph|letters|lives"),
    ("Mathematics",         r"mathemat|statis|probabilit|geometr|algebra"),
]


def topic_of(subjects, title, tagline):
    """Bucket a book by the press's *primary* subject where there is one.

    Each press lists subjects most-important first, so testing them in their
    own order beats matching against one big string, where whichever rule
    happens to sit highest wins.
    """
    for subject in subjects:
        low = subject.lower()
        for name, pat in TOPIC_RULES:
            if re.search(pat, low):
                return name
    hay = f"{title} {tagline}".lower()
    for name, pat in TOPIC_RULES:
        if re.search(pat, hay):
            return name
    return "Other"


# Words that mark an attribution as a publication rather than a person.
OUTLET = re.compile(
    r"\b(reviews?|times|journal|magazine|weekly|monthly|quarterly|post|guardian"
    r"|telegraph|standard|observer|spectator|economist|nature|scientist|herald"
    r"|tribune|gazette|bulletin|press|radio|bbc|npr|news|booklist|kirkus"
    r"|publishers|foreword|choice|supplement|atlantic|harper|nation|republic"
    r"|yorker|books|literary|library|wire|daily|sunday|week|blog|podcast)\b",
    re.I)
# Two to five capitalised words, allowing initials and the usual particles.
PERSON = re.compile(
    r"^(?:[A-Z][\w.'’-]*|van|von|de|del|della|di|da|du|la|le|bin|al)"
    r"(?:\s+(?:[A-Z][\w.'’-]*|van|von|de|del|della|di|da|du|la|le|bin|al)){1,4}$")


def normalise_blurb(p):
    """One blurb as {q, by, who, cred, kind}.

    `by` is what the press printed. `who` is the endorser on their own —
    the name if a person recommended the book, the publication if a review
    did — which is what makes them countable across the whole list.
    """
    if isinstance(p, str):                       # data from an older run
        p = {"q": p, "by": ""}
    q, by = P.clean(p.get("q")), P.clean(p.get("by"))
    if len(q) < 50:
        return None

    who, cred, kind = "", "", ""
    if by:
        head, _, tail = by.partition(",")
        head, tail = head.strip(), tail.strip()
        if PERSON.match(head) and not OUTLET.search(head):
            who, cred, kind = head, tail, "person"
        else:
            who, cred, kind = by if not tail else head, tail, "outlet"
    return {"q": q, "by": by, "who": who, "cred": cred, "kind": kind}


def normalise(rec):
    """Trim, tidy and derive the fields the dashboard actually reads."""
    rec = dict(rec)
    for k in ("title", "subtitle", "authors", "tagline", "series", "format",
              "pages", "price", "trim", "bio", "description"):
        rec[k] = P.clean(rec.get(k, "")) if k not in ("bio", "description") else (rec.get(k) or "")

    # Multi-author bylines are read out of separate links, which leaves a space
    # in front of the separator: "Adam G. Riess , Donald Goldsmith".
    rec["authors"] = re.sub(r"\s+([,;])", r"\1", rec["authors"])

    # A few presses fold the subtitle into the title with a colon.
    if not rec["subtitle"] and ":" in rec["title"]:
        head, _, tail = rec["title"].partition(":")
        if 3 < len(head) < 70 and len(tail) > 3:
            rec["title"], rec["subtitle"] = head.strip(), tail.strip()

    # The hook is set as a pull quote above the jacket copy, so it must not
    # also open the copy itself. Presses vary in whether they repeat it.
    if rec["tagline"] and rec["description"]:
        paras = [p for p in rec["description"].split("\n\n") if p.strip()]
        head = rec["tagline"][:60]
        paras = [p for p in paras if p != rec["tagline"] and not p.startswith(head)]
        rec["description"] = "\n\n".join(paras)

    rec["subjects"] = [P.clean(s) for s in (rec.get("subjects") or []) if P.clean(s)]
    rec["praise"] = [b for b in (normalise_blurb(p) for p in (rec.get("praise") or [])) if b]
    rec["formats"] = [P.clean(f) for f in (rec.get("formats") or []) if P.clean(f)]

    # Prefer a physical format as the headline one; "eBook" first reads oddly.
    order = {"Hardcover": 0, "Cloth": 0, "Paperback": 1, "Trade Paperback": 1,
             "Audio": 3, "Audiobook": 3}
    if rec["formats"]:
        rec["format"] = sorted(rec["formats"], key=lambda f: order.get(f, 2))[0]

    rec["topic"] = topic_of(rec["subjects"], rec["title"], rec["tagline"])
    rec["word_count"] = len(rec["description"].split()) if rec["description"] else 0
    rec["has_praise"] = bool(rec["praise"])

    # Only Chicago distributes for other houses; everyone else publishes its own.
    rec["own_list"] = bool(rec.get("own_list", True))
    rec["distributor"] = P.clean(rec.get("distributor", ""))

    # What the press has actually spent on this title so far. Blurbs are the
    # expensive part — a house solicits endorsements only for books it intends
    # to push — then the length of the jacket copy, then whether anyone wrote
    # an author note.
    rec["endorsers"] = [b["who"] for b in rec["praise"] if b["kind"] == "person"]
    rec["outlets"] = [b["who"] for b in rec["praise"] if b["kind"] == "outlet"]

    rec["push"] = (2.0 * min(len(rec["praise"]), 5)
                   + min(rec["word_count"], 400) / 100.0
                   + (0.5 if rec["bio"] else 0.0))
    return rec


def canonicalise_outlets(books):
    """Settle on one spelling per publication.

    Presses cite the same outlet several ways — "Choice" and "Choice Reviews",
    "New Yorker" and "The New Yorker" — which splits a name that should be one
    row in the endorser list. Group on a loosened key, then adopt whichever
    spelling the presses used most. A starred review stays its own entry,
    because that is a stronger signal than a plain one.
    """
    def key(name):
        k = name.lower().strip()
        k = re.sub(r"^the\s+", "", k)
        k = re.sub(r"\s*\(\s*star(?:red)?\s+review\s*\)", " (starred review)", k)
        k = re.sub(r"\s+reviews?(?=$| \()", "", k)
        return re.sub(r"[.,]", "", k).strip()

    counts = {}
    for b in books:
        for w in set(b["outlets"]):
            counts.setdefault(key(w), {}).setdefault(w, 0)
            counts[key(w)][w] += 1
    best = {k: max(v.items(), key=lambda kv: (kv[1], -len(kv[0])))[0]
            for k, v in counts.items()}

    for b in books:
        for blurb in b["praise"]:
            if blurb["kind"] == "outlet" and blurb["who"]:
                blurb["who"] = best.get(key(blurb["who"]), blurb["who"])
        b["outlets"] = list(dict.fromkeys(
            best.get(key(w), w) for w in b["outlets"]))
    return books


def mark_lead_titles(books, share=0.10):
    """Flag the titles each press is pushing hardest in each month.

    Ranking on raw effort would just surface whatever publishes soonest, since
    blurbs accumulate as publication approaches and a book eighteen months out
    has none yet. Comparing each title only against its own press in its own
    month takes that bias out, so a May 2027 book with two endorsements can
    outrank a September title with three.
    """
    # Chicago's own list is bucketed apart from the houses it distributes for,
    # so its own books are not crowded out by a much larger distributed pile.
    buckets = {}
    for b in books:
        buckets.setdefault((b["press"], b.get("own_list", True), b["pub_date"][:7]), []).append(b)
    for group in buckets.values():
        group.sort(key=lambda b: (-b["push"], -b["word_count"], b["title"]))
        n = max(1, round(len(group) * share))
        for i, b in enumerate(group):
            b["lead"] = i < n and b["push"] > 0
    return books


def main(only=None, retidy=False):
    started = time.time()
    today = date.today()
    cutoff = today - timedelta(days=BACK_DAYS)
    horizon = today + timedelta(days=AHEAD_DAYS)
    log = print
    wanted = set() if retidy else set(only or P.PRESSES)

    log(f"University press radar — window {cutoff} .. {horizon}")
    if only:
        log(f"only: {', '.join(sorted(wanted))}")
    log("")
    books = []

    # keep the presses we are not re-fetching this run
    if (only or retidy) and OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
        books += [b for b in old["books"] if b["press"] not in wanted]
        log(f"keeping {len(books)} titles from the last run"
            f"{' — re-tidying only, no fetching' if retidy else ''}\n")
        if retidy:
            cutoff = date.fromisoformat(old["window"]["from"])
            horizon = date.fromisoformat(old["window"]["to"])

    if "princeton" in wanted:
        log("Princeton (Algolia)")
        hits = P.princeton_list(cutoff, horizon, log=log)
        books += P.pool_map(P.princeton_detail, hits, workers=6, log=log, label="princeton")

    if "harvard" in wanted:
        log("\nHarvard (curl, serialised and spaced out — this is the slow one)")
        isbns = P.harvard_list(log=log)
        # Serialised inside presses.curl, so extra workers would only queue up.
        books += P.pool_map(P.harvard_detail, isbns, workers=1, log=log, label="harvard")

    for press in ("yale", "mit"):
        if press not in wanted:
            continue
        log(f"\n{press.title()} (Supafolio)")
        rows = P.supa_list(press, cutoff, horizon, amount=400, log=log)
        books += P.pool_map(P.supa_detail, rows, workers=6, log=log, label=press)

    if "chicago" in wanted:
        log("\nChicago (subject index, 1 request every 2s per robots.txt)")
        rows = C.listing(cutoff, horizon, log=log)
        # Serialised inside chicago.get, so extra workers would only queue up.
        books += P.pool_map(C.detail, rows, workers=1, log=log, label="chicago")
        C.save_details()

    log("\nTidying")
    books = [normalise(b) for b in books if b and b.get("title")]

    # Harvard's forthcoming list is not date-filtered at source
    books = [b for b in books if b.get("pub_date")
             and cutoff.isoformat() <= b["pub_date"] <= horizon.isoformat()]

    canonicalise_outlets(books)
    mark_lead_titles(books)

    seen, unique = set(), []
    for b in sorted(books, key=lambda b: (b["pub_date"], b["title"])):
        key = (b["press"], b["isbn"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)

    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "window": {"from": cutoff.isoformat(), "to": horizon.isoformat(),
                   "today": today.isoformat()},
        "presses": P.PRESSES,
        "books": unique,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    by_press = {}
    for b in unique:
        by_press[b["press"]] = by_press.get(b["press"], 0) + 1
    log(f"\n{len(unique)} titles in {time.time() - started:.0f}s -> {OUT}")
    for k, v in sorted(by_press.items()):
        withdesc = sum(1 for b in unique if b["press"] == k and b["word_count"] > 30)
        praise = sum(1 for b in unique if b["press"] == k and b["has_praise"])
        log(f"   {k:<10} {v:>4}   {withdesc:>4} with description   {praise:>4} with praise")
    return 0


if __name__ == "__main__":
    # `python scrape.py harvard yale` refreshes only those, keeping the rest.
    # `python scrape.py --retidy` re-runs the cleanup over what is on disk.
    args = sys.argv[1:]
    sys.exit(main(only=[a for a in args if a in P.PRESSES] or None,
                  retidy="--retidy" in args))
