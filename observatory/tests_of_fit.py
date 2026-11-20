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
    })
    t["excess"] = t.ret - t.rf
    t["market_part"] = t.beta * (t.market_ret - t.rf)                                  # what the CAPM explains
    t["market_required"] = band["market_term"] / 12                                    # of which holders required: beta x ERP
    t["concentration_mortality_part"] = monthly(band["midpoint"] - band["market_term"]) - t.rf  # what MCM adds
    t["capm_unexplained"] = t.excess - t.market_part
    t["mcm_unexplained"] = t.capm_unexplained - t.concentration_mortality_part
    return t.dropna()[start:]


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
        "cumulative_capm": float(100 * t.capm_unexplained.sum()),
        "cumulative_mcm": float(100 * t.mcm_unexplained.sum()),
    }


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
