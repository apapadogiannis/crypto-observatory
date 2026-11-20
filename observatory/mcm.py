"""The required-return (MCM) equation for Bitcoin, month by month.

    required return = risk-free rate + market risk + concentration risk + mortality risk
                    = r_f + beta * ERP + gamma * sigma^2 * w + lambda * (1 - delta)

Follows "Bitcoin's Required Return" (Papadogiannis 2026), Sections 2 to 5 and Appendices B and D.
The band prices three holders: the average owner counting fund and treasury investors (lower edge),
the average surveyed owner and the early holder (the larger of the two is the upper edge). The
midpoint is the simple average of the two edges.

This module reads no files and makes no network calls: it takes series and a configuration and
returns a table, so the same code serves the live update and the check against the paper.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

YEAR = 365.25


def _month_end(s: pd.Series, how: str) -> pd.Series:
    r = s.dropna().resample("ME")
    return r.last() if how == "last" else r.mean()


def _interp(dates: dict, at_age: pd.Series, genesis: pd.Timestamp, log: bool = False) -> np.ndarray:
    """Piecewise-linear (or log-linear) path through dated anchors, flat beyond the first and last."""
    x = np.array([(pd.Timestamp(d) - genesis).days / YEAR for d in dates])
    y = np.array(list(dates.values()), dtype=float)
    out = np.interp(at_age, x, np.log(y) if log else y)
    return np.exp(out) if log else out


def required_return_band(btc: pd.DataFrame, market_return: pd.Series, risk_free: pd.Series, cfg: dict) -> pd.DataFrame:
    """One row per month-end.

    btc            daily table indexed by date with PriceUSD, CapMrktCurUSD, AdrBalCnt
    market_return  simple monthly return of the equity market, indexed by month-end
    risk_free      ten-year Treasury yield as a fraction, indexed by month-end
    cfg            the parsed config/model.toml
    """
    c = cfg["constants"]
    genesis = pd.Timestamp(c["genesis"])
    px = _month_end(btc["PriceUSD"], "last")
    idx = px.index
    cap = _month_end(btc["CapMrktCurUSD"], "last").reindex(idx)
    adr = _month_end(btc["AdrBalCnt"], "mean").reindex(idx).interpolate()
    age = pd.Series((idx - genesis).days / YEAR, index=idx)

    # --- volatility: exponentially weighted squared monthly log returns, annualized
    log_ret = np.log(px).diff()
    variance = log_ret.pow(2).ewm(halflife=c["volatility_halflife_months"]).mean() * 12

    # --- ownership: share of adults who own crypto. Survey anchors, log-linear in between;
    #     before the first survey the count of funded addresses carries the shape.
    own = cfg["ownership"]
    first_date, first_value = next(iter(own.items()))
    q = pd.Series(_interp(own, age, genesis, log=True), index=idx)
    i_first = idx.get_indexer([pd.Timestamp(first_date)], method="nearest")[0]
    before = age < (pd.Timestamp(first_date) - genesis).days / YEAR
    q[before] = first_value * adr[before] / adr.iloc[i_first]

    # --- wealth of surveyed owners, carried back and forward from the anchor survey
    i_anchor = idx.get_indexer([pd.Timestamp(c["anchor_date"])], method="nearest")[0]
    wealth_path = pd.Series(_interp(cfg["wealth_per_owner"], age, genesis), index=idx)
    owners_wealth = cap.iloc[i_anchor] / c["owner_weight_2021"] * (q / q.iloc[i_anchor]) * wealth_path

    # --- Bitcoin held through funds and by public companies, and the wealth of those investors
    fund_btc = pd.Series(1e6 * _interp(cfg["fund_and_treasury_btc"], age, genesis), index=idx)
    fund_value = fund_btc * px
    w_surveyed = (cap / owners_wealth).clip(upper=c["weight_cap"])
    w_with_funds = (cap / (owners_wealth + fund_value / c["fund_investor_weight"])).clip(upper=c["weight_cap"])
    w_early = (c["few_hands_ownership"] / q).clip(upper=1.0)

    # --- market risk: rolling beta of monthly log returns on the equity market's
    both = pd.DataFrame({"b": log_ret, "m": np.log1p(market_return)}).dropna()
    win, start = c["beta_window_months"], c["beta_min_months"] - 1

    def window(i):
        return both.iloc[max(0, i - win + 1): i + 1]

    beta = pd.Series({both.index[i]: np.cov(window(i).b, window(i).m)[0, 1] / window(i).m.var()
                      for i in range(start, len(both))})
    corr = pd.Series({both.index[i]: window(i).corr().iloc[0, 1] for i in range(start, len(both))})
    beta = beta.reindex(idx).bfill().ffill().clip(0, c["beta_cap"])
    corr = corr.reindex(idx).bfill().ffill()
    rf = risk_free.reindex(idx).ffill().bfill()
    market_term = beta * c["equity_risk_premium"]

    # --- the band
    lower = rf + c["market_scale_low"] * market_term + c["risk_aversion_low"] * variance * w_with_funds + c["mortality_low"]
    upper_surveyed = rf + c["market_scale_high"] * market_term + c["risk_aversion_high"] * variance * w_surveyed + c["mortality_high"]
    upper_early = rf + w_early * variance
    upper = np.maximum(upper_surveyed, upper_early)
    mid = 0.5 * (lower + upper)
    mortality_term = 0.5 * (c["mortality_low"] + c["mortality_high"])
    concentration_term = (mid - rf - market_term - mortality_term).clip(lower=0)

    return pd.DataFrame({
        "price": px, "market_cap": cap, "age_years": age,
        "risk_free": rf, "volatility": np.sqrt(variance), "variance": variance,
        "beta": beta, "correlation": corr, "ownership": q,
        "w_with_funds": w_with_funds, "w_surveyed": w_surveyed, "w_early": w_early,
        "fund_btc": fund_btc,
        "market_term": market_term, "concentration_term": concentration_term, "mortality_term": mortality_term,
        "lower": lower, "upper_surveyed": upper_surveyed, "upper_early": upper_early, "upper": upper,
        "midpoint": mid, "early_holder_sets_upper": upper_early > upper_surveyed,
    })
