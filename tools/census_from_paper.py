"""Builds the census tables in data/census/ from the result files of the paper's replication package.

    python3 tools/census_from_paper.py PATH_TO/bitcoin-required-return/outputs data/census

Run once, when the census is taken. It reads the paper's stored outputs (panel_v3.csv, the hazard
tables, the ever-top-twenty tables and the monthly volume matrix) and writes small CSV files that the
page is built from. Needs scipy for the exact Poisson intervals; the observatory itself does not.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
YR = 365.25
# Left out of the top-twenty cohort: the paper's census counts it, but it is not a cryptoasset.
# ltl is the Lithuanian litas, a national currency replaced by the euro in January 2015.
NOT_A_CRYPTOASSET = {"ltl"}


def garwood(deaths, exposure):
    """Exact Poisson 95% interval for a rate."""
    lo = chi2.ppf(0.025, 2 * deaths) / 2 / exposure if deaths > 0 else 0.0
    return lo, chi2.ppf(0.975, 2 * (deaths + 1)) / 2 / exposure


# ---- death rate by age: the paper's nine buckets (ages 1 to 1.5 and 1.5 to 2 shown as one)
hb = pd.read_csv(SRC / "hazard_buckets_curated.csv")
hb = hb[hb.deaths > 0].reset_index(drop=True)
m = hb[(hb.a >= 1.0) & (hb.b <= 2.0)]
hb = pd.concat([hb[hb.b <= 1.0], pd.DataFrame([dict(a=1.0, b=2.0, deaths=m.deaths.sum(), exp=m.exp.sum())]), hb[hb.a >= 2.0]], ignore_index=True)
rows = []
for r in hb.itertuples():
    lo, hi = garwood(r.deaths, r.exp)
    rows.append(dict(age_from=r.a, age_to=r.b, deaths=int(r.deaths), asset_years=round(r.exp, 1), rate=round(100 * r.deaths / r.exp, 2), ci_low=round(100 * lo, 2), ci_high=round(100 * hi, 2)))
pd.DataFrame(rows).to_csv(OUT / "death_rate_by_age.csv", index=False)

# ---- death rate by size: quartiles of peak trading volume, then the assets that were ever near the top
sz = pd.read_csv(SRC / "hazard_by_size_curated.csv")
names = ["Smallest quartile", "Second quartile", "Third quartile", "Largest quartile"]
rows = []
for name, r in zip(names, sz.itertuples()):
    exp = r.deaths / r.lam
    lo, hi = garwood(r.deaths, exp)
    rows.append(dict(group=name, kind="quartile of peak trading volume", assets=int(r.n), deaths=int(r.deaths), asset_years=round(exp, 1), rate=round(100 * r.lam, 2), ci_low=round(100 * lo, 2), ci_high=round(100 * hi, 2)))
for name, f, only_sudden in (("Ever in the top fifty", "elite_top50_curated.csv", False), ("Ever in the top twenty", "elite_top20_curated.csv", False),
                             ("Ever in the top twenty: sudden collapse only", "elite_top20_curated.csv", True)):
    e = pd.read_csv(SRC / f)
    e = e[~e.asset.isin(NOT_A_CRYPTOASSET)]
    d = int(((e.death == 1) & ((e.cat == 1) | (not only_sudden))).sum())
    exp = e.exp_yr.sum()
    lo, hi = garwood(d, exp)
    rows.append(dict(group=name, kind="followed from first entry", assets=len(e), deaths=d, asset_years=round(exp, 1), rate=round(100 * d / exp, 2), ci_low=round(100 * lo, 2), ci_high=round(100 * hi, 2)))
pd.DataFrame(rows).to_csv(OUT / "death_rate_by_size.csv", index=False)

# ---- survival by size (Kaplan-Meier), as in the paper's figure
panel = pd.read_csv(SRC / "panel_v3.csv", parse_dates=["birth", "last", "death_cur_date"])
core = panel[~panel.stable2 & ~panel.tokstock & ~panel.wrapped_like].copy()
core = core[(core["last"] - core.birth).dt.days >= 30].set_index("asset")
end = panel["last"].max()
V = pd.read_pickle(SRC / "volume_monthly.pkl")
core["peak_vol"] = V.max().reindex(core.index)
core["T"] = np.clip(np.where(core.dead_cur, (core.death_cur_date - core.birth).dt.days / YR, (end - core.birth).dt.days / YR), 1 / YR, None)
core["E"] = core.dead_cur.astype(int)


def km(T, E, entry=None, grid=np.arange(0, 13.01, 0.25)):
    T, E = np.asarray(T, float), np.asarray(E, int)
    entry = np.zeros(len(T)) if entry is None else np.asarray(entry, float)
    s, out, times = 1.0, [], np.unique(T[E == 1])
    k = 0
    for g in grid:
        while k < len(times) and times[k] <= g:
            t = times[k]
            at_risk = ((entry < t) & (T >= t)).sum()
            if at_risk:
                s *= 1 - ((T == t) & (E == 1)).sum() / at_risk
            k += 1
        out.append(round(s, 4))
    return grid, out


has = core.peak_vol.notna()
q = pd.qcut(core.loc[has, "peak_vol"], 4, labels=names)
surv = []
for name in names:
    sub = core.loc[has][q == name]
    g, s = km(sub["T"], sub["E"])
    g = g[g <= sub["T"].max()]
    surv += [dict(group=name, age=float(a), alive=v) for a, v in zip(g, s)]
e20 = pd.read_csv(SRC / "elite_top20_curated.csv", parse_dates=["first_top"]).set_index("asset")
sub = core.loc[core.index.isin(e20.index)].copy()
sub["entry"] = ((e20.first_top.reindex(sub.index) - sub.birth).dt.days / YR).clip(lower=0)
sub = sub[sub.entry < sub["T"]]
g, s = km(sub["T"], sub["E"], sub.entry)
surv += [dict(group="Ever in the top twenty", age=float(a), alive=v) for a, v in zip(g[g <= sub["T"].max()], s)]
pd.DataFrame(surv).to_csv(OUT / "survival_by_size.csv", index=False)

# ---- the assets that were ever in the top twenty, with their deaths
e20 = e20[~e20.index.isin(NOT_A_CRYPTOASSET)]
e20.reset_index().to_csv(OUT / "ever_top20.csv", index=False)

# ---- which rule classified each of those deaths, and how much the asset still traded at the census date
rules = []
for r in e20[e20.death == 1].reset_index().itertuples():
    q = panel.set_index("asset").loc[r.asset]
    rule = ("sudden collapse" if r.cat == 1 else "trading dried up" if bool(q.vol_dead_c)
            else "price below 1% of peak" if bool(q.econ_dead) else "data feed ended")
    rules.append(dict(asset=r.asset, rule=rule, feed_last_day=str(q["last"].date()),
                      volume_at_end_usd_a_day="" if pd.isna(q.final_vol_3m) else int(round(q.final_vol_3m, -3))))
pd.DataFrame(rules).sort_values("asset").to_csv(OUT / "death_rules.csv", index=False)

# The universe totals and the tables by age and by peak volume are the paper's as they stand: they
# still count the one asset named in NOT_A_CRYPTOASSET, 1 of 1,815. The top-twenty cohort does not.
summary = dict(census_date=str(end.date()), first_asset_born=str(core.birth.min().date()), assets=int(len(core)), deaths=int(core.E.sum()),
               ever_top_twenty=int(len(e20)), ever_top_twenty_deaths=int((e20.death == 1).sum()),
               age_elasticity_of_death=0.42, source="Papadogiannis (2026), Bitcoin's Required Return, Section 3 and Appendix C")
(OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
print(summary)
