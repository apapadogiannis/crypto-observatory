"""Continuity with the paper. Run on the frozen snapshot in tests/snapshot (data to 24 May 2026), the
code must reproduce the stored results of "Bitcoin's Required Return": the monthly band, and the
monthly test with its CAPM and MCM figures. The live update is published only if this passes.

    python3 -I tests/test_continuity.py
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from observatory import inputs, mcm, tests_of_fit  # noqa: E402

SNAP = ROOT / "tests" / "snapshot"
REF = ROOT / "reference"
failures = []


def check(name, got, want, tol):
    ok = abs(got - want) <= tol
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {got:.4f} (paper {want})")
    if not ok:
        failures.append(name)


cfg = inputs.config()
mkt = inputs.market_return(SNAP)
band = mcm.required_return_band(inputs.bitcoin(SNAP), mkt, inputs.risk_free(SNAP), cfg)

# 1. the monthly band, every month and every column the paper stores (four decimals)
ref = pd.read_csv(REF / "required_band_monthly.csv", parse_dates=["month_end"]).set_index("month_end")
cols = {"age_years": "age_years", "risk_free": "risk_free", "volatility": "volatility", "beta_4y": "beta",
        "w_lower_edge": "w_with_funds", "w_upper_edge": "w_surveyed", "required_lower": "lower",
        "required_upper": "upper", "required_midpoint": "midpoint"}
worst = 0.0
for r, m in cols.items():
    diff = float((band[m].reindex(ref.index) - ref[r]).abs().max())
    worst = max(worst, diff)
    if not diff <= 5.1e-5:
        failures.append(f"band column {r}")
        print(f"FAIL  band column {r}: largest difference {diff:.2e}")
print(f"{'PASS' if worst <= 5.1e-5 else 'FAIL'}  band: {len(ref)} months x {len(cols)} columns, largest difference {worst:.1e} (stored to 4 decimals)")

# 2. the monthly test, against the figures printed in the paper's monthly_test.txt
t = tests_of_fit.monthly_test(band, mkt)
rows = {r["period"]: r for r in tests_of_fit.period_table(t)}
txt = (REF / "monthly_test.txt").read_text()
check("months in the test", len(t), int(re.search(r"months (\d+):", txt).group(1)), 0)
for label, key in (("2012–26, all", "2012–26"), ("2012–14", "2012–14"), ("2015–17", "2015–17"), ("2018–20", "2018–20"),
                   ("2021–23", "2021–23"), ("2024–26", "2024–26"), ("2018–26", "2018–26")):
    m = re.search(rf"^{label}\s+(\d+)\s+(-?\d+) \(\s*\d+\)\s+(\d+)-\s*(\d+)\s+(\d+) \|\s+[+-]\d+ \([+-][\d.]+\)\s+([+-]\d+) \(\s*(\d+);", txt, re.M)
    n, real, lo, hi, mid, gap, gse = map(float, m.groups())
    x = rows[key]
    check(f"{key} months", x["months"], n, 0)
    check(f"{key} delivered", x["delivered"], real, 0.5)
    check(f"{key} required midpoint", x["required_mid"], mid, 0.5)
    check(f"{key} gap", x["gap"], gap, 0.5)
    check(f"{key} gap standard error", x["gap_se"], gse, 0.5)
for a, b, key in (("2012", "2026", "2012–26"), ("2018", "2026", "2018–26")):
    m = re.search(rf"cumulative unexplained return {a}-{b}, points: CAPM ([+-]\d+), MCM ([+-]\d+); per year: CAPM ([+-]\d+), MCM ([+-]\d+)", txt)
    cc, cm, ac, am = map(float, m.groups())
    check(f"{key} cumulative unexplained, CAPM", rows[key]["cumulative_capm"], cc, 0.5)
    check(f"{key} cumulative unexplained, MCM", rows[key]["cumulative_mcm"], cm, 0.5)
    check(f"{key} CAPM alpha", rows[key]["capm_alpha"], ac, 0.5)
    check(f"{key} MCM alpha", rows[key]["mcm_alpha"], am, 0.5)
for label, key in (("whole sample", "2012–26"), ("since 2018", "2018–26")):
    m = re.search(rf"explained, {label}: CAPM (\d+)%, MCM (\d+)%", txt)
    check(f"{key} share explained, CAPM", rows[key]["explained_capm"], float(m.group(1)), 0.5)
    check(f"{key} share explained, MCM", rows[key]["explained_mcm"], float(m.group(2)), 0.5)
for label in ("2012–14", "2015–17", "2018–20", "2021–23", "2024–26"):
    m = re.search(rf"share explained {label}: CAPM (\d+)%, MCM (\d+)%", txt)
    check(f"{label} share explained, MCM", rows[label]["explained_mcm"], float(m.group(2)), 0.5)

print(f"\n{'All checks passed' if not failures else str(len(failures)) + ' checks FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
