"""
p3_score.py — score every keyword, group them into niches, rank the niches.

    python scripts/p3_score.py

Two things worth understanding before you trust the output.

**Every number here is a proxy.** Nothing in this phase touches real search
volume or real revenue — it is all inferred from who currently ranks and how
strong they look. Columns ending in `_proxy` are estimates, and the bands
(Very Easy … Very Hard) are the honest resolution of this data. Treat a
difficulty of 41 vs 44 as identical.

**Niches are grouped by which apps rank, not by shared words.** Two phrases with
no words in common can return nearly the same apps, which makes them the same
niche. That is what makes the grouping semantic rather than string matching.

Output: data/03_scored.csv
"""

from __future__ import annotations

import math
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, banner, die, load_config, primary_market  # noqa: E402

PHASE = "p3_score"

# ---------------------------------------------------------------------------
# Weights. These decide which niches surface, so they are stated here in the
# open rather than buried. Each is a share of the 100-point difficulty score.
# ---------------------------------------------------------------------------
WEIGHT_SETS = {
    "base": {
        "rating_count": 30,    # best single proxy for entrenchment
        "pct_over_10k": 20,    # catches "3 giants + 7 minnows", which a median hides
        "exact_in_title": 20,  # most actionable: is anyone even targeting this phrase
        "staleness": 15,       # stale incumbents LOWER difficulty
        "rating": 10,          # happy users are hard to peel away
        "diversity": 5,        # deliberately low — see note below
    },
    # Bets harder on asleep incumbents being the opening.
    "staleness_heavy": {
        "rating_count": 20, "pct_over_10k": 20, "exact_in_title": 20,
        "staleness": 25, "rating": 10, "diversity": 5,
    },
    # Bets harder on pure ASO winnability.
    "title_heavy": {
        "rating_count": 25, "pct_over_10k": 15, "exact_in_title": 30,
        "staleness": 15, "rating": 10, "diversity": 5,
    },
}

# Publisher diversity is kept at 5 on purpose. The usual reading is "low
# diversity = one player dominates = hard". But low diversity just as often
# means one small developer shipping five near-identical apps, which is easy to
# beat. The same number supports opposite conclusions, so it gets little say.
# The raw count is in the output so you can look at it yourself.

BANDS = [(20, "Very Easy"), (35, "Easy"), (50, "Moderate"), (70, "Hard"),
         (101, "Very Hard")]
STOPWORDS = {"app", "apps", "free", "best", "for", "the", "and", "with", "my",
             "pro", "plus", "to", "of", "a", "in", "on", "your", "it"}


def band(score: float | None) -> str | None:
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return None
    for edge, name in BANDS:
        if score < edge:
            return name
    return "Very Hard"


# ---------------------------------------------------------------------------
# Normalisers — each returns 0..1 where 1 means HARDER
# ---------------------------------------------------------------------------
def n_rating_count(median_ratings: float) -> float:
    """Log-scaled: 100 -> 1,000 ratings matters far more than 100k -> 101k."""
    return min(math.log10(1 + max(median_ratings, 0)) / 5.0, 1.0)   # 100k+ = 1.0


def n_staleness(median_days: float) -> float:
    """Fresh incumbents are hard; a top 10 nobody has touched in a year is not."""
    return 1.0 - min(max(median_days, 0) / 365.0, 1.0)


def n_rating(median_rating: float) -> float:
    return min(max((median_rating - 1.0) / 4.0, 0.0), 1.0)


def keyword_in(text: str | None, keyword: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    return keyword.lower().strip() in text.lower()


# ---------------------------------------------------------------------------
def score_keywords(comp: pd.DataFrame, kw: pd.DataFrame, weights: dict) -> pd.DataFrame:
    rows = []
    for keyword, g in comp.groupby("keyword"):
        g = g.sort_values("search_rank").head(10)
        n = len(g)
        if n == 0:
            continue

        ratings_ct = g.rating_count.dropna()
        ratings = g.rating.dropna()
        stale = g.days_since_update.dropna()

        med_ct = float(ratings_ct.median()) if len(ratings_ct) else None
        med_rating = float(ratings.median()) if len(ratings) else None
        med_stale = float(stale.median()) if len(stale) else None
        pct_10k = float((ratings_ct > 10_000).mean()) if len(ratings_ct) else None
        diversity = g.developer.nunique() / n

        # Title always exists; subtitle only for enriched apps. Track coverage so
        # you can see when this signal is running on partial data.
        hits = sum(keyword_in(r["name"], keyword) or keyword_in(r["subtitle"], keyword)
                   for _, r in g.iterrows())
        pct_exact = hits / n
        sub_cov = float(g.subtitle.notna().mean())

        # Any component we could not measure is left out of the weighted mean
        # rather than being treated as zero. Zero would mean "easy", which is a
        # very different claim from "we don't know".
        parts = {
            "rating_count": n_rating_count(med_ct) if med_ct is not None else None,
            "pct_over_10k": pct_10k,
            "exact_in_title": pct_exact,
            "staleness": n_staleness(med_stale) if med_stale is not None else None,
            "rating": n_rating(med_rating) if med_rating is not None else None,
            "diversity": 1.0 - diversity,
        }
        usable = {k: v for k, v in parts.items() if v is not None}
        wsum = sum(weights[k] for k in usable)
        difficulty = (sum(weights[k] * v for k, v in usable.items()) / wsum * 100
                      if wsum else None)

        iap = g.has_iap.dropna()
        rows.append({
            "keyword": keyword,
            "difficulty_proxy": round(difficulty, 1) if difficulty is not None else None,
            "difficulty_band": band(difficulty),
            "n_apps": n,
            "median_rating_count": med_ct,
            "pct_over_10k_ratings": round(pct_10k, 2) if pct_10k is not None else None,
            "publisher_diversity": round(diversity, 2),
            "unique_developers": g.developer.nunique(),
            "median_rating": round(med_rating, 2) if med_rating is not None else None,
            "median_days_since_update": med_stale,
            "pct_exact_keyword_in_title": round(pct_exact, 2),
            "subtitle_coverage": round(sub_cov, 2),
            "iap_pct_proxy": round(float(iap.mean()), 2) if len(iap) else None,
            "iap_apps_measured": len(iap),
            "components_missing": ",".join(k for k, v in parts.items() if v is None) or None,
            "difficulty_inputs": (
                f"med_ratings={med_ct} pct>10k={pct_10k} exact_title={pct_exact:.2f} "
                f"med_stale_days={med_stale} med_rating={med_rating} "
                f"diversity={diversity:.2f}"),
        })

    df = pd.DataFrame(rows)
    ranks = kw.set_index("keyword")["autocomplete_rank"].to_dict()
    df["autocomplete_rank"] = df.keyword.map(ranks)
    # rank 1 -> 1.0, rank 10 -> 0.1. Ordering only; it is not search volume.
    df["demand_proxy"] = ((11 - df.autocomplete_rank.fillna(10)) / 10).clip(0.05, 1.0)
    df["opportunity_proxy"] = (
        df.demand_proxy * (1 - df.difficulty_proxy.fillna(100) / 100) * 100).round(1)
    df["opportunity_inputs"] = (
        "demand=" + df.demand_proxy.round(2).astype(str)
        + " x weakness=" + (1 - df.difficulty_proxy.fillna(100) / 100).round(2).astype(str))
    return df


# ---------------------------------------------------------------------------
def _jaccard(a: set, b: set) -> float:
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def cluster_niches(scored: pd.DataFrame, comp: pd.DataFrame,
                   threshold: float = 0.15, min_size: int = 3) -> pd.DataFrame:
    """Group keywords by which apps rank for them.

    Two keywords are the same niche if the App Store returns substantially the
    same apps — a behavioural definition, not a linguistic one, which is why it
    groups phrases that share no words at all but compete for the same apps.

    Merging is agglomerative: repeatedly join the *most similar* pair of
    clusters until nothing is similar enough. An earlier greedy version walked
    the keywords once and assigned each to the first good-enough cluster, which
    split obviously-related groups purely by accident of ordering: a measured
    pair overlapping 0.30 still landed in separate niches. Order must not
    decide the answer.

    Threshold is 0.15 because even within one niche the top-10 lists only
    partly coincide; measured same-niche overlap ran 0.10-0.30.
    """
    app_sets = {k: set(g.app_id.dropna()) for k, g in comp.groupby("keyword")}
    clusters = [{"keywords": [k], "apps": s} for k, s in app_sets.items() if s]

    while len(clusters) > 1:
        best, best_sim = None, threshold
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                sim = _jaccard(clusters[i]["apps"], clusters[j]["apps"])
                if sim >= best_sim:
                    best, best_sim = (i, j), sim
        if best is None:
            break
        i, j = best
        clusters[i]["keywords"] += clusters[j]["keywords"]
        clusters[i]["apps"] |= clusters[j]["apps"]
        clusters.pop(j)

    # Absorb stragglers into their nearest neighbour. A one-keyword "niche"
    # ranking #1 is noise presented as a finding.
    small = [c for c in clusters if len(c["keywords"]) < min_size]
    big = [c for c in clusters if len(c["keywords"]) >= min_size]
    for c in small:
        if not big:
            big.append(c)
            continue
        host = max(big, key=lambda b: _jaccard(c["apps"], b["apps"]))
        if _jaccard(c["apps"], host["apps"]) > 0:
            host["keywords"] += c["keywords"]
            host["apps"] |= c["apps"]
        else:
            big.append(c)          # genuinely unrelated to anything — keep it
    clusters = big

    appish = set(scored.loc[scored.probably_app_name.fillna(False), "keyword"]) \
        if "probably_app_name" in scored.columns else set()

    # Name each niche after a real keyword from inside it, rather than by
    # stitching together its commonest words. Assembling tokens produced
    # "drinking stop" and "money save" — readable only if you already knew what
    # they meant. The shortest keyword containing the niche's dominant word is
    # both real and usually the plain-English version of the niche.
    seed_of = scored.set_index("keyword")["seed"].to_dict() \
        if "seed" in scored.columns else {}

    seen: dict[str, int] = {}
    final = {}
    for c in clusters:
        naming = [k for k in c["keywords"] if k not in appish] or c["keywords"]

        # The seed that most of this cluster descends from. Seeds are phrases
        # you chose and understand, so they make far better labels than either
        # stitched-together tokens or whichever app title happened to be
        # shortest — an earlier version named a niche after an app title,
        # because the seed itself had clustered elsewhere.
        seeds = Counter(seed_of.get(k) for k in naming if seed_of.get(k))
        base = seeds.most_common(1)[0][0] if seeds else min(naming, key=len)

        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            # Same seed, genuinely different app cluster — distinguish it by
            # what its keywords talk about that the seed does not.
            seed_words = set(re.findall(r"[a-z]+", base.lower()))
            extra = Counter(t for k in naming
                            for t in re.findall(r"[a-z]+", k.lower())
                            if t not in STOPWORDS and t not in seed_words and len(t) > 2)
            qualifier = extra.most_common(1)[0][0] if extra else str(seen[base])
            base = f"{base} / {qualifier}"
        for k in c["keywords"]:
            final[k] = base

    return scored.assign(niche=scored.keyword.map(final))


def summarise_niches(scored: pd.DataFrame) -> pd.DataFrame:
    real = scored[~scored.probably_app_name.fillna(False)].dropna(subset=["niche"])
    if real.empty:
        return pd.DataFrame()
    g = real.groupby("niche")

    # Highest-opportunity keyword per niche. Done with idxmax rather than
    # groupby.apply because the apply signature has churned across pandas
    # versions and this has to keep working on whatever the user has installed.
    best = (real.sort_values("opportunity_proxy", ascending=False)
                .drop_duplicates("niche").set_index("niche")["keyword"])

    out = pd.DataFrame({
        "keywords": g.size(),
        "opportunity_proxy": g.opportunity_proxy.median().round(1),
        "difficulty_proxy": g.difficulty_proxy.median().round(1),
        "median_rating_count": g.median_rating_count.median(),
        "median_days_since_update": g.median_days_since_update.median(),
        "pct_exact_in_title": g.pct_exact_keyword_in_title.median().round(2),
        "iap_pct_proxy": g.iap_pct_proxy.median().round(2),
        "iap_apps_measured": g.iap_apps_measured.sum(),
        "top_keyword": best,
    }).reset_index()
    out["difficulty_band"] = out.difficulty_proxy.map(band)
    return out.sort_values("opportunity_proxy", ascending=False)


# ---------------------------------------------------------------------------
def main():
    cfg = load_config()
    market = primary_market(cfg)

    for f in ("01_keywords.csv", "02_competitors.csv"):
        if not (DATA / f).exists():
            die(f"data/{f} not found — run the earlier phases first.")

    kw = pd.read_csv(DATA / "01_keywords.csv")
    kw = kw[kw.market == market["code"]].drop_duplicates("keyword")
    comp = pd.read_csv(DATA / "02_competitors.csv")
    comp = comp[comp.market == market["code"]]

    banner(f"PHASE 3 — SCORE   {comp.keyword.nunique()} keywords, "
           f"{comp.app_id.nunique()} apps")

    scored = score_keywords(comp, kw, WEIGHT_SETS["base"])
    flags = kw.set_index("keyword")["probably_app_name"].to_dict() \
        if "probably_app_name" in kw.columns else {}
    scored["probably_app_name"] = scored.keyword.map(flags).fillna(False)
    scored["seed"] = scored.keyword.map(kw.set_index("keyword")["seed"].to_dict())
    scored = cluster_niches(scored, comp)

    out = DATA / "03_scored.csv"
    scored.sort_values("opportunity_proxy", ascending=False).to_csv(out, index=False)

    niches = summarise_niches(scored)

    # --------------------------------------------------- sensitivity check
    # Does the ranking survive a different opinion about the weights? A niche
    # that only wins under one weighting is not a robust finding.
    alt_ranks = {}
    for name, w in WEIGHT_SETS.items():
        if name == "base":
            continue
        alt = score_keywords(comp, kw, w)
        alt["probably_app_name"] = alt.keyword.map(flags).fillna(False)
        # `seed` must be carried over or the niches get named differently and
        # the comparison silently compares nothing.
        alt["seed"] = alt.keyword.map(kw.set_index("keyword")["seed"].to_dict())
        alt = cluster_niches(alt, comp)
        alt_ranks[name] = {r.niche: i + 1 for i, r in
                           enumerate(summarise_niches(alt).itertuples())}

    # A niche resting on one or two keywords is not a niche, it is a keyword.
    # Ranking one #3 would put noise in front of you dressed as a finding.
    MIN_KEYWORDS = 3
    ranked = niches[niches.keywords >= MIN_KEYWORDS]
    thin = niches[niches.keywords < MIN_KEYWORDS]

    banner("TOP NICHES  (median across each niche's keywords)")
    top = ranked.head(8).reset_index(drop=True)

    print(f"\n  {'#':<3}{'niche':22}{'kws':>4}{'opp':>6}{'diff':>6}  "
          f"{'band':11}{'IAP%':>6}{'stale_d':>8}  {'rank if weights change':<24}")
    print("  " + "-" * 100)
    for i, r in top.iterrows():
        iap = f"{r.iap_pct_proxy * 100:.0f}%" if pd.notna(r.iap_pct_proxy) else "n/a"
        stale = f"{r.median_days_since_update:.0f}" if pd.notna(r.median_days_since_update) else "n/a"
        shifts = " / ".join(f"{n.split('_')[0]}:#{alt_ranks[n].get(r.niche, '-')}"
                            for n in alt_ranks)
        print(f"  {i+1:<3}{str(r.niche)[:21]:22}{r.keywords:>4}"
              f"{r.opportunity_proxy:>6.0f}{r.difficulty_proxy:>6.0f}  "
              f"{r.difficulty_band:11}{iap:>6}{stale:>8}  {shifts:<24}")

    if len(thin):
        print(f"\n  {len(thin)} niche(s) held back for having under {MIN_KEYWORDS} "
              f"keywords — too thin to rank, listed in 03_scored.csv:")
        print(f"    {', '.join(thin.niche.head(6))}")

    print(f"\n  -> {out.relative_to(DATA.parent)}")
    print("\n  'rank if weights change' shows where each niche lands under the two")
    print("  alternative weightings. A niche that moves a lot is a weighting")
    print("  artifact, not a finding. One that stays put is robust.\n")

    n_missing_iap = int(niches.iap_apps_measured.eq(0).sum())
    if n_missing_iap:
        print(f"  {n_missing_iap} niche(s) have no in-app-purchase data at all — their")
        print("  IAP column is 'n/a', not 0. Do not read that as 'does not monetise'.\n")


if __name__ == "__main__":
    main()
