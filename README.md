# Crypto observatory

[![check](https://github.com/apapadogiannis/crypto-observatory/actions/workflows/check.yml/badge.svg)](https://github.com/apapadogiannis/crypto-observatory/actions/workflows/check.yml)
[![Zenodo](https://img.shields.io/badge/Zenodo-10.5281%2Fzenodo.24403325-007ec6)](https://doi.org/10.5281/zenodo.24403325)

What return should a cryptoasset's holders require, and did they get it? Recomputed every month from
public data.

**Live page: https://apapadogiannis.github.io/crypto-observatory/**

By [Agisilaos Papadogiannis](https://github.com/apapadogiannis).

![The page](docs/screenshot.png)

## Use it from your own AI assistant

One skill covers this tool and the rest of the research: a short file that tells an assistant when to
use the work, where the files are and how to read them. It holds no figures, so it does not go stale.
For Claude Code:

```bash
mkdir -p ~/.claude/skills/papadogiannis-finance-research
curl -o ~/.claude/skills/papadogiannis-finance-research/SKILL.md https://raw.githubusercontent.com/apapadogiannis/apapadogiannis/main/skill/SKILL.md
```

Then ask, for example, "what return should Bitcoin's holders require now?". Other assistants that
read `SKILL.md` files take the same file in their own skills folder. This tool no longer publishes a
skill of its own: a copy added earlier keeps working, since it only points to the files below.

## For AI agents and programs

Read [`api/llms.txt`](api/llms.txt) first. It says what this is, what it adds over computing it
yourself, which file to use for what, and what not to use it for. The same files are served from the
live page's address.

| File | Content |
|---|---|
| `api/latest.json` | start here: the latest required return of every asset with its terms and inputs, the comparison with stocks, the licence and the citation, in one small file with units in the field names |
| `api/assets.csv` | the same figures as a table, one row per asset |
| `api/assets_monthly.csv` | one row per asset and month-end, since each asset has been priced |
| `api/data.json` | everything behind the page in one large file |
| `api/months.csv` | one row per month-end: the required-return band, its terms and inputs |
| `api/periods.csv` | one row per period: delivered and required return, and what each model explains |
| `api/census_deaths.csv` | every cryptoasset that was ever in the top twenty by trading volume and died, with the rule that classified it |
| `api/vintages.csv` | the required return of each month-end as first published; rows are added, never rewritten |
| `api/datapackage.json` | the licence, the citation and the meaning of every column |
| `api/llms.txt` | the guide |

These files are rebuilt from `data/` by `build.py` and checked by the tests. Do not edit them by hand.

## What it is

A page and a data file that answer one question for a cryptoasset: what return should its holders
require for the risks they carry, and what did the asset deliver?

The required return is computed with the MCM equation of
[Bitcoin's Required Return](https://doi.org/10.2139/ssrn.7705239) (Papadogiannis 2026):

```
required return = risk-free rate + market risk + concentration risk + mortality risk
                = r_f + beta x ERP + gamma x sigma^2 x w + lambda x (1 - delta)
```

The site has five sections.

**Compare** is the landing page: the required return of Bitcoin, Ether, BNB, Solana and Tron side by
side, what each is made of (risk-free rate, market, concentration and mortality risk), the inputs
behind it, and how each has moved. The US stock market is shown for scale. The other four assets are
priced with the paper's equation for other cryptoassets: an asset's holder weight is the crypto
owner's weight times the share of a crypto holding that moves with the asset (kappa).

**Bitcoin** has the full history and the tests, in five tabs:

1. **Overview.** The required return and what was delivered, by three-year period.
2. **Required return.** How the band is built, which holder sets each edge, and the three risks
   (market, concentration, mortality), each with its formula and the inputs that move it.
3. **Holders.** Where the holder's weight in the concentration term comes from: the surveyed owner at
   19%, the surveys in the United Kingdom and Canada that show holdings per owner not following the
   price, the lower weight once fund and treasury investors are counted, and the early holder.
4. **Tests.** How much of the delivered return the CAPM and the MCM equation each explain, why
   delivered differed from required, and, folded away, the regression, the cumulative view and the
   rerun with the equity premium implied by stock prices.
5. **Versus stocks.** Bitcoin beside the US stock market, developed markets and US small caps: average
   and compound required returns, drag and Sharpe ratios.

**Data** lists the files, gives a prompt to paste into an AI assistant, and says what the site does
not claim, with the method, sources and dates.

**How it works** explains the MCM equation term by term, with sliders: start from one of five cases
taken from the site's own data (two Bitcoin holders, Bitcoin at a negligible weight, an early holder in
2013, a stock index fund) and see the required return rebuild as the inputs move.

**Deaths** shows how often cryptoassets die, by age and by size, how long they last, and
every death among the assets that were ever in the top twenty. It is where the mortality term of the
required return comes from. The census is the paper's, taken on 24 May 2026, and is not yet updated
monthly. Each death carries the rule that classified it (trading dried up, price below 1% of its
peak, the data feed ended, or a sudden collapse) and how much the asset still traded at the census
date. The census is that of version 2.0 of the paper: 1,624 assets and 471 deaths, of which 35
among the 216 assets that were ever in the top twenty (3.46% a year, the upper mortality figure of
3.5%). The deaths came in a wave in 2025 and 2026, so the page gives each rate with its period.

It reports required returns. It forecasts nothing.

**What was said at the time.** The monthly series is recomputed at every update with the data and
the hand-entered anchors of that day, so the figure for a past month can change, and the band for
the years before 2021 uses a survey taken in 2021. `data/vintages.csv` keeps what was published for
each month-end when it was first computed, from November 2026 on. No build rewrites a stored row.

## Status

First version: Bitcoin. The data are updated on the third of each month by a scheduled job, which
downloads the new days, stores them in `data/`, reruns the check and rebuilds the page. Other assets
and a live census of deaths are to follow.

## Quickstart

Python 3.11 or later.

```bash
pip install -r requirements.txt
python3 -I tests/test_continuity.py    # reproduces the paper's stored results
python3 -I tests/test_agent_files.py   # the files in api/ agree with data.json
python3 -I build.py                    # writes _site/index.html and _site/data.json
python3 update.py                      # optional: downloads the latest data into data/
```

Open `_site/index.html` in a browser. The page loads one library (d3) from a public CDN and
nothing else.

## Layout

```
observatory/mcm.py            the required-return band, month by month
observatory/tests_of_fit.py   the monthly test, CAPM and MCM alpha, shares explained
observatory/compare.py        Bitcoin beside equities: average and compound required returns
observatory/build.py          builds the page and the data file from the stored data
observatory/publish.py        writes the files for programs and AI agents (api/)
api/                          those files: latest.json, assets.csv, assets_monthly.csv, months.csv, periods.csv, census_deaths.csv, vintages.csv, datapackage.json, llms.txt
observatory/assets.py         the same equation for Ether, BNB, Solana and Tron (kappa, the crypto market)
tools/census_from_paper.py     builds the census tables in data/census/ from the paper's result files (run once)
observatory/inputs.py         reads the stored files
observatory/update.py         downloads the latest data into data/ (the only code that uses the network)
config/model.toml             constants and hand-entered anchors, each with its source
data/                         all input data (see data/README.md)
site/template.html            the page
tests/test_continuity.py      checks the code against the paper on a frozen snapshot
tests/test_agent_files.py     checks the files in api/ against data.json
tests/snapshot/               the frozen inputs of the paper
reference/                    the paper's stored results that the test compares against
```

## The data file

`data.json` carries every number on the page under plain names, so that a script or an AI tool
can read it without scraping the page.

| Key | Holds |
|---|---|
| `meta` | asset, date of the data, units, method, sources, and under `credit` the licence, the citation and the paper |
| `latest` | the required return of the latest month, worked out term by term at both edges and the midpoint |
| `months` | one entry per month-end: the band, the terms at the midpoint, the inputs, supply measures, and the next month's return with what each model leaves unexplained |
| `periods` | three-year periods and the two summary samples: delivered, required, the gap and its split, the part each model explains and leaves unexplained, the regression alphas, the average beta and correlation |
| `comparison` | Bitcoin and three equity series at the latest month-end: beta, average and compound required return, volatility, drag, Sharpe ratios |
| `notes` | the figures quoted under "What this page does not claim", recomputed at each update |
| `equity_premium` | the tests of fit recomputed with other equity risk premia: the paper's fixed 4%, and the premium implied by stock prices each month |
| `assets` | Bitcoin, Ether, BNB, Solana and Tron side by side: the latest month-end and every month each has been priced |
| `holders` | what the holder's weight rests on: the owners' weight, the weight of fund and treasury investors, the ownership surveys behind the early holder's weight, and the British and Canadian survey waves shown under Holders |
| `census` | the census of deaths: death rates by age and by size with their intervals, survival by size, deaths by year, the list of top-twenty deaths with the rule behind each, the counts by rule, and what is left out |
| `vintages` | what was published for each month-end when it was first computed |
| `meta.model` | the model's fixed settings (equity premium, risk aversion, scales, windows, caps) and `meta.anchors_age_months`, the age of the hand-entered inputs |

Figures are percent a year unless the key says otherwise.

## How the check works

```bash
python3 -I tests/test_continuity.py
```

The model code in this repository is a clean rewrite of the paper's scripts. To show that it is the
same model, the test runs it on the paper's frozen inputs (`tests/snapshot/`) and compares the result
with the paper's stored outputs (`reference/`):

1. the monthly band: 173 months and nine columns, each within the four decimals the paper stores;
2. the monthly test: delivered, required, gap and its standard error for every period;
3. the unexplained return of the CAPM and of the MCM equation, added up and as a share explained;
4. the regression alphas, their standard errors and slopes.

A second test, `tests/test_agent_files.py`, checks that the files in `api/` are exactly what the build
produces and carry the same numbers, licence and citation as `data.json`.

The page is built only if both pass. The check shows that the code reproduces the paper. It does
not show that the data or the argument is right.

The live page uses sources that can be downloaded on a schedule, which differ slightly from the
paper's for the equity market and the Treasury yield. `data/README.md` states the differences.

## Configuration

`config/model.toml` holds every constant of the equation and every anchor that is entered by hand:
the surveyed owners' portfolio weight, survey ownership, and Bitcoin held through funds and by public companies. Each
carries its date and its place in the paper. Changing a value there changes the page; nothing is
hard-coded in the model.

## Privacy

The page is a static file. It sets no cookies and asks nothing of the visitor. It counts visits with GoatCounter, which sets no cookies and keeps no IP address: it records the page
opened, the site the visitor came from, the browser, the screen size and the country.
The only other outside request is for the d3 library.

## Data and licensing

- Copyright (c) 2026 Agisilaos Papadogiannis.
- Code: MIT License.
- The page's text, charts and numbers (`data.json`): CC BY 4.0. Cite the tool and the paper.
- Coin Metrics community data in `data/coinmetrics`: CC BY-NC 4.0, non-commercial use with
  attribution. It is not covered by the two licenses above.
- Equity market returns in `data/market`: copyright Kenneth R. French.
- Implied equity premium in `data/market`: Aswath Damodaran, NYU Stern, used with attribution.
- Other sources are listed in `data/README.md`.

## Citation

Cite the tool and the paper whose method it uses:

> Papadogiannis, A. (2026). "Crypto Observatory: required returns, risks and survival." Zenodo.
> https://doi.org/10.5281/zenodo.24403325

> Papadogiannis, A. (2026). "Bitcoin's Required Return: Market Risk, Concentration and Mortality."
> Working paper. https://doi.org/10.2139/ssrn.7705239

The Zenodo DOI above is the concept DOI: it always resolves to the latest archived version. Each
release also has its own DOI, listed on the Zenodo record.

## Disclaimer

Independent research; no funding, no institutional position. For informational and academic purposes
only. Not financial, investment, tax or legal advice, and not a recommendation to buy or sell any
financial instrument.
