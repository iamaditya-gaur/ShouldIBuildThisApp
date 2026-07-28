# Should I Build This App? 📱

A research pipeline that answers one question before you write a line of code: is there a real App Store niche here, or are you about to spend six months on nothing?

![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)
![License](https://img.shields.io/badge/license-MIT-green)
![API keys](https://img.shields.io/badge/API%20keys-none%20needed-orange)
![Cost](https://img.shields.io/badge/cost-%240-lightgrey)

It is deliberately slow, deliberately cached, and it stops to ask you things. Of the four niches it has judged so far, three came back KILL and one WATCH. Nothing has cleared BUILD yet. A tool that talks you out of building is more useful than one that talks you into it.

---

## What it does 🔍

You give it a few phrases people might type into App Store search. It comes back with:

* which phrases actually get typed, and roughly in what order of popularity
* who currently ranks for them, how entrenched those apps look, and whether they have gone stale
* what users complain about in the incumbents' one to three star reviews
* a written **BUILD / WATCH / KILL** verdict, with the strongest argument against itself included

Every claim in the final report carries a confidence level and the file it came from. A guess never gets to read like a fact.

**What it cannot tell you:** how many people search a term per month. Apple does not publish that for free. The pipeline uses autocomplete position as a stand-in, because Apple orders suggestions by popularity, so rank 1 is searched more than rank 10. That gives you ordering, not magnitude. Any column ending in `_proxy` is this kind of estimate.

**What it cannot tell you without your help:** whether the niche makes money. Nothing free can. That is what the manual step in Phase 6 is for, and it is the only phase that can actually answer it.

---

## Why I built it 🤔

Every app store optimisation tool I could find optimises an app you have already shipped. Keyword rankings, listing conversion, competitor tracking. All of it assumes the hard decision is behind you.

The decision I actually needed help with was the one before that. Not "how do I rank for this", but "should I be in this market at all". The tools that answer that question cost real money per month and still hand you a dashboard rather than an answer.

There was a second problem, and it turned out to be the interesting one. Apple's public endpoints do not return a "too many requests" error when you go too fast. They return a perfectly valid, successful, completely empty response. That looks exactly like "this market is empty". Take it at face value and you get a confident recommendation to enter a market that does not exist.

So most of this project is not scraping. It is the machinery that stops me from believing bad data.

---

## A real run 📉

Run 2 studied `ai note taker`. 560 keywords, 935 apps, 5,489 keyword by app rows, 768 reviews. Verdict: **KILL**, high confidence.

The finding that decided it was not the competition level. It was the cohort curve: every app in the cluster grouped by the year it launched, against how many ratings it has today.

| Launch year | Apps | Median ratings today |
|---|---|---|
| 2019 | 4 | 41,047 |
| 2022 | 5 | 3,812 |
| 2023 | 15 | 5,920 |
| 2024 | 30 | 751 |
| **2025** | **56** | **24** |
| **2026** | **35** | **0** |

Ninety-one developers launched an AI note taker in 2025 and 2026. The median one has zero ratings. That is not a crowded market, because crowded markets still have a middle class. That is a market where entry stopped working, and it stopped working recently.

Two things I want to point at in that run, because they are the reason I trust the output:

**The run overturned its own headline finding.** I had reported an accessibility and live captioning pocket as the one promising lead. An adversarial pass, instructed to break the conclusions, showed the cluster was a scoring artifact: two of its keywords were the same query counted twice, and two more had been glued in below the clustering algorithm's own merge threshold. The lead was retracted in the final document, in writing, as my error.

**It also rejected my stated reason for the kill.** I had blamed ChatGPT, Copilot, OneNote, Apple Notes and Voice Memos sitting at the top of the results. Those five apps turned out to account for 17 of 1,161 rows. Removing them changed the difficulty score by 0.00. The kill was right, the argument for it was not, and the document says so.

Full verdict document: [`examples/decision-ai-note-taker.md`](examples/decision-ai-note-taker.md).

---

## How it works 🧩

```
   config.yaml   your seed phrases, the only file you edit
        │
   ┌────▼─────┐
   │ p0 recon │  are Apple's endpoints alive today?              1 min
   └────┬─────┘
   ┌────▼─────┐
   │ p1 expand│  seeds to ~1,000 real keywords                   ~30 min
   └────┬─────┘
   ┌────▼─────┐
   │ p2 compet│  for each keyword, the top 10 apps and their     ~40 min
   └────┬─────┘  ratings, freshness, pricing, paywall
   ┌────▼─────┐
   │ p3 score │  difficulty 0-100, keywords grouped into niches  seconds
   └────┬─────┘
        │
      ⏸  GATE       a human picks 2 to 4 niches to go deep on
        │
   ┌────┴───────────────┬────────────────────┐
   │                    │                    │
┌──▼────────┐   ┌───────▼──────┐   ┌─────────▼───┐
│ p4 search │   │ p5 reviews   │   │ p6 revenue  │
│ ads       │   │ 1-3 star     │   │             │
│ BY HAND   │   │ complaints   │   │ BY HAND     │
│ ~40 min   │   │ ~30-60 min   │   │ ~30 min     │
└──┬────────┘   └───────┬──────┘   └─────────┬───┘
   └────────────────────┼────────────────────┘
                 ┌──────▼──────┐
                 │p7 synthesize│  builds the Excel workbook
                 └──────┬──────┘
                        │
          FINAL_ANALYSIS.xlsx  +  DECISION.md (written by the analyst)
```

Every phase can be stopped with Ctrl-C and re-run. Nothing is downloaded twice, so the second run of a phase finishes in about a second.

| | Script | What it does | Your time |
|---|---|---|---|
| 0 | `p0_recon.py` | Checks Apple's endpoints are answering | 1 min |
| 1 | `p1_expand.py` | Seeds become a few hundred real keywords | automatic |
| 2 | `p2_competition.py` | Who ranks for each keyword, and how strong they are | automatic |
| 3 | `p3_score.py` | Scores difficulty, groups keywords into niches | **you pick 2 to 4** |
| 4 | `p4_ingest_asa.py` | Apple Search Ads popularity | **~40 min of clicking** |
| 5 | `p5_reviews.py` | Mines competitor complaints | automatic |
| 6 | `p6_revenue.py` | Revenue check | **~30 min, needs a free trial** |
| 7 | `p7_synthesize.py` | The workbook | automatic |

A first full run is 2 to 3 hours of wall clock, nearly all of it waiting on a self-imposed rate limit. See [why it is that slow](#why-does-a-run-take-three-hours).

---

## Quickstart ⚡

```bash
git clone https://github.com/iamaditya-gaur/ShouldIBuildThisApp.git
cd ShouldIBuildThisApp
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp config.example.yaml config.yaml
```

Check Apple is answering before you trust anything downstream:

```bash
./venv/bin/python scripts/p0_recon.py
```

You want `0 dead`. The autocomplete row is the one that matters. If it is dead, the pipeline has no free demand signal and the rest is not worth running.

Now open `config.yaml` and replace the seed phrases:

```yaml
seeds:
  - habit tracker
  - sleep sounds
  - meal planner
```

Use 3 to 6 seeds. Short phrases, the way a real person types them into search. Two words is usually right.

> **The expensive lesson from run 2:** a seed has to be something a person *types*, not a description of the task. `interview transcription` returned literally zero keywords, because nobody searches for that. Those users exist. They just do not describe themselves that way.

Then run the phases in order:

```bash
./venv/bin/python scripts/p1_expand.py
./venv/bin/python scripts/p2_competition.py
./venv/bin/python scripts/p3_score.py
```

Phase 3 prints a ranked table of niches and stops. Pick 2 to 4 and pass them on:

```bash
./venv/bin/python scripts/p5_reviews.py --niches "habit tracker,sleep sounds"
./venv/bin/python scripts/p7_synthesize.py --niches "habit tracker,sleep sounds"
```

Phases 4 and 6 are the manual ones. Run `p4_ingest_asa.py --niches "..."` and `p6_revenue.py --niches "..."` to get the worksheets, fill them in following [`manual/`](manual/), then run each script again with no arguments to check the numbers back in.

`config.yaml` is gitignored, because your seed topics are the one genuinely private thing here. They say which niche you are about to build in.

---

## What is code and what is AI 🤖

I run this through Claude Code, so it is fair to ask how much of the output is computed and how much is a language model talking. Here is the honest split.

| Output | Who produces it | Reproducible? |
|---|---|---|
| `01_keywords.csv`, `02_competitors.csv` | Python. Downloads, nothing else. | Yes, exactly |
| `03_scored.csv`, difficulty, clustering | Python. Fixed arithmetic. | Yes, exactly |
| `data/reviews/*.jsonl` | Python. Raw review text. | Yes, exactly |
| `FINAL_ANALYSIS.xlsx` | Python (`p7_synthesize.py`) | Yes, exactly |
| Picking which niches to go deep on | Human, with AI input | No, it is a judgment call |
| `04_asa_filled.csv`, `06_revenue_filled.csv` | Human, typed in by hand | No, you collected it |
| `05_complaints.md` (complaint themes) | AI reading the raw reviews | In shape, not word for word |
| `skeptic.md` (the adversarial pass) | AI attacking its own conclusions | In shape, not word for word |
| `DECISION.md` (the verdict) | AI writing from the CSVs | In shape, not word for word |

The short version: **the numbers are deterministic, the narrative is not.** No script writes `DECISION.md`. Every claim in it names the file it came from, which is what makes it checkable rather than plausible.

---

## Stack 🛠️

Deliberately boring, which is the point.

* **Python 3.11+**
* **requests** for HTTP. No browser, no Selenium, no scraping framework.
* **pandas** for the CSVs
* **openpyxl** to write the Excel workbook
* **PyYAML** for the config
* **SQLite** as the HTTP cache, one file at `data/cache.db`
* **Apple's own public endpoints:** search autocomplete, app search, app lookup, the reviews RSS feed, and the top charts feed

No database server, no cloud, no API keys, no paid data source, no LLM framework. It runs on a laptop and costs nothing.

---

## Decisions I made on purpose 🧠

**1. Silence is treated as missing, never as zero.**
Apple does not return "429 Too Many Requests". It returns HTTP 200 with an empty body, which is indistinguishable from a real answer of nothing. Measured on one URL:

```
t+0      empty   (after ~15 rapid requests)
t+120s   empty   6 fast retries, 0 recovered
t+300s   fine    50 reviews
t+600s   fine
t+1200s  empty again
```

Note the last line. This is not a clean cooldown you can wait out. So a response is only cached if it passes a shape check for its endpoint, an empty response produces `None` and never a `0`, and everything that came back empty goes on a queue to be retried after a real wait.

**2. The cache is keyed on URL plus storefront, not URL alone.**
The autocomplete URL is identical for all eight countries. Only a header differs. Keying on the URL would have collapsed all eight markets into one row and quietly served US data for Germany, forever, with no error anywhere.

**3. Niches are grouped by which apps rank, not by shared words.**
Two phrases with no words in common are the same market if the App Store returns the same apps for both. `pdf to word` and `convert document` share nothing linguistically and everything commercially. The clustering is agglomerative on Jaccard overlap of the top 10, at a threshold of 0.15, because measured same-niche overlap ran between 0.10 and 0.30.

**4. The ranking is re-run under two other weightings.**
A niche that only wins under one set of weights is a weighting artifact, not a finding. The output shows where each niche lands under all three, so you can see which ones move.

**5. Publisher diversity carries only 5% of the score.**
The usual reading is "low diversity means one player dominates, so it is hard". But low diversity just as often means one small developer shipping five near-identical apps, which is easy to beat. The same number supports opposite conclusions, so it gets almost no say. The raw count is in the output for you to read yourself. I now think this signal should be replaced rather than down-weighted, and the FAQ below explains what with.

**6. Nothing is ever estimated to fill a gap.**
If a value could not be fetched, it is written as empty and the reason goes in `data/errors.log` with a timestamp. A missing number is always better than an invented one.

There is a test for exactly this. `scripts/selftest.py` does not check that the pipeline finds good data. It checks that when Apple lies, the pipeline records an absence rather than a zero, and does not poison the cache with the lie.

---

## The two steps I could not automate ✋

Both gaps are structural, not laziness, and the workbook shouts about them if you skip them.

**Phase 4, Apple Search Ads popularity. About 40 minutes of your clicking.**
This is the only real measurement of search demand in the entire study. Everything else is inferred from who currently ranks. It sits behind a login, inside an ad campaign builder, in a JavaScript interface. Automating it would mean driving a headless browser with your Apple credentials, which is both fragile and against Apple's terms. So the pipeline generates a worksheet, you fill 30 rows, and it validates them back in. It then reports **where Apple's real numbers disagree with its own estimates**, which tells you how much to trust the rest of the run.

**Phase 6, revenue. About 30 minutes on a free trial you cancel.**
Nothing free tells you whether a niche makes money. Appfigures and similar tools do, behind a paywall. Fifteen rows, by hand. Without it, no BUILD verdict from this pipeline is financially supported, and the summary tab says so in red.

Step by step guides for both are in [`manual/`](manual/). They open with an admission that I cannot see Apple's current interface and it changes, so the click path is a direction rather than gospel.

---

## Known limits 📌

Being honest about what is still rough:

* No run has completed Phases 4 or 6 yet, so no verdict so far is demand-verified or money-verified.
* The difficulty weights were reasoned, never fitted to an outcome. Nothing has been calibrated against a result yet.
* `opportunity_proxy` correlates with autocomplete position at -0.927, which means it is largely a restatement of where a phrase sits in Apple's suggestion list. Treat it as low confidence. Difficulty is measured from real competitor attributes and is unaffected.
* Subtitles and paywall flags exist only for the ~100 apps that rank for the most keywords, because they are not in Apple's JSON API at all and have to come from the public listing page. The `subtitle_coverage` column shows where that signal ran on partial data.
* The in-app-purchase percentage is measured on those same ~100 apps, which are by definition the winners. It describes apps that already won and says nothing about a new entrant.
* Review coverage is uneven. Apple throttles the review feed hard. `05_review_stats.csv` marks every gap as throttled rather than empty, but the gaps are real.
* The seven secondary markets are queried with English keywords. For Germany, France and the Netherlands that is a weak lower bound, and the scoring refuses to call those markets empty.

---

## FAQ 💬

#### "Your difficulty score is a weighted average someone made up. Why would I trust it?"

**Do not trust the number. Trust the band.** It blends six observable facts about the top 10 apps: median rating count (30% of the score), share with over 10k ratings (20), share with the exact keyword in the title or subtitle (20), staleness (15), median rating (10), publisher diversity (5). Those weights were chosen by reasoning, not fitted to any outcome, and I say so in the workbook.

Two things make it usable anyway. Every input is printed alongside the score, so the arithmetic can be checked by hand. And the whole ranking is re-run under two different weightings, so anything that only wins under one is flagged as an artifact. Calibrating them against real Apple Search Ads popularity is the next job. Until that happens, treat 41 and 44 as the same answer.

#### "A lone giant dominating a keyword sounds like the best indie setup, not the worst. Demand is proven, page one is thin, and someone is clearly paying. Is your diversity signal backwards?"

**Partly yes, which is why it carries 5% and not 20%.** Publisher count is genuinely ambiguous: one giant can mean an impossible fight or a validated market with no real second place. Five clones from one developer can mean an easy win or a category so thin that cloning is the only viable business.

The number cannot settle it because it is answering the wrong question. What actually decides it is whether money is being made and how weak positions 4 to 10 are, because that is where a new app realistically lands. The current score gets your scenario right by accident: a lone giant with weak neighbours produces a low median rating count, which pulls difficulty down. Right answer, wrong reason. The fix is to replace publisher count with two signals that speak to your scenario directly: how much money the incumbents are visibly taking, and how weak ranks 4 to 10 are on their own.

#### "Do the user complaints actually change the verdict?"

**They decide what to build, not whether to build.** In run 2 the complaint mining supported one lead and killed another. Supported: "the app silently lost my recording", 50 reviews across six apps from six different developers, which is an engineering discipline problem rather than a model access problem, and the rare kind a solo developer beats a funded team at. Killed: "better AI summaries", which looked obvious until the reviews showed users asking for *less* AI.

The caveat matters. The loudest theme in that entire dataset, about 110 reviews, was predatory trials and hard cancellation. Nobody can build their way out of that. Separating complaints you can fix from complaints you cannot is the highest-value change left in this project, and nothing in the pipeline does it yet. A human does it by reading.

#### "Why is there no real search volume?"

**Because Apple does not publish it for free, and I would rather have no number than a made-up one.** Autocomplete position gives you ordering, not magnitude. Two keywords both at rank 1 are not necessarily searched equally.

Apple Search Ads gives you a real popularity figure, straight from Apple, based on actual searches. That is Phase 4, it is manual, and it is the single most valuable data point in the study. Everything before it is a proxy. It is the only evidence.

#### "How much of this is the AI making things up?"

**None of the numbers. Some of the prose.** Keyword collection, competitor data, scoring, clustering and the Excel workbook are plain Python and reproduce exactly. The complaint themes, the adversarial review and the final verdict document are written by an AI reading those files. See the "what is code and what is AI" table above. Every claim in the verdict names its source file, so anything that sounds too confident can be checked in about a minute.

#### "Why does a run take three hours?"

**It is waiting, not computing.** The pipeline holds itself to 15 requests per minute, and 10 for reviews. That is slow on purpose. Apple signals throttling with a successful empty response, and pushing harder does not get you more data, it gets you silence that looks like data. Recovery is also intermittent rather than a clean cooldown, so a single empty response proves nothing and several sweeps are needed to converge. The CPU is idle the whole time. Start it and go do something else.

#### "Can I use this for Google Play?"

**Not yet.** Same architecture, different endpoints. It sits behind the scoring work, because doubling the reach of a score I do not fully trust yet is the wrong order.

---

## What is in the repo 📂

```
config.example.yaml      copy to config.yaml, put your seeds in it
config.yaml              yours, gitignored, everything you can change
requirements.txt

scripts/
  common.py              caching, throttling, and the rules that keep data honest
  p0_recon.py            endpoint health check
  p1_expand.py           seeds to keywords
  p2_competition.py      who ranks, and how strong they are
  p3_score.py            difficulty scoring and niche clustering
  p4_ingest_asa.py       Apple Search Ads worksheet, in and out
  p5_reviews.py          complaint mining
  p6_revenue.py          revenue worksheet, in and out
  p7_synthesize.py       the Excel workbook
  selftest.py            proves the pipeline fails safely

manual/                  guides for the two steps you do by hand
examples/                a real verdict document from run 2
data/                    CSVs, raw reviews, the HTTP cache, errors.log   (gitignored)
output/                  FINAL_ANALYSIS.xlsx and DECISION.md             (gitignored)
runs/                    archived previous runs                          (gitignored)
```

`data/`, `output/` and `runs/` are gitignored on purpose. They hold the seed topics, the niche rankings and the app about to get built. That is not a security risk, since nothing here touches a credential, but it is a competitive one. The committed `*.example.csv` files show the column layout using a throwaway topic.

**When something looks wrong,** open `data/errors.log` first. Every skipped keyword and app has a row there with a reason. Nothing is ever skipped silently. "0 keywords" is almost always an endpoint problem rather than a finding about your niche, so run `p0_recon.py`. A phase that stopped complaining that more than 20% of requests failed is telling you about a rate limit, not about your market: wait 15 minutes and re-run, and you will resume rather than restart.

---

## What is next 🚧

I keep a longer backlog privately. The three items on it that would change what this thing concludes:

1. **Score the gap at ranks 4 to 10**, not the average of the top 10, because that is where a new app lands.
2. **Calibrate the weights** against real Apple Search Ads popularity, so they stop being an opinion.
3. **Separate fixable complaints from unfixable ones**, so pricing rage stops competing with real product gaps.

---

## Say hi 👋

If any of this looks useful, broken, or worth arguing about, I would like to hear it. Especially if you have shipped consumer subscription apps and think the scoring is wrong somewhere. That is the part I most want pushed on.

Reach me through [my GitHub profile](https://github.com/iamaditya-gaur).

---

*Built with Claude Code over three research runs in July 2026. It has not told me to build anything yet.*
