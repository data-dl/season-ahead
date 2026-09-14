# Notes for whoever builds this next

Everything here is in `0 - The Season Ahead.html` and `books.json`. This file is
the part that is not in either: how each press was actually got at, what took
the longest to work out, and where this build is weak. Take any of it.

## The five presses, and how to read them

None of the five publishes a forthcoming feed. Each needed a different way in,
and four of the five turned out to have one that is far better than scraping
listing pages.

**Princeton — an Algolia index, wide open.** `press.uchicago`-style scraping is
unnecessary. The site's own search box is Algolia, and `drupalSettings` on any
page carries `pup_algolia.appId` and `apiKey` (a public search key). There is a
replica index called `books_published_date_desc`, and its records already
contain `book_overview` — the entire jacket copy — plus tagline, subtitle,
subjects, series, contributors and a `book_published_date_us` timestamp. One
POST returns 200 complete books. This is by far the cheapest source of the five;
only blurbs and page counts need the detail page. Canonical URLs come from
`press.princeton.edu/isbn/<isbn>`, which redirects.

**Yale and MIT — the same software.** Both run Supafolio on the same WordPress
theme, so one parser covers both. The listing endpoints are
`yalebooks.yale.edu/search-results-list/` and
`mitpress.mit.edu/search-result-list/`, and the useful part is that `amount=` is
uncapped: `?keyword=&order=publishdate-desc&amount=400` returns four hundred
records in one request, each with ISBN, title, subtitle, author, pub date, page
count and price. Detail pages then give description / authors / reviews as three
`.tabs__panel--*` blocks. MIT sits behind a WAF that rejects a bare
`User-Agent`; send a full browser header set (see `presses.py: HEADERS`) and it
is fine. Yale does not care.

**Harvard — slow, and there is no way around it.** `hup.harvard.edu` is behind
an AWS WAF that returns HTTP 202 with a JavaScript challenge page once you have
read a few dozen pages, then needs several minutes of quiet. Two things worth
knowing: it rejects `python-requests` on TLS fingerprint alone while accepting
`curl` for the same URL, and its *image* host is not gated at all, so jackets
fetch normally at full concurrency. The forthcoming list is
`/forthcoming-books?sort=date&page=N`, **1-indexed** — `page=0` and `page=1`
both return the first twenty, which will silently cost you a page if you assume
otherwise. 88 titles over 5 pages. Detail pages are clean:
`[data-component="editorial:intro"]` is the hook,
`editorial:wysiwyg` the copy, and each `pdp:section` is headed Author / Book
Details / Reviews. Subjects are `/browse/` links, but the nav repeats five of
them on every page — the book's own are the ones appearing exactly once.
`harvest_harvard.py` reads in batches with a seven-minute rest and caches every
page to `data/hup_cache`, so it survives being interrupted. Half an hour cold.

**Chicago — the whole catalogue is sitting in the HTML.** This was the good
find. There is no forthcoming feed, but every browse-by-subject page under
`/ucp/books/subject/` contains `books = eval([{...}])` with a complete record
per book: title, author, publisher, jacket path, `pubDate` as an epoch, and a
`ucp` boolean. Walking the 256 subject pages listed on `/books/subject.html`
and merging on URL reconstructs all **22,945 titles** — the entire catalogue,
including the 14,611 they distribute for other houses — after which
"forthcoming" is just a date filter. `robots.txt` asks for `Crawl-delay: 2`.
Two traps: the detail page lists **recommended titles' ISBNs too**, so take the
ISBN from the listing's own basket link (`buy` field, `?ISBN=`) or from the
jacket filename — reading the first ISBN off the page got 133 of 756 wrong here
before it was caught. And prices and formats are never in the HTML; the cart
loads them separately.

## Getting the endorsers out of the blurbs

Worth knowing before you try: **four of the five presses credit their
endorsements, and each does it somewhere different.** Chicago pairs a
`blockquote.blockquote-review` with a sibling `p.blockquote-review-attribution`.
MIT gives one `<blockquote>` per endorsement, the attribution either in a
`<cite>` (prefixed with a tilde) or inline after a dash. Yale runs *every*
endorsement into a single `<blockquote>` separated by `<br><br>`, so you have
to split on the line breaks before you split on the dash — miss that and Yale
yields one enormous blurb instead of ten. Princeton runs it inline after an
em dash.

**Harvard credits nobody.** Its praise sections are bare `<blockquote>`s with
no `cite`, `footer` or trailing attribution anywhere in the markup, on all 37
of its blurbed titles. That is a publishing decision, not a scraping problem.

The one trap in splitting an inline attribution: quotes contain em dashes too.
Take the *last* dash on the line and only accept what follows if it is short
enough to be a credit line and not another sentence. That gets 90 % of 3,590
blurbs credited. Sorting the result into people and publications is then a
name-shape test plus a list of outlet words — see `normalise_blurb` and
`canonicalise_outlets` in `scrape.py`; the second exists because presses cite
the same outlet several ways ("Choice" and "Choice Reviews") and it splits one
row into two if you do not settle on a spelling.

## Two things that took longer to get right than they look

**The subject taxonomy.** Five presses, five vocabularies, and the obvious
approach — join a book's subjects into one string and run rules over it — gives
a badly skewed result, because whichever rule sits highest wins for every book.
Testing each subject *in the press's own order* and taking the first rule that
matches any one of them is much better: it respects the press's own idea of the
book's primary subject. That one change moved History from 298 to 132 and
Society & Culture from 19 to 78.

**Ranking by promotional effort.** Blurbs are the honest signal — a house
solicits endorsements only for books it means to push — but ranking on them
raw just surfaces whatever publishes soonest, because blurbs accumulate as
publication nears and a book eighteen months out has none. Bucketing each title
against its own press in its own publication month removes that, and Chicago's
own list is bucketed apart from its distributed pile so it is not crowded out.
See `mark_lead_titles` in `scrape.py`.

## Where this build is weak

Genuinely, not as false modesty:

- **The endorser list is not disambiguated.** Two different people with the
  same name merge; one person cited as "J. Smith" and "John Smith" splits.
  With 2,575 names the tail is long and largely unchecked.
- **"Lead titles" measures effort, not quality**, and the 10 % cut-off is
  arbitrary at the boundary — a book with 8 blurbs and 248 words of copy can
  fall out while one with 8 blurbs and 298 words stays in. A better version
  would use blurb *source* prestige, or the seasonal catalogue's page order.
- **The seasonal catalogue PDFs are the real lead-title signal and I did not
  use them.** Chicago publishes `F26_Chicago_FINAL.pdf` and the others have
  equivalents; front-of-catalogue position is precisely the marketing hierarchy
  this build only approximates. Parsing ISBNs in page order would beat any
  heuristic here. I judged it too fragile and press-specific to be worth it,
  but that is a defensible call rather than an obviously right one.
- **No author disambiguation.** Authors are strings. There is no way to ask
  "what else has this person written" or to follow one across presses.
- **No prices for Chicago**, and formats are inconsistent between presses —
  Yale reports every edition, Harvard reports the ones it sells directly.
- **Princeton's 459 includes paperback reissues and new editions.** They are
  genuinely forthcoming editions, but a reader looking for new books will
  find some old ones. Deduplicating by work rather than edition would fix it;
  `work_ref_id` is in the Algolia record and is only partly used.
- **The window is fixed at −30/+400 days.** Beyond about fourteen months the
  presses have announced little and the copy is thin, so the far end of the
  list is much emptier than the near end.
- **Nothing is verified against a second source.** If a press's own page is
  wrong, this is wrong the same way.

## Things that would obviously improve it

- The catalogue PDFs, as above.
- Review coverage from outside the presses — a title that has been reviewed in
  the *TLS* or *LRB* is a stronger signal than any number of jacket blurbs, and
  none of that is here.
- Series awareness. A new volume in a series the reader already follows is more
  interesting than a random monograph, and every press exposes series names.
- Author following, once authors are entities rather than strings.
- More presses. Columbia, Oxford, Cambridge and California all publish on this
  scale, and two of them run the same Supafolio software as Yale and MIT, so
  the existing parser would cover them nearly unchanged.

## What is in this folder

| File | |
|---|---|
| `0 - The Season Ahead.html` | The dashboard, self-contained, 9.7 MB |
| `books.json` | The 1,826 records behind it, a snapshot of 8 September 2026 |
| `data/picks.json` (in source) | A hand-written reading list, `"press:isbn": "why"` |
| `README.md` | What it does and how to use it |
| `Source and scripts` | Shortcut to the scrapers and the build |

`books.json` is offered so this does not have to be crawled again from cold —
Harvard and Chicago together are about an hour of deliberately slow requests,
and their servers do not need it twice.
