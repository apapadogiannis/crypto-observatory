# Stored data

Everything the page shows is computed from the files in this folder. The build reads only these
files and never the network. `update.py` is the only code that downloads, and it writes here, so
every published number can be recomputed from what is stored.

| File | What it is | Source and license |
|---|---|---|
| `coinmetrics/btc.csv` | Daily funded addresses, market value, flows into and out of exchanges, issuance, price and supply of Bitcoin | Coin Metrics community data, CC BY-NC 4.0 (non-commercial, with attribution). Days to 23 May 2026 are from the public archive at github.com/coinmetrics/data, which stopped updating on 24 May 2026 (last commit `f1a36afb`). Later days are from the Coin Metrics Community API. |
| `rates/treasury_10y_daily.csv` | Daily ten-year par yield | US Department of the Treasury, Daily Treasury Par Yield Curve Rates |
| `market/us_market_monthly.csv` | Monthly excess return of the US equity market (`mkt_rf`) and the one-month bill rate (`rf`), in percent | Kenneth R. French data library, Fama/French 3 Factors. Copyright Kenneth R. French. Published with a lag of one to two months. |
| `market/developed_markets_monthly.csv` | The same two columns for developed-market equities, in US dollars | Kenneth R. French data library, Fama/French Developed 3 Factors. Copyright Kenneth R. French. |
| `market/us_small_caps_monthly.csv` | Monthly value-weighted return of the smallest 30% of US companies by size (`ret`), in percent | Kenneth R. French data library, Portfolios Formed on Size, column "Lo 30". Copyright Kenneth R. French. |
| `market/implied_equity_premium_monthly.csv` | The equity premium implied by the level of the S&P 500 at the start of each month, in percent (`implied_premium`), from September 2008. One column of the source file: the estimate on trailing twelve-month cash flows | Aswath Damodaran, Stern School of Business, New York University, "Implied ERP by month", https://pages.stern.nyu.edu/~adamodar/. Used only for the sensitivity table under Tests; the page's own numbers use the 4% of the paper. |
| `census/` | The census of cryptoasset deaths: `death_rate_by_age.csv`, `death_rate_by_size.csv` (both with exact 95% intervals), `survival_by_size.csv`, `ever_top20.csv` (every asset that was ever in the top twenty by trading volume, with the date and kind of its death if it died) and `summary.json` | Built by `tools/census_from_paper.py` from the result tables of the paper's replication package (CC BY 4.0). Census taken on 24 May 2026; not updated monthly. |
| `sources.json` | What the last update retrieved from each source, and to which date | written by `update.py` |

Survey and filing anchors (ownership, wealth per owner, fund and treasury holdings) are not data
files: they are entered by hand in `config/model.toml`, each with its date.

A value in the implied-premium file is dated at the start of a month. The build files it at the
month-end before, which is when it was known. Two cells of the source are typed as text ("4.06%",
"1-Sep-24"); `update.py` reads them as the numbers and date they stand for.

## Where the live data differ from the paper

- **Equity market.** The paper measures beta against an S&P 500 ETF. The live page uses the US market
  return of the French data library, which can be downloaded on a schedule. Over 2011 to April 2026
  the two series have a correlation of 0.994, and the required return at the midpoint differs by 0.1
  point on average.
- **Equity comparisons.** The paper sets Bitcoin beside the S&P 500, the MSCI ACWI and the Russell 2000,
  from ETF prices. The live page uses the US stock market, developed markets and the smallest 30% of
  US companies. Over 2012 to April 2026 the developed-markets series has a correlation of 0.993 with
  the ACWI ETF, and the small-company series 0.975 with the Russell 2000 ETF.
- **Treasury yield.** The paper uses the CBOE ten-year yield index. The live page uses the Treasury's
  own ten-year par yield. Month-end values differ by 1 basis point on average.
- **Coin Metrics.** Where the archive and the API overlap, price and issuance are identical. The API's
  supply and market value are higher by 100 BTC (0.0005% to 0.0009%), and its count of funded
  addresses is lower by up to 1.0%.

`tests/snapshot/` holds the paper's own inputs, frozen: the Coin Metrics archive, the S&P 500 ETF
prices and the CBOE yield index (the last two from Yahoo Finance, retrieved November 2026). It is
never updated, and the continuity test runs on it.
