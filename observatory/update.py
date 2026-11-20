"""Downloads the latest data and stores it in data/. This is the only code that uses the network.

    python3 update.py [DATA_DIR]

Three sources, each appended to the file already stored:

    Coin Metrics Community API   daily Bitcoin series               data/coinmetrics/btc.csv
    US Treasury                  daily ten-year par yield           data/rates/treasury_10y_daily.csv
    Kenneth French data library  monthly US equity market return    data/market/us_market_monthly.csv

Stored history is never rewritten: new days are added after the last stored one, and the days
that overlap are compared with what is stored, so a revision upstream is reported and not absorbed.
"""
from __future__ import annotations

import csv
import io
import json
import sys
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


def main(argv):
    data = Path(argv[1]) if len(argv) > 1 else ROOT / "data"
    log = {"coinmetrics": update_coinmetrics(data), "treasury": update_treasury(data), "market": update_market(data),
           "developed_markets": update_developed(data), "us_small_caps": update_small_caps(data)}
    changed = any(v["rows_added"] for v in log.values())
    for k, v in log.items():
        print(f"{k:18s} to {v['last_observation']}, {v['rows_added']} rows added" + (f", {len(v['revisions'])} series differ from the stored overlap" if v.get("revisions") else ""))
        for r in v.get("revisions", []):
            print("   ", r)
    # A source that has stopped must fail the run, so that the page is never rebuilt on stale data unnoticed.
    today = date.today()
    limits = {"coinmetrics": 7, "treasury": 10, "market": 130, "developed_markets": 130, "us_small_caps": 130}
    late = []
    for k, days in limits.items():
        obs = log[k]["last_observation"]
        last = date.fromisoformat(obs if len(obs) == 10 else obs + "-28")
        if (today - last).days > days:
            late.append(f"{k}: last observation {obs}, more than {days} days old")
    if late:
        raise SystemExit("Stale source. " + "; ".join(late))
    log_path = data / "sources.json"
    if changed or not log_path.exists():
        log["retrieved"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_path.write_text(json.dumps(log, indent=1) + "\n")
    return log
