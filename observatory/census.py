"""The census of cryptoasset deaths: the paper's rules, run on daily volume and price series.

An asset is dead if its data feed ended more than 180 days before the census date, if its price fell
below 1% of its peak and did not recover, or if its trading dried up (three-month volume below 1% of
its peak year and under $250,000 a day at the end). Migrations to a successor token are not deaths,
and the known sudden collapses are entered at their public dates. Section 3 and Appendix C of the paper.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

YEAR = 365.25
FEED_DEAD_DAYS = 180
PRICE_FLOOR = 0.01             # of the all-time high
VOLUME_FLOOR = 0.01            # of the best twelve-month average
ABANDONED_BELOW = 2.5e5        # dollars a day, last three months

FIAT = set("""aed afn all amd ang aoa ars aud awg azn bam bbd bdt bgn bhd bif bmd bnd bob brl bsd btn bwp byn bzd cad cdf chf clp cny cop crc cup cve czk djf dkk dop dzd egp ern etb eur fjd fkp gbp gel ghs gip gmd gnf gtq gyd hkd hnl hrk htg huf idr ils inr iqd irr isk jmd jod jpy kes kgs khr kmf kpw krw kwd kyd kzt lak lbp lkr lrd lsl lyd mad mdl mga mkd mmk mnt mop mru mur mvr mwk mxn myr mzn nad ngn nio nok npr nzd omr pab pen pgk php pkr pln pyg qar ron rsd rub rwf sar sbd scr sdg sek sgd shp sll sos srd ssp stn svc syp szl thb tjs tmt tnd top try ttd twd tzs uah ugx usd uyu uzs ves vnd vuv wst xaf xcd xof xpf yer zar zmw zwl xau xag xpt xpd""".split())
# National currencies since retired. They are in no current list of currency codes, which is how the
# Lithuanian litas (ltl, replaced by the euro in January 2015) once entered the census as a death.
FIAT |= set("ltl lvl eek skk sit cyp mtl trl rol bgl zwd vef mro std byr azm ghc mzm sdd tmm zmk".split())
_STOCKS = "aal aapl abbv abnb abt acn adbe amd amzn avgo axp ba bac brk brkb cat coin crcl crm csco cvx dfdv dis gld glxy gme goog googl hd hon hood iau ibm intc jnj jpm ko lin lly ma mcd meta mrk mrvl msft mstr nflx nke nvda orcl pep pfe pg pltr qqq slv spy tqqq tsla unh uso v vst vti vz wmt xom azn nvo sap tm".split()
TOKENIZED_STOCKS = {s + "x" for s in _STOCKS} | {s + "on" for s in _STOCKS}
WRAPPED = set("wbtc weth wsteth steth cbbtc cbeth reth rseth wbeth frxeth sfrxeth tbtc renbtc hbtc btcb wbnb wsol bnsol jitosol msol ezeth weeth rsweth sweth oseth lseth meth ankreth btse cmeth stsol solvbtc wavax wmatic wpol".split())
MIGRATIONS = {"matic", "eos", "ftm", "gnt", "rndr", "btt", "nu", "strat", "maid", "ht", "rep", "agix", "xzc", "npxs", "bnx", "ocean",
              "one", "klay", "mith2", "erd", "dgd", "lend", "ant", "sai", "ven", "poly", "tomo"}
SUDDEN_COLLAPSES = {"luna": "2022-05-12", "ust": "2022-05-12", "ftt": "2022-11-10", "srm": "2022-11-10", "anc": "2022-05-12",
                    "mir": "2022-05-12", "cel": "2022-06-13", "tmtg": "2022-06-28"}


def take_census(volume: dict, price_a: dict, price_b: dict, as_of=None, price_rule: bool = True):
    """volume, price_a, price_b: asset -> daily Series. Returns (assets table, monthly volume matrix, census date)."""
    none = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    cut = (lambda s: s if as_of is None else s[s.index <= pd.Timestamp(as_of)])
    rows, monthly_px, V = [], {}, {}
    for a in sorted(set(volume) | set(price_a) | set(price_b)):
        if a in FIAT:
            continue
        pa, pb = cut(price_a.get(a, none)), cut(price_b.get(a, none))
        px = pa.combine_first(pb) if pa.notna().sum() >= pb.notna().sum() else pb.combine_first(pa)
        px = px[px > 0].sort_index()
        px.index = pd.DatetimeIndex(px.index)
        vol = cut(volume.get(a, none))
        vol = vol[(vol > 0) & (vol < 1e12)].sort_index()        # above $1 trillion a day is a feed error
        if len(px) == 0 and len(vol) < 30:
            continue
        ends = [s.index for s in (px, vol) if len(s)]
        rec = dict(asset=a, birth=min(i[0] for i in ends), last=max(i[-1] for i in ends), n_px=len(px), n_vol=len(vol),
                   price_dead=False, price_death_date=pd.NaT, stable=False)
        if len(px) >= 90:
            high, floor = px.max(), PRICE_FLOOR * px.max()
            if px.iloc[-1] < floor:
                above = np.where(px.values >= floor)[0]
                rec.update(price_dead=True, price_death_date=px.index[above[-1] + 1 if len(above) else 0])
            m = px.resample("ME").last().dropna()
            monthly_px[a] = m
            rec["stable"] = bool(0.95 <= px.median() <= 1.05 and high < 2.0) or bool(
                len(m) >= 6 and 0.9 <= m.median() <= 1.1 and m.quantile(0.05) > 0.8 and m.quantile(0.95) < 1.2)
            rec["stable_first_rule"] = bool(0.95 <= px.median() <= 1.05 and high < 2.0)
        if len(vol) >= 10:
            V[a] = vol.resample("ME").mean()
        rows.append(rec)
    p = pd.DataFrame(rows)
    p["stable_first_rule"] = p["stable_first_rule"].fillna(False).astype(bool)
    end = p["last"].max()
    p["feed_dead"] = (end - p["last"]).dt.days > FEED_DEAD_DAYS
    p["feed_death_date"] = p["last"].where(p["feed_dead"])
    p["excluded"] = p.asset.isin(TOKENIZED_STOCKS) | p.asset.isin(WRAPPED)
    span_ok = (p["last"] - p.birth).dt.days >= 30
    # the monthly volume matrix holds the assets that pass the first stablecoin rule, as in the paper
    keep = set(p.asset[~p.stable_first_rule & ~p.excluded & span_ok])
    V = pd.DataFrame({a: s for a, s in V.items() if a in keep})

    vol_date, final = {}, {}
    for a in V.columns:
        s = V[a].dropna()
        if len(s) == 0:
            continue
        final[a] = s.tail(3).mean()
        if len(s) < 6:
            continue
        peak = s.rolling(12, min_periods=3).mean().max()
        if not peak > 0:
            continue
        below = (s.rolling(3, min_periods=1).mean() < VOLUME_FLOOR * peak).values
        if below[-1]:
            alive = np.where(~below)[0]
            vol_date[a] = s.index[alive[-1] + 1 if len(alive) else 0]
    p["volume_death_date"] = pd.to_datetime(p.asset.map(vol_date))
    p["final_volume"] = p.asset.map(final)
    p["volume_dead"] = p.asset.isin(vol_date) & (p.final_volume.fillna(0) < ABANDONED_BELOW)

    p = p[~p.asset.str.endswith("_eth")].copy()
    if not price_rule:
        p["price_dead"], p["price_death_date"] = False, pd.NaT
    p["dead"] = p.feed_dead | p.volume_dead | p.price_dead
    p.loc[p.asset.isin(MIGRATIONS), "dead"] = False
    p["death_date"] = p[["feed_death_date", "price_death_date", "volume_death_date"]].min(axis=1)
    p["sudden_collapse"] = p.asset.isin(SUDDEN_COLLAPSES)
    for a, d in SUDDEN_COLLAPSES.items():
        if pd.Timestamp(d) <= end:
            p.loc[p.asset == a, ["dead", "death_date"]] = [True, pd.Timestamp(d)]
    p.loc[~p.dead, "death_date"] = pd.NaT
    core = p[~p.stable & ~p.excluded & ((p["last"] - p.birth).dt.days >= 30)].set_index("asset")
    return core, V, end


def ever_in_top(core: pd.DataFrame, V: pd.DataFrame, end, n: int = 20) -> pd.DataFrame:
    """Assets that ever ranked in the top n by monthly volume, followed from the month they entered."""
    ranks = V.rank(axis=1, ascending=False)
    rows = []
    for a in V.columns:
        hit = ranks.index[(ranks[a] <= n).fillna(False)]
        if not len(hit) or a not in core.index:
            continue
        r, t0 = core.loc[a], hit[0]
        stop = r.death_date if r.dead else end
        if (r.dead and pd.notna(stop) and stop <= t0) or (stop - t0).days <= 0:
            continue
        rows.append(dict(asset=a, first_top=t0, exp_yr=(stop - t0).days / YEAR, death=int(r.dead),
                         cat=int(r.dead and r.sudden_collapse), death_date=r.death_date))
    return pd.DataFrame(rows)
