"""
p1_expand.py — turn your seed topics into a keyword universe.

    python scripts/p1_expand.py

What it does: asks App Store search-autocomplete what real people type. The
*position* of a suggestion in that list is the demand signal — Apple orders
them by popularity, so rank 1 is searched more than rank 10.

That is a proxy, not a volume number. It tells you ordering, not magnitude.
Two keywords both at rank 1 are not necessarily equally popular. Phase 4 (the
Apple Search Ads step) is what turns this into something you can trust.

Safe to interrupt. Everything is cached, so re-running resumes rather than
restarting.

Output: data/01_keywords.csv
"""

from __future__ import annotations

import re
import string
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (DATA, Client, CooldownQueue, all_markets, banner, die,  # noqa: E402
                    load_config, log_error, primary_market)

PHASE = "p1_expand"

# Words that are brands/apps, not niches. A keyword that is really just a
# competitor's name tells us nothing about unmet demand.
BRAND_STOPWORDS = {
    "google", "apple", "microsoft", "meta", "facebook", "instagram", "tiktok",
    "whatsapp", "youtube", "netflix", "spotify", "amazon", "samsung", "disney",
    "snapchat", "twitter", "reddit", "linkedin", "pinterest", "uber", "paypal",
}


def looks_like_brand(kw: str, seeds: list[str]) -> bool:
    """Drop obvious brand terms — but never drop something that contains a seed,
    because 'habit tracker by habitica' still tells us about the habit niche."""
    low = kw.lower()
    if any(s.lower() in low for s in seeds):
        return False
    return any(tok in BRAND_STOPWORDS for tok in re.findall(r"[a-z]+", low))


# Apple's autocomplete returns actual app titles alongside generic search
# phrases. "acme: do the thing now" is an app title; "sleep sounds free" is a
# search. Both are real user behaviour, but only the second is a keyword you can
# target — you cannot out-rank an app for its own name.
#
# These are FLAGGED, not dropped. A niche whose suggestions are nearly all app
# names is telling you something important: people search that category by brand,
# not by description. That is a finding, and deleting it would hide it.
APP_TITLE_MARKERS = re.compile(
    r"[:®™|]"                      # punctuation basically only app titles use
    r"|\s[-–—]\s"                  # "acme — some app"
    r"|\b(?:llc|inc|ltd|magazine)\b"
)


def looks_like_app_title(kw: str) -> bool:
    return bool(APP_TITLE_MARKERS.search(kw))


def clean(kw: str, min_chars: int) -> str | None:
    kw = re.sub(r"\s+", " ", (kw or "")).strip().lower()
    if len(kw) < min_chars:
        return None
    if not re.search(r"[a-z]", kw):     # pure numbers/punctuation
        return None
    return kw


def fanout_terms(term: str) -> list[str]:
    """'habit' -> 'habit ', 'habit a', 'habit b' ... The trailing-letter trick
    makes Apple reveal suggestions it would not show for the bare term."""
    return [f"{term} "] + [f"{term} {c}" for c in string.ascii_lowercase]


def main():
    cfg = load_config()
    seeds = cfg["seeds"]
    if not seeds:
        die("No seed topics set. Open config.yaml and replace REPLACE_ME under "
            "`seeds:` with 3-6 plain phrases, e.g. 'habit tracker'.")

    exp = cfg["expansion"]
    net = cfg["network"]
    min_chars = exp["min_keyword_chars"]
    client = Client(cfg, PHASE)
    primary = primary_market(cfg)

    banner(f"PHASE 1 — EXPAND   seeds={seeds}   primary market={primary['code']}")

    # rows keyed by (keyword, market) so a keyword can hold a rank per market
    rows: dict[tuple[str, str], dict] = {}

    def record(keyword, market_code, rank, seed, depth, query, proxy):
        key = (keyword, market_code)
        # keep the BEST (lowest) rank we ever saw for a keyword in a market
        if key in rows and rows[key]["autocomplete_rank"] <= rank:
            return
        rows[key] = {
            "keyword": keyword, "seed": seed, "depth": depth,
            "market": market_code, "autocomplete_rank": rank,
            "first_seen_query": query, "english_query_proxy": proxy,
            "probably_app_name": looks_like_app_title(keyword),
        }

    cooldown = CooldownQueue(net["empty_response_cooldown_seconds"],
                             net["empty_response_max_sweeps"])

    # ---------------------------------------------------------------- depth 1
    def harvest(term, seed, depth, market):
        res = client.hints(term, market)
        if not res:
            if "unresponsive" in res.reason:
                cooldown.add((term, seed, depth, market))
            return False
        for rank, sug in enumerate(res.data, start=1):
            kw = clean(sug, min_chars)
            if not kw or looks_like_brand(kw, seeds):
                continue
            record(kw, market["code"], rank, seed, depth, term,
                   market.get("english_query_proxy", False))
        return True

    queries = []
    for seed in seeds:
        queries.append((seed, seed, 1))
        if exp["alphabet_fanout_depth"] >= 1:
            queries += [(t, seed, 1) for t in fanout_terms(seed)]

    print(f"\n  Depth 1: {len(queries)} queries "
          f"(~{len(queries) * 60 // net['requests_per_minute'] // 60 + 1} min)")
    for i, (term, seed, depth) in enumerate(queries, 1):
        harvest(term, seed, depth, primary)
        if i % 25 == 0:
            print(f"    {i}/{len(queries)} queries · {len(rows)} keywords so far")
            client.check_failure_rate()

    # ---------------------------------------------------------------- depth 2
    if exp["depth"] >= 2:
        d1 = sorted((r for r in rows.values()
                     if r["depth"] == 1 and r["market"] == primary["code"]),
                    key=lambda r: r["autocomplete_rank"])[:exp["depth2_top_n"]]
        d2_queries = []
        for r in d1:
            d2_queries.append((r["keyword"], r["seed"], 2))
            if exp["alphabet_fanout_depth"] >= 2:
                d2_queries += [(t, r["seed"], 2) for t in fanout_terms(r["keyword"])]

        print(f"\n  Depth 2: {len(d2_queries)} queries")
        for i, (term, seed, depth) in enumerate(d2_queries, 1):
            harvest(term, seed, depth, primary)
            if i % 25 == 0:
                print(f"    {i}/{len(d2_queries)} queries · {len(rows)} keywords so far")
                client.check_failure_rate()

    # Write the primary-market results now, before the slow echo pass. The echo
    # only adds per-market ranks; Phase 2 works off the primary market alone, so
    # there is no reason to make it wait an hour for data it does not read.
    def write_csv() -> pd.DataFrame:
        d = pd.DataFrame(rows.values()).sort_values(
            ["market", "autocomplete_rank", "keyword"])
        d.to_csv(DATA / "01_keywords.csv", index=False)
        return d

    if rows:
        write_csv()
        print(f"\n  Wrote {len({r['keyword'] for r in rows.values()})} keywords so far "
              f"-> data/01_keywords.csv (you can start Phase 2 now if you like)")

    # ------------------------------------------------- secondary market echo
    # We do NOT re-expand in every market. English keywords are the same in the
    # US and Australia, so re-expanding there costs 8x the requests to rediscover
    # the same list. Instead we take the best keywords and ask each market where
    # they rank — which is the part that actually differs.
    # Selection matters more than it looks. Sorting by autocomplete_rank alone
    # does almost nothing: most discovered keywords tie at rank 1, and Python's
    # sort is stable, so the "top 75" collapses to insertion order — which is
    # SEED order. Measured on a real 12-seed run: all 75 echoed keywords came
    # from the first 6 seeds and the other 6 were never tested abroad at all,
    # while 34 of the 75 were app titles, which trivially rank 1 in every store.
    # The result looked like international coverage and was nothing of the kind.
    #
    # So: drop probable app titles, then round-robin across seeds so every seed
    # is represented before any seed gets a second slot.
    primary_kws = sorted((r for r in rows.values() if r["market"] == primary["code"]),
                         key=lambda r: r["autocomplete_rank"])
    by_seed: dict[str, list] = {}
    for r in primary_kws:
        if not r.get("probably_app_name"):
            by_seed.setdefault(r["seed"], []).append(r)
    echo_list = []
    for i in range(max((len(v) for v in by_seed.values()), default=0)):
        if len(echo_list) >= exp["echo_top_n"]:
            break
        for seed_rows in by_seed.values():
            if i < len(seed_rows) and len(echo_list) < exp["echo_top_n"]:
                echo_list.append(seed_rows[i])
    # Fall back to the old behaviour only if every keyword looked like an app
    # title — an empty echo would be worse than a biased one.
    if not echo_list:
        echo_list = primary_kws[:exp["echo_top_n"]]
    secondaries = [m for m in all_markets(cfg) if not m["is_primary"]]

    if secondaries and echo_list:
        total = len(echo_list) * len(secondaries)
        print(f"\n  Market echo: top {len(echo_list)} keywords x {len(secondaries)} "
              f"markets = {total} queries (~{total * 60 // net['requests_per_minute'] // 60 + 1} min)")
        done = 0
        for market in secondaries:
            for r in echo_list:
                kw = r["keyword"]
                res = client.hints(kw, market)
                done += 1
                if res:
                    # rank of the keyword within its own market's suggestions
                    terms = [clean(t, min_chars) for t in res.data]
                    rank = terms.index(kw) + 1 if kw in terms else len(terms) + 1
                    record(kw, market["code"], rank, r["seed"], r["depth"], kw,
                           market.get("english_query_proxy", False))
                elif "unresponsive" in res.reason:
                    cooldown.add((kw, r["seed"], r["depth"], market))
                if done % 25 == 0:
                    print(f"    {done}/{total} echo queries")
                    client.check_failure_rate()

    # ------------------------------------------------------ cooldown re-sweep
    if cooldown.items:
        leftover = cooldown.sweep(lambda it: harvest(*it), label="from autocomplete")
        for term, seed, depth, market in leftover:
            log_error(PHASE, f"hint:{term}", "empty_after_all_cooldown_sweeps",
                      market=market["code"])

    # ------------------------------------------------------------------ write
    if not rows:
        client.summary()
        die("Zero keywords collected. That is an endpoint problem, not a niche "
            "problem — run `python scripts/p0_recon.py` and check the autocomplete row.")

    df = write_csv()
    out = DATA / "01_keywords.csv"

    unique_primary = df[df.market == primary["code"]].keyword.nunique()
    client.summary()

    banner("PHASE 1 RESULT")
    print(f"  {unique_primary} unique keywords in {primary['code']} "
          f"({len(df)} keyword x market rows across {df.market.nunique()} markets)")
    print(f"  -> {out.relative_to(DATA.parent)}\n")
    for m, g in df.groupby("market"):
        proxy = " (English-query proxy — weak signal)" if g.english_query_proxy.iloc[0] else ""
        print(f"    {m}: {g.keyword.nunique():4} keywords{proxy}")

    # ------------------------------------------------ per-seed viability
    # A healthy total can hide a dead seed. Report each seed separately, and
    # count only targetable phrases — suggestions that are really app titles
    # inflate the count without giving you anything you can rank for.
    us = df[df.market == primary["code"]]
    print("\n  Per seed (targetable = generic phrases, excluding app titles):\n")
    print(f"    {'seed':24} {'found':>6} {'app titles':>11} {'targetable':>11}")
    weak = []
    for seed, g in us.groupby("seed"):
        real = int((~g.probably_app_name).sum())
        print(f"    {seed:24} {len(g):6} {int(g.probably_app_name.sum()):11} {real:11}")
        if real < 10:
            weak.append((seed, real))

    if weak:
        print("\n  WEAK SEEDS — these produced almost nothing targetable:")
        for seed, real in weak:
            print(f"    - {seed!r}: {real} usable phrase(s)")
        print("\n  Usually this means the phrase is how you describe the problem, not")
        print("  how people search for it. Describe the solution, not the problem —")
        print("  users type what they want to find, not what they want to fix.")
        print("  Consider re-seeding those in config.yaml and re-running — cached")
        print("  queries are not re-fetched, so only the new seeds cost anything.")

    target = exp["target_min_keywords"]
    if unique_primary < target:
        print(f"\n  ONLY {unique_primary} KEYWORDS (wanted {target}+).")
        print("  Your seeds are probably too narrow or too specific. Widen them in")
        print("  config.yaml and re-run — cached queries won't be re-fetched.")
        sys.exit(2)

    print(f"\n  Next: python scripts/p2_competition.py")


if __name__ == "__main__":
    main()
