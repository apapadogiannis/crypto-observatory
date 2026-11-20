# Stored data

Everything the page shows is computed from the files in this folder. The build reads only these
files and never the network. `update.py` is the only code that downloads, and it writes here, so
every published number can be recomputed from what is stored.

| File | What it is | Source and license |
|---|---|---|
| `coinmetrics/btc.csv` | Daily funded addresses, market value, issuance, price and supply of Bitcoin | Coin Metrics community data, CC BY-NC 4.0 (non-commercial, with attribution). Days to 23 May 2026 are from the public archive at github.com/coinmetrics/data, which stopped updating on 24 May 2026 (last commit `f1a36afb`). Later days are from the Coin Metrics Community API. |
| `rates/treasury_10y_daily.csv` | Daily ten-year par yield | US Department of the Treasury, Daily Treasury Par Yield Curve Rates |
| `market/us_market_monthly.csv` | Monthly excess return of the US equity market (`mkt_rf`) and the one-month bill rate (`rf`), in percent | Kenneth R. French data library, Fama/French 3 Factors. Copyright Kenneth R. French. Published with a lag of one to two months. |
| `census/ever_top20.csv` | Every cryptoasset that was ever in the top twenty by trading volume, with the date and kind of its death if it died | Result table of the paper's replication package (CC BY 4.0), census taken on 24 May 2026 |
| `sources.json` | What the last update retrieved from each source, and to which date | written by `update.py` |

Survey and filing anchors (ownership, wealth per owner, fund and treasury holdings) are not data
files: they are entered by hand in `config/model.toml`, each with its date.

## Where the live data differ from the paper

- **Equity market.** The paper measures beta against an S&P 500 ETF. The live page uses the US market
  return of the French data library, which can be downloaded on a schedule. Over 2011 to April 2026
  the two series have a correlation of 0.994, and the required return at the midpoint differs by 0.1
  point on average.
- **Treasury yield.** The paper uses the CBOE ten-year yield index. The live page uses the Treasury's
  own ten-year par yield. Month-end values differ by 1 basis point on average.
- **Coin Metrics.** Where the archive and the API overlap, price and issuance are identical. The API's
  supply and market value are higher by 100 BTC (0.0005% to 0.0009%), and its count of funded
  addresses is lower by up to 1.0%.

`tests/snapshot/` holds the paper's own inputs, frozen: the Coin Metrics archive, the S&P 500 ETF
prices and the CBOE yield index (the last two from Yahoo Finance, retrieved November 2026). It is
never updated, and the continuity test runs on it.
