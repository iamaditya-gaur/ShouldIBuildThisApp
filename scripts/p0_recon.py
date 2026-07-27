"""
p0_recon.py — verify every Apple endpoint before anything depends on it.

Run this first, and re-run it any time the pipeline starts behaving oddly.
Apple's endpoints are mostly undocumented and change without notice; this
script is the difference between "the niche has no demand" and "the endpoint
moved last Tuesday".

    python scripts/p0_recon.py

It deliberately does NOT use the cache. Recon that reads yesterday's cached
answer is not recon.
"""

from __future__ import annotations

import json
import plistlib
import sys
import time
import urllib.parse
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (UA_BROWSER, UA_ITUNES, all_markets, banner, load_config)  # noqa: E402

TIMEOUT = 25
PROBE_APP = 1477376905          # GitHub — stable, moderate review count
PROBE_TERM = "habit"

OK, DIFF, DEAD = "WORKS", "WORKS (shape differs)", "DEAD"
results: list[tuple[str, str, str]] = []


def record(purpose: str, status: str, evidence: str) -> None:
    results.append((purpose, status, evidence))
    mark = {OK: "[ok]  ", DIFF: "[warn]", DEAD: "[DEAD]"}[status]
    print(f"  {mark} {purpose}\n         {evidence}")


def get(url: str, headers: dict | None = None):
    try:
        r = requests.get(url, headers=headers or {"User-Agent": UA_BROWSER}, timeout=TIMEOUT)
        return r.status_code, r.content
    except requests.RequestException as e:
        return f"EXC:{type(e).__name__}", b""


# ---------------------------------------------------------------------------
def probe_search():
    url = ("https://itunes.apple.com/search?"
           + urllib.parse.urlencode({"term": PROBE_TERM, "country": "us",
                                     "entity": "software", "limit": 5}))
    code, body = get(url)
    if code != 200:
        return record("App search", DEAD, f"HTTP {code}")
    try:
        d = json.loads(body)
    except Exception:
        return record("App search", DEAD, "HTTP 200 but body is not JSON")
    n = d.get("resultCount", 0)
    if not n:
        return record("App search", DIFF, "HTTP 200 but zero results for a common term")
    need = {"trackId", "trackName", "userRatingCount", "currentVersionReleaseDate",
            "sellerName", "formattedPrice", "primaryGenreName", "fileSizeBytes"}
    missing = need - set(d["results"][0])
    record("App search", OK if not missing else DIFF,
           f"{n} results, {len(d['results'][0])} fields"
           + (f"; MISSING {sorted(missing)}" if missing else "; all needed fields present"))


def probe_lookup():
    url = f"https://itunes.apple.com/lookup?id={PROBE_APP}&country=us"
    code, body = get(url)
    if code != 200:
        return record("App lookup by ID", DEAD, f"HTTP {code}")
    d = json.loads(body)
    if not d.get("results"):
        return record("App lookup by ID", DEAD, "HTTP 200 but no app returned")
    app = d["results"][0]
    record("App lookup by ID", OK,
           f"{app.get('trackName')} — {app.get('userRatingCount')} ratings, "
           f"updated {app.get('currentVersionReleaseDate')}")


def probe_autocomplete():
    """The highest-risk dependency in the pipeline: our only free demand proxy.

    Tested twice on purpose. Without the storefront header Apple returns a
    perfectly valid HTTP 200 with an empty list — indistinguishable from "no
    one searches this" unless you know to look."""
    url = ("https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints"
           f"?clientApplication=Software&term={urllib.parse.quote(PROBE_TERM)}")

    code_n, body_n = get(url)
    n_without = 0
    if code_n == 200:
        try:
            n_without = len(plistlib.loads(body_n).get("hints", []))
        except Exception:
            n_without = -1

    time.sleep(2)
    code_h, body_h = get(url, {"User-Agent": UA_ITUNES,
                               "X-Apple-Store-Front": "143441-1,29"})
    if code_h != 200:
        return record("Autocomplete (hints)", DEAD,
                      f"HTTP {code_h} WITH storefront header — demand proxy is gone")
    try:
        hints = [h["term"] for h in plistlib.loads(body_h).get("hints", [])]
    except Exception as e:
        return record("Autocomplete (hints)", DEAD, f"unparseable plist: {e}")

    if not hints:
        return record("Autocomplete (hints)", DEAD,
                      "HTTP 200 but EMPTY even with the storefront header. "
                      "This is the free demand proxy — treat as a hard stop.")

    record("Autocomplete (hints)", OK,
           f"{len(hints)} ranked suggestions with header vs {n_without} without. "
           f"Top 3: {hints[:3]}")
    if n_without != 0:
        record("  ↳ header behaviour", DIFF,
               f"Expected 0 hints without the header, got {n_without}. "
               "Apple may have changed the rules — re-check before trusting ranks.")


def probe_storefronts():
    """A wrong storefront ID returns valid-looking data for the wrong country."""
    cfg = load_config()
    bad = []
    for m in all_markets(cfg):
        time.sleep(1.5)
        code, body = get("https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/"
                         "wa/hints?clientApplication=Software&term=budget",
                         {"User-Agent": UA_ITUNES,
                          "X-Apple-Store-Front": f"{m['storefront']}-1,29"})
        n = 0
        if code == 200:
            try:
                n = len(plistlib.loads(body).get("hints", []))
            except Exception:
                n = -1
        if n <= 0:
            bad.append(f"{m['code']}({m['storefront']})")
    record("Storefront IDs in config.yaml", OK if not bad else DEAD,
           "all configured markets returned suggestions" if not bad
           else f"NO DATA for: {', '.join(bad)} — fix these before running Phase 1")


def probe_reviews():
    """Expected to be flaky. An empty feed here means throttled, not 'no reviews'."""
    url = (f"https://itunes.apple.com/us/rss/customerreviews/"
           f"id={PROBE_APP}/sortBy=mostRecent/page=1/json")
    code, body = get(url)
    if code != 200:
        return record("Reviews RSS", DEAD, f"HTTP {code}")
    entries = (json.loads(body).get("feed") or {}).get("entry") or []

    # Cross-check: does this app actually have reviews? If lookup says it has
    # thousands of ratings and the feed says zero, the feed is lying.
    _, lbody = get(f"https://itunes.apple.com/lookup?id={PROBE_APP}&country=us")
    try:
        ratings = json.loads(lbody)["results"][0].get("userRatingCount")
    except Exception:
        ratings = None

    if entries:
        record("Reviews RSS", OK, f"{len(entries)} reviews on page 1 ({len(body)} bytes)")
    elif ratings and ratings > 100:
        record("Reviews RSS", DIFF,
               f"HTTP 200 with an EMPTY feed, but lookup says the app has {ratings:,} "
               f"ratings — so this is throttling, not absence. Body was {len(body)} bytes. "
               "Phase 5 handles this with cooldown sweeps; nothing to fix.")
    else:
        record("Reviews RSS", DIFF,
               "empty feed and could not cross-check rating count — inconclusive, re-run")


def probe_charts():
    """The documented host 301s to a different one, and intermittently 504s."""
    old = "https://rss.applemarketingtools.com/api/v2/us/apps/top-free/25/apps.json"
    new = "https://rss.marketingtools.apple.com/api/v2/us/apps/top-free/25/apps.json"
    code, body = get(new)
    if code != 200:
        time.sleep(4)
        code, body = get(new)          # 504s were observed; one retry is fair
    if code != 200:
        return record("Top charts", DEAD, f"HTTP {code} on {new} after retry")
    n = len(((json.loads(body).get("feed")) or {}).get("results") or [])
    record("Top charts", OK if n else DIFF,
           f"{n} apps from rss.marketingtools.apple.com "
           f"(note: {old.split('/')[2]} 301-redirects here and intermittently 504s)")


# ---------------------------------------------------------------------------
def main():
    banner("PHASE 0 — RECON  (no cache; every call is live)")
    print()
    probe_search()
    probe_lookup()
    probe_autocomplete()
    probe_storefronts()
    probe_reviews()
    probe_charts()

    dead = [r for r in results if r[1] == DEAD]
    diff = [r for r in results if r[1] == DIFF]

    banner("RECON SUMMARY")
    print(f"  {len(results) - len(dead) - len(diff)} working, "
          f"{len(diff)} working-with-caveats, {len(dead)} dead\n")
    if dead:
        print("  DEAD — do not run the pipeline until these are resolved:")
        for p, _, e in dead:
            print(f"    - {p}: {e}")
        print()
    print("  Autocomplete is the one that matters most. If it is dead, the pipeline")
    print("  has no free demand signal and Phase 1 onward is not worth running.\n")
    sys.exit(1 if dead else 0)


if __name__ == "__main__":
    main()
