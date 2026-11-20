"""Builds the published files from the stored data.

    python3 -I build.py [DATA_DIR] [OUT_DIR]

Writes OUT_DIR/data.json (the documented data file, see README) and OUT_DIR/index.html (the page,
with the same numbers embedded so that it opens without a server).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import inputs, mcm, tests_of_fit

ROOT = inputs.ROOT
TRAILING = 36


def _r(v, n=2):
    return None if v is None or pd.isna(v) else round(float(v), n)


def build(data: Path, out: Path) -> dict:
    cfg = inputs.config()
    btc = inputs.bitcoin(data)
    mkt = inputs.market_return(data)
    band = mcm.required_return_band(btc, mkt, inputs.risk_free(data), cfg)
    band = band[band.index >= "2012-01-01"].dropna(subset=["midpoint"])
    # The page is dated at the last complete month-end: a month in progress is left out.
    last_day = btc["PriceUSD"].dropna().index[-1]
    month_complete = last_day == last_day + pd.offsets.MonthEnd(0)
    if not month_complete:
        band = band.iloc[:-1]
    t = tests_of_fit.monthly_test(band, mkt)
    periods = tests_of_fit.period_table(t)

    supply = btc["SplyCur"].dropna().resample("ME").last()
    issuance = btc["IssTotNtv"].resample("ME").sum() * 12 / supply
    fund_share = band["fund_btc"] / supply.reindex(band.index)
    roll = lambda s: 1200 * s.rolling(TRAILING).mean()
    trail = pd.DataFrame({"excess": roll(t.excess), "capm": roll(t.capm_unexplained), "mcm": roll(t.mcm_unexplained)})

    months = []
    for d, b in band.iterrows():
        has = d in t.index
        months.append({
            "month_end": d.strftime("%Y-%m-%d"),
            "required": {"lower": _r(100 * b.lower), "midpoint": _r(100 * b.midpoint), "upper": _r(100 * b.upper),
                         "upper_if_surveyed_owner": _r(100 * b.upper_surveyed), "upper_if_early_holder": _r(100 * b.upper_early),
                         "upper_set_by": "early holder" if b.early_holder_sets_upper else "average surveyed owner"},
            "terms_at_midpoint": {"risk_free": _r(100 * b.risk_free), "market": _r(100 * b.market_term),
                                  "concentration": _r(100 * b.concentration_term), "mortality": _r(100 * b.mortality_term)},
            "inputs": {"volatility": _r(100 * b.volatility, 1), "beta": _r(b.beta), "correlation": _r(b.correlation),
                       "weight_with_funds": _r(100 * b.w_with_funds, 1), "weight_surveyed": _r(100 * b.w_surveyed, 1),
                       "weight_early_holder": _r(100 * b.w_early, 1)},
            "supply": {"issuance_rate": _r(100 * issuance.get(d, np.nan)), "fund_and_treasury_share": _r(100 * fund_share.get(d, np.nan))},
            "next_month": None if not has else {
                "return": _r(100 * t.ret[d], 3), "capm_unexplained": _r(100 * t.capm_unexplained[d], 3),
                "mcm_unexplained": _r(100 * t.mcm_unexplained[d], 3)},
            "trailing_3y": None if not has or pd.isna(trail.mcm.get(d, np.nan)) else {
                "excess": _r(trail.excess[d], 1), "capm_unexplained": _r(trail.capm[d], 1), "mcm_unexplained": _r(trail.mcm[d], 1)},
        })

    census = pd.read_csv(ROOT / "data" / "census" / "ever_top20.csv", parse_dates=["death_date"])
    dead = census[census.death == 1].assign(year=lambda x: x.death_date.dt.year)
    by = dead.groupby(["year", "cat"]).size().unstack(fill_value=0)
    deaths = [{"year": int(y), "abandoned_or_delisted": int(by.loc[y].get(0, 0)) if y in by.index else 0,
               "sudden_collapse": int(by.loc[y].get(1, 0)) if y in by.index else 0}
              for y in range(2012, int(band.index[-1].year) + 1)]

    c = cfg["constants"]
    L = band.iloc[-1]
    pct = lambda v: _r(100 * v)
    doc = {
        "meta": {
            "asset": "btc", "name": "Bitcoin",
            "data_to": last_day.strftime("%Y-%m-%d"), "latest_month_end": band.index[-1].strftime("%Y-%m-%d"),
            "units": "percent a year unless stated; next_month figures are percent a month",
            "method": "Papadogiannis (2026), Bitcoin's Required Return. https://doi.org/10.2139/ssrn.7705239",
            "equity_market_to": mkt.dropna().index[-1].strftime("%Y-%m"),
            "tests_to": (t.index[-1] + pd.offsets.MonthEnd(1)).strftime("%Y-%m"),
            "anchors_to": {"ownership_survey": max(cfg["ownership"])[:7], "fund_and_treasury_holdings": max(cfg["fund_and_treasury_btc"])[:7]},
            "sources": ["Coin Metrics community data (CC BY-NC 4.0)", "US equity market return, Kenneth R. French data library",
                        "US Treasury daily par yield curve rates (ten-year)",
                        "ownership surveys and fund holdings as listed in config/model.toml"],
        },
        "latest": {
            "month_end": band.index[-1].strftime("%Y-%m-%d"),
            "required": {"lower": pct(L.lower), "midpoint": pct(L.midpoint), "upper": pct(L.upper)},
            "worked": {
                "risk_free": pct(L.risk_free),
                "market": {"beta": _r(L.beta), "equity_risk_premium": pct(c["equity_risk_premium"]),
                           "lower": pct(c["market_scale_low"] * L.market_term), "upper": pct(c["market_scale_high"] * L.market_term), "midpoint": pct(L.market_term)},
                "concentration": {"volatility": _r(100 * L.volatility, 1),
                                  "risk_aversion_lower": c["risk_aversion_low"], "risk_aversion_upper": c["risk_aversion_high"],
                                  "weight_lower": _r(100 * L.w_with_funds, 1), "weight_upper": _r(100 * L.w_surveyed, 1),
                                  "lower": pct(c["risk_aversion_low"] * L.variance * L.w_with_funds),
                                  "upper": pct(c["risk_aversion_high"] * L.variance * L.w_surveyed), "midpoint": pct(L.concentration_term)},
                "mortality": {"lower": pct(c["mortality_low"]), "upper": pct(c["mortality_high"]), "midpoint": pct(L.mortality_term)},
                "upper_set_by": "early holder" if L.early_holder_sets_upper else "average surveyed owner",
            },
        },
        "months": months,
        "periods": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in p.items()} for p in periods],
        "census": {"ever_top_twenty": int(len(census)), "died": int(len(dead)), "deaths_by_year": deaths,
                   "as_of": "2026-05-24"},
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
    template = (ROOT / "site" / "template.html").read_text()
    (out / "index.html").write_text(template.replace("__DATA__", json.dumps(_page_payload(doc), separators=(",", ":"), ensure_ascii=False)))
    return doc


def _page_payload(doc: dict) -> dict:
    """The same numbers under the short keys the page's script reads."""
    ym = lambda s: s[:7]
    nxt = lambda s: (pd.Timestamp(s) + pd.offsets.MonthEnd(1)).strftime("%Y-%m")
    rows = []
    for m in doc["months"]:
        q, tm, i, s, n, tr = m["required"], m["terms_at_midpoint"], m["inputs"], m["supply"], m["next_month"] or {}, m["trailing_3y"] or {}
        rows.append({"d": nxt(m["month_end"]), "asof": ym(m["month_end"]), "rf": tm["risk_free"], "mkt": tm["market"], "conc": tm["concentration"],
                     "mort": tm["mortality"], "mid": q["midpoint"], "lo": q["lower"], "hi": q["upper"], "ua": q["upper_if_surveyed_owner"],
                     "ub": q["upper_if_early_holder"], "eb": int(q["upper_set_by"] == "early holder"),
                     "capm": n.get("capm_unexplained"), "mcm": n.get("mcm_unexplained"),
                     "tex": tr.get("excess"), "tcapm": tr.get("capm_unexplained"), "tmcm": tr.get("mcm_unexplained"),
                     "vol": i["volatility"], "beta": i["beta"], "corr": i["correlation"], "wlo": i["weight_with_funds"], "whi": i["weight_surveyed"],
                     "we": i["weight_early_holder"], "iss": s["issuance_rate"], "inst": s["fund_and_treasury_share"]})
    per = [{"p": p["period"], "n": p["months"], "a": p["from"], "b": p["to"], "sum": p["summary"], "real": p["delivered"], "mid": p["required_mid"],
            "gap": p["gap"], "gse": p["gap_se"], "ex": p["excess"], "prem": p["required_premium"], "eq": p["equity_beyond_premium"], "mk": p["market_part"], "cm": p["concentration_mortality_part"],
            "alpha": p["mcm_alpha"], "se": p["mcm_alpha_se"], "calpha": p["capm_alpha"],
            "s_capm": round(p["explained_capm"]), "s_mcm": round(p["explained_mcm"])} for p in doc["periods"]]
    w, lt = doc["latest"]["worked"], doc["latest"]
    tr_rows = [r for r in rows if r["tmcm"] is not None]
    meta = {"data_to": doc["meta"]["data_to"], "month_end": doc["meta"]["latest_month_end"],
            "market_to": doc["meta"]["equity_market_to"], "anchors": doc["meta"]["anchors_to"],
            "band_lo": lt["required"]["lower"], "band_hi": lt["required"]["upper"], "band_mid": lt["required"]["midpoint"],
            "tmcm": tr_rows[-1]["tmcm"], "tcapm": tr_rows[-1]["tcapm"], "to": tr_rows[-1]["d"],
            "deaths": [{"y": d["year"], "fade": d["abandoned_or_delisted"], "jump": d["sudden_collapse"]} for d in doc["census"]["deaths_by_year"]],
            "n_elite": doc["census"]["ever_top_twenty"], "n_dead": doc["census"]["died"], "census_as_of": doc["census"]["as_of"],
            "now": {"asof": ym(lt["month_end"]), "rf": w["risk_free"], "mkt": w["market"]["midpoint"], "conc": w["concentration"]["midpoint"],
                    "mort": w["mortality"]["midpoint"], "mid": lt["required"]["midpoint"], "lo": lt["required"]["lower"], "hi": lt["required"]["upper"],
                    "beta": w["market"]["beta"], "vol": w["concentration"]["volatility"], "wlo": w["concentration"]["weight_lower"],
                    "whi": w["concentration"]["weight_upper"], "mlo": w["market"]["lower"], "mhi": w["market"]["upper"],
                    "clo": w["concentration"]["lower"], "chi": w["concentration"]["upper"], "early": int(w["upper_set_by"] == "early holder")}}
    return {"rows": rows, "per": per, "meta": meta}


def main(argv):
    data = Path(argv[1]) if len(argv) > 1 else ROOT / "data"
    out = Path(argv[2]) if len(argv) > 2 else ROOT / "_site"
    d = build(data, out)
    r = d["latest"]["required"]
    print(f"built {out}/index.html and data.json: data to {d['meta']['data_to']}, "
          f"required return {r['midpoint']}% (band {r['lower']}% to {r['upper']}%)")
