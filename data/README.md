# Stored data

Everything the page shows is computed from the files in this folder. The build reads only these
files and never the network; the update step is the only code that downloads, and it writes here.

| File | What it is | Source and license |
|---|---|---|
| `coinmetrics/btc.csv` | Daily price, market value, funded addresses, supply and issuance of Bitcoin | Coin Metrics community data, CC BY-NC 4.0 (non-commercial, with attribution). Columns `PriceUSD`, `CapMrktCurUSD`, `AdrBalCnt`, `SplyCur`, `IssTotNtv`, unmodified. Now ends 24 May 2026, the last update of the public archive at github.com/coinmetrics/data (commit `f1a36afb`). |
| `market/sp500_etf_monthly.csv` | Month-end close and adjusted close of the Vanguard S&P 500 ETF (VOO) | Yahoo Finance, retrieved November 2026, as used in the paper |
| `rates/treasury_10y_monthly.csv` | Month-end ten-year Treasury yield (CBOE TNX index) | Yahoo Finance, retrieved November 2026, as used in the paper |
| `census/ever_top20.csv` | Every cryptoasset that was ever in the top twenty by trading volume, with the date and kind of its death if it died | Result table of the paper's replication package (CC BY 4.0), census taken on 24 May 2026 |

Survey and filing anchors (ownership, wealth per owner, fund and treasury holdings) are not data
files: they are entered by hand in `config/model.toml`, each with its date.

`tests/snapshot/` holds a frozen copy of the first three files as they stood for the paper. It is
never updated: the continuity test runs on it.
