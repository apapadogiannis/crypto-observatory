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

from . import compare, inputs, mcm, tests_of_fit

ROOT = inputs.ROOT
TRAILING = 36


def _r(v, n=2):
    return None if v is None or pd.isna(v) else round(float(v), n)


def _round(p: dict) -> dict:
    out = {}
    for k, v in p.items():
        if k in ("average_beta", "average_correlation"):
            out[k] = round(v, 2)
        elif k == "regression":
            out[k] = v and {m: {"alpha": round(x["alpha"], 1), "se": round(x["se"], 1), "t": round(x["t"], 1), "slope": round(x["slope"], 2)} for m, x in v.items()}
        else:
            out[k] = round(v, 1) if isinstance(v, float) else v
    return out


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
    page_notes = tests_of_fit.notes(band, t, btc)
    implied = inputs.implied_equity_premium(data)
    if implied is not None:
        implied = implied.reindex(implied.index.union(band.index)).ffill()      # a month the source has not posted yet keeps the last value
    premium_rows = tests_of_fit.equity_premium_sensitivity(band, mkt, cfg, implied)
    mid_implied = None if implied is None else mcm.with_equity_premium(band, implied, cfg)["midpoint"]
    rnd = lambda v: None if v is None else round(v, 2)
    premium_doc = {"assumed": 100 * cfg["constants"]["equity_risk_premium"],
                   "implied_source": "Aswath Damodaran, implied equity risk premium by month (trailing twelve-month cash flows), NYU Stern",
                   "implied_to": None if implied is None else (inputs.implied_equity_premium(data).index[-1] + pd.offsets.MonthBegin(1)).strftime("%Y-%m"),
                   "rows": [{**{k: (rnd(v) if isinstance(v, float) else v) for k, v in r.items() if k != "samples"},
                             "samples": {k: {a: rnd(x) for a, x in v.items()} for k, v in r["samples"].items()}} for r in premium_rows]}
    compared = compare.comparison(band, inputs.equity_benchmarks(data), cfg)

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
                       "weight_early_holder": _r(100 * b.w_early, 1),
                       "implied_equity_premium": None if implied is None or pd.isna(implied.get(d, np.nan)) else _r(100 * implied[d])},
            "midpoint_with_implied_equity_premium": None if mid_implied is None else _r(100 * mid_implied[d]),
            "supply": {"issuance_rate": _r(100 * issuance.get(d, np.nan)), "fund_and_treasury_share": _r(100 * fund_share.get(d, np.nan))},
            "next_month": None if not has else {
                "return": _r(100 * t.ret[d], 3), "capm_unexplained": _r(100 * t.capm_unexplained[d], 3),
                "mcm_unexplained": _r(100 * t.mcm_unexplained[d], 3)},
            "trailing_3y": None if not has or pd.isna(trail.mcm.get(d, np.nan)) else {
                "excess": _r(trail.excess[d], 1), "capm_unexplained": _r(trail.capm[d], 1), "mcm_unexplained": _r(trail.mcm[d], 1)},
        })

    census_dir = data / "census"
    census = pd.read_csv(census_dir / "ever_top20.csv", parse_dates=["first_top", "death_date"])
    dead = census[census.death == 1].assign(year=lambda x: x.death_date.dt.year).sort_values("death_date")
    by = dead.groupby(["year", "cat"]).size().unstack(fill_value=0)
    census_summary = json.loads((census_dir / "summary.json").read_text())
    deaths = [{"year": int(y), "abandoned_or_delisted": int(by.loc[y].get(0, 0)) if y in by.index else 0,
               "sudden_collapse": int(by.loc[y].get(1, 0)) if y in by.index else 0}
              for y in range(2012, int(census_summary["census_date"][:4]) + 1)]
    survival = pd.read_csv(census_dir / "survival_by_size.csv")
    names = dict(pd.read_csv(census_dir / "asset_names.csv").fillna("").itertuples(index=False, name=None))
    census_doc = {
        **census_summary, "updated_monthly": False,
        "death_rate_by_age": pd.read_csv(census_dir / "death_rate_by_age.csv").to_dict("records"),
        "death_rate_by_size": pd.read_csv(census_dir / "death_rate_by_size.csv").to_dict("records"),
        "survival_by_size": {g: [[float(a), float(v)] for a, v in zip(x.age, x.alive)] for g, x in survival.groupby("group", sort=False)},
        "deaths_by_year": deaths,
        "ever_top_twenty_deaths_list": [{"asset": r.asset, "name": names.get(r.asset, ""), "entered_top_twenty": r.first_top.strftime("%Y-%m"), "died": r.death_date.strftime("%Y-%m-%d"),
                                         "kind": "sudden collapse" if r.cat == 1 else "abandoned or delisted"} for r in dead.itertuples()],
    }

    c = cfg["constants"]
    L = band.iloc[-1]
    pct = lambda v: _r(100 * v)
    doc = {
        "meta": {
            "asset": "btc", "name": "Bitcoin",
            "author": "Agisilaos Papadogiannis, https://github.com/apapadogiannis",
            "license": "CC BY 4.0 for the numbers in this file, https://creativecommons.org/licenses/by/4.0/. Cite the tool and the paper. "
                       "The source data keep their own terms; Coin Metrics community data are CC BY-NC 4.0.",
            "data_to": last_day.strftime("%Y-%m-%d"), "latest_month_end": band.index[-1].strftime("%Y-%m-%d"),
            "units": "percent a year unless stated; next_month figures are percent a month",
            "method": "Papadogiannis (2026), Bitcoin's Required Return. https://doi.org/10.2139/ssrn.7705239",
            "equity_market_to": mkt.dropna().index[-1].strftime("%Y-%m"),
            "tests_to": (t.index[-1] + pd.offsets.MonthEnd(1)).strftime("%Y-%m"),
            "anchors_to": {"ownership_survey": max(cfg["ownership"])[:7], "fund_and_treasury_holdings": max(cfg["fund_and_treasury_btc"])[:7]},
            "sources": ["Coin Metrics community data (CC BY-NC 4.0)", "US equity market return, Kenneth R. French data library",
                        "US Treasury daily par yield curve rates (ten-year)",
                        "implied equity risk premium by month, Aswath Damodaran (NYU Stern): used for the sensitivity table only",
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
        "periods": [_round(p) for p in periods],
        "comparison": {**compared, "risk_free": round(compared["risk_free"], 2),
                       "rows": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()} for r in compared["rows"]]},
        "notes": page_notes,
        "equity_premium": premium_doc,
        "census": census_doc,
    }
    out.mkdir(parents=True, exist_ok=True)
    from . import publish                              # the files written for programs and AI agents
    doc["meta"]["credit"] = publish.credit(doc)
    doc["meta"]["files"] = publish.publish(doc, [ROOT / "api", out] if data == ROOT / "data" else [out])
    for d in ([ROOT / "api", out] if data == ROOT / "data" else [out]):
        (d / "data.json").write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
    template = (ROOT / "site" / "template.html").read_text()
    html = template.replace("__DATA__", json.dumps(_page_payload(doc), separators=(",", ":"), ensure_ascii=False))
    for mark, text in _static(doc).items():           # readable without JavaScript
        html = html.replace(mark, text)
    (out / "index.html").write_text(html)
    return doc


def _static(doc: dict) -> dict:
    """What is written into the page itself, so that a reader that runs no scripts (a search engine,
    a program, an AI agent) still gets the answer: the latest required return and the periods."""
    from . import publish
    L, w, m = doc["latest"], doc["latest"]["worked"], doc["meta"]
    pct = lambda v: "" if v is None else f"{v:.1f}%"
    rows = "".join(
        f"<tr><td>{p['period']}</td><td>{pct(p['delivered'])}</td><td>{pct(p['required_mid'])}</td>"
        f"<td>{pct(p['required_lower'])} to {pct(p['required_upper'])}</td><td>{pct(p['explained_capm'])}</td>"
        f"<td>{pct(p['explained_mcm'])}</td></tr>" for p in doc["periods"])
    summary = (
        f"<p>At the month-end of {L['month_end']} the required return on Bitcoin is {L['required']['midpoint']}% a year "
        f"at the midpoint, in a band of {L['required']['lower']}% to {L['required']['upper']}%. Of the midpoint, "
        f"{w['risk_free']} points are the risk-free rate, {w['market']['midpoint']} market risk, "
        f"{w['concentration']['midpoint']} concentration risk and {w['mortality']['midpoint']} mortality risk.</p>"
        "<table><thead><tr><th>Period</th><th>Delivered, a year</th><th>Required at the midpoint</th>"
        "<th>Required band</th><th>Explained by the CAPM</th><th>Explained by the MCM equation</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f"<p>Source data to {m['data_to']}; tests to {m['tests_to']}. Required returns are dated at the month-end "
        "they are set; they are not forecasts.</p>")
    ld = {"@context": "https://schema.org", "@type": "Dataset",
          "name": "Crypto Observatory: required returns, risks and survival",
          "description": "Bitcoin's required return for market, concentration and mortality risk, computed each month "
                         "with the MCM equation of the paper Bitcoin's Required Return, with tests of fit and a census "
                         "of cryptoasset deaths.",
          "url": publish.SITE, "identifier": f"https://doi.org/{publish.DOI}",
          "creator": {"@type": "Person", "name": "Agisilaos Papadogiannis", "url": "https://github.com/apapadogiannis",
                      "identifier": "https://orcid.org/0009-0002-7753-7052"},
          "license": publish.LICENCE["url"], "isAccessibleForFree": True,
          "temporalCoverage": f"{doc['months'][0]['month_end']}/{m['latest_month_end']}",
          "dateModified": m["data_to"], "citation": publish.PAPER["doi"],
          "distribution": [{"@type": "DataDownload", "encodingFormat": f["format"], "contentUrl": f["file"],
                            "description": f["what"]} for f in m["files"]]}
    return {"<!--STATIC-->": summary, "/*LD*/": json.dumps(ld, separators=(",", ":"), ensure_ascii=False)}


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
                     "we": i["weight_early_holder"], "erp": i["implied_equity_premium"], "mid2": m["midpoint_with_implied_equity_premium"], "iss": s["issuance_rate"], "inst": s["fund_and_treasury_share"]})
    per = [{"p": p["period"], "n": p["months"], "a": p["from"], "b": p["to"], "sum": p["summary"], "real": p["delivered"], "mid": p["required_mid"],
            "gap": p["gap"], "gse": p["gap_se"], "ex": p["excess"], "prem": p["required_premium"], "eq": p["equity_beyond_premium"], "mk": p["market_part"], "cm": p["concentration_mortality_part"],
            "alpha": p["mcm_alpha"], "se": p["mcm_alpha_se"], "calpha": p["capm_alpha"],
            "beta": p["average_beta"], "corr": p["average_correlation"], "reg": p["regression"],
            "s_capm": round(p["explained_capm"]), "s_mcm": round(p["explained_mcm"])} for p in doc["periods"]]
    w, lt = doc["latest"]["worked"], doc["latest"]
    tr_rows = [r for r in rows if r["tmcm"] is not None]
    meta = {"data_to": doc["meta"]["data_to"], "month_end": doc["meta"]["latest_month_end"],
            "market_to": doc["meta"]["equity_market_to"], "anchors": doc["meta"]["anchors_to"], "notes": doc["notes"], "cmp": doc["comparison"], "erp": doc["equity_premium"],
            "band_lo": lt["required"]["lower"], "band_hi": lt["required"]["upper"], "band_mid": lt["required"]["midpoint"],
            "tmcm": tr_rows[-1]["tmcm"], "tcapm": tr_rows[-1]["tcapm"], "to": tr_rows[-1]["d"],
            "deaths": [{"y": d["year"], "fade": d["abandoned_or_delisted"], "jump": d["sudden_collapse"]} for d in doc["census"]["deaths_by_year"]],
            "n_elite": doc["census"]["ever_top_twenty"], "n_dead": doc["census"]["ever_top_twenty_deaths"], "census": doc["census"],
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
