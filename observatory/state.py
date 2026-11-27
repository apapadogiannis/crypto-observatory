"""Volatility and compounding: what the equation implies, and where Bitcoin stands.

Two things, both read off the band and the price. Neither is a forecast.

1.  What volatility does to the return. The required return is an average, asked by holders who keep a
    share w of their wealth in the asset. At each edge of the band it rises with variance at a rate of
    risk aversion times that share (the "pay for variance"). A position held alone and never
    rebalanced loses half the variance; a holder with share w, kept roughly constant, loses w times
    that on each unit invested. So

        price compounds at   = required average return - variance / 2
        the holder is paid   = risk aversion x w x variance      and bears   w x variance / 2

    The holders who set the band are paid more than the drag they bear. The required return covers
    the drag of a position held alone only where the pay for variance is above one half.

2.  The state at the month-end, and the record of what followed similar states: how far the price
    stands below its highest month-end close, and where the model's volatility sits in its own
    history. The record is descriptive. Twelve-month windows that start in neighbouring months share
    eleven months, so the count of separate spells says how much independent evidence there is.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZON = 12                                   # months of outcome set beside each state
SAMPLES = ("2012", "2018")                     # the two periods the page offers
DRAWDOWNS = [("within 20% of the peak", -20.0, 0.0), ("20% to 40% below the peak", -40.0, -20.0),
             ("40% to 60% below the peak", -60.0, -40.0), ("more than 60% below the peak", -100.0, -60.0)]
VOLATILITY_GRID = (20, 30, 40, 60, 80, 100)    # percent a year, beside the month's own volatility
BREAK_EVEN = 0.5


def loadings(band: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Pay for variance at the two edges and the midpoint: the change in the required return for a
    unit change in variance, the other inputs held. Where the early holder sets the upper edge it is
    that holder's weight (the upper edge is then the risk-free rate plus weight times variance)."""
    c = cfg["constants"]
    lower = c["risk_aversion_low"] * band.w_with_funds
    upper = pd.Series(np.where(band.early_holder_sets_upper, band.w_early, c["risk_aversion_high"] * band.w_surveyed), index=band.index)
    return pd.DataFrame({"lower": lower, "midpoint": 0.5 * (lower + upper), "upper": upper})


def compound(band: pd.DataFrame) -> pd.DataFrame:
    """What a position held alone and never rebalanced would compound at, at each edge of the band: the edge less half the variance."""
    drag = band.variance / 2
    return pd.DataFrame({"drag": drag, "lower": band.lower - drag, "midpoint": band.midpoint - drag, "upper": band.upper - drag})


def sensitivity(band: pd.DataFrame, cfg: dict) -> dict:
    """The latest month's band recomputed at other volatilities, everything else as it is that month."""
    c, L = cfg["constants"], band.iloc[-1]
    now = 100 * float(L.volatility)
    grid = sorted([v for v in VOLATILITY_GRID if abs(v - now) > 4] + [now])
    rows = []
    for vol in grid:
        var = (vol / 100) ** 2
        lower = L.risk_free + c["market_scale_low"] * L.market_term + c["risk_aversion_low"] * var * L.w_with_funds + c["mortality_low"]
        surveyed = L.risk_free + c["market_scale_high"] * L.market_term + c["risk_aversion_high"] * var * L.w_surveyed + c["mortality_high"]
        early = L.risk_free + L.w_early * var
        upper = max(surveyed, early)
        mid, drag = 0.5 * (lower + upper), var / 2
        rows.append({"volatility": round(vol, 1), "current": vol == now, "drag": round(100 * drag, 2),
                     "average": {"lower": round(100 * lower, 2), "midpoint": round(100 * mid, 2), "upper": round(100 * upper, 2)},
                     "compound": {"lower": round(100 * (lower - drag), 2), "midpoint": round(100 * (mid - drag), 2), "upper": round(100 * (upper - drag), 2)},
                     "upper_set_by": "early holder" if early > surveyed else "average surveyed owner"})
    load = loadings(band, cfg).iloc[-1]
    return {"month_end": band.index[-1].strftime("%Y-%m-%d"), "break_even_pay_for_variance": BREAK_EVEN,
            "pay_for_variance": {k: round(float(load[k]), 3) for k in ("lower", "midpoint", "upper")},
            "held_fixed": "the risk-free rate, beta, the holders' weights and the mortality rate of the month-end",
            "rows": rows}


def _spells(dates: pd.DatetimeIndex) -> int:
    """Separate spells: runs of month-ends in the state, a new one starting after a gap of more than HORIZON months."""
    if not len(dates):
        return 0
    gaps = np.diff(dates.year * 12 + dates.month)
    return int(1 + (gaps > HORIZON).sum())


def _table(btc: pd.DataFrame, band: pd.DataFrame) -> pd.DataFrame:
    px = btc["PriceUSD"].dropna().resample("ME").last()
    px = px[px.index <= band.index[-1]]
    simple, log = px.pct_change(), np.log(px).diff()
    ahead = lambda s: s.shift(-1).rolling(HORIZON).mean().shift(-(HORIZON - 1))      # the HORIZON months after each month-end
    peak = px.cummax()
    t = pd.DataFrame({"price": px, "peak": peak, "drawdown": 100 * (px / peak - 1),
                      "next_average": 1200 * ahead(simple), "next_holding": 100 * (px.shift(-HORIZON) / px - 1),
                      "next_variance": 12 * ahead(log.pow(2))})
    t = t.reindex(band.index)
    t["variance"], t["required"] = band.variance, 100 * band.midpoint
    return t


def state(btc: pd.DataFrame, band: pd.DataFrame) -> dict:
    t = _table(btc, band)
    L, last = t.iloc[-1], band.index[-1]
    px = btc["PriceUSD"].dropna().resample("ME").last()
    px = px[px.index <= last]
    r = lambda v, n=1: None if pd.isna(v) else round(float(v), n)
    vol = lambda variance: 100 * np.sqrt(variance)
    samples = {}
    for start in SAMPLES:
        s = t[t.index >= f"{start}-01-01"]
        done = s.dropna(subset=["next_average"])
        here = lambda lo, hi, v: bool(lo < v <= hi) if lo > -100 else bool(v <= hi)
        by_drawdown = []
        for label, lo, hi in DRAWDOWNS:
            g = done[(done.drawdown > lo) & (done.drawdown <= hi)] if lo > -100 else done[done.drawdown <= hi]
            by_drawdown.append({"state": label, "current": here(lo, hi, L.drawdown), "months": int(len(g)), "spells": _spells(g.index),
                                "volatility": r(vol(g.variance.mean())), "required": r(g.required.mean()),
                                "next_average": r(g.next_average.mean()), "next_holding_median": r(g.next_holding.median()),
                                "next_volatility": r(vol(g.next_variance.mean()))})
        # thirds of the sample by the model's volatility; the cuts come from every month-end of the sample
        cuts = [float(s.variance.quantile(q)) for q in (1 / 3, 2 / 3)]
        third = lambda v: 0 if v <= cuts[0] else 1 if v <= cuts[1] else 2
        which = done.variance.map(third)
        by_volatility = []
        for i, label in enumerate(("lowest third", "middle third", "highest third")):
            g = done[which == i]
            by_volatility.append({"state": label, "current": third(L.variance) == i, "months": int(len(g)), "spells": _spells(g.index),
                                  "volatility": r(vol(g.variance.mean())), "next_volatility": r(vol(g.next_variance.mean())),
                                  "drag": r(50 * g.variance.mean()), "next_drag": r(50 * g.next_variance.mean()),
                                  "required": r(g.required.mean()), "next_average": r(g.next_average.mean())})
        samples[start] = {"from": s.index[0].strftime("%Y-%m"), "months": int(len(s)), "months_with_outcome": int(len(done)),
                          "outcomes_from": done.index[0].strftime("%Y-%m"), "outcomes_to": done.index[-1].strftime("%Y-%m"),
                          "volatility_percentile": r(100 * (s.variance < L.variance).mean(), 0),
                          "volatility_median": r(vol(s.variance.median())),
                          "volatility_thirds": [r(vol(c)) for c in cuts],
                          "by_drawdown": by_drawdown, "by_volatility": by_volatility}
    return {"month_end": last.strftime("%Y-%m-%d"), "price_usd": r(L.price, 0), "peak_month_end_close_usd": r(L.peak, 0),
            "peak_month": px[px == L.peak].index[-1].strftime("%Y-%m"), "drawdown": r(L.drawdown), "volatility": r(vol(L.variance)),
            "horizon_months": HORIZON, "basis": "month-end closes; a month in progress is left out",
            "samples": samples}


def drawdown(btc: pd.DataFrame, band: pd.DataFrame) -> pd.Series:
    """Percent below the highest month-end close so far, at each month-end of the band."""
    return _table(btc, band)["drawdown"]


HORIZON_AHEAD = 36                             # months the paths are carried past the latest month-end


def paths(btc: pd.DataFrame, band: pd.DataFrame) -> dict:
    """A straight trend line beside the path the required return implies.

    The trend line is the kind drawn on price dashboards: a least-squares line through the log of the
    month-end closes, with the standard deviation of the distances from it. It assumes one growth rate
    for ever. The MCM path always starts at the latest month-end and grows at the latest required
    compound return, with the latest volatility. Its spread is the standard deviation of the log price
    of a random walk, which widens with time, because the equation says nothing that would pull the
    price back. The equation gives a growth rate and no level, so the price the path starts from is a
    choice: the latest close is the buyer's own case, and a past peak or the level of the trend line
    answer "what if the price were there today". The page lets the reader pick any level. None of this
    is a forecast.
    """
    t = _table(btc, band)
    lp, n, H = np.log(t.price), len(t) - 1, HORIZON_AHEAD
    comp = compound(band)
    usd = lambda v: round(float(np.exp(v)))
    month = lambda i: t.index[i].strftime("%Y-%m")
    horizon_month = (t.index[-1] + pd.offsets.MonthEnd(H)).strftime("%Y-%m")
    growth = {e: float(comp[e].iloc[n]) * H / 12 for e in ("lower", "midpoint", "upper")}
    spread = float(np.sqrt(band.variance.iloc[n] * H / 12))

    def from_level(level: float) -> dict:
        return {"level": usd(level), "price_against_it": round(100 * float(np.exp(lp.iloc[n] - level) - 1), 1),
                "path_at_horizon": usd(level + growth["midpoint"]),
                "range_at_horizon": [usd(level + growth["midpoint"] - 2 * spread), usd(level + growth["midpoint"] + 2 * spread)],
                "edges_at_horizon": [usd(level + growth["lower"]), usd(level + growth["upper"])]}

    trend = {}
    for start in SAMPLES:
        i0 = int(np.argmax(t.index >= f"{start}-01-01"))
        x, y = np.arange(n - i0 + 1) / 12, lp.iloc[i0:].to_numpy()
        k, c = np.polyfit(x, y, 1)
        sd = float(np.std(y - (c + k * x), ddof=1))
        now, ahead = c + k * x[-1], c + k * (x[-1] + H / 12)
        trend[start] = {"fitted_from": month(i0), "growth": round(100 * (np.exp(k) - 1), 1), "sd_factor": round(float(np.exp(sd)), 2),
                        "value_now": usd(now), "price_against_it": round(float((y[-1] - now) / sd), 2),
                        "value_at_horizon": usd(ahead), "range_at_horizon": [usd(ahead - 2 * sd), usd(ahead + 2 * sd)],
                        "path_from_its_level": from_level(now)}

    peak = int(np.argmax(t.price.to_numpy() == t.peak.iloc[n]))                # the highest month-end close so far
    deep = np.flatnonzero(t.drawdown.to_numpy() <= -50)                        # the peak before the last fall of more than half
    before = int(np.argmax(t.price.to_numpy() == t.peak.iloc[deep[-1]])) if len(deep) else None
    levels = [{"key": "latest", "what": "the latest month-end close", "month": month(n), **from_level(lp.iloc[n])}]
    if peak != n:
        levels.append({"key": "peak", "what": "the highest month-end close", "month": month(peak), **from_level(lp.iloc[peak])})
    if before is not None and before not in (n, peak):
        levels.append({"key": "previous_peak", "what": "the peak before the last fall of more than half", "month": month(before), **from_level(lp.iloc[before])})
    return {"month_end": t.index[-1].strftime("%Y-%m-%d"), "horizon_months": H, "horizon_month": horizon_month,
            "growth_ahead": {e: round(100 * float(comp[e].iloc[n]), 2) for e in ("lower", "midpoint", "upper")},        # the page's own compound figures
            "volatility": round(100 * float(band.volatility.iloc[n]), 1), "trend": trend, "levels": levels,
            "prices": [[d.strftime("%Y-%m"), round(float(p), 2)] for d, p in t.price.items()]}
