"""
p2_competition.py — who currently owns each keyword.

    python scripts/p2_competition.py

For every keyword from Phase 1, this asks the App Store what the top results
actually are, and records what each of those apps looks like: how many ratings,
how well rated, how long since anyone updated it, how big the team behind it
seems. That is the raw material for judging whether a niche is winnable.

Then it enriches the apps that matter — the ones ranking for the most keywords —
with two things Apple's JSON API does not expose at all: whether the app has
in-app purchases, and its subtitle. Both are needed by Phase 3.

This is the longest phase. It is safe to interrupt; everything is cached, so
re-running picks up where it stopped.

Output: data/02_competitors.csv
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (DATA, Client, banner, days_since, die, load_config,  # noqa: E402
                    log_error, parse_app_page, primary_market)

PHASE = "p2_competition"


def app_row(app: dict, keyword: str, rank: int, market_code: str) -> dict:
    """One app as it appeared for one keyword. Missing values stay None."""
    size = app.get("fileSizeBytes")
    updated = app.get("currentVersionReleaseDate")
    return {
        "keyword": keyword,
        "market": market_code,
        "search_rank": rank,
        "app_id": app.get("trackId"),
        "name": app.get("trackName"),
        "developer": app.get("sellerName") or app.get("artistName"),
        "developer_id": app.get("artistId"),
        "rating": app.get("averageUserRating"),
        "rating_count": app.get("userRatingCount"),
        "price": app.get("price"),
        "formatted_price": app.get("formattedPrice"),
        "release_date": app.get("releaseDate"),
        "last_updated": updated,
        "days_since_update": days_since(updated),
        "genre": app.get("primaryGenreName"),
        "size_mb": round(int(size) / 1_048_576, 1) if size else None,
        # filled in by the enrichment pass below; None means "not looked up",
        # which is different from False and must stay different.
        "subtitle": None,
        "has_iap": None,
        "iap_price_points": None,
        "enriched": False,
    }


def main():
    cfg = load_config()
    comp = cfg["competition"]
    client = Client(cfg, PHASE)
    market = primary_market(cfg)

    kw_path = DATA / "01_keywords.csv"
    if not kw_path.exists():
        die("data/01_keywords.csv not found. Run `python scripts/p1_expand.py` first.")

    kw_df = pd.read_csv(kw_path)
    keywords = (kw_df[kw_df.market == market["code"]]
                .sort_values("autocomplete_rank").keyword.dropna().unique().tolist())
    if not keywords:
        die(f"No {market['code']} keywords in 01_keywords.csv.")

    banner(f"PHASE 2 — COMPETITION   {len(keywords)} keywords x top {comp['top_n_apps']}")
    est = len(keywords) * 60 // cfg["network"]["requests_per_minute"] // 60 + 1
    print(f"\n  Searching {len(keywords)} keywords (~{est} min on a cold run)\n")

    rows: list[dict] = []
    empty_keywords = 0
    for i, kw in enumerate(keywords, 1):
        res = client.search(kw, market, limit=comp["top_n_apps"])
        if not res:
            continue                       # already logged to errors.log
        if not res.data:
            # A genuinely zero-result search is a real finding, not an error:
            # it means nothing at all ranks for this phrase.
            empty_keywords += 1
            log_error(PHASE, f"keyword:{kw}", "search_returned_zero_apps_genuine",
                      market=market["code"])
            continue
        for rank, app in enumerate(res.data, 1):
            rows.append(app_row(app, kw, rank, market["code"]))

        if i % comp["progress_every"] == 0:
            print(f"    {i}/{len(keywords)} keywords · {len(rows)} rows · "
                  f"{len({r['app_id'] for r in rows})} unique apps")
            client.check_failure_rate()

    if not rows:
        client.summary()
        die("No competitor rows collected at all. That is an endpoint problem, not "
            "a finding — run `python scripts/p0_recon.py`.")

    df = pd.DataFrame(rows)

    # ------------------------------------------------------ enrichment pass
    # Only the apps that define niches. See the note in config.yaml.
    top_n = comp.get("enrich_top_apps", 0)
    if top_n:
        freq = Counter(df.app_id.dropna())
        targets = [app_id for app_id, _ in freq.most_common(top_n)]
        names = df.drop_duplicates("app_id").set_index("app_id")["name"].to_dict()

        print(f"\n  Enriching the {len(targets)} most-ranking apps with subtitle + "
              f"in-app purchases (~{len(targets) * 60 // cfg['network']['requests_per_minute'] // 60 + 1} min)\n")

        enriched: dict[int, dict] = {}
        for i, app_id in enumerate(targets, 1):
            res = client.app_page(app_id, market)
            if not res:
                continue
            parsed = parse_app_page(res.data, str(names.get(app_id, "")))
            if parsed is None:
                # Layout changed or we matched the wrong app. Leave the fields
                # null rather than write a neighbouring app's subtitle.
                log_error(PHASE, f"app_page:{app_id}",
                          "page_parse_failed_or_name_mismatch_left_null",
                          market=market["code"])
                continue
            enriched[app_id] = parsed
            if i % comp["progress_every"] == 0:
                print(f"    {i}/{len(targets)} apps enriched")
                client.check_failure_rate()

        for field in ("subtitle", "has_iap", "iap_price_points"):
            df[field] = df.app_id.map(lambda a: enriched.get(a, {}).get(field))
        df["enriched"] = df.app_id.isin(enriched)

    out = DATA / "02_competitors.csv"
    df.to_csv(out, index=False)
    client.summary()

    # --------------------------------------------------------------- report
    banner("PHASE 2 RESULT")
    n_apps = df.app_id.nunique()
    n_enriched = int(df.enriched.sum() and df.drop_duplicates("app_id").enriched.sum())
    print(f"  {len(df):,} keyword x app rows · {n_apps:,} unique apps · "
          f"{df.keyword.nunique():,} keywords covered")
    print(f"  -> {out.relative_to(DATA.parent)}\n")

    if empty_keywords:
        print(f"  {empty_keywords} keyword(s) returned zero apps — genuinely nothing "
              f"ranks for them (logged, not an error)")

    e = df.drop_duplicates("app_id")
    e = e[e.enriched]
    if len(e):
        iap_pct = 100.0 * e.has_iap.fillna(False).mean()
        print(f"  {n_enriched} apps enriched · {iap_pct:.0f}% of them have in-app purchases")
        print("    (this is the monetisation signal Phase 3 uses — a low number here")
        print("     means the niche may simply not make money)")
    else:
        print("  No apps enriched — has_iap and subtitle are null throughout.")
        print("  Phase 3 will have no monetisation signal. Set competition.enrich_top_apps")
        print("  in config.yaml if you want one.")

    print(f"\n  Next: python scripts/p3_score.py")


if __name__ == "__main__":
    main()
