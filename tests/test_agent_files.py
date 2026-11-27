"""The files written for programs and AI agents agree with the page's own data file.

    python3 -I tests/test_agent_files.py

Builds from the stored data into a temporary folder and checks that the CSV files carry the same
numbers as data.json, that every column is described, and that licence and citation are the same
wherever they appear.
"""
import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from observatory.build import build  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)
    build(ROOT / "data", out)
    doc = json.loads((out / "data.json").read_text(encoding="utf-8"))
    pkg = json.loads((out / "datapackage.json").read_text(encoding="utf-8"))
    guide = (out / "llms.txt").read_text(encoding="utf-8")
    page = (out / "index.html").read_text(encoding="utf-8")
    read = lambda name: list(csv.DictReader((out / name).open(encoding="utf-8")))
    months, periods, deaths = read("months.csv"), read("periods.csv"), read("census_deaths.csv")
    latest_json = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    assets_now, assets_all = read("assets.csv"), read("assets_monthly.csv")
    latest_size = len((out / "latest.json").read_bytes())
    vintages = read("vintages.csv")
    api = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "api").iterdir()}
    assets = {p.name for p in (ROOT / "site" / "assets").iterdir()}
    assert assets == {"favicon.svg", "apple-touch-icon.png", "social-card.png", "d3.min.js"} and all((out / n).stat().st_size > 0 for n in assets)
    for name, text in api.items():
        assert (out / name).read_text(encoding="utf-8") == text, f"api/{name} is not what the build produces"

# Same rows and the same numbers as the data file.
assert len(months) == len(doc["months"]) and len(periods) == len(doc["periods"])
for row, m in zip(months, doc["months"]):
    assert row["month_end"] == m["month_end"]
    assert float(row["required_midpoint"]) == m["required"]["midpoint"]
    assert float(row["concentration_term"]) == m["terms_at_midpoint"]["concentration"]
    assert (row["next_month_return"] == "") == (m["next_month"] is None)
for row, p in zip(periods, doc["periods"]):
    assert row["period"] == p["period"] and float(row["delivered"]) == p["delivered"]
    assert float(row["delivered_compound"]) == p["delivered_compound"]
    assert float(row["explained_mcm"]) == p["explained_mcm"]
assert len(deaths) == doc["census"]["ever_top_twenty_deaths"] == len(doc["census"]["ever_top_twenty_deaths_list"])

# Every column is described, in the order it appears.
for name, rows in (("months", months), ("periods", periods), ("census_deaths", deaths), ("vintages", vintages), ("assets", assets_now), ("assets_monthly", assets_all)):
    fields = next(r for r in pkg["resources"] if r["name"] == name)["schema"]["fields"]
    assert [f["name"] for f in fields] == list(rows[0].keys()), name
    assert all(f["description"] for f in fields)

# The small file for assistants: one record per asset, Bitcoin's the page's own figure, the terms adding up,
# and the same numbers as the tables. It stays small.
la = {a["asset_id"]: a for a in latest_json["assets"]}
assert list(la) == ["btc", "eth", "bnb", "sol", "trx"] and len(assets_now) == 5
assert la["btc"]["required_midpoint_pct_per_year"] == doc["latest"]["required"]["midpoint"] and la["btc"]["kappa"] == 1.0
assert latest_json["as_of_month_end"] == doc["latest"]["month_end"] and latest_json["source_data_to"] == doc["meta"]["data_to"]
for a in la.values():
    parts = a["risk_free_pct_per_year"] + a["market_term_pct_per_year"] + a["concentration_term_pct_per_year"] + a["mortality_term_pct_per_year"]
    assert abs(parts - a["required_midpoint_pct_per_year"]) < 0.03, a["asset_id"]
    assert a["required_lower_pct_per_year"] < a["required_midpoint_pct_per_year"] < a["required_upper_pct_per_year"]
    # both sides are rounded for publication (weights to 0.1, kappa to 0.01), which alone allows 0.2
    assert abs(a["holder_weight_upper_pct"] - a["kappa"] * la["btc"]["holder_weight_upper_pct"]) < 0.2
for row in assets_now:
    assert float(row["required_midpoint_pct_per_year"]) == la[row["asset_id"]]["required_midpoint_pct_per_year"]
assert latest_size < 14_000 and [b['name'] for b in latest_json['benchmarks_for_comparison']][-1] == 'Gold' and "latest.json" in guide.split("## Coverage")[0]
# Ether's kappa in April 2026 is the paper's 0.70 to within 0.02, although the crypto market here is five assets.
eth_apr = next(r for r in assets_all if r["asset_id"] == "eth" and r["month_end"] == "2026-04-30")
assert abs(float(eth_apr["kappa"]) - 0.70) <= 0.02, eth_apr["kappa"]

# The census: no national currency among the deaths, every death carries the rule that classified it,
# and the counts by rule add up. The upper mortality figure stays the paper's.
c = doc["census"]
assert "ltl" not in {d["asset"] for d in deaths} and c["ever_top_twenty_deaths"] == 35 and c["ever_top_twenty"] == 216
rules = {"trading dried up", "price below 1% of peak", "data feed ended", "sudden collapse"}
assert {d["rule"] for d in deaths} <= rules and sum(c["deaths_by_rule"].values()) == len(deaths)
assert all((d["rule"] == "sudden collapse") == (d["kind"] == "sudden collapse") for d in deaths)
assert all(float(d["volume_at_end_usd_a_day"]) > 250_000 for d in deaths if d["rule"] == "price below 1% of peak")
top = next(r for r in c["death_rate_by_size"] if r["group"] == "Ever in the top twenty")
assert top["deaths"] == 35 and c["death_rate_without_price_rule_deaths"] < top["rate"] == c["ever_top_twenty_death_rate"]
assert round(top["rate"], 1) == 3.5 == doc["meta"]["model"]["mortality"][1]
assert c["by_period"]["all assets"]["rate_to_2024"] < c["by_period"]["all assets"]["rate"]
from observatory.census import FIAT  # noqa: E402
assert "ltl" in FIAT and "usd" in FIAT

# Compounding and the state. The compound band is the band less the drag in every month, and agrees with
# the assets file; the pay for variance times variance is the concentration term at the latest month; the
# sensitivity table reproduces the latest band at the month's own volatility; one row of each record is "now".
btc_monthly = {r["month_end"]: r for r in assets_all if r["asset_id"] == "btc"}
for row, m in zip(months, doc["months"]):
    drag = float(row["volatility_drag"])
    for edge in ("lower", "midpoint", "upper"):
        assert abs(float(row[f"required_compound_{edge}"]) - (float(row[f"required_{edge}"]) - drag)) < 0.02, row["month_end"]
    assert float(row["required_compound_midpoint"]) == float(btc_monthly[row["month_end"]]["required_compound_pct_per_year"])
    assert float(row["required_compound_lower"]) == float(btc_monthly[row["month_end"]]["required_compound_lower_pct_per_year"])
    assert 0 < float(row["pay_for_variance_lower"]) <= float(row["pay_for_variance_midpoint"]) <= float(row["pay_for_variance_upper"]) <= 1
    assert -100 < float(row["drawdown"]) <= 0
vs, st, last = doc["volatility_sensitivity"], doc["state"], doc["months"][-1]
variance = 2 * last["compound"]["drag"]                                   # points a year
if last["required"]["upper_set_by"] == "average surveyed owner":
    assert abs(vs["pay_for_variance"]["midpoint"] * variance - last["terms_at_midpoint"]["concentration"]) < 0.05
now = [r for r in vs["rows"] if r["current"]]
assert len(now) == 1 and now[0]["average"] == {k: last["required"][k] for k in ("lower", "midpoint", "upper")}
assert now[0]["compound"] == {k: last["compound"][k] for k in ("lower", "midpoint", "upper")}
assert [r["volatility"] for r in vs["rows"]] == sorted(r["volatility"] for r in vs["rows"])
for r in vs["rows"]:                                                      # below one half the compound figure falls with volatility, above it rises
    for edge, prev in zip(("lower", "upper"), (vs["rows"][0]["compound"]["lower"], vs["rows"][0]["compound"]["upper"])):
        if r is not vs["rows"][0] and r["upper_set_by"] == "average surveyed owner":
            assert (r["compound"][edge] > prev) == (vs["pay_for_variance"][edge] > vs["break_even_pay_for_variance"]), (edge, r["volatility"])
assert st["month_end"] == doc["latest"]["month_end"] == latest_json["as_of_month_end"] and st["drawdown"] == last["drawdown"]
assert abs(st["drawdown"] - 100 * (st["price_usd"] / st["peak_month_end_close_usd"] - 1)) < 0.06
for sample in st["samples"].values():
    for rows in (sample["by_drawdown"], sample["by_volatility"]):
        assert sum(r["current"] for r in rows) == 1 and sum(r["months"] for r in rows) == sample["months_with_outcome"]
        assert all(1 <= r["spells"] <= r["months"] for r in rows if r["months"])
assert latest_json["next_update_expected"] > latest_json["as_of_month_end"] and latest_json["next_update_expected"][8:] == "03"
assert latest_json["bitcoin_state_at_month_end"]["price_usd"] == st["price_usd"]
assert "record, not a forecast" in guide and "record, not a forecast" in page

# The trend line and the path: every path starts at the latest month-end; the one from the latest close starts
# on the price, a higher level leads to a higher price, and the edges and the range bracket the path.
pa = doc["path"]
assert pa["month_end"] == doc["latest"]["month_end"] and [x[0] for x in pa["prices"]] == [m["month_end"][:7] for m in doc["months"]]
assert abs(pa["prices"][-1][1] - st["price_usd"]) < 1
first = pa["levels"][0]
assert first["key"] == "latest" and first["level"] == round(pa["prices"][-1][1]) and first["price_against_it"] == 0
for lv in pa["levels"]:
    assert lv["range_at_horizon"][0] < lv["path_at_horizon"] < lv["range_at_horizon"][1]
    assert lv["edges_at_horizon"][0] <= lv["path_at_horizon"] <= lv["edges_at_horizon"][1]
    assert abs(lv["path_at_horizon"] / lv["level"] - first["path_at_horizon"] / first["level"]) < 1e-3      # one growth rate for every level
    assert (lv["price_against_it"] < 0) == (lv["level"] > first["level"])
assert pa["growth_ahead"]["midpoint"] == last["compound"]["midpoint"]
for tr in pa["trend"].values():
    assert tr["range_at_horizon"][0] < tr["value_at_horizon"] < tr["range_at_horizon"][1] and tr["growth"] > 0
    assert tr["path_from_its_level"]["level"] == tr["value_now"]
assert "Neither is a forecast" in page and "`path` in data.json" in guide

# The test of the other assets: one row each, the MCM equation leaving no more unexplained than the CAPM
# (it adds two terms that are never negative), and the limits stated wherever the figures are.
at = {r["asset"]: r for r in doc["assets"]["tests"]}
assert list(at) == ["eth", "bnb", "sol", "trx"]
for r in at.values():
    assert r["mcm_unexplained"] <= r["capm_unexplained"] and r["months"] >= 36 and r["mcm_unexplained_se"] > 0
    assert abs(r["gap"] - (r["delivered"] - r["required_mid"])) < 0.2
    assert sum(p["months"] for p in r["periods"]) == r["months"] and all(p["gap_se"] > 0 for p in r["periods"])
assert "survivors" in guide and "These four are survivors" in page
# The sections: five, and every address the site has used opens one of them.
for view in ("compare", "bitcoin", "altcoins", "method", "data"):
    assert f'id="view-{view}"' in page
for pane in ("overview", "tests", "volatility", "path", "equation", "band", "holders", "census"):
    assert page.count(f'id="pane-{pane}"') == 1 and f'data-tab="{pane}"' in page
assert 'id="onpage"' in page and page.count('<section class="card"') == page.count('data-nav="')      # every card is listed in "On this page"
assert '"required-return":["method","band"]' in page and 'compared:["compare"]' in page

# The record of what was first published: one row per month-end, the latest month in it, and stored
# rows unchanged by a build.
stored = list(csv.DictReader((ROOT / "data" / "vintages.csv").open(encoding="utf-8")))
assert [v["month_end"] for v in stored] == sorted({v["month_end"] for v in stored}) and stored == vintages
assert doc["latest"]["month_end"] in {v["month_end"] for v in stored}
row = next(v for v in stored if v["month_end"] == doc["latest"]["month_end"])
assert row["recorded_with_data_to"] <= doc["meta"]["data_to"]

# The model's fixed settings are stated to agents, with the age of the hand-entered inputs.
mo = doc["meta"]["model"]
assert f"half-life {mo['volatility_halflife_months']} months" in guide and f"trailing {mo['beta_window_months']} months" in guide
assert "requirement built in hindsight" in guide and set(doc["meta"]["anchors_age_months"]) == {"ownership_survey", "fund_and_treasury_holdings"}
assert all(k in doc["meta"]["anchors_age_months"] for k in doc["meta"]["anchors_overdue"])

# Licence and citation are the same everywhere, and the guide states the latest figure.
credit = doc["meta"]["credit"]
assert credit["cite_as"] == pkg["citation"] and credit["cite_as"] in guide
assert credit["paper"]["doi"] in guide and credit["licence"]["source_data"] in guide
latest = doc["latest"]["required"]
assert f"{latest['midpoint']}% a year at the midpoint" in guide

# No skill of its own: the guide and the page point to the one skill of the whole account.
assert "SKILL.md" not in api and "apapadogiannis/main/skill/SKILL.md" in guide and "apapadogiannis/blob/main/skill/SKILL.md" in page
for name in ("llms.txt", "latest.json", "assets.csv", "assets_monthly.csv", "data.json", "months.csv", "periods.csv", "census_deaths.csv", "vintages.csv", "datapackage.json"):
    assert name in api, name

# The mark, the tab icon and the share card are linked from the page, and the card by its full address.
assert 'href="favicon.svg' in page and 'href="apple-touch-icon.png' in page and page.count("Market Risk, Concentration and Mortality") >= 5 and credit["site"] + "social-card.png" in page

# The page says the answer without JavaScript, and no placeholder is left in it.
assert "<noscript>" in page and "<!--STATIC-->" not in page and "/*LD*/" not in page and "__DATA__" not in page
assert f"is {latest['midpoint']}% a year" in page
print(f"agent files agree with data.json: {len(months)} months, {len(periods)} periods, {len(deaths)} deaths")

# What keeps the monthly update from stopping, and the page from coming up empty.
# 1. The three-year periods cover every month, also in the first months of a new period and for a record that starts late in one.
import pandas as pd
from observatory import tests_of_fit
for first, last in (("2012-01", "2027-01"), ("2012-01", "2027-05"), ("2012-01", "2027-06"), ("2012-01", "2030-02"), ("2020-10", "2027-03"),
                    ("2023-11", "2026-08"), ("2026-09", "2027-02"), ("2026-11", "2027-01")):
    idx = pd.date_range(first, last, freq="ME")
    spans = tests_of_fit.period_spans(idx)
    sizes = [int(((idx.year >= a) & (idx.year <= b)).sum()) for a, b in spans]
    assert sum(sizes) == len(idx) and (min(sizes) >= 6 or len(spans) == 1), (first, last, spans)
    assert all(b < c for (_, b), (c, _) in zip(spans, spans[1:]))
# 2. The page draws with a library it serves itself, checked against a fixed hash, and says so when it is missing.
import base64, hashlib
d3 = (ROOT / "site" / "assets" / "d3.min.js").read_bytes()
# d3 7.9.0 as published: the hash is the one cdnjs lists for the file
assert base64.b64encode(hashlib.sha512(d3).digest()).decode() == "vc58qvvBdrDR4etbxMdlTt4GBQk1qjvyORR2nrsPsFPyrs+/u5c3+1Ct6upOgdZoIl7eq6k3a1UPDSNAQi/32A=="
assert 'src="d3.min.js"' in page and "cdnjs" not in page
assert page.index("<noscript>") < page.index('id="view-compare"') and 'id="nolib"' in page and "function safely" in page
# 3. One name, one unit; the months of the test say what they are; one answer on the other assets' test.
assert all("price_against_it_sd" in v and "price_against_it" not in v for v in doc["path"]["trend"].values())
dr = latest_json["bitcoin_delivered_against_required"]
assert dr["required_set_from_month_end"] == "2018-01" and dr["returns_from_month"] == "2018-02" and dr["unexplained_by_mcm_standard_error_pct_points"] > 0
assert "are not tested" not in guide + json.dumps(latest_json) and "by-nc/4.0" in guide and "by-nc/4.0" in doc["path"]["prices_licence"]
assert "% of month-ends since 2018 had lower volatility" in guide and "required compound return" not in guide
