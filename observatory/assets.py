"""The same equation for other cryptoassets (paper, Section 6).

An owner of crypto holds a mix of coins. What she must be paid for holding one of them depends on how
much of her whole crypto holding moves with it, not on that coin's slice of the holding:

    weight of asset i  =  kappa_i  x  the owner's weight in crypto
    kappa_i            =  Cov(r_i, r_market) / Var(r_i)          the crypto market's beta on the asset

The owner's weight in crypto is Bitcoin's (mcm.py): the surveyed owner's at the upper edge, the average
owner's counting fund and treasury investors at the lower edge. Volatility, the beta to the equity
market and kappa are each asset's own, measured as for Bitcoin. The mortality term is that of the
assets ever in the top twenty, which all of these are. No early-holder edge is taken for them.

The crypto market is the value-weighted return of Bitcoin and the assets listed in the configuration,
with the previous month-end's market values as weights. In April 2026 it gives a kappa of 0.69 for
Ether, against 0.70 in the paper, whose market is every priced asset of the Coin Metrics archive.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def read(data: Path, asset: str) -> pd.DataFrame:
    return pd.read_csv(data / "coinmetrics" / f"{asset}.csv", parse_dates=["time"]).set_index("time").sort_index()


def required_returns(data: Path, btc: pd.DataFrame, band: pd.DataFrame, market_return: pd.Series, cfg: dict) -> dict:
    """{'market_weights': DataFrame, 'assets': {code: DataFrame by month-end}} for the listed assets."""
    c, names = cfg["constants"], cfg["other_assets"]
    px = {"btc": btc["PriceUSD"]}
    cap = {"btc": btc["CapMrktCurUSD"]}
    for a in names:
        d = read(data, a)
        px[a], cap[a] = d["PriceUSD"], d["MarketCapUSD"]
    P = pd.DataFrame(px).resample("ME").last().reindex(band.index.union(pd.DataFrame(px).resample("ME").last().index)).loc[:band.index[-1]]
    C = pd.DataFrame(cap).resample("ME").last().reindex(P.index)
    R = P.pct_change(fill_method=None)
    W = C.shift(1).where(R.notna())
    W = W.div(W.sum(axis=1), axis=0)
    market = np.log1p((W * R).sum(axis=1, min_count=1))
    L = np.log1p(R)
    equity = np.log1p(market_return)
    win, least = c["beta_window_months"], c["asset_min_months"]

    def rolling(x: pd.Series, y: pd.Series, of: str) -> pd.Series:
        """Cov(x, y) / Var(of) on the last `win` months both have, from `least` months on."""
        both = pd.DataFrame({"x": x, "y": y}).dropna()
        out = {}
        for i in range(least - 1, len(both)):
            w = both.iloc[max(0, i - win + 1): i + 1]
            out[both.index[i]] = np.cov(w.x, w.y)[0, 1] / w[of].var()
        return pd.Series(out, dtype=float)

    out = {}
    for a in names:
        r = L[a]
        variance = r.pow(2).ewm(halflife=c["volatility_halflife_months"]).mean() * 12
        beta = rolling(r, equity, "y").reindex(band.index).ffill().clip(0, c["beta_cap"])      # carried forward where the equity series ends
        kappa = rolling(r, market, "x").reindex(band.index).clip(lower=0)
        variance = variance.reindex(band.index)
        w_hi = (kappa * band.w_surveyed).clip(upper=c["weight_cap"])
        w_lo = (kappa * band.w_with_funds).clip(upper=c["weight_cap"])
        market_term = beta * c["equity_risk_premium"]
        lower = band.risk_free + c["market_scale_low"] * market_term + c["risk_aversion_low"] * variance * w_lo + c["mortality_low"]
        upper = band.risk_free + c["market_scale_high"] * market_term + c["risk_aversion_high"] * variance * w_hi + c["mortality_high"]
        mid = 0.5 * (lower + upper)
        mortality = 0.5 * (c["mortality_low"] + c["mortality_high"])
        f = pd.DataFrame({"risk_free": band.risk_free, "volatility": np.sqrt(variance), "variance": variance, "beta": beta, "kappa": kappa,
                          "w_lower": w_lo, "w_upper": w_hi, "market_term": market_term, "mortality_term": mortality,
                          "concentration_term": (mid - band.risk_free - market_term - mortality).clip(lower=0),
                          "lower": lower, "upper": upper, "midpoint": mid,
                          "market_share": W[a].reindex(band.index)}).dropna(subset=["midpoint"])
        out[a] = f
    return {"market_weights": W.reindex(band.index), "assets": out}


def tests(data: Path, band: pd.DataFrame, market_return: pd.Series, other: dict) -> list[dict]:
    """Bitcoin's monthly test (tests_of_fit) run on each of the other assets, over the months it has been priced.

    It is shown, not relied on. These assets are listed because they are large today, so they are survivors:
    a delivered return above the required one is what selection produces, with or without a correct model.
    Their records are short, and the standard errors say how little the test can tell apart."""
    from . import tests_of_fit as tf
    rows = []
    for code, f in other["assets"].items():
        b = f.assign(price=read(data, code)["PriceUSD"].dropna().resample("ME").last().reindex(f.index), correlation=0.0)
        t = tf.monthly_test(b, market_return, str(f.index[0].date()))
        n = len(t)
        year = lambda s: float(1200 * s.mean())
        se = lambda s: float(1200 * s.std() / np.sqrt(n))
        excess, market, extra = year(t.excess), year(t.market_part), year(t.concentration_mortality_part)
        rows.append({"asset": code, "from": t.index[0].strftime("%Y-%m"), "to": t.index[-1].strftime("%Y-%m"), "months": n,
                     "delivered": round(year(t.ret), 1), "required_mid": round(year(t.required_mid), 1),
                     "gap": round(year(t.ret - t.required_mid), 1), "gap_se": round(se(t.ret - t.required_mid), 1),
                     "capm_unexplained": round(year(t.capm_unexplained), 1), "capm_unexplained_se": round(se(t.capm_unexplained), 1),
                     "mcm_unexplained": round(year(t.mcm_unexplained), 1), "mcm_unexplained_se": round(se(t.mcm_unexplained), 1),
                     "explained_capm": round(100 * market / excess, 1), "explained_mcm": round(100 * (market + extra) / excess, 1),
                     # the same three-year periods as Bitcoin's, over the months this asset has
                     "periods": [{"period": p["period"], "from": p["from"], "to": p["to"], "months": p["months"], "delivered": round(p["delivered"], 1),
                                  "required_mid": round(p["required_mid"], 1), "gap": round(p["gap"], 1), "gap_se": round(p["gap_se"], 1)}
                                 for p in tf.period_table(t) if not p["summary"]]})
    return rows
