# iOS ASO Opportunity Pipeline

Takes a few seed topics and works out whether there is a real, winnable App
Store niche underneath them — ending in a written BUILD / WATCH / KILL verdict
with the argument against it included.

It is deliberately slow, deliberately cached, and deliberately stops to ask you
things. It will tell you "none of these are good" if that is the answer.

---

## What this can and cannot tell you

**It can tell you:** which phrases people actually type into App Store search,
how they rank against each other, who currently owns those results, how strong
those incumbents look, whether they've gone stale, and what their users
complain about.

**It cannot tell you** how many people search a term per month. Apple does not
publish that for free. The pipeline uses *autocomplete position* as a stand-in —
Apple orders suggestions by popularity, so rank 1 is more searched than rank 10.
That gives you ordering, not magnitude. Any column ending in `_proxy` is this
kind of estimate.

**It cannot tell you whether the niche makes money.** Nothing free can. That is
what the manual step in Phase 6 is for, and it is the only phase that can
actually answer it.

Everything in the final report is tagged High / Medium / Low confidence with the
phase it came from, so a guess never reads like a fact.

---

## Setup (once)

```bash
cd aso-pipeline && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
```

```bash
cp config.example.yaml config.yaml
```

`config.yaml` is gitignored, because your seed topics are the one genuinely
private thing here — they say which niche you're about to build in.

Then check Apple's endpoints are alive before trusting anything:

```bash
./venv/bin/python scripts/p0_recon.py
```

You want to see `0 dead`. The autocomplete row is the one that matters — if it
is dead, the pipeline has no free demand signal and the rest is not worth
running.

---

## Running it

Set your seed topics first — open `config.yaml` and replace `REPLACE_ME`:

```yaml
seeds:
  - habit tracker
  - sleep sounds
  - meal planner
```

Then run the phases in order. Each one stops and hands back to you.

| | Command | What happens | Your time |
|---|---|---|---|
| 0 | `scripts/p0_recon.py` | Checks Apple's endpoints are alive | 1 min |
| 1 | `scripts/p1_expand.py` | Seeds → a few hundred real keywords | automatic, ~30 min |
| 2 | `scripts/p2_competition.py` | Who ranks for each keyword | automatic, ~40 min |
| 3 | `scripts/p3_score.py` | Scores and groups them into niches | **you pick 2–3 niches** |
| 4 | `scripts/p4_ingest_asa.py` | Apple Search Ads numbers | **~40 min of your clicking** |
| 5 | `scripts/p5_reviews.py` | Mines competitor complaints | automatic, ~30 min |
| 6 | — | Revenue check | **~30 min, needs a free trial** |
| 7 | `scripts/p7_synthesize.py` | The workbook and the verdict | automatic |

The first full run is **2–3 hours of wall clock**, nearly all of it waiting on a
rate limit. It is not a five-minute script. Leave it running.

Every phase can be stopped with Ctrl-C and re-run. Nothing is re-downloaded —
the second run of a phase finishes in under a second.

---

## Changing the run

**Everything is in `config.yaml`.** You should never need to open a `.py` file.
If you want to change something and can't find it there, that's a bug — say so.

The things you're most likely to touch:

- `seeds` — the starting phrases
- `markets` — which countries (US plus 7 others are set up already)
- `expansion.alphabet_fanout_depth` — set to `2` for a much wider keyword net
  and a several-hour run
- `network.requests_per_minute` — **don't raise this.** See below.

---

## When something goes wrong

**Check `data/errors.log` first.** Every skipped keyword and app has a row there
with a reason. Nothing is ever skipped silently.

**"0 keywords" or "no results"** — almost always an endpoint problem, not a
finding about your niche. Run `scripts/p0_recon.py`.

**A phase stopped saying >20% of requests failed** — that is a rate limit, not
data. Wait 15 minutes and re-run. You'll resume, not restart.

**Results look suspiciously empty** — run `scripts/selftest.py`. It checks that
the pipeline is still correctly telling the difference between "zero" and "we
couldn't find out."

### Why the rate limit is so low

Apple doesn't return "too many requests". It returns **success with an empty
body**, which looks exactly like a real answer of zero. Measured on one URL:

```
t+0      empty   (after ~15 rapid requests)
t+120s   empty   — 6 fast retries, 0 recovered
t+300s   fine    — 50 reviews
t+600s   fine
t+1200s  empty again
```

So it's intermittent, and hammering it makes things worse, not better. Going
faster doesn't get you more data — it gets you silence that looks like data.
The pipeline treats every empty response as *missing*, never as *zero*, logs it,
and retries it later after a real wait.

---

## Files

```
config.yaml              everything you can change
scripts/
  common.py              caching, throttling, and the rules that keep data honest
  p0_recon.py … p7_*.py  one per phase
  selftest.py            proves the pipeline fails safely
data/                    intermediate CSVs + the HTTP cache   (not in git)
manual/                  step-by-step guides for the two manual phases
output/                  FINAL_ANALYSIS.xlsx and DECISION.md  (not in git)
```

`data/` and `output/` are gitignored on purpose: they contain your seed topics,
your niche rankings and the app you're about to build. The `*.example.csv` files
show the column layout using a throwaway topic.

---

## A note on the numbers

Apple's endpoints here are public but mostly undocumented, and they change
without warning. That's why `p0_recon.py` exists and why you should re-run it if
anything looks strange.

Nothing in this pipeline is ever estimated to fill a gap. If a value couldn't be
fetched, it is written as empty and explained in `errors.log`. A missing number
is always better than an invented one.
