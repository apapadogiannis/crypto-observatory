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
    api = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "api").iterdir()}
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
for name, rows in (("months", months), ("periods", periods), ("census_deaths", deaths)):
    fields = next(r for r in pkg["resources"] if r["name"] == name)["schema"]["fields"]
    assert [f["name"] for f in fields] == list(rows[0].keys()), name
    assert all(f["description"] for f in fields)

# Licence and citation are the same everywhere, and the guide states the latest figure.
credit = doc["meta"]["credit"]
assert credit["cite_as"] == pkg["citation"] and credit["cite_as"] in guide
assert credit["paper"]["doi"] in guide and credit["licence"]["source_data"] in guide
latest = doc["latest"]["required"]
assert f"{latest['midpoint']}% a year at the midpoint" in guide

# The skill names only files that exist, holds no figure that would go stale, and has a valid header.
skill = api["SKILL.md"]
assert skill.startswith("---\nname: crypto-observatory\ndescription: ") and skill.count("---\n") >= 2
for name in ("llms.txt", "data.json", "months.csv", "periods.csv", "census_deaths.csv", "datapackage.json"):
    assert name in skill and name in api, name
assert str(latest["midpoint"]) not in skill

# The page says the answer without JavaScript, and no placeholder is left in it.
assert "<noscript>" in page and "<!--STATIC-->" not in page and "/*LD*/" not in page and "__DATA__" not in page
assert f"is {latest['midpoint']}% a year" in page
print(f"agent files agree with data.json: {len(months)} months, {len(periods)} periods, {len(deaths)} deaths")
