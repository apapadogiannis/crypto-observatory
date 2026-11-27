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
        "delivered": a(t.ret), "delivered_compound": float(100 * ((1 + t.ret).prod() ** (12 / n) - 1)),
        "required_mid": a(t.required_mid),
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


def strength(t: pd.DataFrame) -> dict:
    """The equation set against a fixed premium.

    placebos    by sample (2012, 2018): the share explained, for the two models and for the CAPM plus a
                constant equal to the average of the two added terms in that sample. Within one sample
                the share depends on the average size of what is added, not on when.
    halves      what tells the equation from a constant: the two terms are set from surveys and the
                census, not fitted to returns, and fall from 2012-17 to the years since 2018. One constant
                for the whole record, even chosen with hindsight, is too small in the first and too large since."""
    a = lambda s: float(1200 * s.mean())
    se_ = lambda s: float(1200 * s.std(ddof=1) / np.sqrt(len(s)))
    out = {}
    for label, x in (("2012", t), ("2018", t["2018-01-01":])):
        added = x.concentration_mortality_part
        stand_ins = [("capm", "CAPM", x.capm_unexplained), ("mcm", "MCM equation", x.mcm_unexplained),
                     ("constant", "CAPM plus a constant", x.capm_unexplained - added.mean())]
        gap = x.ret - x.required_mid
        out[label] = {
            "months": int(len(x)), "constant": a(added),
            "placebos": [{"key": k, "name": n, "unexplained": a(u), "se": se_(u), "explained": float(100 - 100 * u.mean() / x.excess.mean())}
                         for k, n, u in stand_ins],
            "arithmetic": {"delivered": a(x.ret), "required": a(x.required_mid), "gap": a(gap), "se": se_(gap)},
        }
    c = t.concentration_mortality_part.mean()
    parts = [("2012-17", t[:"2017-12-31"]), ("since 2018", t["2018-01-01":]), ("whole record", t)]
    out["halves"] = {"constant": a(t.concentration_mortality_part), "samples": [n for n, _ in parts],
                     "months": [int(len(x)) for _, x in parts], "added_terms": [a(x.concentration_mortality_part) for _, x in parts],
                     "rows": [{"key": k, "unexplained": [a(f(x)) for _, x in parts], "se": [se_(f(x)) for _, x in parts]}
                              for k, f in (("capm", lambda x: x.capm_unexplained), ("mcm", lambda x: x.mcm_unexplained),
                                           ("one_constant", lambda x: x.capm_unexplained - c))]}
    return out


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


def period_spans(index: pd.DatetimeIndex, least: int = 6) -> list[tuple[int, int]]:
    """Three-year periods from 2012 as (first year, last year), covering every month of `index`.

    A period with fewer than `least` months (the first months of a new three-year period, or a record that
    starts late in one) is joined to the period beside it."""
    count = pd.Series(1, index=index).groupby(index.year).sum()
    n = lambda a, b: int(count.loc[a:b].sum())
    last = int(index[-1].year)
    spans = [[y, min(y + 2, last)] for y in range(2012, last + 1, 3) if n(y, min(y + 2, last))]
    i = 0
    while len(spans) > 1 and i < len(spans):
        if n(*spans[i]) >= least:
            i += 1
        elif i:                                                     # joined to the period before it
            spans[i - 1][1] = spans.pop(i)[1]
        else:                                                       # the first period: joined to the next
            first = spans.pop(0)
            spans[0][0] = first[0]
    return [(a, b) for a, b in spans]


def period_table(t: pd.DataFrame, least: int = 6) -> list[dict]:
    """Three-year periods from 2012, then the whole sample and the sample since 2018 (flagged summary)."""
    last = int(t.index[-1].year)
    spans = [(a, b, False) for a, b in period_spans(t.index, least)] + [(y, last, True) for y in (2012, 2018) if len(t[str(y):]) >= least]
    rows = []
    for a, b, is_summary in spans:
        x = t[str(a):str(b)]
        rows.append({"period": f"{a}–{str(b)[2:]}", "from": x.index[0].strftime("%Y-%m"),
                     "to": x.index[-1].strftime("%Y-%m"), "summary": is_summary, **summarize(x)})
    return rows


def equity_premium_sensitivity(band: pd.DataFrame, market_return: pd.Series, cfg: dict, implied: pd.Series | None) -> list[dict]:
    """The required return and the tests under other equity premiums. The first row is the page's own."""
    from . import mcm
    base = cfg["constants"]["equity_risk_premium"]
    check = mcm.with_equity_premium(band, base, cfg)
    if not np.allclose(check[["lower", "upper", "midpoint"]], band[["lower", "upper", "midpoint"]], rtol=0, atol=1e-12):
        raise AssertionError("with_equity_premium does not reproduce the band at the base premium")
    cases = [(f"{100 * base:.0f}%, as in the paper", "base", base)]
    if implied is not None:
        cases.append(("Implied by US stock prices, month by month", "implied", implied))
    cases += [(f"{100 * v:.0f}%", "constant", v) for v in (0.03, 0.05, 0.06) if abs(v - base) > 1e-9]
    rows = []
    for name, kind, premium in cases:
        b = mcm.with_equity_premium(band, premium, cfg)
        t = monthly_test(b, market_return)
        L = b.iloc[-1]
        row = {"premium": name, "kind": kind, "required_now": float(100 * L.midpoint), "lower_now": float(100 * L.lower), "upper_now": float(100 * L.upper),
               "premium_now": float(100 * L.market_term / L.beta) if L.beta else None, "samples": {}}
        for label, tt in (("2012", t), ("2018", t["2018-01-01":])):
            S = summarize(tt)
            row["samples"][label] = {"required_mid": S["required_mid"], "gap": S["gap"], "gap_se": S["gap_se"], "mcm_unexplained": S["mcm_alpha"],
                                     "explained_mcm": S["explained_mcm"], "regression_alpha": S["regression"]["mcm"]["alpha"],
                                     "average_premium": float(1200 * (tt.market_required / tt.beta).mean())}
        rows.append(row)
    return rows
