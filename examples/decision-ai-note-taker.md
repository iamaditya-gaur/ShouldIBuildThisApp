<!--
  Unedited output from run 2 of this pipeline, July 2026. Published as a worked
  example. The niche was killed, so there is nothing here worth keeping private.

  This file was written by an AI analyst reading the CSVs in data/. No script
  generates it. Every number in it traces back to a file the pipeline produced,
  which is the point: you can check the arithmetic yourself.

  Real runs live in runs/ and are gitignored.
-->

# DECISION — "ai note taker"

**Run date:** 2026-07-28 · **Market:** US primary, 7 secondary
**Data:** 560 keywords · 935 apps · 5,489 keyword×app rows · 768 unique reviews
**Phases complete:** 0, 1, 2, 3, 5, 7 · **Not run:** 4 (Apple Search Ads), 6 (revenue) — both need you

---

## VERDICT

# `ai note taker` — KILL

Confidence: **HIGH.** This verdict survived a deliberate adversarial attack that
was specifically instructed to try to break it, including the exact statistical
test that overturned the previous run's recommendation.

**Secondary verdict:** the accessibility / live-captioning pocket, which I
initially reported as the one promising lead, is **NOT a lead**. I was wrong
about it. The reasoning is in §3 and it was my error, not a data problem.

**Nothing in this run clears the bar for a BUILD.** One lead survives at WATCH
(§4) and it is contingent on a measurement you have not taken yet.

---

## 1. THE FINDING THAT DECIDES IT

Not the competition level. The **cohort curve**.

Every app that ranks for the `ai note taker` keyword cluster, grouped by the year
it launched, against how many ratings it has today:

| Launch year | Apps | Median ratings today | Best in cohort |
|---|---|---|---|
| 2019 | 4 | 41,047 | 437,233 |
| 2020 | 4 | 7,063 | 13,652 |
| 2021 | 2 | 7,446 | 13,482 |
| 2022 | 5 | 3,812 | 14,258 |
| 2023 | 15 | 5,920 | 8,919,622 |
| 2024 | 30 | 751 | 44,150 |
| 2025 | **56** | **24** | 51,845 |
| 2026 | **35** | **0** | 50 |

Confidence: **HIGH** — measured directly from `release_date` and `rating_count`
in `02_competitors.csv`, every app in the cluster, no sampling.

Read the last two rows. **Ninety-one developers launched an AI note-taker in
2025-2026. The median one has zero ratings.**

This is not "the market is crowded." Crowded markets still have a middle class.
This is a market where **entry stopped working**, and it stopped working
recently — the 2024 cohort still reached a median of 751, the 2025 cohort
reached 24. Whatever window existed closed somewhere in 2024.

You would be the 92nd person to try this since January 2025, using the same
APIs, against the same incumbents, with less time.

> **Why this replaces my first argument.** I originally justified the kill by
> pointing at ChatGPT (8.9M ratings), Copilot, OneNote and Apple's preinstalled
> Notes and Voice Memos sitting at the top of the results. **That argument was
> weak and the skeptic was right to reject it.** Those five giants account for
> 17 of 1,161 rows — ChatGPT ranks for 3 keywords out of 118, Apple Notes for 1.
> They are noise, not competitors. Removing them changes the difficulty score by
> **0.00**. The cohort curve is the real evidence and it does not depend on them.

---

## 2. SUPPORTING EVIDENCE

| Measure | Value | Confidence | Note |
|---|---|---|---|
| Difficulty | **60.25 — Hard** | HIGH | 2nd hardest of 15 clusters |
| Opportunity | 30.10 | **LOW** | see methodology caveat, §6 |
| Median competitor ratings | 11,021 | HIGH | 7,996 among genuine note-takers only |
| Apps over 10k ratings | 56% | HIGH | 47% among genuine note-takers only |
| Median days since last update | **7** | HIGH | incumbents actively defended |
| Real competitors | Otter (83 kws), Voicenotes (76), Goodnotes (73), Summary (70) | HIGH | these, not the giants |
| Under a *stricter* keyword filter | difficulty **62.95**, median 15,618 | HIGH | the kill strengthens, not weakens |

**`meeting notes` is not a separate market.** 23 of its 27 keywords clustered
into `ai note taker`. Confirmed independently. Do not treat "meetings" as a way
in.

**Apple's autocomplete for your term is 75% app titles** — 77 of 102 suggestions
for `ai note taker`, 74 of 97 for `ai notes`. Developers have already stuffed
your exact phrase into their app names and won those slots. For contrast,
`voice recorder` — a far broader category term — is only 45 of 120. The niche
term is more brand-saturated than the category term, which is backwards from
what an opening looks like.

---

## 3. WHERE I WAS WRONG — the accessibility pocket

I reported `speech to text / deaf` as the highest-opportunity cluster in the run
(50.8, Moderate difficulty) and called it the one real lead. **Retracted.**

The cluster is a scoring artifact:

- `speech to text for deaf` and `speech to text deaf` return **literally the
  same nine apps — Jaccard similarity 1.000.** One query, counted twice, and
  those two rows are half of the four the median was computed over.
- `voice to text dictation` (0.125) and `voicy: speech to text keyboard` (0.118)
  are **both below the clustering algorithm's own 0.15 merge threshold.** They
  were glued in transitively by two text-to-speech apps that have nothing to do
  with captioning.
- Strip those out and the cluster is **1-2 genuine keywords**, not 4. That is
  not enough to build a positioning on.

Confidence: **HIGH** — I re-computed the pairwise Jaccard overlaps myself after
the skeptic flagged it, and reproduced all four numbers.

The app classification held up — I found 8 genuine captioning apps of 25, the
skeptic independently found 7, and the difference is one borderline app. But a
correct classification of an incoherent cluster is still not a finding.

Two further problems the skeptic caught that I had missed:

- **Rylo/Nagish is FCC-subsidised captioned telephone**, like CaptionCall. I had
  counted it as an ordinary competitor. Two of the seven genuine apps are
  therefore funded by a US federal programme and free to the user.
- Two more of the seven have **0 ratings and launched in May 2026**, one of them
  a name-squat on the leader. The actual market is **Live Transcribe, Ava, and
  an abandoned third app.**

Add the platform risk I flagged earlier — **Apple ships Live Captions free and
system-wide in iOS** (this is my own knowledge, not a pipeline measurement) —
and there is no case here.

---

## 4. THE ONE LEAD LEFT — WATCH, not build

**`transcribe speech to text live`**, in the `transcribe audio` cluster.

| | |
|---|---|
| Difficulty | 47.7 — Moderate |
| Median competitor ratings | 1,213 |
| Apps under 1,400 ratings | 6 of 10 |
| Cluster size | 11 targetable keywords (vs 1-2 for the deaf cluster) |
| Review coverage | best in the run — 5 of 5 apps, 592 reviews |

The top-10 for this keyword is genuinely mixed rather than fortified: Transcribe
(10,688), a 3-rating app at rank 2, Live Transcribe (7,419), Transkriptor
(1,054), Transcribe AI (847), a 39-rating app at rank 8, Whisper (385). Two of
the ten have not been updated in over 8 months.

**Why it is WATCH and not BUILD:** it sits inside the same category as the
kill, and it has not been tested against the cohort curve that killed the main
niche. It also fails the same way if demand turns out to be thin — and demand
is precisely what this pipeline cannot measure for free.

**The complaint that would justify it** (from 768 reviews, MEDIUM confidence —
the strongest theme that survived the analyst's own filter):

> **"Never lose the audio."** 50 reviews across 6 apps from **6 different
> developers**: silent mid-session stops, files that transcribe only partway,
> recordings that vanish. This is an engineering-discipline problem, not a
> model-access problem, which is the rare kind a solo developer can actually
> beat a funded team at.

Explicitly rejected as opportunities, and worth knowing why:

- **"Predatory trials / hard cancellation"** — ~110 reviews, the loudest theme
  in the entire dataset. Rejected: it is an App-Store-wide pattern, not a gap
  in this category.
- **"Better AI summaries"** — rejected: Otter's reviewers ask for *less* AI, and
  not one captioning reviewer asks for it at all.

---

## 5. MANDATORY COUNTER-ARGUMENT

The strongest case *against* my own kill, stated as fairly as I can:

1. **The cohort curve may measure the App Store, not this niche.** Apps launched
   in 2026 have had at most seven months to accumulate ratings. Some of that
   collapse is simply age. **Rebuttal:** the 2024 cohort reached a median of 751
   with roughly two years, while the 2023 cohort reached 5,920 with three. The
   decline is steeper than age alone explains, and the 2025 cohort at 24 has had
   long enough to do better than that.

2. **Rating count is not revenue.** A niche full of small apps might still
   contain a quiet earner. **Rebuttal:** true, and this is exactly what Phase 6
   exists to test. It has not been run. This is a real gap in the verdict.

3. **93% of enriched apps have in-app purchases**, which normally signals a
   category people pay for. **Rebuttal — and this one is a caution about my own
   data:** that 93% is **survivorship-biased**. Enrichment selected apps by
   keyword ubiquity, so 100% of apps ranking for more than 10 keywords were
   measured and **0% of the 593 apps that rank for exactly one keyword were.**
   Median enriched app: 7,376 ratings. Median unenriched app: 18. The 93% describes
   the winners, and tells you nothing about whether a new entrant can monetise.

---

## 6. METHODOLOGY LIMITATIONS — read before reusing these scores

Three defects in my own scoring, found by the skeptic and verified by me. They
do not change the verdict but they do bound how much weight the numbers carry.

**1. `opportunity_proxy` is largely a restatement of autocomplete position.**
Measured correlations: opportunity vs autocomplete rank **−0.927**; opportunity
vs difficulty only **−0.247**; and `demand_proxy` vs autocomplete rank
**−1.000**, i.e. demand *is* autocomplete rank, exactly. So the 15-cluster
opportunity ranking is roughly 86% explained by where a phrase sits in Apple's
suggestion list. **Treat every opportunity number in this run as LOW confidence,
including the 50.8 that made me wrong in §3.** Difficulty is measured from real
competitor attributes and is unaffected.

**2. `probably_app_name` is a punctuation detector and leaks about 33%.** 73 of
224 supposedly-generic keywords are competitor brand names (Memio, Vocanote,
Sembly, ZIVO, Quickminutes and others). Three of the 15 clusters do not survive
a strict filter. Keyword *counts* in this run are inflated; the app data behind
them is not affected.

**3. `pct_exact_keyword_in_title` reads subtitles that exist for only 100 of 935
apps**, and it carries 20% of the difficulty weight. Clusters with poor subtitle
coverage score artificially easy. Across the dataset,
`corr(subtitle_coverage, difficulty) = +0.378`. The deaf cluster's coverage was
0.44 against `ai note taker`'s 0.90 — part of why the former looked easier than
it is.

**Fixed during this run:** the Phase 5 coverage table was being written *before*
the throttle-recovery sweeps, so reviews we successfully recovered were reported
as missing — iTranscribe showed 0 reviews while 114 sat on disk. That is the
precise failure this pipeline exists to prevent ("we didn't get it" masquerading
as "there's nothing there"). Corrected at `scripts/p5_reviews.py:151`; the table
was rebuilt from the review files, with `pages_fetched` left null rather than
back-filled with a guess.

---

## 7. WHAT TO DO NEXT

**If you want certainty on the kill — 40 minutes.** Run Phase 4 on the 45
keywords already exported to `data/04_asa_input.csv`. Apple Search Ads popularity
is the only measurement that separates *"nobody has built it"* from *"nobody
wants it"*, and both my verdicts turn on it.

```bash
./venv/bin/python scripts/p4_ingest_asa.py
```

Instructions in `manual/STEP_04_APPLE_SEARCH_ADS.md`. Record the number you see
and its scale; never convert between the 1-5 and 5-100 scales.

**What would overturn each verdict:**

| Verdict | Overturned if |
|---|---|
| `ai note taker` KILL | ASA popularity is high *and* Phase 6 shows mid-band revenue among the small apps — i.e. the 91 recent entrants failed on execution, not on market |
| accessibility NOT a lead | ASA shows real popularity for `speech to text for deaf` — that would mean demand exists and the cluster was merely too small to measure, not empty |
| `transcribe speech to text live` WATCH | ASA popularity is mid-band or better → promote toward BUILD; low → kill it too |

**My honest recommendation:** do not build an AI note-taker. If you want to stay
in this space, spend the 40 minutes on Phase 4 first, and let the popularity
numbers decide between the transcription lead and starting over with new seeds.

**If you would rather re-seed:** the seeds that produced nothing usable this run
were `lecture notes`, `lecture recorder`, `interview transcription` and
`interview recorder` — those users exist but do not search for themselves on the
App Store, so they cannot be reached this way. Pick a category where you have an
unfair advantage instead; this run found no structural opening in note-taking.

---

## 8. SKEPTIC REPORT — VERBATIM

The full adversarial review is at `data/skeptic.md` (551 lines). It was given the
data and my conclusions, instructed to break them, and told that a confirmed kill
was an acceptable outcome. It confirmed Claim 1 while rejecting my reasoning for
it, and broke Claim 2 outright. Its section 7, "WHAT WOULD CHANGE MY MIND",
lists ten specific measurements and is the best guide to what to measure next.

Its own summary of verdicts:

> **Claim 1 (KILL on "ai note taker") survives — but the analyst's stated reason
> for it is wrong.**
> **Claim 2 (accessibility pocket is the one real lead) does not survive.**

---

*Generated by the ASO Opportunity Pipeline. Every number above is traceable to a
file in `data/`. Nothing was estimated: where a value could not be measured it is
recorded as null and the reason is in `data/errors.log`.*
