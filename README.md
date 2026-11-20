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

The page shows:

1. **The required return and what was delivered.** The band and its midpoint at each month-end,
   with the delivered and required averages of each three-year period.
2. **How the band is built.** The lower edge, the two candidates for the upper edge, and which
   holder sets it in each month.
3. **The three risks.** Market, concentration and mortality, each with its formula, the points a
   year it adds, and the inputs that move it.
4. **The tests.** How much of the delivered return the CAPM explains, how much the MCM equation
   explains, and the alpha each leaves, by period and through time.

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
observatory/build.py          builds the page and the data file from the stored data
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
| `periods` | three-year periods and the two summary samples: delivered, required, gap, the part each model explains, alpha with its standard error |
| `census` | deaths among assets that were ever in the top twenty, by year and kind |

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
3. the CAPM and MCM alpha, the cumulative unexplained return and the share explained.

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
