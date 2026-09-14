"""Fill data/hup_cache one page at a time, however long it takes.

Harvard's WAF lets a few dozen page loads through, then serves a challenge to
everything for a while. Rather than hammer it, this walks the forthcoming list
in small batches with a long rest between them, and keeps every page it gets.
It is safe to stop and start again: anything already cached is skipped, so a
later run only fetches what is still missing.

    python harvest_harvard.py            # until the list is complete
    python harvest_harvard.py --once     # one batch, then stop
"""

from __future__ import annotations

import re
import sys
import time
from datetime import datetime

import presses as P

BATCH = 20            # pages to try before resting
REST = 420            # seconds to rest between batches
MAX_ROUNDS = 40


def stamp():
    return datetime.now().strftime("%H:%M:%S")


def main(once=False):
    isbns = P.harvard_list(log=lambda m: print(f"[{stamp()}] {m}", flush=True))
    if not isbns:
        print(f"[{stamp()}] could not read the forthcoming list at all — "
              f"Harvard is blocking; try again later", flush=True)
        return 1
    print(f"[{stamp()}] {len(isbns)} titles on the forthcoming list", flush=True)

    for rnd in range(MAX_ROUNDS):
        missing = [i for i in isbns
                   if not (P.HUP_CACHE / f"{i}.html").exists()
                   or (P.HUP_CACHE / f"{i}.html").stat().st_size <= 2000]
        have = len(isbns) - len(missing)
        print(f"[{stamp()}] round {rnd + 1}: {have}/{len(isbns)} cached, "
              f"{len(missing)} to go", flush=True)
        if not missing:
            print(f"[{stamp()}] complete", flush=True)
            return 0

        got = blocked = 0
        for isbn in missing[:BATCH]:
            body = P.curl_cached(f"https://www.hup.harvard.edu/books/{isbn}", isbn, tries=1)
            if body and re.search(r"<h1", body):
                got += 1
            else:
                blocked += 1
                if blocked >= 3:        # the door has shut; stop knocking
                    break
        print(f"[{stamp()}] batch: {got} fetched, {blocked} refused", flush=True)

        if once:
            return 0
        P.HUP_DELAY[0] = 2.0            # a rest resets the pacing
        rest = REST if blocked else 60
        print(f"[{stamp()}] resting {rest}s", flush=True)
        time.sleep(rest)

    print(f"[{stamp()}] gave up after {MAX_ROUNDS} rounds", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main(once="--once" in sys.argv[1:]))
