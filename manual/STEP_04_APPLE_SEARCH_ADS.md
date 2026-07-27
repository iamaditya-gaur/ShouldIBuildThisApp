# Step 4 (manual) — Apple Search Ads keyword popularity

**Time:** about 30–45 minutes
**You need:** a free Apple Search Ads account (an Apple ID and, at some point in
signup, a payment card — you will not be charged unless you actually run a campaign)
**Input:** `data/04_asa_input.csv` (generated for you)
**Output:** save your filled version as `data/04_asa_filled.csv`

---

## Why this step exists

Everything up to now rests on **autocomplete position** — where a phrase sits in
Apple's suggestion list. That tells you the *order* of demand. It does not tell
you the *size* of it. A keyword ranked #1 might be searched a million times a
month or four hundred times; autocomplete cannot tell you which.

Apple Search Ads is the only free source that gives you a real popularity
number, straight from Apple, based on actual searches. It is the single most
valuable data point in this entire pipeline.

Everything before this is a proxy. This is evidence.

---

## Honest warning about the instructions below

**I cannot see Apple's current interface, and it changes.** The click path below
is my best understanding, but treat it as a starting direction rather than gospel.
If a menu is not where I say it is, look around — the feature exists, it just may
have moved or been renamed.

What you are looking for is a **keyword popularity or search-volume indicator**,
usually shown when you are adding or researching keywords for a campaign.

### Roughly where to look

1. Go to `searchads.apple.com` and sign in.
2. You will land in either **Apple Search Ads Basic** or **Advanced**. You want
   **Advanced** — Basic hides keyword-level tooling. If you only see Basic, look
   for a way to switch or upgrade (it's free to have; cost only comes from
   running campaigns).
3. Start creating a campaign — **you do not have to finish or launch it.** The
   keyword tooling appears during setup.
   - Pick any app, any country (set the country to **United States**, since that
     is what `config.yaml` uses as the primary market).
4. Find the **Keywords** step, and the search/suggestion box within it.
5. Type in one of your keywords. You should see a **popularity** figure next to it.
6. Record that number.

If you get stuck for more than a few minutes, search "Apple Search Ads keyword
popularity" — Apple's own help pages track the current UI better than I can.

**Do not launch the campaign.** You are only here for the numbers. There is no
need to enter a budget or set anything live.

---

## The scale trap — read this before you record anything

There are **two different popularity scales in the wild** and they are not
convertible:

| Where you're looking | Scale |
|---|---|
| Apple Search Ads itself (Apple's own docs) | **1 to 5** |
| Third-party tools (AppTweak, Appfigures, Sensor Tower, MobileAction…) | **5 to 100** |

These measure the same underlying idea but publish it differently, and the
mapping between them is **not** public or linear.

**So: write down whatever number you actually see, and put which scale it was in
the `asa_scale` column.** Do not convert. Do not normalise. Do not "adjust" a 4
into an 80. If half your rows are one scale and half the other, that is fine —
the column tells us which is which, and Phase 7 handles them separately.

A converted number is a fabricated number, and it will quietly poison the final
recommendation.

---

## What "good" looks like for a solo indie

The instinct is to chase the highest-popularity keyword. **That is how indie apps
lose.** The highest-popularity keywords are where the funded companies with
marketing budgets already are, and you will never outrank them.

What you actually want:

| | 1–5 scale | 5–100 scale | Why |
|---|---|---|---|
| **Too small** | under 2 | under 15 | Real, but nobody's searching. You'd rank #1 for nothing. |
| **The sweet spot** | **2.5 – 4** | **25 – 55** | Enough people searching to matter, not enough to attract serious money. |
| **Danger zone** | 4.5+ | 70+ | Big, valuable, and already owned. You are bidding against companies with staff. |

Then cross-reference with the difficulty proxy already in your file: **mid
popularity + low difficulty is the target.** High popularity + low difficulty
usually means the difficulty proxy is wrong, not that you found a gift — flag
those rather than trusting them.

---

## Filling in the file

Open `data/04_asa_input.csv`. It has these columns:

| Column | Who fills it | Notes |
|---|---|---|
| `keyword` | done | |
| `niche` | done | |
| `my_difficulty_proxy` | done | my estimate, from Phase 3 |
| `asa_popularity` | **you** | the raw number you see |
| `asa_scale` | **you** | `1-5` or `5-100` |
| `asa_notes` | **you** | optional — anything odd |

**If a keyword isn't found in Apple Search Ads, leave `asa_popularity` blank.**
Do not put 0. Blank means "no data"; 0 means "nobody searches this", and those
are very different things. If you want, note why in `asa_notes`.

Work through the list top-down. If you run out of patience, **stop and save** —
partial data is genuinely useful, and the ingest script handles gaps. Getting
30 good rows beats guessing at 60.

---

## When you're done

Save the file as:

```
data/04_asa_filled.csv
```

Keep the same column names. Then run:

```bash
./venv/bin/python scripts/p4_ingest_asa.py
```

That checks your file, and — the interesting part — flags any keyword where
**Apple's real popularity strongly disagrees with my difficulty estimate.**
Those disagreements are the most valuable rows in the whole dataset:

- **Apple says popular, I said easy** → either a genuine gap, or my proxy missed
  something. Worth looking at by hand.
- **Apple says unpopular, I said hard** → a crowded fight over nothing. Drop it.

Tell me when the file is saved and I'll take it from there.
