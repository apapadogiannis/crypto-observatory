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

from . import compare, inputs, mcm, state, tests_of_fit

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
    compared = compare.comparison(band, inputs.equity_benchmarks(data), cfg, gold=inputs.gold_return(data, cfg))

    supply = btc["SplyCur"].dropna().resample("ME").last()
    issuance = btc["IssTotNtv"].resample("ME").sum() * 12 / supply
    fund_share = band["fund_btc"] / supply.reindex(band.index)
    roll = lambda s: 1200 * s.rolling(TRAILING).mean()
    trail = pd.DataFrame({"excess": roll(t.excess), "capm": roll(t.capm_unexplained), "mcm": roll(t.mcm_unexplained)})

    comp, load, fall = state.compound(band), state.loadings(band, cfg), state.drawdown(btc, band)
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
            "compound": {"drag": _r(100 * comp.drag[d]), "lower": _r(100 * comp.lower[d]), "midpoint": _r(100 * comp.midpoint[d]),
                         "upper": _r(100 * comp.upper[d])},
            "pay_for_variance": {"lower": _r(load.lower[d], 3), "midpoint": _r(load.midpoint[d], 3), "upper": _r(load.upper[d], 3)},
            "drawdown": _r(fall[d], 1),
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
    rules = pd.read_csv(census_dir / "death_rules.csv").set_index("asset")
    by_rule = rules.rule.value_counts()
    # Deaths by the price rule alone: the asset lost 99% of its peak value and still trades.
    still_trading = rules[rules.rule == "price below 1% of peak"]
    at_risk = pd.read_csv(census_dir / "death_rate_by_size.csv").set_index("group").loc["Ever in the top twenty", "asset_years"]
    census_end = pd.Timestamp(census_summary["census_date"])
    extra_years = sum((census_end - d).days / 365.25 for d in dead[dead.asset.isin(still_trading.index)].death_date)
    census_doc = {
        **census_summary, "updated_monthly": False,
        "deaths_by_rule": {k: int(v) for k, v in by_rule.items()},
        "paper_version": "2.0",
        "changed_since_version_1": "Version 2.0 of the paper leaves out the Lithuanian litas (a national currency), 116 tokenized shares "
                                   "and funds, three gold tokens, 57 stablecoins and 17 copies of other assets, and no longer counts 27 "
                                   "ticker changes and token swaps as deaths. Version 1.0 had 1,815 assets and 520 deaths, and 36 deaths "
                                   "among 219 top-twenty assets (3.54% a year).",
        "death_rate_without_price_rule_deaths": _r(100 * (len(dead) - len(still_trading)) / (at_risk + extra_years)),
        "death_rate_by_age": pd.read_csv(census_dir / "death_rate_by_age.csv").to_dict("records"),
        "death_rate_by_size": pd.read_csv(census_dir / "death_rate_by_size.csv").to_dict("records"),
        "survival_by_size": {g: [[float(a), float(v)] for a, v in zip(x.age, x.alive)] for g, x in survival.groupby("group", sort=False)},
        "deaths_by_year": deaths,
        "ever_top_twenty_deaths_list": [{"asset": r.asset, "name": names.get(r.asset, ""), "entered_top_twenty": r.first_top.strftime("%Y-%m"), "died": r.death_date.strftime("%Y-%m-%d"),
                                         "kind": "sudden collapse" if r.cat == 1 else "abandoned or delisted",
                                         "rule": rules.rule[r.asset],
                                         "volume_at_end_usd_a_day": None if pd.isna(rules.volume_at_end_usd_a_day[r.asset]) else int(rules.volume_at_end_usd_a_day[r.asset]),
                                         "feed_last_day": rules.feed_last_day[r.asset]} for r in dead.itertuples()],
    }

    c = cfg["constants"]
    L = band.iloc[-1]
    pct = lambda v: _r(100 * v)
    months_since = lambda d: (band.index[-1].year - int(d[:4])) * 12 + band.index[-1].month - int(d[5:7])
    anchor_age = {"ownership_survey": months_since(max(cfg["ownership"])),
                  "fund_and_treasury_holdings": max(0, months_since(max(cfg["fund_and_treasury_btc"])))}
    doc = {
        "meta": {
            "asset": "btc", "name": "Bitcoin",
            "author": "Agisilaos Papadogiannis, https://github.com/apapadogiannis",
            "license": "CC BY 4.0 for the numbers in this file, https://creativecommons.org/licenses/by/4.0/. Cite the tool and the paper. "
                       "The source data keep their own terms and CC BY 4.0 does not extend to them: Coin Metrics community data, which include the Bitcoin "
                       "prices under state and path, are CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/), for non-commercial use.",
            "data_to": last_day.strftime("%Y-%m-%d"), "latest_month_end": band.index[-1].strftime("%Y-%m-%d"),
            # the update runs on the third of each month, for the month-end before it
            "next_update": (band.index[-1] + pd.offsets.MonthBegin(2) + pd.Timedelta(days=2)).strftime("%Y-%m-%d"),
            "units": "percent a year unless stated; next_month figures are percent a month",
            "method": "Papadogiannis (2026), Bitcoin's Required Return. https://doi.org/10.2139/ssrn.7705239",
            "equity_market_to": mkt.dropna().index[-1].strftime("%Y-%m"),
            "tests_to": (t.index[-1] + pd.offsets.MonthEnd(1)).strftime("%Y-%m"),
            "anchors_to": {"ownership_survey": max(cfg["ownership"])[:7], "fund_and_treasury_holdings": max(cfg["fund_and_treasury_btc"])[:7]},
            "anchors_age_months": anchor_age,
            "anchors_overdue": [k for k, limit in (("ownership_survey", c["ownership_survey_max_age_months"]),
                                                   ("fund_and_treasury_holdings", c["fund_holdings_max_age_months"])) if anchor_age[k] > limit],
            "model": {
                "equity_risk_premium": pct(c["equity_risk_premium"]),
                "market_scale": [c["market_scale_low"], c["market_scale_high"]],
                "risk_aversion": [c["risk_aversion_low"], c["risk_aversion_high"]],
                "mortality": [pct(c["mortality_low"]), pct(c["mortality_high"])],
                "volatility_halflife_months": c["volatility_halflife_months"],
                "beta_window_months": c["beta_window_months"], "beta_min_months": c["beta_min_months"], "beta_cap": c["beta_cap"],
                "weight_cap_pct": 100 * c["weight_cap"], "owner_weight_pct": round(100 * c["owner_weight"], 1),
                "fund_investor_weight_pct": round(100 * c["fund_investor_weight"], 1),
                "beta_carried_forward_from": mkt.dropna().index[-1].strftime("%Y-%m"),
                "history_uses_later_anchors": True,
            },
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
                       "gold_inputs": {"weight_pct": [round(100 * cfg["gold"]["weight_low"], 1), round(100 * cfg["gold"]["weight_high"], 1)],
                                       "mortality_pct": [round(100 * cfg["gold"]["mortality_low"], 2), round(100 * cfg["gold"]["mortality_high"], 2)],
                                       "beta": [cfg["gold"]["beta_low"], cfg["gold"]["beta_high"]], "basis": "set by judgment, not surveyed (paper, Appendix E.1)"},
                       "rows": [{k: (round(v, 2) if isinstance(v, float) else {a: round(b, 2) for a, b in v.items()} if isinstance(v, dict) else v) for k, v in r.items()} for r in compared["rows"]]},
        "notes": page_notes,
        "equity_premium": premium_doc,
        "census": census_doc,
        "holders": _holders(data, cfg),
        "assets": _assets(data, btc, band, mkt, cfg),
        "volatility_sensitivity": state.sensitivity(band, cfg),
        "state": {**state.state(btc, band), "prices_licence": "Coin Metrics community data, CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/): non-commercial use with attribution. CC BY 4.0 does not extend to these prices."},
        "path": {**state.paths(btc, band), "prices_licence": "Coin Metrics community data, CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/): non-commercial use with attribution. CC BY 4.0 does not extend to these prices."},
    }
    out.mkdir(parents=True, exist_ok=True)
    doc["vintages"] = _vintages(data, doc)
    from . import publish                              # the files written for programs and AI agents
    doc["meta"]["credit"] = publish.credit(doc)
    doc["meta"]["files"] = publish.publish(doc, [ROOT / "api", out] if data == ROOT / "data" else [out])
    for d in ([ROOT / "api", out] if data == ROOT / "data" else [out]):
        (d / "data.json").write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
    template = (ROOT / "site" / "template.html").read_text()
    html = template.replace("__DATA__", json.dumps(_page_payload(doc), separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c"))
    for mark, text in _static(doc).items():           # readable without JavaScript
        html = html.replace(mark, text)
    (out / "index.html").write_text(html)
    for asset in sorted((ROOT / "site" / "assets").iterdir()):         # the mark, the tab icon and the card shown when the page is shared
        (out / asset.name).write_bytes(asset.read_bytes())
    return doc


VINTAGE_COLUMNS = ["month_end", "recorded_with_data_to", "required_lower", "required_midpoint", "required_upper",
                   "risk_free", "market_term", "concentration_term", "mortality_term"]


def _vintages(data: Path, doc: dict) -> list[dict]:
    """The record of what was published for each month-end when it was first computed.

    months.csv is recomputed at every build with the data and the hand-entered anchors of that day,
    so a past month's figure can change. This file does not: a month-end gets one row, the first
    time a build has it as its latest month, and that row is never rewritten. It is kept in the
    data folder beside the sources, and only added to.
    """
    path = data / "vintages.csv"
    rows = pd.read_csv(path, dtype=str).to_dict("records") if path.exists() else []
    L, w = doc["latest"], doc["latest"]["worked"]
    if L["month_end"] not in {r["month_end"] for r in rows}:
        rows.append({k: str(v) for k, v in zip(VINTAGE_COLUMNS, [
            L["month_end"], doc["meta"]["data_to"], L["required"]["lower"], L["required"]["midpoint"], L["required"]["upper"],
            w["risk_free"], w["market"]["midpoint"], w["concentration"]["midpoint"], w["mortality"]["midpoint"]])})
        rows.sort(key=lambda r: r["month_end"])
        pd.DataFrame(rows, columns=VINTAGE_COLUMNS).to_csv(path, index=False)
    return [{k: (r[k] if k in ("month_end", "recorded_with_data_to") else float(r[k])) for k in VINTAGE_COLUMNS} for r in rows]


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
    return {"<!--STATIC-->": summary, "/*LD*/": json.dumps(ld, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")}


def _assets(data: Path, btc: pd.DataFrame, band: pd.DataFrame, mkt: pd.Series, cfg: dict) -> dict:
    """Bitcoin and the other priced assets side by side: the latest month-end, and every month each has been priced."""
    from . import assets
    other = assets.required_returns(data, btc, band, mkt, cfg)
    names = {"btc": "Bitcoin", **cfg["other_assets"]}
    frames = {"btc": pd.DataFrame({"risk_free": band.risk_free, "volatility": band.volatility, "beta": band.beta, "kappa": 1.0,
                                   "w_lower": band.w_with_funds, "w_upper": band.w_surveyed, "market_term": band.market_term,
                                   "mortality_term": band.mortality_term, "concentration_term": band.concentration_term,
                                   "lower": band.lower, "upper": band.upper, "midpoint": band.midpoint,
                                   "market_share": other["market_weights"]["btc"]}), **other["assets"]}

    def record(code, d, b):
        vol, mid, rf = 100 * b.volatility, 100 * b.midpoint, 100 * b.risk_free
        drag = vol ** 2 / 200
        return {"month_end": d.strftime("%Y-%m-%d"), "asset": code, "name": names[code],
                "required_return": _r(mid), "required_low": _r(100 * b.lower), "required_high": _r(100 * b.upper),
                "risk_free": _r(rf), "market_term": _r(100 * b.market_term), "concentration_term": _r(100 * b.concentration_term),
                "mortality_term": _r(100 * b.mortality_term), "volatility": _r(vol, 1), "beta_to_us_equities": _r(b.beta),
                "kappa": _r(b.kappa), "holder_weight_low": _r(100 * b.w_lower, 1), "holder_weight_high": _r(100 * b.w_upper, 1),
                "volatility_drag": _r(drag), "compound_required_return": _r(mid - drag),
                "compound_required_low": _r(100 * b.lower - drag), "compound_required_high": _r(100 * b.upper - drag),
                "sharpe_ratio": _r((mid - rf) / vol), "sharpe_ratio_on_compound": _r((mid - drag - rf) / vol), "share_of_crypto_market": None if pd.isna(b.market_share) else _r(100 * b.market_share, 1)}

    monthly = [record(code, d, b) for code, f in frames.items() for d, b in f.iterrows()]
    latest = [{**record(code, f.index[-1], f.iloc[-1]), "priced_since": f.index[0].strftime("%Y-%m")} for code, f in frames.items()]
    if {r["month_end"] for r in latest} != {band.index[-1].strftime("%Y-%m-%d")}:
        raise ValueError("the assets are not all priced at the same month-end: " + ", ".join(f"{r['asset']} {r['month_end']}" for r in latest))
    return {"month_end": band.index[-1].strftime("%Y-%m-%d"), "latest": latest, "monthly": monthly,
            "tests": [{**r, "name": names[r["asset"]]} for r in assets.tests(data, band, mkt, other)],
            "crypto_market": "value-weighted return of " + ", ".join(names.values()) + ", weights from the previous month-end's market values",
            "min_months": cfg["constants"]["asset_min_months"]}


def _holders(data: Path, cfg: dict) -> dict:
    """What the holder's weight rests on: the three hand-entered settings, the ownership surveys behind the
    early holder's weight, and the survey waves shown as evidence that holdings per owner do not follow the price."""
    import csv
    num = lambda v: None if v == "" else float(v)
    waves = [{**{k: r[k] for k in ("country", "survey", "fieldwork", "month", "currency")},
              **{k: num(r[k]) for k in ("ownership_pct", "owners_million", "median_holding", "mean_holding", "bitcoin_price_usd")}}
             for r in csv.DictReader((data / "surveys" / "holder_surveys.csv").open(encoding="utf-8"))]
    c = cfg["constants"]
    return {"owner_weight": round(100 * c["owner_weight"], 1), "fund_investor_weight": round(100 * c["fund_investor_weight"], 1),
            "early_holder_all_in_below_ownership": round(100 * c["few_hands_ownership"], 1),
            "us_ownership_surveys": [{"date": d, "ownership_pct": round(100 * v, 1)} for d, v in cfg["ownership"].items()],
            "survey_waves": waves}


def _page_payload(doc: dict) -> dict:
    """The same numbers under the short keys the page's script reads."""
    ym = lambda s: s[:7]
    nxt = lambda s: (pd.Timestamp(s) + pd.offsets.MonthEnd(1)).strftime("%Y-%m")
    rows = []
    price = dict(doc["path"]["prices"])
    for m in doc["months"]:
        q, tm, i, s, n, tr = m["required"], m["terms_at_midpoint"], m["inputs"], m["supply"], m["next_month"] or {}, m["trailing_3y"] or {}
        cp, pv = m["compound"], m["pay_for_variance"]
        rows.append({"d": nxt(m["month_end"]), "asof": ym(m["month_end"]), "rf": tm["risk_free"], "mkt": tm["market"], "conc": tm["concentration"],
                     "mort": tm["mortality"], "mid": q["midpoint"], "lo": q["lower"], "hi": q["upper"], "ua": q["upper_if_surveyed_owner"],
                     "ub": q["upper_if_early_holder"], "eb": int(q["upper_set_by"] == "early holder"),
                     "capm": n.get("capm_unexplained"), "mcm": n.get("mcm_unexplained"),
                     "tex": tr.get("excess"), "tcapm": tr.get("capm_unexplained"), "tmcm": tr.get("mcm_unexplained"),
                     "vol": i["volatility"], "beta": i["beta"], "corr": i["correlation"], "wlo": i["weight_with_funds"], "whi": i["weight_surveyed"],
                     "we": i["weight_early_holder"], "erp": i["implied_equity_premium"], "mid2": m["midpoint_with_implied_equity_premium"], "iss": s["issuance_rate"], "inst": s["fund_and_treasury_share"],
                     "drag": cp["drag"], "clo": cp["lower"], "cmid": cp["midpoint"], "chi": cp["upper"],
                     "plo": pv["lower"], "pmid": pv["midpoint"], "phi": pv["upper"], "dd": m["drawdown"], "px": price[ym(m["month_end"])]})
    per = [{"p": p["period"], "n": p["months"], "a": p["from"], "b": p["to"], "sum": p["summary"], "real": p["delivered"], "mid": p["required_mid"],
            "gap": p["gap"], "gse": p["gap_se"], "ex": p["excess"], "prem": p["required_premium"], "eq": p["equity_beyond_premium"], "mk": p["market_part"], "cm": p["concentration_mortality_part"],
            "alpha": p["mcm_alpha"], "se": p["mcm_alpha_se"], "calpha": p["capm_alpha"],
            "beta": p["average_beta"], "corr": p["average_correlation"], "reg": p["regression"],
            "s_capm": round(p["explained_capm"]), "s_mcm": round(p["explained_mcm"])} for p in doc["periods"]]
    w, lt = doc["latest"]["worked"], doc["latest"]
    tr_rows = [r for r in rows if r["tmcm"] is not None]
    meta = {"data_to": doc["meta"]["data_to"], "month_end": doc["meta"]["latest_month_end"], "next_update": doc["meta"]["next_update"],
            "state": doc["state"], "vsens": doc["volatility_sensitivity"], "path": {k: v for k, v in doc["path"].items() if k != "prices"},
            "market_to": doc["meta"]["equity_market_to"], "anchors": doc["meta"]["anchors_to"], "anchors_age": doc["meta"]["anchors_age_months"], "anchors_overdue": doc["meta"]["anchors_overdue"], "notes": doc["notes"], "cmp": doc["comparison"], "erp": doc["equity_premium"],
            "band_lo": lt["required"]["lower"], "band_hi": lt["required"]["upper"], "band_mid": lt["required"]["midpoint"],
            "tmcm": tr_rows[-1]["tmcm"], "tcapm": tr_rows[-1]["tcapm"], "to": tr_rows[-1]["d"],
            "deaths": [{"y": d["year"], "fade": d["abandoned_or_delisted"], "jump": d["sudden_collapse"]} for d in doc["census"]["deaths_by_year"]],
            "assets": {"latest": doc["assets"]["latest"], "tests": doc["assets"]["tests"],
                       "detail": {a: [{"m": r["month_end"][:7], "mid": r["required_return"], "lo": r["required_low"], "hi": r["required_high"], "rf": r["risk_free"],
                                       "mkt": r["market_term"], "conc": r["concentration_term"], "mort": r["mortality_term"], "vol": r["volatility"],
                                       "beta": r["beta_to_us_equities"], "kappa": r["kappa"], "whi": r["holder_weight_high"], "wlo": r["holder_weight_low"],
                                       "cmid": r["compound_required_return"], "clo": r["compound_required_low"], "chi": r["compound_required_high"]}
                                      for r in doc["assets"]["monthly"] if r["asset"] == a] for a in [r["asset"] for r in doc["assets"]["latest"] if r["asset"] != "btc"]},
                       "hist": {a: [[r["month_end"][:7], r["required_return"]] for r in doc["assets"]["monthly"] if r["asset"] == a] for a in [r["asset"] for r in doc["assets"]["latest"]]}}, "holders": doc["holders"], "n_elite": doc["census"]["ever_top_twenty"], "n_dead": doc["census"]["ever_top_twenty_deaths"], "census": doc["census"],
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
