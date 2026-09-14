# The Season Ahead

Every book five university presses — Chicago, Harvard, MIT, Princeton and Yale — have
announced for the coming year, merged into one searchable page with each press's own jacket
copy, every blurb credited to the person or outlet that gave it, the author note and the
specifications. **1,826 titles, 3,590 blurbs, 1,451 jackets, one 10 MB file** that needs no
server and no internet.

**Live page:** https://data-dl.github.io/season-ahead/ · **the data:** [`data/books.json`](data/books.json)

The point: a seasonal catalogue tells you what is coming, but there are five of them, they are
PDFs, and you cannot search inside them. This is the five lists merged, sorted by publication
date, and searchable down to the last sentence of jacket copy — *cleopatra* returns the Yale
biography and a Princeton book that only mentions her three paragraphs into the description.

    Chicago  237 own + 519 distributed    Princeton  459
    Yale     275                          MIT        249        Harvard  88

## How it was built

None of the five presses publishes a forthcoming feed. Each needed a different way in, and
four of the five turned out to have one far better than scraping listing pages
([docs/NOTES.md](docs/NOTES.md) has the full account):

| Press | Source | How |
|---|---|---|
| Princeton | the public Algolia index its own search box queries | one POST returns 200 complete records, jacket copy included |
| Yale, MIT | Supafolio storefronts on the same theme | `amount=` is uncapped, so the whole window arrives in one request; one parser covers both |
| Harvard | plain server-rendered pages behind an AWS firewall | serves a challenge page after a few dozen loads, then needs a seven-minute rest — `harvest_harvard.py` reads in small batches, caches every page and resumes |
| Chicago | no feed, but every browse-by-subject page embeds its whole listing as JSON with publication timestamps | walking the 256 subject pages once reconstructs all ~23,000 titles; the forthcoming slice is a filter |

Two problems shaped the page more than the harvesting:

- **Chicago distributes for about a hundred other houses**, and in this window those 519
  titles would outnumber Chicago's own 237 three to two. They sit behind an *…and distributed*
  toggle, off by default, each naming the house it belongs to.
- **Ranking "lead titles" fairly.** A press solicits endorsements only for books it means to
  push, so blurbs are the honest signal of promotional effort — but they accumulate as
  publication nears, and a raw ranking would only surface whatever publishes soonest. Each
  title is therefore ranked only against its own press in its own publication month, and the
  top tenth of each bucket is flagged. A May 2027 book with two endorsements can outrank a
  September book with three.

Blurb attribution is the other detail: four presses credit endorsements, each in a different
place in the markup (a sibling attribution element, a `<cite>`, one blockquote per book split
by `<br><br>`, an inline em dash). Harvard credits nobody — bare blockquotes, a publishing
decision — so its praise shows without a name. Nine in ten blurbs end up credited, and the rail
lets you browse by endorser: *Kirkus* on 42 titles, one science writer on five across two presses.

## The page

Three panes. **Left** — shelves, presses, the season (one row per publication month), subject,
and *Recommended by* (2,575 named endorsers, 223 review outlets). **Middle** — the list, grouped
by month, with the press colour, the title, how far off publication is, blurb count and extent.
**Right** — the whole promotional apparatus for one book: hook, jacket copy, every blurb, author
note, specifications, and a link through to the press for pre-ordering. Keyboard: `/` search,
`j`/`k` move, `Esc` closes the pane on a narrow screen. Jackets travel inside the file as small
WebP data URIs because a hosted page cannot fetch images from the presses' servers; 376 titles
with no jacket posted yet draw a typographic one in the press's colour.

`data/picks.json` is a hand-written reading list (`"press:isbn": "why"`) merged in as the
*Editor's picks* shelf — an opinion, not a score.

## Rebuilding

```bash
python scrape.py                # all five presses (15-20 min cold; Harvard is the slow one)
python scrape.py yale mit       # only some of them; the rest are kept from the last run
python covers.py                # fetch jackets for anything new -> data/covers.json
python build.py                 # data/*.json -> dist/the-season-ahead.html
```

`data/hup_cache/` (Harvard pages), `data/uc_index.json` and `data/uc_details.json` (Chicago's
catalogue index and parsed records) are caches the harvesters rebuild; they are not committed.
`data/books.json`, `data/covers.json` and `data/picks.json` are, so `build.py` runs from a clone.

## Known limits

- Harvard contributes fewest titles (88) because that is how long its public forthcoming list is.
- Chicago has no prices or formats; its cart loads them client-side after the page arrives.
- Princeton's count includes new editions and paperback reissues, because its feed does.
- Subjects are derived: each press uses its own vocabulary, so a rule set maps them onto
  fifteen shared buckets; the press's own terms are shown in full in the specifications block.
- Blurbs are thin for the furthest-out titles, which is the world rather than a hole in the data.

## Provenance

Built in September 2026 with an AI coding assistant as pair programmer, as one of two parallel
builds from the same brief; the harvesting strategy, the ranking rule and the picks are mine.
Data belongs to the presses and is reproduced here for reading and search. MIT licensed.
