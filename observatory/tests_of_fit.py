"""Delivered against required: the monthly test and its regression form (paper, Section 5).

At each month-end the required return is evaluated from that date's inputs and set beside the
return over the following month. Two models are compared:

    CAPM  explains  beta * (equity market return - risk-free)
    MCM   explains  the same, plus the concentration and mortality terms of the midpoint

"Unexplained" is the month's return less what the model allows, with the beta known at that
month-end. Annual figures are twelve times the monthly mean.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def monthly(d):
    """Expected one-month simple return at an annual rate d (continuous compounding)."""
    return np.exp(d / 12) - 1


def monthly_test(band: pd.DataFrame, market_return: pd.Series, start: str = "2012-01-01") -> pd.DataFrame:
    """One row per month-end that has a following month. Returns are monthly fractions."""
    r = band["price"].shift(-1) / band["price"] - 1
    rf = monthly(band["risk_free"])
    t = pd.DataFrame({
        "ret": r,
        "market_ret": market_return.shift(-1).reindex(band.index),
        "rf": rf,
        "required_lower": monthly(band["lower"]),
        "required_mid": monthly(band["midpoint"]),
        "required_upper": monthly(band["upper"]),
        "beta": band["beta"],
        "correlation": band["correlation"],
    })
    t["excess"] = t.ret - t.rf
    t["market_part"] = t.beta * (t.market_ret - t.rf)                                  # what the CAPM explains
    t["market_required"] = band["market_term"] / 12                                    # of which holders required: beta x ERP
    t["concentration_mortality_part"] = monthly(band["midpoint"] - band["market_term"]) - t.rf  # what MCM adds
    t["capm_unexplained"] = t.excess - t.market_part
    t["mcm_unexplained"] = t.capm_unexplained - t.concentration_mortality_part
    return t.dropna()[start:]


def ols(y: np.ndarray, X: np.ndarray, lags: int = 0):
    """Least squares with an intercept. Returns coefficients, standard errors and R squared.
    With lags > 0 the standard errors are Newey-West (Bartlett kernel)."""
    X = np.column_stack([np.ones(len(y)), X])
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ X.T @ y
    e = y - X @ b
    n, k = X.shape
    if lags == 0:
        cov = XtX_inv * (e @ e) / (n - k)
    else:
        u = X * e[:, None]
        S = u.T @ u
        for j in range(1, lags + 1):
            G = u[j:].T @ u[:-j]
            S += (1 - j / (lags + 1)) * (G + G.T)
        cov = XtX_inv @ S @ XtX_inv
    r2 = 1 - (e @ e) / ((y - y.mean()) @ (y - y.mean()))
    return b, np.sqrt(np.diag(cov)), float(r2)


def regression_alphas(t: pd.DataFrame) -> dict:
    """The test as a regression (paper, Section 5): Bitcoin's excess return on the equity market's.
    The intercept is alpha, in percent a year. For the MCM equation the concentration and mortality
    terms are subtracted from Bitcoin's return first."""
    x = (t.market_ret - t.rf).to_numpy()
    out = {}
    for name, y in (("capm", t.excess), ("mcm", t.excess - t.concentration_mortality_part)):
        b, se, _ = ols(y.to_numpy(), x)
        out[name] = {"alpha": float(1200 * b[0]), "se": float(1200 * se[0]), "t": float(b[0] / se[0]), "slope": float(b[1])}
    return out


def summarize(t: pd.DataFrame) -> dict:
    """Annualized averages over the rows given, in percent a year."""
    n = len(t)
    a = lambda s: float(1200 * s.mean())
    se = lambda s: float(1200 * s.std(ddof=1) / np.sqrt(n))
    gap = t.ret - t.required_mid
    return {
        "months": n,
        "delivered": a(t.ret), "required_mid": a(t.required_mid),
        "required_lower": a(t.required_lower), "required_upper": a(t.required_upper),
        "gap": a(gap), "gap_se": se(gap),
        "excess": a(t.excess), "market_part": a(t.market_part),
        "concentration_mortality_part": a(t.concentration_mortality_part),
        # the observatory's own split of the same sum: what holders required, and what equities added beyond their premium
        "required_premium": a(t.market_required + t.concentration_mortality_part),
        "equity_beyond_premium": a(t.market_part - t.market_required),
        "mcm_alpha": a(t.mcm_unexplained), "mcm_alpha_se": se(t.mcm_unexplained),
        "capm_alpha": a(t.capm_unexplained),
        "explained_capm": float(100 - 100 * t.capm_unexplained.mean() / t.excess.mean()),
        "explained_mcm": float(100 - 100 * t.mcm_unexplained.mean() / t.excess.mean()),
        "average_beta": float(t.beta.mean()), "average_correlation": float(t.correlation.mean()),
        "regression": regression_alphas(t) if n >= 24 else None,
        "cumulative_capm": float(100 * t.capm_unexplained.sum()),
        "cumulative_mcm": float(100 * t.mcm_unexplained.sum()),
    }


def notes(band: pd.DataFrame, t: pd.DataFrame, btc: pd.DataFrame) -> dict:
    """The figures quoted under "What this page does not claim", recomputed on the current data."""
    idx = t.index
    d_mid = (band["midpoint"].shift(-1) - band["midpoint"]).reindex(idx)
    d_rf = (band["risk_free"].shift(-1) - band["risk_free"]).reindex(idx)
    d_own = np.log(band["ownership"]).diff().shift(-1).reindex(idx)
    u = t.mcm_unexplained
    _, _, r2_inputs = ols(u.to_numpy(), np.column_stack([d_rf, d_own]))
    # supply and demand series over the month the return is earned in, as shares of market value
    cap = band["market_cap"].reindex(idx)
    m = lambda s: s.resample("ME").sum().shift(-1).reindex(idx)
    issuance = m(btc["IssTotNtv"] * btc["PriceUSD"]) / cap
    exchange = m(btc["FlowInExUSD"] - btc["FlowOutExUSD"]) / cap
    supply = btc["SplyCur"].dropna().resample("ME").last()
    fund_share = band["fund_btc"] / supply.reindex(band.index)
    d_fund = (fund_share.shift(-1) - fund_share).reindex(idx)
    X = pd.DataFrame({"u": u, "issuance": issuance, "exchange": exchange, "fund": d_fund}).dropna()
    b, se, r2 = ols(X.u.to_numpy(), X[["issuance", "exchange", "fund"]].to_numpy(), lags=6)
    return {"months": int(len(X)), "to": (idx[-1] + pd.offsets.MonthEnd(1)).strftime("%Y-%m"),
            "flows_r2": round(r2, 2), "flows_largest_t": round(float(np.abs(b[1:] / se[1:]).max()), 1),
            "repricing_correlation": round(float(np.corrcoef(d_mid, t.ret)[0, 1]), 2),
            "repricing_r2_price_free_inputs": round(r2_inputs, 3),
            "monthly_correlation_required_delivered": round(float(np.corrcoef(t.required_mid, t.ret)[0, 1]), 2)}


def period_table(t: pd.DataFrame) -> list[dict]:
    """Three-year periods from 2012, then the whole sample and the sample since 2018 (flagged summary)."""
    last = int(t.index[-1].year)
    spans = [(y, min(y + 2, last), False) for y in range(2012, last + 1, 3)] + [(2012, last, True), (2018, last, True)]
    rows = []
    for a, b, is_summary in spans:
        x = t[str(a):str(b)]
        if len(x) < 6:
            continue
        rows.append({"period": f"{a}–{str(b)[2:]}", "from": x.index[0].strftime("%Y-%m"),
                     "to": x.index[-1].strftime("%Y-%m"), "summary": is_summary, **summarize(x)})
    return rows
