"""Reads the stored input files. Nothing here touches the network: the update step writes the
files, and everything downstream reads only what is stored in the repository."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config" / "model.toml", "rb") as f:
        return tomllib.load(f)


def bitcoin(data: Path) -> pd.DataFrame:
    """Daily Coin Metrics series for Bitcoin, indexed by date."""
    return pd.read_csv(data / "coinmetrics" / "btc.csv", parse_dates=["time"]).set_index("time").sort_index()


def _to_month_end(s: pd.Series) -> pd.Series:
    s = s.sort_index()
    s.index = s.index + pd.offsets.MonthEnd(0)
    return s


def market_return(data: Path) -> pd.Series:
    """Simple monthly total return of the equity market, indexed by month-end."""
    f = pd.read_csv(data / "market" / "sp500_etf_monthly.csv", parse_dates=["Date"]).set_index("Date")
    return _to_month_end(f["AdjClose"]).pct_change()


def risk_free(data: Path) -> pd.Series:
    """Ten-year Treasury yield at month-end, as a fraction."""
    f = pd.read_csv(data / "rates" / "treasury_10y_monthly.csv", parse_dates=["Date"]).set_index("Date")
    return _to_month_end(f["Close"]) / 100
