"""Downloads the latest data and stores it in data/. This is the only code that uses the network.

    python3 update.py [DATA_DIR]

The sources, each appended to the file already stored:

    Coin Metrics Community API   daily Bitcoin series               data/coinmetrics/btc.csv
    US Treasury                  daily ten-year par yield           data/rates/treasury_10y_daily.csv
    Kenneth French data library  monthly US equity market return    data/market/us_market_monthly.csv
    Aswath Damodaran, NYU Stern  monthly implied equity premium     data/market/implied_equity_premium_monthly.csv

Coin Metrics and the implied equity premium are only added to: new rows go after the last stored
one, and the rows that overlap are compared with what is stored, so a revision upstream is
reported and not absorbed. The Treasury file is refreshed for the current year, and the French
series are stored as published each time, with any revision of a stored month printed in the log:
those two can therefore change a past figure in months.csv. What was published at the time is
kept in data/vintages.csv, which no build rewrites.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CM_API = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
CM_METRICS = ["AdrBalCnt", "CapMrktCurUSD", "FlowInExUSD", "FlowOutExUSD", "IssTotNtv", "PriceUSD", "SplyCur"]
TREASURY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
            "{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
FRENCH_ROOT = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FRENCH = FRENCH_ROOT + "F-F_Research_Data_Factors_CSV.zip"
FRENCH_DEVELOPED = FRENCH_ROOT + "Developed_3_Factors_CSV.zip"
FRENCH_SIZE = FRENCH_ROOT + "Portfolios_Formed_on_ME_CSV.zip"
DAMODARAN = "https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbymonth.xlsx"
OVERLAP_DAYS = 14
TOLERANCE = 1e-6


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-observatory (research, non-commercial)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def update_coinmetrics(data: Path, asset: str = "btc") -> dict:
    path = data / "coinmetrics" / f"{asset}.csv"
    stored = [r for r in _read_csv(path) if r["PriceUSD"]]          # drop a trailing day that has no price yet
    last = stored[-1]["time"]
    start = (date.fromisoformat(last) - timedelta(days=OVERLAP_DAYS)).isoformat()
    url = CM_API + "?" + urllib.parse.urlencode({"assets": asset, "metrics": ",".join(CM_METRICS), "frequency": "1d",
                                                 "start_time": start, "page_size": 10000, "paging_from": "start"})
    fetched = []
    while url:
        page = json.loads(_get(url))
        fetched += page["data"]
        url = page.get("next_page_url")
    fresh = {r["time"][:10]: r for r in fetched if r.get("PriceUSD")}
    if not fresh:
        raise SystemExit("Coin Metrics returned no rows")
    # the overlapping days must agree with what is stored
    by_day = {r["time"]: r for r in stored}
    worst = {}
    for day, r in fresh.items():
        if day in by_day:
            for m in CM_METRICS:
                a, b = by_day[day].get(m), r.get(m)
                if a and b:
                    rel = abs(float(a) - float(b)) / max(1.0, abs(float(a)))
                    if rel > TOLERANCE and rel > worst.get(m, (0,))[0]:
                        worst[m] = (rel, day, a, b)
    revised = [f"{m}: differs from the stored value by up to {100 * rel:.4f}% ({day}: stored {a}, now {b})"
               for m, (rel, day, a, b) in sorted(worst.items())]
    added = [{"time": day, **{m: r.get(m, "") for m in CM_METRICS}} for day, r in sorted(fresh.items()) if day > last]
    days = [date.fromisoformat(r["time"]) for r in added]
    gaps = [str(d) for prev, d in zip([date.fromisoformat(last)] + days, days) if (d - prev).days != 1]
    if gaps:
        raise SystemExit(f"Coin Metrics: days missing before {gaps[:5]}")
    if added:
        _write_csv(path, stored + added, ["time"] + CM_METRICS)
    return {"source": "Coin Metrics Community API", "last_observation": (added or stored)[-1]["time"], "rows_added": len(added),
            "overlap_days_checked": sum(1 for d in fresh if d in by_day), "revisions": revised}


def update_other_asset(data: Path, asset: str) -> dict:
    """Price and market value of one of the other priced assets, appended to data/coinmetrics/<asset>.csv.

    The market value is Coin Metrics' current-supply figure where the community API serves it (Ether)
    and its estimate otherwise. Stored days are kept; the overlapping days' prices are compared."""
    path = data / "coinmetrics" / f"{asset}.csv"
    stored = _read_csv(path)
    last = stored[-1]["time"]
    start = (date.fromisoformat(last) - timedelta(days=OVERLAP_DAYS)).isoformat()
    fetched = []
    for metrics in ("PriceUSD,CapMrktEstUSD,CapMrktCurUSD", "PriceUSD,CapMrktEstUSD"):      # the second where the first is not served
        url = CM_API + "?" + urllib.parse.urlencode({"assets": asset, "metrics": metrics, "frequency": "1d", "start_time": start,
                                                     "page_size": 10000, "paging_from": "start"})
        try:
            while url:
                page = json.loads(_get(url))
                fetched += page["data"]
                url = page.get("next_page_url")
            break
        except urllib.error.HTTPError as e:
            if e.code not in (400, 403):
                raise
            fetched = []
    fresh = {r["time"][:10]: r for r in fetched if r.get("PriceUSD")}
    if not fresh:
        raise SystemExit(f"Coin Metrics returned no rows for {asset}")
    by_day = {r["time"]: r for r in stored}
    worst = max(((abs(float(by_day[d]["PriceUSD"]) - float(r["PriceUSD"])) / abs(float(by_day[d]["PriceUSD"])), d) for d, r in fresh.items() if d in by_day),
                default=(0, ""))
    added = [{"time": d, "PriceUSD": r["PriceUSD"], "MarketCapUSD": r.get("CapMrktCurUSD") or r.get("CapMrktEstUSD") or ""}
             for d, r in sorted(fresh.items()) if d > last]
    if added:
        _write_csv(path, stored + added, ["time", "PriceUSD", "MarketCapUSD"])
    return {"source": "Coin Metrics Community API", "last_observation": (added or stored)[-1]["time"], "rows_added": len(added),
            "revisions": [f"PriceUSD: differs from the stored value by up to {100 * worst[0]:.4f}% ({worst[1]})"] if worst[0] > TOLERANCE else []}


def update_treasury(data: Path) -> dict:
    path = data / "rates" / "treasury_10y_daily.csv"
    stored = {r["date"]: r["yield_10y"] for r in _read_csv(path)} if path.exists() else {}
    first_year = int(max(stored)[:4]) if stored else 2011
    before = len(stored)
    for y in range(first_year, date.today().year + 1):
        for r in csv.DictReader(io.StringIO(_get(TREASURY.format(y=y)).decode())):
            if r.get("10 Yr"):
                stored[datetime.strptime(r["Date"], "%m/%d/%Y").date().isoformat()] = r["10 Yr"]
    if not stored:
        raise SystemExit("Treasury returned no rows")
    _write_csv(path, [{"date": d, "yield_10y": stored[d]} for d in sorted(stored)], ["date", "yield_10y"])
    return {"source": "US Treasury, daily par yield curve rates", "last_observation": max(stored), "rows_added": len(stored) - before}


def _french_table(url: str, header: str) -> tuple[list[str], list[list[str]], str]:
    """The first monthly table of a French data library file: column names, rows, and the file's first line."""
    with zipfile.ZipFile(io.BytesIO(_get(url))) as z:
        lines = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    head = next(i for i, l in enumerate(lines) if l.replace(" ", "").startswith(header))
    cols = [c.strip() for c in lines[head].split(",")]
    rows = []
    for l in lines[head + 1:]:
        p = [x.strip() for x in l.split(",")]
        if len(p) < 2 or len(p[0]) != 6 or not p[0].isdigit():
            break                                                   # the monthly table ends at the first other line
        if p[0] >= "201001":
            rows.append(p)
    if not rows:
        raise SystemExit(f"French data library: no monthly rows found in {url}")
    return cols, rows, lines[0].strip()


def _store_french(path: Path, rows: list[dict], fields: list[str], key: str, source: str, note: str) -> dict:
    stored = _read_csv(path) if path.exists() else []
    old = {r["month"]: r for r in stored}
    revised = [f"{r['month']}: stored {old[r['month']][key]}, now {r[key]}" for r in rows
               if r["month"] in old and abs(float(old[r["month"]][key]) - float(r[key])) > 0.005]
    _write_csv(path, rows, fields)
    return {"source": source, "last_observation": rows[-1]["month"], "rows_added": len(rows) - len(stored), "revisions": revised, "note": note}


def update_market(data: Path) -> dict:
    """The US equity market: excess return and bill rate, percent a month."""
    _, rows, note = _french_table(FRENCH, ",Mkt-RF")
    rows = [{"month": f"{p[0][:4]}-{p[0][4:]}", "mkt_rf": p[1], "rf": p[4]} for p in rows]
    return _store_french(data / "market" / "us_market_monthly.csv", rows, ["month", "mkt_rf", "rf"], "mkt_rf",
                         "Kenneth R. French data library, Fama/French 3 factors (Mkt-RF plus RF)", note)


def update_developed(data: Path) -> dict:
    """Developed-market equities, in US dollars: excess return and bill rate, percent a month."""
    _, rows, note = _french_table(FRENCH_DEVELOPED, ",Mkt-RF")
    rows = [{"month": f"{p[0][:4]}-{p[0][4:]}", "mkt_rf": p[1], "rf": p[4]} for p in rows]
    return _store_french(data / "market" / "developed_markets_monthly.csv", rows, ["month", "mkt_rf", "rf"], "mkt_rf",
                         "Kenneth R. French data library, Fama/French developed 3 factors (Mkt-RF plus RF)", note)


def update_small_caps(data: Path) -> dict:
    """US small caps: the value-weighted return of the smallest 30% of companies, percent a month."""
    cols, rows, note = _french_table(FRENCH_SIZE, ",<=0")
    i = cols.index("Lo 30")
    rows = [{"month": f"{p[0][:4]}-{p[0][4:]}", "ret": p[i]} for p in rows]
    return _store_french(data / "market" / "us_small_caps_monthly.csv", rows, ["month", "ret"], "ret",
                         "Kenneth R. French data library, portfolios formed on size, Lo 30, value-weighted", note)


def _xlsx_columns(blob: bytes, sheet: str, columns: list[str]) -> tuple[list[dict], date]:
    """The named columns of one sheet of an .xlsx file, one dict per row, and the day its date numbers count from.
    Read with the standard library only."""
    import xml.etree.ElementTree as ET
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
    z = zipfile.ZipFile(io.BytesIO(blob))
    book = ET.fromstring(z.read("xl/workbook.xml"))
    rid = next(e.get(f"{{{ns['r']}}}id") for e in book.iterfind("m:sheets/m:sheet", ns) if e.get("name") == sheet)
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = next(e.get("Target") for e in rels.iterfind("p:Relationship", ns) if e.get("Id") == rid)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        shared = ["".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iterfind("m:si", ns)]
    rows = []
    for row in ET.fromstring(z.read("xl/" + target.lstrip("/").removeprefix("xl/"))).iterfind("m:sheetData/m:row", ns):
        cells = {}
        for c in row.iterfind("m:c", ns):
            v = c.find("m:v", ns)
            if c.get("t") == "inlineStr":
                text = "".join(t.text or "" for t in c.iter(f"{{{ns['m']}}}t"))
            elif v is None or v.text is None:
                continue
            else:
                text = shared[int(v.text)] if c.get("t") == "s" else v.text
            cells["".join(ch for ch in c.get("r") if ch.isalpha())] = text
        rows.append(cells)
    head = {name.strip(): col for col, name in rows[0].items()}
    missing = [c for c in columns if c not in head]
    if missing:
        raise SystemExit(f"Damodaran: the sheet no longer has the column(s) {missing}")
    pr = book.find("m:workbookPr", ns)
    epoch = date(1904, 1, 1) if pr is not None and pr.get("date1904") in ("1", "true") else date(1899, 12, 30)
    return [{c: r.get(head[c]) for c in columns} for r in rows[1:]], epoch


def update_equity_premium(data: Path) -> dict:
    """The equity premium implied by the level of the S&P 500 at the start of each month (trailing twelve-month cash flows)."""
    path = data / "market" / "implied_equity_premium_monthly.csv"
    stored = _read_csv(path) if path.exists() else []
    fresh = {}
    rows, epoch = _xlsx_columns(_get(DAMODARAN), "Historical ERP", ["Start of month", "ERP (T12m)"])
    for r in rows:
        day, v = r["Start of month"], r["ERP (T12m)"]
        if day is None or v is None:
            continue
        try:
            first = epoch + timedelta(days=float(day))
        except ValueError:
            try:
                first = datetime.strptime(day.strip(), "%d-%b-%y").date()      # one date is typed as text ("1-Sep-24")
            except ValueError:
                continue                                          # a note under the table, not a row of it
        if first.day != 1:
            raise SystemExit(f"Damodaran: a row is dated {first}, not the first of a month")
        month = first.strftime("%Y-%m")
        v = v.strip()
        value = float(v.rstrip("%").replace(",", ".")) if v.endswith("%") else 100 * float(v)   # a few cells are typed as text
        if not 1 <= value <= 15:
            raise SystemExit(f"Damodaran: implausible premium {v!r} for {month}")
        fresh[month] = f"{value:.2f}"
    if not fresh:
        raise SystemExit("Damodaran: no rows read")
    by_month = {r["start_of_month"]: r["implied_premium"] for r in stored}
    revised = [f"implied premium for {m}: stored {by_month[m]}, now {v}" for m, v in sorted(fresh.items()) if m in by_month and by_month[m] != v]
    last = stored[-1]["start_of_month"] if stored else ""
    added = [{"start_of_month": m, "implied_premium": v} for m, v in sorted(fresh.items()) if m > last]
    months = [r["start_of_month"] for r in stored + added]
    gaps = [b for a, b in zip(months, months[1:]) if (int(b[:4]) - int(a[:4])) * 12 + int(b[5:]) - int(a[5:]) != 1]
    if gaps:
        raise SystemExit(f"Damodaran: months missing before {gaps[:5]}")
    if added:
        _write_csv(path, stored + added, ["start_of_month", "implied_premium"])
    return {"source": "Aswath Damodaran, implied equity risk premium by month (NYU Stern)", "last_observation": months[-1],
            "rows_added": len(added), "revisions": revised[:20]}


def main(argv):
    data = Path(argv[1]) if len(argv) > 1 else ROOT / "data"
    log = {"coinmetrics": update_coinmetrics(data), "treasury": update_treasury(data), "market": update_market(data),
           "developed_markets": update_developed(data), "us_small_caps": update_small_caps(data),
           "implied_equity_premium": update_equity_premium(data)}
    import tomllib
    others = list(tomllib.loads((ROOT / "config" / "model.toml").read_text(encoding="utf-8"))["other_assets"])
    log.update({f"coinmetrics_{a}": update_other_asset(data, a) for a in others})
    changed = any(v["rows_added"] for v in log.values())
    for k, v in log.items():
        print(f"{k:18s} to {v['last_observation']}, {v['rows_added']} rows added" + (f", {len(v['revisions'])} series differ from the stored overlap" if v.get("revisions") else ""))
        for r in v.get("revisions", []):
            print("   ", r)
    # A source that has stopped must fail the run, so that the page is never rebuilt on stale data unnoticed.
    today = date.today()
    limits = {**{f"coinmetrics_{a}": 7 for a in others}, "coinmetrics": 7, "treasury": 10, "market": 130, "developed_markets": 130, "us_small_caps": 130, "implied_equity_premium": 75}
    late = []
    for k, days in limits.items():
        obs = log[k]["last_observation"]
        last = date.fromisoformat(obs if len(obs) == 10 else obs + "-28")
        if (today - last).days > days:
            late.append(f"{k}: last observation {obs}, more than {days} days old")
    if late:
        raise SystemExit("Stale source. " + "; ".join(late))
    # Hand-entered anchors grow old silently. Say so in the run's log; the page says so too.
    try:
        import tomllib
        cfg = tomllib.loads((ROOT / "config" / "model.toml").read_text(encoding="utf-8"))
        months_old = lambda d: (today.year - int(d[:4])) * 12 + today.month - int(d[5:7])
        for name, table, limit in (("ownership survey", "ownership", "ownership_survey_max_age_months"),
                                   ("fund and treasury holdings", "fund_and_treasury_btc", "fund_holdings_max_age_months")):
            newest = max(cfg[table])
            if months_old(newest) > cfg["constants"][limit]:
                print(f"::warning::The newest {name} anchor in config/model.toml is dated {newest}, "
                      f"more than {cfg['constants'][limit]} months ago. Enter a newer one.")
    except Exception as e:  # the warning is a courtesy; the update does not depend on it
        print(f"anchor ages not checked ({e!r})")
    log_path = data / "sources.json"
    if changed or not log_path.exists():
        log["retrieved"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_path.write_text(json.dumps(log, indent=1) + "\n")
    return log
