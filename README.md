# Crypto observatory

Required returns, risks and survival of cryptoassets, measured from public data.

![The page](docs/screenshot.png)

## What it is

A page and a data file that answer one question for a cryptoasset: what return should its holders
require for the risks they carry, and what did the asset deliver?

The required return is computed with the MCM equation of
[Bitcoin's Required Return](https://doi.org/10.2139/ssrn.7705239) (Papadogiannis 2026):

```
required return = risk-free rate + market risk + concentration risk + mortality risk
                = r_f + beta x ERP + gamma x sigma^2 x w + lambda x (1 - delta)
```

The site has two sections. **Bitcoin** has five tabs:

1. **Overview.** The required return and what was delivered, by three-year period, and why the two
   differed: the premium holders required, what the equity market added beyond its own premium, and
   alpha.
2. **Required return.** How the band is built, which holder sets each edge, and the three risks
   (market, concentration, mortality), each with its formula and the inputs that move it.
3. **Tests.** How much of the delivered return the CAPM explains, how much the MCM equation explains,
   and the alpha each leaves, by period and through time.
4. **Compared.** Bitcoin beside the US stock market, developed markets and US small caps: average and
   compound required returns, drag and Sharpe ratios.
5. **Data and notes.** Supply and holders for context, and what the page does not claim.

**Census of deaths** shows how often cryptoassets die, by age and by size, how long they last, and
every death among the assets that were ever in the top twenty. It is where the mortality term of the
required return comes from. The census is the paper's, taken on 24 May 2026, and is not yet updated
monthly.

It reports required returns. It forecasts nothing.

## Status

First version: Bitcoin. The data are updated on the third of each month by a scheduled job, which
downloads the new days, stores them in `data/`, reruns the check and rebuilds the page. Other assets
and a live census of deaths are to follow.

## Quickstart

Python 3.11 or later.

```bash
pip install -r requirements.txt
python3 -I tests/test_continuity.py    # reproduces the paper's stored results
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
tools/census_from_paper.py     builds the census tables in data/census/ from the paper's result files (run once)
observatory/inputs.py         reads the stored files
observatory/update.py         downloads the latest data into data/ (the only code that uses the network)
config/model.toml             constants and hand-entered anchors, each with its source
data/                         all input data (see data/README.md)
site/template.html            the page
tests/test_continuity.py      checks the code against the paper on a frozen snapshot
tests/snapshot/               the frozen inputs of the paper
reference/                    the paper's stored results that the test compares against
```

## The data file

`data.json` carries every number on the page under plain names, so that a script or an AI tool
can read it without scraping the page.

| Key | Holds |
|---|---|
| `meta` | asset, date of the data, units, method, sources |
| `latest` | the required return of the latest month, worked out term by term at both edges and the midpoint |
| `months` | one entry per month-end: the band, the terms at the midpoint, the inputs, supply measures, and the next month's return with what each model leaves unexplained |
| `periods` | three-year periods and the two summary samples: delivered, required, the gap and its split, the part each model explains and leaves unexplained, the regression alphas, the average beta and correlation |
| `comparison` | Bitcoin and three equity series at the latest month-end: beta, average and compound required return, volatility, drag, Sharpe ratios |
| `notes` | the figures quoted under "What this page does not claim", recomputed at each update |
| `census` | the census of deaths: death rates by age and by size with their intervals, survival by size, deaths by year, and the list of top-twenty deaths |

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

The page is built only if this passes. The check shows that the code reproduces the paper. It does
not show that the data or the argument is right.

The live page uses sources that can be downloaded on a schedule, which differ slightly from the
paper's for the equity market and the Treasury yield. `data/README.md` states the differences.

## Configuration

`config/model.toml` holds every constant of the equation and every anchor that is entered by hand:
survey ownership, wealth per owner, and Bitcoin held through funds and by public companies. Each
carries its date and its place in the paper. Changing a value there changes the page; nothing is
hard-coded in the model.

## Privacy

The page is a static file. It sets no cookies, runs no analytics and sends nothing anywhere. The
only outside request is for the d3 library.

## Data and licensing

- Code: MIT License.
- The page's numbers (`data.json`): CC BY 4.0, cite the paper.
- Coin Metrics community data in `data/coinmetrics`: CC BY-NC 4.0, non-commercial use with
  attribution. It is not covered by the two licenses above.
- Equity market returns in `data/market`: copyright Kenneth R. French.
- Other sources are listed in `data/README.md`.

## Citation

> Papadogiannis, A. (2026). "Bitcoin's Required Return: Pricing a New Asset Beside Equities and Gold." Working paper.
> SSRN: https://doi.org/10.2139/ssrn.7705239

## Disclaimer

Independent research; no funding, no institutional position. For informational and academic purposes
only. Not financial, investment, tax or legal advice, and not a recommendation to buy or sell any
financial instrument.
