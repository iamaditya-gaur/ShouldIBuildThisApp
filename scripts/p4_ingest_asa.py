"""
p4_ingest_asa.py — build the Apple Search Ads worksheet, then check it back in.

Two modes:

    python scripts/p4_ingest_asa.py --niches "habit tracker,sleep sounds"
        Writes data/04_asa_input.csv for you to fill in by hand.
        See manual/STEP_04_APPLE_SEARCH_ADS.md.

    python scripts/p4_ingest_asa.py
        Validates data/04_asa_filled.csv after you've filled it, and reports
        where Apple's real numbers disagree with my estimates.

The disagreements are the point. Everything before this phase is inferred from
who ranks; Apple Search Ads popularity is measured from actual searches. Where
the two conflict, the measured number wins and my proxy was wrong — and knowing
*which* keywords my proxy got wrong tells you how much to trust the rest of it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, MANUAL, banner, die, load_config, log_error  # noqa: E402

PHASE = "p4_ingest_asa"
REQUIRED = ["keyword", "niche", "my_difficulty_proxy",
            "asa_popularity", "asa_scale", "asa_notes"]
SCALES = {"1-5": (1.0, 5.0), "5-100": (5.0, 100.0)}


# ---------------------------------------------------------------------------
def generate(niches: list[str], per_niche: int) -> None:
    path = DATA / "03_scored.csv"
    if not path.exists():
        die("data/03_scored.csv not found — run `python scripts/p3_score.py` first.")
    scored = pd.read_csv(path)

    known = set(scored.niche.dropna().unique())
    unknown = [n for n in niches if n not in known]
    if unknown:
        die(f"These niches aren't in 03_scored.csv: {unknown}\n"
            f"  Available: {sorted(known)}")

    # Real search phrases only. An app's own name is not something you can
    # research in Apple Search Ads in any useful way.
    pick = scored[scored.niche.isin(niches) & ~scored.probably_app_name.fillna(False)]
    pick = (pick.sort_values("opportunity_proxy", ascending=False)
                .groupby("niche").head(per_niche))

    out = pd.DataFrame({
        "keyword": pick.keyword,
        "niche": pick.niche,
        "my_difficulty_proxy": pick.difficulty_proxy,
        "asa_popularity": "",
        "asa_scale": "",
        "asa_notes": "",
    })
    dest = DATA / "04_asa_input.csv"
    out.to_csv(dest, index=False)

    banner("PHASE 4 — YOUR TURN")
    print(f"\n  Wrote {len(out)} keywords across {out.niche.nunique()} niche(s)")
    print(f"  -> {dest.relative_to(DATA.parent)}\n")
    for niche, g in out.groupby("niche"):
        print(f"    {niche}: {len(g)} keywords")
    print(f"\n  Instructions: {(MANUAL / 'STEP_04_APPLE_SEARCH_ADS.md').relative_to(DATA.parent)}")
    print("  Roughly 30-45 minutes. Save your version as data/04_asa_filled.csv,")
    print("  then run this script again with no arguments.\n")
    print("  Reminder: record whatever number you see and put its scale in")
    print("  asa_scale. Never convert between the 1-5 and 5-100 scales.\n")


# ---------------------------------------------------------------------------
def validate() -> None:
    path = DATA / "04_asa_filled.csv"
    if not path.exists():
        die("data/04_asa_filled.csv not found.\n"
            "  Fill in data/04_asa_input.csv and save it under that name.\n"
            "  See manual/STEP_04_APPLE_SEARCH_ADS.md")

    df = pd.read_csv(path)
    banner(f"PHASE 4 — CHECKING YOUR FILE   ({len(df)} rows)")

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        die(f"Missing column(s): {missing}\n  Expected: {REQUIRED}")

    problems: list[str] = []

    # --- scale ------------------------------------------------------------
    filled = df[df.asa_popularity.notna() & (df.asa_popularity.astype(str) != "")]
    bad_scale = filled[~filled.asa_scale.isin(SCALES)]
    for _, r in bad_scale.iterrows():
        problems.append(f"row '{r.keyword}': asa_scale is {r.asa_scale!r}, "
                        f"expected one of {list(SCALES)}")
        log_error(PHASE, f"keyword:{r.keyword}", f"bad_asa_scale:{r.asa_scale}")

    # --- range ------------------------------------------------------------
    df["asa_popularity"] = pd.to_numeric(df.asa_popularity, errors="coerce")
    for scale, (lo, hi) in SCALES.items():
        sub = df[(df.asa_scale == scale) & df.asa_popularity.notna()]
        out_of_range = sub[(sub.asa_popularity < lo) | (sub.asa_popularity > hi)]
        for _, r in out_of_range.iterrows():
            problems.append(f"row '{r.keyword}': {r.asa_popularity} is outside "
                            f"the {scale} scale — did you mix the two up?")
            log_error(PHASE, f"keyword:{r.keyword}",
                      f"asa_popularity_out_of_range:{r.asa_popularity}:{scale}")

    n_filled = int(df.asa_popularity.notna().sum())
    print(f"\n  {n_filled}/{len(df)} rows have a popularity number "
          f"({len(df) - n_filled} blank — that's fine, blank means 'no data')")
    for scale in SCALES:
        c = int((df.asa_scale == scale).sum())
        if c:
            print(f"    {c} row(s) on the {scale} scale")

    if problems:
        print(f"\n  {len(problems)} problem(s) found:")
        for p in problems[:15]:
            print(f"    - {p}")
        print("  Logged to data/errors.log. Fix and re-run, or continue if they're")
        print("  rows you don't care about.\n")

    if n_filled < 5:
        die("Fewer than 5 usable rows. Phase 7 cannot lean on Apple's data with "
            "this little — fill in more before continuing.")

    # --- disagreement -----------------------------------------------------
    # Rank within each scale separately, so the two scales are never converted
    # into one another. Percentiles are comparable; the raw numbers are not.
    df["asa_percentile_within_scale"] = (
        df.groupby("asa_scale").asa_popularity.rank(pct=True))
    df["difficulty_percentile"] = df.my_difficulty_proxy.rank(pct=True)
    df["disagreement"] = (df.asa_percentile_within_scale
                          - df.difficulty_percentile).round(2)

    dest = DATA / "04_asa_validated.csv"
    df.to_csv(dest, index=False)

    banner("WHERE APPLE'S DATA DISAGREES WITH MY ESTIMATE")
    ok = df.dropna(subset=["disagreement"])

    gaps = ok.nlargest(8, "disagreement")
    gaps = gaps[gaps.disagreement > 0.3]
    traps = ok.nsmallest(8, "disagreement")
    traps = traps[traps.disagreement < -0.3]

    if len(gaps):
        print("\n  POSSIBLE GAPS — Apple says popular, I said easy:")
        print("  (either a genuine opening, or my proxy missed something. Check by hand.)\n")
        for _, r in gaps.iterrows():
            print(f"    {r.keyword[:38]:40} ASA={r.asa_popularity:>6} ({r.asa_scale})"
                  f"  my_difficulty={r.my_difficulty_proxy:>5}  gap={r.disagreement:+.2f}")

    if len(traps):
        print("\n  POSSIBLE TRAPS — Apple says unpopular, I said hard:")
        print("  (a crowded fight over something nobody searches. Usually: drop it.)\n")
        for _, r in traps.iterrows():
            print(f"    {r.keyword[:38]:40} ASA={r.asa_popularity:>6} ({r.asa_scale})"
                  f"  my_difficulty={r.my_difficulty_proxy:>5}  gap={r.disagreement:+.2f}")

    if not len(gaps) and not len(traps):
        print("\n  No strong disagreements. My difficulty proxy broadly tracks Apple's")
        print("  popularity data, which is mild evidence the proxy is behaving.")

    print(f"\n  -> {dest.relative_to(DATA.parent)}")
    print(f"\n  Next: python scripts/p5_reviews.py\n")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--niches", help="comma-separated niche names to export")
    args = ap.parse_args()

    cfg = load_config()
    if args.niches:
        generate([n.strip() for n in args.niches.split(",") if n.strip()],
                 cfg["manual"]["asa_keywords_per_niche"])
    else:
        validate()


if __name__ == "__main__":
    main()
