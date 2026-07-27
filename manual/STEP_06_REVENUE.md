# Step 6 (manual) — Does this niche actually make money?

**Time:** about 30 minutes
**Cost:** free, on a trial you cancel
**Input:** `data/06_revenue_input.csv` (generated for you, max 15 rows)
**Output:** save your filled version as `data/06_revenue_filled.csv`

---

## Why this is the most important manual step

Everything else in this pipeline measures *attention*: what people search for,
who ranks, what users complain about. None of it measures *money*.

A niche can have healthy search demand, weak competition, and stale incumbents —
and still be worthless, because the people searching will never pay. Free data
genuinely cannot tell you the difference. This step is the only one that can.

Fifteen rows. Half an hour. It is worth it.

---

## Getting the data

**Recommended: Appfigures free trial** (`appfigures.com`). Their Explorer view
shows revenue and download estimates per app without needing to connect your own
developer account. AppTweak and Sensor Tower also work; Sensor Tower tends to
gate estimates behind a sales call, so try the others first.

1. Sign up for the free trial.
2. **Set a calendar reminder to cancel before it renews.** Do this now, not later.
   These tools run $50–$100+/month.
3. Find the app search / Explorer / market-intelligence view.
4. Look up each app in `06_revenue_input.csv` by name.
5. Record **monthly revenue** and **monthly downloads** (US, or worldwide — just
   be consistent, and note which in the `source` column).
6. Cancel the trial.

If an app shows no estimate, **leave the cell blank.** Not 0. Blank means "no
data available"; 0 means "this app earns nothing", and confusing the two would
make a healthy niche look dead.

---

## These numbers are estimates. Treat them as orders of magnitude.

Third-party revenue estimates are modelled from download ranks and public
signals, not from Apple's actual books. They are routinely **off by 2–3x in
either direction**, and worse for small apps.

So: **do not** treat $47,000/month as meaningfully different from $52,000/month.
**Do** treat $2,000/month as meaningfully different from $200,000/month. You are
looking for which order of magnitude a niche lives in — nothing finer than that.

---

## How to read the numbers

These bands are for a **solo indie or a very small team**, monetising through
subscriptions or one-off purchases. They describe the **top 5 apps** in a niche,
which is what your input file contains.

### Band 1 — Empty niche
**Top apps under ~$2,000/month each**

Nobody is making real money here. Two possible reasons, and they look identical
from the outside:

- Nobody will pay for this. Most likely.
- Everyone has monetised it badly and there's an opening. Rare, but real.

Assume the first unless you have specific evidence for the second. **Usually a
KILL**, even if search demand looked great — demand without willingness to pay
is a trap that has eaten a lot of indie years.

### Band 2 — The indie sweet spot
**Top apps roughly $5,000 – $50,000/month each**

This is what you want. Proven that people pay. Big enough to support one person
comfortably if you take a slice; too small to attract a funded competitor with a
marketing team.

If you captured even 10–20% of what the #3 app makes, that is a real income.
**This band plus weak competition is the BUILD case.**

### Band 3 — Crowded and valuable
**Top apps roughly $50,000 – $500,000/month each**

Real money, and everyone knows it. Expect professional ASO, paid user
acquisition, and fast feature response. You can still win a *sub-niche* here,
but not the category — and only with a sharp wedge, not a general competitor.

**WATCH, unless your complaint data (Phase 5) shows a specific, badly-served
segment you could own.**

### Band 4 — Don't
**Top apps over ~$500,000/month**

You are looking at venture-funded companies with paid acquisition budgets. The
keywords are contested by people who can outspend you indefinitely. **KILL**, no
matter how good the other signals look.

---

## Two things that matter more than the raw number

**1. Look at the spread, not just the top.**
If app #1 makes $400k and apps #2–5 make under $3k each, that is a
winner-take-all niche — one incumbent owns everything and there is no middle
class to join. That is far more dangerous than five apps each making $30k, which
tells you the category supports multiple players.

**2. Revenue per download.**
Divide monthly revenue by monthly downloads. Under ~$0.30 means the niche
monetises weakly and you'd need enormous volume. Over ~$2.00 means users convert
well, which is much friendlier to a small app that can't buy scale.

---

## Filling in the file

`data/06_revenue_input.csv` is pre-filled with `niche`, `app_id`, `app_name` and
`developer`. You fill:

| Column | What to put |
|---|---|
| `est_monthly_revenue` | number only, no `$` or commas |
| `est_monthly_downloads` | number only |
| `source` | e.g. `appfigures-us`, `apptweak-worldwide` |
| `date_pulled` | `YYYY-MM-DD` |

Blank is always allowed and always better than a guess.

---

## When you're done

Save as `data/06_revenue_filled.csv`, then tell me. That is the last input I
need before writing the final decision.

**And cancel the trial.**
