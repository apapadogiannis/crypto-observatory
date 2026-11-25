"""Bitcoin beside equities: average and compound required returns (paper, Section 7, Table 8).

The equity series are priced by the CAPM: the risk-free rate plus beta times the equity risk premium,
with no separate size or style premium. Bitcoin is priced by the MCM equation. For every asset

    drag      = half the variance
    compound  = average required return less drag
    Sharpe    = (return less the risk-free rate) divided by volatility
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _row(name, priced_by, beta, average, vol, rf, **extra):
    drag = 100 * (vol / 100) ** 2 / 2
    return {"name": name, "priced_by": priced_by, "beta": float(beta), "average": float(average), "volatility": float(vol),
            "drag": float(drag), "compound": float(average - drag),
            "sharpe_average": float((average - rf) / vol), "sharpe_compound": float((average - drag - rf) / vol), **extra}


def comparison(band: pd.DataFrame, benchmarks: dict[str, pd.Series], cfg: dict, start: str = "2012-01-01", gold: pd.Series | None = None) -> dict:
    """Rows for the latest month-end of the band. Betas and volatilities of the equity series are measured
    on monthly log returns from start to the last month all of them have."""
    L = band.iloc[-1]
    rf = 100 * L.risk_free
    erp = 100 * cfg["constants"]["equity_risk_premium"]
    R = np.log1p(pd.DataFrame(benchmarks))[start:].dropna()
    first = next(iter(benchmarks))                       # the equity market itself, beta of one by definition
    market = R[first]
    rows = []
    for name in benchmarks:
        beta = 1.0 if name == first else np.cov(R[name], market)[0, 1] / market.var()
        rows.append(_row(name, "CAPM", beta, rf + beta * erp, 100 * R[name].std() * np.sqrt(12), rf,
                         terms={"risk_free": float(rf), "market": float(beta * erp), "concentration": 0.0, "mortality": 0.0}))
    if gold is not None:
        # Gold with the MCM equation (paper, Appendix E.1): a beta of zero within a small range, a holder with a few percent
        # of wealth in it, and almost no mortality. Volatility is measured on the same months as the equity series.
        g, c = cfg["gold"], cfg["constants"]
        lg = np.log1p(gold)[start:R.index[-1]].dropna()
        var = float(lg.var() * 12)
        lower = rf + g["beta_low"] * erp + 100 * c["risk_aversion_low"] * var * g["weight_low"] + 100 * g["mortality_low"]
        upper = rf + g["beta_high"] * erp + 100 * c["risk_aversion_high"] * var * g["weight_high"] + 100 * g["mortality_high"]
        mid, mort = 0.5 * (lower + upper), 50 * (g["mortality_low"] + g["mortality_high"])
        both = pd.DataFrame({"g": lg, "m": market}).dropna()
        rows.append(_row("Gold", "MCM", 0.5 * (g["beta_low"] + g["beta_high"]), mid, 100 * np.sqrt(var), rf, lower=float(lower), upper=float(upper),
                         measured_beta=float(np.cov(both.g, both.m)[0, 1] / both.m.var()),
                         terms={"risk_free": float(rf), "market": 0.0, "concentration": float(mid - rf - mort), "mortality": float(mort)}))
    mort = 100 * L.mortality_term
    b = _row("Bitcoin", "MCM", L.beta, 100 * L.midpoint, 100 * L.volatility, rf)
    b["average_net_of_death"] = b["average"] - mort
    b["compound_net_of_death"] = b["compound"] - mort
    rows.append(b)
    return {"month_end": band.index[-1].strftime("%Y-%m-%d"), "risk_free": float(rf), "equity_risk_premium": float(erp),
            "equity_sample": {"from": R.index[0].strftime("%Y-%m"), "to": R.index[-1].strftime("%Y-%m"), "months": int(len(R))},
            "rows": rows}
