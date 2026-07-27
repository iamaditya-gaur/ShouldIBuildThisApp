"""
p5_reviews.py — pull competitor reviews so we can find out what users hate.

    python scripts/p5_reviews.py --niches "habit tracker,sleep sounds"

Ratings tell you an app is disliked. Reviews tell you *why*, and "why" is what
you can actually build against. This phase collects the 1-3 star reviews for the
top apps in each niche and writes them to disk for analysis.

About Apple's review feed: it returns HTTP 200 with an empty body when it is
throttling, which is indistinguishable from "this app has no reviews" unless you
check. So before recording any app as having no complaints, this cross-checks
the rating count from the lookup endpoint. An app with 40,000 ratings and an
empty feed is being throttled, and gets queued for a later sweep rather than
written down as a zero.

Output: data/reviews/<niche>.jsonl  (raw, for the analyst)
        data/05_review_stats.csv    (what we got vs what we missed)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (DATA, Client, CooldownQueue, banner, die, load_config,  # noqa: E402
                    log_error, primary_market)

PHASE = "p5_reviews"
REVIEW_DIR = DATA / "reviews"


def extract(entry: dict) -> dict | None:
    """One review out of Apple's deeply nested RSS JSON."""
    try:
        return {
            "rating": int(entry["im:rating"]["label"]),
            "title": entry.get("title", {}).get("label", ""),
            "body": entry.get("content", {}).get("label", ""),
            "version": entry.get("im:version", {}).get("label"),
            "updated": entry.get("updated", {}).get("label"),
        }
    except (KeyError, TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--niches", required=True, help="comma-separated niche names")
    args = ap.parse_args()
    niches = [n.strip() for n in args.niches.split(",") if n.strip()]

    cfg = load_config()
    rv_cfg = cfg["reviews"]
    net = cfg["network"]
    client = Client(cfg, PHASE)
    market = primary_market(cfg)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    for f in ("02_competitors.csv", "03_scored.csv"):
        if not (DATA / f).exists():
            die(f"data/{f} not found — run the earlier phases first.")
    comp = pd.read_csv(DATA / "02_competitors.csv")
    scored = pd.read_csv(DATA / "03_scored.csv")

    unknown = [n for n in niches if n not in set(scored.niche.dropna())]
    if unknown:
        die(f"Unknown niche(s): {unknown}\n  Available: {sorted(set(scored.niche.dropna()))}")

    banner(f"PHASE 5 — COMPLAINT MINING   {len(niches)} niche(s)")

    # ---- pick the apps that actually define each niche --------------------
    targets: list[dict] = []
    for niche in niches:
        kws = set(scored[scored.niche == niche].keyword)
        g = comp[comp.keyword.isin(kws)]
        # Rank by how many of the niche's keywords each app ranks for, then by
        # size. An app that shows up everywhere IS the niche, whatever its
        # rating count says.
        freq = (g.groupby(["app_id", "name"])
                 .agg(kw_hits=("keyword", "nunique"),
                      ratings=("rating_count", "max"))
                 .reset_index()
                 .sort_values(["kw_hits", "ratings"], ascending=False))
        for _, r in freq.head(rv_cfg["apps_per_niche"]).iterrows():
            targets.append({"niche": niche, "app_id": int(r.app_id),
                            "name": r["name"], "known_ratings": r.ratings})

    print(f"\n  {len(targets)} apps across {len(niches)} niche(s), "
          f"up to {rv_cfg['max_pages']} pages each")
    for niche in niches:
        apps = [t for t in targets if t["niche"] == niche]
        print(f"    {niche}: {', '.join(str(a['name'])[:26] for a in apps)}")

    # ---- fetch -----------------------------------------------------------
    reviews: dict[str, list] = {n: [] for n in niches}
    stats: list[dict] = []
    cooldown = CooldownQueue(net["empty_response_cooldown_seconds"],
                             net["empty_response_max_sweeps"])

    def fetch_page(job) -> bool:
        app, page = job
        res = client.reviews(app["app_id"], page, market)
        if not res:
            return False
        for entry in res.data:
            r = extract(entry)
            if r and rv_cfg["min_star"] <= r["rating"] <= rv_cfg["max_star"]:
                r["app_id"] = app["app_id"]
                r["app_name"] = app["name"]
                reviews[app["niche"]].append(r)
        return True

    print()
    for i, app in enumerate(targets, 1):
        got_pages, empty_pages = 0, 0
        for page in range(1, rv_cfg["max_pages"] + 1):
            if fetch_page((app, page)):
                got_pages += 1
            else:
                empty_pages += 1
                cooldown.add((app, page))
                # Apple stops paginating past the end. Two empties in a row on
                # a small app usually means we've reached it, not throttling —
                # the cross-check below tells the two apart.
                if empty_pages >= 2 and got_pages > 0:
                    break

        known = app["known_ratings"]
        if got_pages == 0 and pd.notna(known) and known > 100:
            # This is the failure mode that matters: the app plainly has
            # reviews, so an empty feed is Apple throttling us, not evidence.
            log_error(PHASE, f"app:{app['app_id']}",
                      f"no_reviews_but_app_has_{int(known)}_ratings_THROTTLED",
                      market=market["code"])

        stats.append({"niche": app["niche"], "app_id": app["app_id"],
                      "app_name": app["name"], "known_rating_count": known,
                      "pages_fetched": got_pages,
                      "reviews_kept": sum(1 for r in reviews[app["niche"]]
                                          if r["app_id"] == app["app_id"])})
        print(f"    [{i}/{len(targets)}] {str(app['name'])[:32]:34} "
              f"{got_pages} pages")
        client.check_failure_rate()

    # ---- re-sweep whatever came back empty --------------------------------
    if cooldown.items:
        leftover = cooldown.sweep(fetch_page, label="from the review feed")
        for app, page in leftover:
            log_error(PHASE, f"reviews:{app['app_id']}:p{page}",
                      "empty_after_all_cooldown_sweeps", market=market["code"])

    # ---- write ------------------------------------------------------------
    written = []
    for niche, rows in reviews.items():
        if not rows:
            print(f"\n  No reviews collected for {niche!r} — see data/errors.log. "
                  "This is missing data, NOT 'users have no complaints'.")
            continue
        path = REVIEW_DIR / f"{niche.replace('/', '-').replace(' ', '_')}.jsonl"
        with open(path, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        written.append((niche, len(rows), path))

    pd.DataFrame(stats).to_csv(DATA / "05_review_stats.csv", index=False)
    client.summary()

    banner("PHASE 5 — RAW REVIEWS COLLECTED")
    for niche, n, path in written:
        print(f"  {niche:22} {n:5} reviews (1-{rv_cfg['max_star']}star)  "
              f"-> {path.relative_to(DATA.parent)}")
    print(f"\n  -> data/05_review_stats.csv")
    print("\n  Next: the review-analyst sub-agent reads these and writes")
    print("  data/05_complaints.md. Nothing here enters the main analysis")
    print("  until it has been clustered.\n")


if __name__ == "__main__":
    main()
