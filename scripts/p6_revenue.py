"""
p6_revenue.py — build the revenue worksheet, then check it back in.

    python scripts/p6_revenue.py --niches "niche one,niche two"
        Writes data/06_revenue_input.csv, pre-filled with the top apps per
        niche. See manual/STEP_06_REVENUE.md.

    python scripts/p6_revenue.py
        Validates data/06_revenue_filled.csv and reports which band each
        niche falls into.

This is the only phase that can tell you whether a niche makes money. Search
demand, weak competition and stale incumbents can all look great in a category
nobody will pay for, and nothing free can tell the difference.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, MANUAL, banner, die, load_config, log_error  # noqa: E402

PHASE = "p6_revenue"
REQUIRED = ["niche", "app_id", "app_name", "developer", "est_monthly_revenue",
            "est_monthly_downloads", "source", "date_pulled"]

# Bands are per-app monthly revenue for the TOP apps in a niche, framed for a
# solo indie. Reasoning is in manual/STEP_06_REVENUE.md. They are deliberately
# coarse: these estimates are routinely off by 2-3x, so anything finer would be
# false precision.
BANDS = [
    (2_000, "EMPTY", "nobody is making real money here — usually means users won't pay"),
    (50_000, "INDIE SWEET SPOT", "proven people pay, too small to attract funded competitors"),
    (500_000, "CROWDED", "real money and everyone knows it — win a sub-niche or nothing"),
    (float("inf"), "OUT OF REACH", "venture-funded competitors with acquisition budgets"),
]


def band_for(revenue: float) -> tuple[str, str]:
    for ceiling, name, why in BANDS:
        if revenue < ceiling:
            return name, why
    return BANDS[-1][1], BANDS[-1][2]


# ---------------------------------------------------------------------------
def generate(niches: list[str], per_niche: int, max_rows: int) -> None:
    for f in ("02_competitors.csv", "03_scored.csv"):
        if not (DATA / f).exists():
            die(f"data/{f} not found — run the earlier phases first.")
    comp = pd.read_csv(DATA / "02_competitors.csv")
    scored = pd.read_csv(DATA / "03_scored.csv")

    unknown = [n for n in niches if n not in set(scored.niche.dropna())]
    if unknown:
        die(f"Unknown niche(s): {unknown}")

    rows = []
    for niche in niches:
        kws = set(scored[scored.niche == niche].keyword)
        g = comp[comp.keyword.isin(kws)]
        # Same ranking as Phase 5: the apps that rank for the most of the
        # niche's keywords ARE the niche, regardless of raw size.
        freq = (g.groupby(["app_id", "name", "developer"])
                 .agg(kw_hits=("keyword", "nunique"), ratings=("rating_count", "max"))
                 .reset_index()
                 .sort_values(["kw_hits", "ratings"], ascending=False))
        for _, r in freq.head(per_niche).iterrows():
            rows.append({"niche": niche, "app_id": int(r.app_id),
                         "app_name": r["name"], "developer": r.developer,
                         "est_monthly_revenue": "", "est_monthly_downloads": "",
                         "source": "", "date_pulled": ""})

    out = pd.DataFrame(rows).head(max_rows)
    dest = DATA / "06_revenue_input.csv"
    out.to_csv(dest, index=False)

    banner("PHASE 6 — YOUR TURN  (this is a paid data pull, kept deliberately small)")
    print(f"\n  {len(out)} apps across {out.niche.nunique()} niche(s)")
    print(f"  -> {dest.relative_to(DATA.parent)}\n")
    for niche, g in out.groupby("niche"):
        print(f"    {niche}: {', '.join(str(a)[:26] for a in g.app_name)}")
    print(f"\n  Instructions: {(MANUAL / 'STEP_06_REVENUE.md').relative_to(DATA.parent)}")
    print("  ~30 min on a free trial. Cancel it when you're done.")
    print("  Leave a cell BLANK if there's no estimate. Never write 0 —")
    print("  blank means 'unknown', 0 means 'earns nothing'.\n")


# ---------------------------------------------------------------------------
def validate() -> None:
    path = DATA / "06_revenue_filled.csv"
    if not path.exists():
        die("data/06_revenue_filled.csv not found.\n"
            "  Fill in data/06_revenue_input.csv and save it under that name.\n"
            "  See manual/STEP_06_REVENUE.md")

    df = pd.read_csv(path)
    banner(f"PHASE 6 — CHECKING YOUR FILE   ({len(df)} rows)")

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        die(f"Missing column(s): {missing}")

    for col in ("est_monthly_revenue", "est_monthly_downloads"):
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")

    zeros = df[df.est_monthly_revenue == 0]
    for _, r in zeros.iterrows():
        log_error(PHASE, f"app:{r.app_id}", "revenue_entered_as_0_should_be_blank_if_unknown")
    if len(zeros):
        print(f"\n  {len(zeros)} row(s) have revenue exactly 0. If that means 'no")
        print("  estimate available', please blank it instead — 0 is a claim that the")
        print("  app earns nothing, and it will drag the niche's band down.")

    n = int(df.est_monthly_revenue.notna().sum())
    print(f"\n  {n}/{len(df)} rows have a revenue figure")
    if n == 0:
        die("No revenue data at all — Phase 7 cannot assess monetisation.")

    df["revenue_per_download"] = (df.est_monthly_revenue / df.est_monthly_downloads
                                  ).replace([float("inf")], pd.NA).round(2)
    dest = DATA / "06_revenue_validated.csv"
    df.to_csv(dest, index=False)

    banner("WHAT THE MONEY SAYS")
    for niche, g in df.groupby("niche"):
        rev = g.est_monthly_revenue.dropna()
        if rev.empty:
            print(f"\n  {niche}: no data — cannot assess. Not the same as 'no money'.")
            continue
        top = rev.max()
        name, why = band_for(float(rev.median()))
        rpd = g.revenue_per_download.dropna()
        print(f"\n  {niche}")
        print(f"    median ${rev.median():,.0f}/mo · top app ${top:,.0f}/mo · {name}")
        print(f"    {why}")
        if len(rpd):
            v = float(rpd.median())
            verdict = ("weak — you'd need huge volume" if v < 0.30
                       else "healthy — users convert" if v > 2.0 else "workable")
            print(f"    ${v:.2f} revenue per download — {verdict}")
        # Winner-take-all check: one giant and nothing else is far more
        # dangerous than several mid-sized players.
        if len(rev) >= 3 and top > 10 * max(rev.nsmallest(len(rev) - 1).median(), 1):
            print("    WARNING: one app dwarfs the rest — winner-take-all niche,")
            print("    which means there is no middle class for you to join.")

    print(f"\n  -> {dest.relative_to(DATA.parent)}")
    print("\n  Remember these are modelled estimates, routinely off by 2-3x.")
    print("  Read them as orders of magnitude, never as precise figures.\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--niches", help="comma-separated niche names to export")
    args = ap.parse_args()
    cfg = load_config()
    if args.niches:
        generate([n.strip() for n in args.niches.split(",") if n.strip()],
                 cfg["manual"]["revenue_apps_per_niche"],
                 cfg["manual"]["revenue_max_rows"])
    else:
        validate()


if __name__ == "__main__":
    main()
