"""
selftest.py — prove the pipeline fails safely.

    python scripts/selftest.py

Run this after any change to common.py, and any time results look surprising.
It does not test that the pipeline finds good data. It tests that when Apple
lies to us — HTTP 200 with an empty body — we record an absence rather than a
zero, and that we never poison the cache with the lie.

These are the failure modes that would produce a confident, completely wrong
recommendation, so they are worth a test each.
"""

from __future__ import annotations

import sys
import tempfile
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (Cache, Client, ERRORS_LOG, VALIDATORS, load_config,  # noqa: E402
                    parse_app_page, primary_market)

passed, failed = 0, 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  [pass] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}\n         {detail}")


# ---------------------------------------------------------------------------
def test_empty_hints_is_not_zero():
    """The exact bug that would sink the project: no storefront header returns
    HTTP 200 and an empty list, which looks identical to 'no one searches this'."""
    cfg = load_config()
    client = Client(cfg, "selftest")
    broken = {"code": "us", "storefront": "", "english_query_proxy": False}
    url = client._hints_url("habit")

    res = client.hints("habit", broken)

    check("autocomplete without storefront header is rejected, not scored as 0",
          res.ok is False and res.data is None,
          f"got ok={res.ok} data={res.data!r} — an empty list was treated as real data")
    check("  ...and the reason names the cause",
          "unresponsive" in res.reason, f"reason was {res.reason!r}")
    check("  ...and it is NOT written to the cache",
          client.cache.get(url, "") is None,
          "a throttled empty response was cached — every future run inherits it")


def test_genuinely_empty_branch_is_not_an_error():
    """The other half of the same coin, and the one that broke the first run.

    'sleep sounds zq' has no suggestions because nobody searches it. That is a
    real finding, not a failure. Treating it as a failure made 16 legitimate
    dead-ends look like a 64% error rate and aborted the phase."""
    cfg = load_config()
    client = Client(cfg, "selftest")
    market = primary_market(cfg)

    res = client.hints("sleep sounds zqx", market)
    check("a genuinely empty branch is accepted as data, not logged as failure",
          res.ok is True and res.data == [],
          f"got ok={res.ok} data={res.data!r} reason={res.reason!r}")

    live = client.hints("weather", market)
    check("  ...while a real term still returns suggestions",
          live.ok is True and len(live.data) > 0,
          f"got {live.reason!r} — endpoint may actually be down")


def test_cache_key_includes_storefront():
    """Same URL, different storefront = different response. Keying on URL alone
    would collide all 8 markets into one row and serve US data for every market."""
    with tempfile.TemporaryDirectory() as td:
        c = Cache(Path(td) / "t.db", ttl_days=30)
        url = "https://example.invalid/hints?term=budget"
        c.put(url, b"US-DATA", 200, storefront="143441")
        c.put(url, b"DE-DATA", 200, storefront="143443")
        check("cache separates markets that share a URL",
              c.get(url, "143441") == b"US-DATA" and c.get(url, "143443") == b"DE-DATA",
              "storefronts collided — 7 of 8 markets would silently return US data")
        check("  ...and an unknown storefront is a miss, not a wrong hit",
              c.get(url, "143444") is None)


def test_validators_reject_apples_lies():
    empty_feed = b'{"feed":{"author":{"name":{"label":"iTunes Store"}}}}'
    ok, data, reason = VALIDATORS["reviews"](empty_feed)
    check("empty review feed is rejected (throttle, not 'no complaints')",
          ok is False and data is None, f"got ok={ok} data={data!r}")
    check("  ...and the reason says it is probably throttling",
          "throttl" in reason.lower(), f"reason was {reason!r}")

    ok, data, _ = VALIDATORS["reviews"](
        b'{"feed":{"entry":[{"im:rating":{"label":"1"}}]}}')
    check("a real review feed is accepted", ok is True and len(data) == 1)

    # The hints validator checks SHAPE only. An empty list is genuinely
    # ambiguous — it means either "no one searches this" or "we're throttled" —
    # and the bytes cannot tell you which, so liveness is the canary's job
    # (covered by test_empty_hints_is_not_zero above). What the validator must
    # still catch is a body that isn't a hints plist at all.
    ok, data, _ = VALIDATORS["hints"](
        b'<?xml version="1.0"?><!DOCTYPE plist><plist version="1.0">'
        b'<dict><key>hints</key><array></array></dict></plist>')
    check("well-formed but empty hints plist passes the shape check",
          ok is True and data == [], f"got ok={ok} data={data!r}")

    ok, _, reason = VALIDATORS["hints"](
        b'<?xml version="1.0"?><plist version="1.0"><dict/></plist>')
    check("a plist with no hints key at all is rejected",
          ok is False and reason == "no_hints_key", f"got ok={ok} reason={reason!r}")

    ok, _, _ = VALIDATORS["hints"](b"<html>error</html>")
    check("non-plist garbage is rejected by the hints validator", ok is False)

    # A zero-result search IS a real finding (obscure terms legitimately match
    # nothing), so this one must be ACCEPTED. Rejecting it would throw away data.
    ok, data, _ = VALIDATORS["search"](b'{"resultCount":0,"results":[]}')
    check("zero-result search is accepted as a genuine finding",
          ok is True and data == [],
          "a legitimately empty search was discarded as an error")

    ok, _, _ = VALIDATORS["search"](b'<html>503 backend down</html>')
    check("an HTML error page is rejected, not parsed as data", ok is False)


def test_review_absence_discriminator():
    """Live check of the rule that keeps Phase 5 honest: if lookup says an app
    has thousands of ratings but the feed is empty, that is throttling."""
    cfg = load_config()
    client = Client(cfg, "selftest")
    market = primary_market(cfg)
    app_id = 1477376905                     # GitHub, ~35k ratings

    lk = client.lookup(app_id, market)
    if not lk:
        print("  [skip] live discriminator check — lookup unavailable right now")
        return
    ratings = lk.data[0].get("userRatingCount")
    rv = client.reviews(app_id, 1, market)

    if rv:
        check("live: reviews returned data, so absence logic is untested this run",
              True)
    else:
        check("live: empty feed on an app with reviews is treated as an error",
              ratings and ratings > 100 and rv.data is None,
              f"ratings={ratings} data={rv.data!r}")


def test_app_page_parser_refuses_to_guess():
    """App Store pages carry carousels of OTHER apps, and an unanchored regex
    happily returns a neighbour's subtitle. Measured: a naive match gave
    Things 3 the subtitle 'Science-backed habit tracker', from an unrelated
    app. The name cross-check is what makes that impossible."""
    page = ('x' * 25_000 +
            '<h1 class="a"><div><span class="multiline-clamp__text s">Things 3</span>'
            '</div></h1> <p class="subtitle s">Organize your life</p>')

    good = parse_app_page(page, "Things 3")
    check("parses the focal app's own subtitle",
          good and good["subtitle"] == "Organize your life",
          f"got {good!r}")
    check("  ...and reports no IAP when the page says nothing about it",
          good and good["has_iap"] is False)

    wrong = parse_app_page(page, "Duolingo: Language Lessons")
    check("returns None when the page is not the app we asked for",
          wrong is None,
          "a mismatched page was parsed anyway — subtitles would be misattributed")

    check("returns None on a page with no <h1>",
          parse_app_page("x" * 25_000, "Things 3") is None)

    iap_page = page + '"title":"In-App Purchases","summary":"Yes"' \
                      '["12 Months","$39.99"]["1 Month","$9.99"]'
    got = parse_app_page(iap_page, "Things 3")
    check("extracts IAP flag and price points when present",
          got and got["has_iap"] is True and "12 Months=$39.99" in got["iap_price_points"],
          f"got {got!r}")


def test_errors_log_is_written():
    check("failures are recorded in data/errors.log",
          ERRORS_LOG.exists() and ERRORS_LOG.stat().st_size > 0,
          "nothing was logged — failures may be getting skipped silently")


# ---------------------------------------------------------------------------
def main():
    print("\n" + "=" * 72)
    print("  SELF-TEST — does the pipeline fail safely?")
    print("=" * 72 + "\n")
    for fn in (test_empty_hints_is_not_zero, test_genuinely_empty_branch_is_not_an_error,
               test_cache_key_includes_storefront,
               test_validators_reject_apples_lies, test_app_page_parser_refuses_to_guess,
               test_review_absence_discriminator,
               test_errors_log_is_written):
        print(f"{fn.__doc__.splitlines()[0] if fn.__doc__ else fn.__name__}")
        fn()
        print()
    print("=" * 72)
    print(f"  {passed} passed, {failed} failed")
    print("=" * 72 + "\n")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
