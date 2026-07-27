"""
common.py — the shared core every phase imports.

Everything that could silently corrupt the research lives in here, once, so it
cannot drift between phases. Three rules are enforced at this level and cannot
be bypassed by a phase script:

  1. A response is cached only if it passes a validity check for its endpoint.
     HTTP 200 is not good enough. Apple returns 200 with an empty body when it
     is throttling you, and caching that would freeze the lie in permanently.

  2. An invalid or empty response produces None, never a zero. Zero is a
     finding. None is an absence of data. They must never be confused.

  3. Every failure gets a row in data/errors.log. Nothing is skipped silently.

Measured behaviour this is built around (verified 2026-07-26):
  - Autocomplete without the X-Apple-Store-Front header: HTTP 200, zero hints.
  - Reviews RSS under load: HTTP 200 with an empty feed. Tracked one URL over
    20 minutes: empty at t+120s (6 fast retries recovered 0/6), fine at t+300s
    and t+600s, empty again at t+1200s. So it is intermittent, not a cooldown
    you can reliably wait out. One empty response proves nothing; repeated
    sweeps converge; a success must be cached because it may not repeat.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import plistlib
import re
import random
import sqlite3
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
import yaml

# --------------------------------------------------------------------------
# Paths — resolved relative to the project root so scripts work from anywhere
# --------------------------------------------------------------------------
# These phases run for tens of minutes. Python buffers stdout when it is piped
# to a file or another process, which makes a working run look like a hung one.
# Line buffering means progress shows up as it happens, wherever it is sent.
try:
    sys.stdout.reconfigure(line_buffering=True)
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MANUAL = ROOT / "manual"
OUTPUT = ROOT / "output"
ERRORS_LOG = DATA / "errors.log"

for _d in (DATA, MANUAL, OUTPUT):
    _d.mkdir(parents=True, exist_ok=True)


# ==========================================================================
# Config
# ==========================================================================
def load_config(path: Path | None = None) -> dict:
    # ASO_CONFIG lets you point a run at a different config file without editing
    # your real one — used for smoke tests and for running a second market with
    # native-language seeds.
    path = path or Path(os.environ.get("ASO_CONFIG") or (ROOT / "config.yaml"))
    if not path.exists():
        die(f"config.yaml not found at {path}\n"
            "  Copy the template and put your own seed topics in it:\n"
            "    cp config.example.yaml config.yaml\n"
            "  (config.yaml is gitignored — it holds which niches you're researching.)")
    with open(path) as fh:
        cfg = yaml.safe_load(fh)

    seeds = cfg.get("seeds") or []
    cfg["seeds"] = [s for s in seeds if s and s != "REPLACE_ME"]
    return cfg


def all_markets(cfg: dict) -> list[dict]:
    """Primary first, then secondary. Primary is tagged so phases can tell."""
    p = dict(cfg["markets"]["primary"])
    p["is_primary"] = True
    out = [p]
    for m in cfg["markets"].get("secondary") or []:
        m = dict(m)
        m["is_primary"] = False
        out.append(m)
    return out


def primary_market(cfg: dict) -> dict:
    p = dict(cfg["markets"]["primary"])
    p["is_primary"] = True
    return p


def die(msg: str, code: int = 1):
    print(f"\n  STOPPED: {msg}\n", file=sys.stderr)
    sys.exit(code)


# ==========================================================================
# Error log — structured, append-only, one row per skipped thing
# ==========================================================================
_log_lock = threading.Lock()


def log_error(phase: str, entity: str, reason: str, *, market: str = "",
              url: str = "", http_status: Any = "") -> None:
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phase": phase,
        "entity": entity,
        "market": market,
        "http_status": http_status,
        "reason": reason,
        "url": url,
    }
    line = "\t".join(str(row[k]) for k in
                     ("timestamp", "phase", "entity", "market", "http_status", "reason", "url"))
    with _log_lock:
        first = not ERRORS_LOG.exists()
        with open(ERRORS_LOG, "a") as fh:
            if first:
                fh.write("timestamp\tphase\tentity\tmarket\thttp_status\treason\turl\n")
            fh.write(line + "\n")


# ==========================================================================
# Cache — SQLite, keyed on URL *plus* storefront
# ==========================================================================
# Keying on URL alone would be a silent disaster: the autocomplete URL is
# identical for every market and only the header differs, so all 8 markets
# would collide into one row and 7 of them would quietly serve US data.
# --------------------------------------------------------------------------
class Cache:
    def __init__(self, path: Path, ttl_days: int = 30):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS http_cache (
                key         TEXT PRIMARY KEY,
                url         TEXT NOT NULL,
                storefront  TEXT NOT NULL DEFAULT '',
                status      INTEGER,
                body        BLOB,
                fetched_at  REAL NOT NULL
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_url ON http_cache(url)")
        self.conn.commit()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def make_key(url: str, storefront: str = "") -> str:
        return hashlib.sha256(f"{url}||sf={storefront}".encode()).hexdigest()

    def get(self, url: str, storefront: str = "") -> bytes | None:
        row = self.conn.execute(
            "SELECT body, fetched_at FROM http_cache WHERE key=?",
            (self.make_key(url, storefront),),
        ).fetchone()
        if not row:
            self.misses += 1
            return None
        body, fetched_at = row
        if self.ttl_days and (time.time() - fetched_at) > self.ttl_days * 86400:
            self.misses += 1
            return None
        self.hits += 1
        return body

    def put(self, url: str, body: bytes, status: int, storefront: str = "") -> None:
        """Only ever called for responses that passed their validity check."""
        self.conn.execute(
            "INSERT OR REPLACE INTO http_cache (key,url,storefront,status,body,fetched_at) "
            "VALUES (?,?,?,?,?,?)",
            (self.make_key(url, storefront), url, storefront, status, body, time.time()),
        )
        self.conn.commit()

    def stats_line(self) -> str:
        total = self.hits + self.misses
        pct = (100.0 * self.hits / total) if total else 0.0
        return f"cache: {self.hits} hits / {self.misses} misses ({pct:.0f}% hit rate)"


# ==========================================================================
# Throttle — separate lanes, because reviews rate-limit harder than search
# ==========================================================================
class Throttle:
    def __init__(self, per_minute: int, jitter: tuple[float, float]):
        self.min_interval = 60.0 / max(per_minute, 1)
        self.jitter = jitter
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            gap = now - self._last
            delay = max(0.0, self.min_interval - gap) + random.uniform(*self.jitter)
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


# ==========================================================================
# Validity predicates — the heart of "never fabricate a data point"
# ==========================================================================
# Each returns (is_valid, parsed_or_None, reason_if_invalid).
# If a predicate says invalid, the response is NOT cached and the caller gets
# None. It never becomes a zero.
# --------------------------------------------------------------------------
def _valid_hints(body: bytes):
    """Shape check only.

    An empty hints list is genuinely ambiguous and CANNOT be resolved here:
      - "sleep sounds zq" is legitimately empty. Nobody searches that.
      - A missing storefront header, or throttling, is ALSO empty.
    Same bytes, opposite meanings. Telling them apart needs a second live
    request, so it happens in Client._hints_alive() instead.
    """
    try:
        d = plistlib.loads(body)
    except Exception as e:
        return False, None, f"unparseable_plist:{type(e).__name__}"
    hints = d.get("hints")
    if hints is None:
        return False, None, "no_hints_key"
    return True, [h.get("term") for h in hints if h.get("term")], ""


def _valid_search(body: bytes):
    try:
        d = json.loads(body)
    except Exception as e:
        return False, None, f"unparseable_json:{type(e).__name__}"
    if "results" not in d:
        return False, None, "no_results_key"
    # A genuinely zero-result search IS a real finding here (an obscure term can
    # legitimately match nothing), so unlike hints we accept an empty list.
    return True, d["results"], ""


def _valid_lookup(body: bytes):
    try:
        d = json.loads(body)
    except Exception as e:
        return False, None, f"unparseable_json:{type(e).__name__}"
    if "results" not in d:
        return False, None, "no_results_key"
    if not d["results"]:
        return False, None, "lookup_returned_no_app"
    return True, d["results"], ""


def _valid_reviews(body: bytes):
    try:
        d = json.loads(body)
    except Exception as e:
        return False, None, f"unparseable_json:{type(e).__name__}"
    feed = d.get("feed")
    if feed is None:
        return False, None, "no_feed_key"
    entries = feed.get("entry")
    if not entries:
        # Measured: an empty feed is ~860-880 bytes and means throttled, not
        # "no reviews". The caller cross-checks against userRatingCount before
        # this is ever allowed to mean anything.
        return False, None, "empty_review_feed_HTTP200_likely_throttled"
    if isinstance(entries, dict):      # Apple collapses a 1-entry feed to an object
        entries = [entries]
    return True, entries, ""


def _valid_charts(body: bytes):
    try:
        d = json.loads(body)
    except Exception as e:
        return False, None, f"unparseable_json:{type(e).__name__}"
    results = (d.get("feed") or {}).get("results")
    if not results:
        return False, None, "empty_chart_feed"
    return True, results, ""


def _valid_app_page(body: bytes):
    """The public App Store listing page.

    Used only for the two fields Apple's JSON API does not expose anywhere:
    in-app purchases and the app subtitle. Both are required by the Phase 3
    scoring and neither exists in the 44 fields the API returns.

    This is a single plain GET with no browser and no scraping framework, but
    it is HTML rather than JSON, so it is deliberately limited to the handful
    of apps that actually define a niche.
    """
    if len(body) < 20_000:
        return False, None, f"app_page_too_small:{len(body)}b"
    text = body.decode("utf-8", "ignore")
    if "<h1" not in text:
        return False, None, "app_page_has_no_h1"
    return True, text, ""


# Failures that are expected, transient, and recoverable by waiting. These are
# the HTTP-200-with-an-empty-body cases: real, worth logging, but NOT evidence
# that an endpoint is dead. They are retried by the cooldown sweeps, so they
# must not trip the "more than 20% failed, abort" guard before the sweeps have
# even run — an earlier version aborted Phase 5 at 100% "failure" while every
# one of those failures was a case the sweep was designed to fix.
SOFT_FAILURE_REASONS = (
    "empty_review_feed",
    "hints_empty_and_endpoint_unresponsive",
)


def is_soft_failure(reason: str) -> bool:
    return any(r in reason for r in SOFT_FAILURE_REASONS)


VALIDATORS: dict[str, Callable[[bytes], tuple]] = {
    "hints": _valid_hints,
    "app_page": _valid_app_page,
    "search": _valid_search,
    "lookup": _valid_lookup,
    "reviews": _valid_reviews,
    "charts": _valid_charts,
}


# ==========================================================================
# Fetch result
# ==========================================================================
@dataclass
class Result:
    ok: bool
    data: Any = None
    reason: str = ""
    from_cache: bool = False
    http_status: Any = ""

    def __bool__(self) -> bool:
        return self.ok


# ==========================================================================
# Client
# ==========================================================================
UA_ITUNES = "iTunes/12.12.4 (Macintosh; OS X 12.0) AppleWebKit/605.1.15"
UA_BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"

# A term that must return suggestions in every storefront we support. Used to
# tell "this search phrase has no suggestions" apart from "Apple has stopped
# answering us" — the two look identical on the wire.
CANARY_TERM = "weather"
CANARY_TTL_SECONDS = 120


class Client:
    def __init__(self, cfg: dict, phase: str):
        net = cfg["network"]
        self.cfg = cfg
        self.phase = phase
        self.timeout = net["timeout_seconds"]
        self.transport_retries = net["transport_retries"]
        self.fail_threshold = net["fail_rate_abort_threshold"]
        jitter = tuple(net["jitter_seconds"])
        self.lanes = {
            "default": Throttle(net["requests_per_minute"], jitter),
            "reviews": Throttle(net["reviews_requests_per_minute"], jitter),
        }
        self.cache = Cache(ROOT / cfg["cache"]["path"], cfg["cache"]["ttl_days"])
        self.session = requests.Session()
        self.attempted = 0
        self.succeeded = 0
        self.failed = 0          # hard: 4xx, transport, unparseable
        self.soft_failed = 0     # empty-but-200; recoverable by a cooldown sweep
        self.canary_ttl = CANARY_TTL_SECONDS
        self._canary_until: dict[str, float] = {}

    # ---- low level ------------------------------------------------------
    def fetch(self, kind: str, url: str, *, storefront: str = "",
              entity: str = "", market: str = "", lane: str = "default",
              extra_check: Callable[[Any], tuple[bool, str]] | None = None) -> Result:
        """
        Returns a Result. On failure: ok=False, data=None, and a row in
        errors.log. Never returns a zero-value stand-in for missing data.

        `extra_check` runs after the shape validator and BEFORE caching, for
        cases where the body alone cannot tell you whether the response is
        trustworthy. It must gate caching, otherwise a throttled response gets
        written to the cache and every future run inherits it.
        """
        validate = VALIDATORS[kind]
        self.attempted += 1

        cached = self.cache.get(url, storefront)
        if cached is not None:
            ok, parsed, reason = validate(cached)
            if ok:
                self.succeeded += 1
                return Result(True, parsed, from_cache=True, http_status="cache")
            # Shouldn't happen (we only cache valid bodies) but if the schema
            # changed under us, treat it as a miss rather than trusting it.

        headers = {"User-Agent": UA_ITUNES if kind == "hints" else UA_BROWSER,
                   "Accept": "*/*"}
        if storefront:
            headers["X-Apple-Store-Front"] = f"{storefront}-1,29"

        last_status: Any = ""
        last_reason = "unknown"
        for attempt in range(1, self.transport_retries + 1):
            self.lanes[lane].wait()
            try:
                resp = self.session.get(url, headers=headers, timeout=self.timeout)
                last_status = resp.status_code
            except requests.RequestException as e:
                last_reason = f"transport:{type(e).__name__}"
                continue  # genuine network error — retrying is appropriate

            if resp.status_code >= 500:
                last_reason = f"http_{resp.status_code}"
                continue  # 504s were observed on the charts host; retry helps

            if resp.status_code != 200:
                last_reason = f"http_{resp.status_code}"
                break  # 4xx won't fix itself

            ok, parsed, reason = validate(resp.content)
            if ok and extra_check is not None:
                trustworthy, why = extra_check(parsed)
                if not trustworthy:
                    ok, reason = False, why
            if ok:
                self.cache.put(url, resp.content, resp.status_code, storefront)
                self.succeeded += 1
                return Result(True, parsed, http_status=resp.status_code)

            # HTTP 200 but the body is empty/garbage. Measured: fast retry does
            # not recover this. Do not burn attempts, do not cache, hand it back
            # so the phase can put it on the cooldown queue.
            last_reason = reason
            break

        if is_soft_failure(last_reason):
            self.soft_failed += 1
        else:
            self.failed += 1
        log_error(self.phase, entity or url, last_reason,
                  market=market, url=url, http_status=last_status)
        return Result(False, None, reason=last_reason, http_status=last_status)

    # ---- endpoints ------------------------------------------------------
    @staticmethod
    def _hints_url(term: str) -> str:
        return ("https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints"
                f"?clientApplication=Software&term={urllib.parse.quote(term)}")

    def _hints_alive(self, market: dict) -> bool:
        """Is autocomplete actually answering us right now, in this market?

        Deliberately uncached — a cached 'yes' from an hour ago proves nothing
        about this moment. Result is held for canary_ttl seconds so a long run
        of empty branches costs one extra request per window, not one each.
        """
        code = market["code"]
        if time.monotonic() < self._canary_until.get(code, 0.0):
            return True
        self.lanes["default"].wait()
        try:
            resp = self.session.get(
                self._hints_url(CANARY_TERM),
                headers={"User-Agent": UA_ITUNES,
                         "X-Apple-Store-Front": f"{market['storefront']}-1,29"},
                timeout=self.timeout)
            ok, data, _ = _valid_hints(resp.content)
            alive = bool(ok and data)
        except requests.RequestException:
            alive = False
        if alive:
            self._canary_until[code] = time.monotonic() + self.canary_ttl
        return alive

    def hints(self, term: str, market: dict) -> Result:
        """Autocomplete — the free demand proxy.

        An empty result is ambiguous, so when we get one we ask the canary term
        whether the endpoint is alive:
          - canary answers  -> the empty is real. This branch has no searches.
                               Returns ok=True with an empty list, and caches it.
          - canary silent   -> we are throttled or the header is being ignored.
                               Returns ok=False, logs it, caches nothing.
        """
        def check(parsed):
            if parsed:
                return True, ""
            if self._hints_alive(market):
                return True, ""
            return False, "hints_empty_and_endpoint_unresponsive"

        return self.fetch("hints", self._hints_url(term),
                          storefront=str(market["storefront"]),
                          entity=f"hint:{term}", market=market["code"],
                          extra_check=check)

    def search(self, term: str, market: dict, limit: int = 10) -> Result:
        url = ("https://itunes.apple.com/search?"
               + urllib.parse.urlencode({"term": term, "country": market["code"],
                                         "entity": "software", "limit": limit}))
        return self.fetch("search", url, entity=f"search:{term}", market=market["code"])

    def lookup(self, app_id: str | int, market: dict) -> Result:
        url = ("https://itunes.apple.com/lookup?"
               + urllib.parse.urlencode({"id": app_id, "country": market["code"]}))
        return self.fetch("lookup", url, entity=f"lookup:{app_id}", market=market["code"])

    def reviews(self, app_id: str | int, page: int, market: dict) -> Result:
        url = (f"https://itunes.apple.com/{market['code']}/rss/customerreviews/"
               f"id={app_id}/sortBy=mostRecent/page={page}/json")
        return self.fetch("reviews", url, entity=f"reviews:{app_id}:p{page}",
                          market=market["code"], lane="reviews")

    def app_page(self, app_id: str | int, market: dict) -> Result:
        url = f"https://apps.apple.com/{market['code']}/app/id{app_id}"
        return self.fetch("app_page", url, entity=f"app_page:{app_id}",
                          market=market["code"])

    def top_charts(self, market: dict, kind: str = "top-free", limit: int = 50) -> Result:
        # Note the host: rss.applemarketingtools.com 301-redirects here, and the
        # old host intermittently 504s. Go straight to the real one.
        url = (f"https://rss.marketingtools.apple.com/api/v2/{market['code']}"
               f"/apps/{kind}/{limit}/apps.json")
        return self.fetch("charts", url, entity=f"charts:{kind}", market=market["code"])

    # ---- phase accounting ----------------------------------------------
    def check_failure_rate(self) -> None:
        """Per the spec: >20% failures is a rate-limit or dead-endpoint signal,
        not a data signal. Stop rather than produce a confident wrong answer."""
        if self.attempted < 20:
            return
        # Deliberately hard failures only. Soft ones are what the sweeps fix.
        rate = self.failed / self.attempted
        if rate > self.fail_threshold:
            self.summary()
            die(f"{rate:.0%} of requests failed (threshold {self.fail_threshold:.0%}). "
                "That is a rate-limit or a dead endpoint, not a finding about your "
                "niche. Wait 15 minutes and re-run — the cache means you resume, "
                "not restart. See data/errors.log.")

    def summary(self) -> None:
        soft = (f", {self.soft_failed} empty-and-requeued" if self.soft_failed else "")
        print(f"\n  {self.succeeded} succeeded, {self.failed} failed{soft}"
              f"{'  — see data/errors.log' if self.failed or self.soft_failed else ''}")
        print(f"  {self.cache.stats_line()}")


# ==========================================================================
# Cooldown queue — for the HTTP-200-but-empty case
# ==========================================================================
@dataclass
class CooldownQueue:
    """
    Holds work that came back empty-with-200. Measured behaviour is a ~5 minute
    per-URL cooldown that fast retry does not help with, so this re-sweeps after
    a real wait instead of hammering.
    """
    cooldown_s: int
    max_sweeps: int
    items: list = field(default_factory=list)

    def add(self, item) -> None:
        self.items.append(item)

    def sweep(self, worker: Callable[[Any], bool], label: str = "") -> list:
        """worker(item) -> True if it succeeded. Returns whatever never came back."""
        pending = list(self.items)
        for sweep_no in range(1, self.max_sweeps + 1):
            if not pending:
                break
            print(f"\n  {len(pending)} item(s) came back empty {label}. "
                  f"Waiting {self.cooldown_s}s for Apple's cooldown "
                  f"(sweep {sweep_no}/{self.max_sweeps})...")
            time.sleep(self.cooldown_s)
            still: list = []
            for item in pending:
                if not worker(item):
                    still.append(item)
            recovered = len(pending) - len(still)
            print(f"  recovered {recovered}/{len(pending)}")
            pending = still
        self.items = []
        return pending


# ==========================================================================
# Small helpers
# ==========================================================================
def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n  {title}\n{'=' * 72}")


def gate(title: str, body: str) -> None:
    print(f"\n{'=' * 72}\n  STOP — GATE: {title}\n{'=' * 72}\n{body}\n")


def parse_app_page(page: str, expected_name: str) -> dict | None:
    """Pull subtitle / IAP / price points out of an App Store listing page.

    Returns None if anything looks misaligned, because a wrong answer here is
    worse than a missing one. The guard is `expected_name`: these pages carry
    carousels of *other* apps, and a naive regex happily returns a neighbour's
    subtitle. (Measured: an unanchored match gave Things 3 the subtitle
    "Science-backed habit tracker", which belongs to an unrelated app.)

    So we anchor everything to the page's own <h1> and then verify that name
    against the trackName the JSON API already gave us. If they disagree, the
    page layout has changed and every field here is suspect.
    """
    i = page.find("<h1")
    if i < 0:
        return None
    head = page[i:i + 2500]

    m = re.search(r'multiline-clamp__text[^>]*>([^<]{1,120})<', head)
    name = html.unescape(m.group(1)).strip() if m else None
    if not name:
        return None

    # Cross-check against the API's own name. Apple truncates and decorates
    # titles differently between the API and the page, so compare on the
    # leading alphanumeric run rather than demanding an exact match.
    def core(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", s.lower())[:18]
    if not core(name) or core(name) not in core(expected_name):
        return None

    sub = re.search(r'<p class="subtitle[^"]*">([^<]{0,150})</p>', head)
    iap = re.search(r'"title":"In-App Purchases","summary":"(Yes|No)"', page)

    seen, prices = set(), []
    for label, price in re.findall(r'\["([^"]{1,40})","(\$[\d.,]+)"\]', page):
        if (label, price) not in seen:
            seen.add((label, price))
            prices.append(f"{label}={price}")

    return {
        "name_on_page": name,
        "subtitle": html.unescape(sub.group(1)).strip() if sub else None,
        "has_iap": (iap.group(1) == "Yes") if iap else False,
        "iap_price_points": " | ".join(prices[:6]) or None,
    }


def days_since(iso_ts: str | None) -> int | None:
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None
