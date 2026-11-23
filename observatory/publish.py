"""Writes the files meant for programs and AI agents, from the same numbers as the page.

    llms.txt           what this is, what it adds, which file to use, what not to use it for
    months.csv         one row per month-end: the required-return band, its terms and inputs
    periods.csv        one row per period: delivered and required return, and what each model explains
    census_deaths.csv  every cryptoasset that was ever in the top twenty and died
    datapackage.json   licence, citation and the meaning of every column of the CSV files

The same files go to api/ in the repository and to the published site, next to data.json.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

SITE = "https://apapadogiannis.github.io/crypto-observatory/"
REPO = "https://github.com/apapadogiannis/crypto-observatory"
DOI = "10.5281/zenodo.24403325"            # all versions; always resolves to the latest release
PAPER = {"citation": "Papadogiannis, A. (2026). Bitcoin's Required Return: Pricing a New Asset Beside Equities and Gold. "
                     "Working paper.",
         "doi": "https://doi.org/10.2139/ssrn.7705239",
         "replication_package": "https://github.com/apapadogiannis/bitcoin-required-return",
         "relation": "The method. Every required return here is computed with the paper's MCM equation and constants."}
DESCRIBE_AS = ("Crypto Observatory, by Agisilaos Papadogiannis: Bitcoin's required return computed each month with the "
               "MCM equation of the paper \"Bitcoin's Required Return\".")
LICENCE = {"name": "CC-BY-4.0", "url": "https://creativecommons.org/licenses/by/4.0/",
           "condition": "Reuse is allowed with credit to the tool and to the paper.",
           "source_data": "The source data keep their own terms. Coin Metrics community data are CC BY-NC 4.0, for "
                          "non-commercial use; the equity market returns are copyright Kenneth R. French."}

MONTH_FIELDS = [
    ("month_end", "date", "The month-end at which the required return is set"),
    ("required_lower", "number", "Lower edge of the required-return band, percent a year: the average owner when fund and treasury investors are counted, with the low inputs"),
    ("required_midpoint", "number", "Midpoint of the band, percent a year: the average of the two edges, a convention and not an estimate"),
    ("required_upper", "number", "Upper edge of the band, percent a year: the larger of the two candidates below"),
    ("upper_if_surveyed_owner", "number", "Upper-edge candidate, percent a year: the average surveyed owner with the high inputs"),
    ("upper_if_early_holder", "number", "Upper-edge candidate, percent a year: the early holder"),
    ("upper_set_by", "string", "Which candidate sets the upper edge that month"),
    ("risk_free", "number", "Risk-free rate at the midpoint, percent a year: the ten-year Treasury yield"),
    ("market_term", "number", "Market risk at the midpoint, percent a year: beta times the equity risk premium"),
    ("concentration_term", "number", "Concentration risk at the midpoint, percent a year. At each edge it is risk aversion times variance times the holder's weight; at the midpoint it is what remains of the midpoint after the other three terms"),
    ("mortality_term", "number", "Mortality risk at the midpoint, percent a year: a constant, the middle of the census range (0.3 to 3.5), the same in every month"),
    ("volatility", "number", "Annualised volatility of Bitcoin used in the month, percent: the square root of twelve times an exponentially weighted average of squared monthly log returns, half-life nine months (computed from Coin Metrics prices)"),
    ("beta", "number", "Beta of Bitcoin to the US equity market: covariance over variance of monthly log returns in the trailing 48 months (at least 18), kept between 0 and 3. The equity series is published one to two months late, so the latest months carry the last beta that could be computed; before 18 months of data the first one is carried back"),
    ("correlation", "number", "Correlation of Bitcoin with the US equity market over the same window as beta, carried forward and back in the same way"),
    ("weight_with_funds", "number", "Share of wealth held in Bitcoin by the average owner when fund and treasury investors are counted, percent"),
    ("weight_surveyed", "number", "Share of wealth held in Bitcoin by the average surveyed owner, percent"),
    ("weight_early_holder", "number", "Share of wealth held in Bitcoin by the early holder, percent. When the early holder sets the upper edge, that edge is the risk-free rate plus this weight times variance, with no market or mortality term"),
    ("implied_equity_premium", "number", "Equity risk premium implied by stock prices that month (Damodaran), percent; used only for the sensitivity figure"),
    ("midpoint_with_implied_equity_premium", "number", "Midpoint of the band if the implied premium replaces the paper's fixed 4%, percent a year"),
    ("issuance_rate", "number", "The month's new issuance at a yearly rate, as a share of supply, percent; context, not an input"),
    ("fund_and_treasury_share", "number", "Share of supply held by funds and public companies, percent; context"),
    ("next_month_return", "number", "Bitcoin's simple return in the calendar month after month_end, percent a month (from Coin Metrics prices); empty until that month is complete and the equity market return for it is published"),
    ("next_month_capm_unexplained", "number", "That return, less the risk-free rate, less beta times the equity market's realised excess return in the same month; percent a month"),
    ("next_month_mcm_unexplained", "number", "The CAPM figure less the month's required premium for concentration and mortality risk at the midpoint; percent a month. It equals return less required midpoint less beta times (equity market excess return less the 4% premium)"),
    ("trailing_3y_excess", "number", "Average monthly return over the risk-free rate in the three years ending the following month, times twelve; percent a year, not compounded"),
    ("trailing_3y_capm_unexplained", "number", "The part of it the CAPM leaves unexplained, percent a year"),
    ("trailing_3y_mcm_unexplained", "number", "The part of it the MCM equation leaves unexplained, percent a year"),
]
PERIOD_FIELDS = [
    ("period", "string", "Label of the period (years joined by an en dash)"),
    ("from", "yearmonth", "First month-end at which a required return is set. The return compared with it is that of the following month"),
    ("to", "yearmonth", "Last such month-end; the last return in the period is that of the month after it"),
    ("summary", "boolean", "True for the two summary samples (whole sample, and since 2018), False for the three-year periods; the last period is shorter"),
    ("months", "integer", "Number of months"),
    ("delivered", "number", "Average monthly return times twelve, percent a year. An arithmetic average, not a compound or buy-and-hold return: see delivered_compound"),
    ("delivered_compound", "number", "Compound return over the same months, percent a year: what holding through the period earned. It differs from delivered in both directions: volatility lowers it, and compounding months within the year raises it when returns are large. Shown for reference; the tests compare averages, not this figure"),
    ("required_mid", "number", "Average required return at the midpoint, percent a year. Each month's annual rate is converted to a one-month return, exp(rate/12) - 1, before averaging and multiplying by twelve, so it is on the same basis as delivered. It is therefore not the plain average of required_midpoint in months.csv and can lie below the middle of the two edges"),
    ("required_lower", "number", "Average required return at the lower edge, percent a year, converted in the same way"),
    ("required_upper", "number", "Average required return at the upper edge, percent a year, converted in the same way"),
    ("gap", "number", "delivered less required_mid, points a year. This is not the unexplained return: see mcm_alpha"),
    ("gap_se", "number", "Standard error of the gap, points a year"),
    ("excess", "number", "Delivered return over the risk-free rate, percent a year"),
    ("market_part", "number", "Part of the excess return that came with the equity market: beta times the market's own excess return, points a year"),
    ("concentration_mortality_part", "number", "Premium required for concentration and mortality risk, points a year"),
    ("required_premium", "number", "Premium over the risk-free rate that holders required: beta times the 4% equity premium, plus concentration_mortality_part; points a year. excess = required_premium + equity_beyond_premium + mcm_alpha"),
    ("equity_beyond_premium", "number", "beta times (the equity market's realised excess return less the 4% premium), points a year"),
    ("mcm_alpha", "number", "Return the MCM equation leaves unexplained: excess less market_part less concentration_mortality_part, points a year"),
    ("mcm_alpha_se", "number", "Its standard error"),
    ("capm_alpha", "number", "Return the CAPM leaves unexplained: excess less market_part, points a year"),
    ("explained_capm", "number", "market_part as a share of excess, percent. A share of the average return, not an R squared. It uses the equity market's realised return"),
    ("explained_mcm", "number", "market_part plus concentration_mortality_part as a share of excess, percent. Not an R squared; above 100 when Bitcoin delivered less than the two parts together"),
    ("average_beta", "number", "Average beta over the period"),
    ("average_correlation", "number", "Average correlation with the equity market over the period"),
    ("regression_capm_alpha", "number", "Intercept of the regression under the CAPM, points a year"),
    ("regression_capm_se", "number", "Its standard error"),
    ("regression_mcm_alpha", "number", "Intercept of the regression under the MCM equation, points a year"),
    ("regression_mcm_se", "number", "Its standard error"),
]
DEATH_FIELDS = [
    ("asset", "string", "Ticker of the asset as in the Coin Metrics data, in lower case"),
    ("name", "string", "Name of the asset in the Coin Metrics catalogue on 21 November 2026. A name can be newer than the event: the asset that collapsed in May 2022 as Terra (luna) is listed as Terra Classic"),
    ("entered_top_twenty", "yearmonth", "Month it first entered the top twenty by trading volume"),
    ("died", "date", "Date of death as classified in the paper's census. Death is a definition, not a delisting notice: the data feed ended more than 180 days before the end of the data, or the price fell below 1% of its peak and did not recover, or trading volume fell below 1% of its peak and below 250,000 dollars a day and did not recover. An asset that is dead by this definition can still be listed and trade"),
    ("kind", "string", "Kind of death: abandoned or delisted, or sudden collapse"),
    ("rule", "string", "The rule that classified it: trading dried up (three-month volume below 1% of its peak year and under 250,000 dollars a day), price below 1% of peak (and trading did not dry up), data feed ended, or sudden collapse (entered by hand at its public date). An asset dead by the price rule alone lost 99% of its peak value and still trades"),
    ("volume_at_end_usd_a_day", "number", "Average daily trading volume in the source over the last three months of its data, in US dollars, rounded to thousands. It shows how much the asset still traded when the census was taken"),
    ("feed_last_day", "date", "Last day the asset has data in the source. The census date itself, or a day or two before, for an asset whose feed was still running"),
]
VINTAGE_FIELDS = [
    ("month_end", "date", "The month-end the required return is set at"),
    ("recorded_with_data_to", "date", "Last day of source data in the build that first had this month-end as its latest month"),
    ("required_lower", "number", "Lower edge of the band as first published, percent a year"),
    ("required_midpoint", "number", "Midpoint as first published, percent a year"),
    ("required_upper", "number", "Upper edge as first published, percent a year"),
    ("risk_free", "number", "Risk-free rate at the midpoint as first published, percent a year"),
    ("market_term", "number", "Market risk at the midpoint as first published, percent a year"),
    ("concentration_term", "number", "Concentration risk at the midpoint as first published, percent a year"),
    ("mortality_term", "number", "Mortality risk at the midpoint as first published, percent a year"),
]


def table(fields: list[tuple], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([f[0] for f in fields])
    w.writerows([["" if v is None else v for v in r] for r in rows])
    return buf.getvalue()


def credit(doc: dict) -> dict:
    """Licence and citation, carried inside data.json so that they travel with the numbers."""
    cite = (f"Papadogiannis, A. (2026). Crypto Observatory: required returns, risks and survival, data to "
            f"{doc['meta']['latest_month_end']}. Zenodo. https://doi.org/{DOI}")
    return {"licence": LICENCE, "cite_as": cite, "doi": f"https://doi.org/{DOI}", "site": SITE, "code": REPO,
            "describe_as": DESCRIBE_AS,
            "author": {"name": "Agisilaos Papadogiannis", "orcid": "https://orcid.org/0009-0002-7753-7052",
                       "url": "https://github.com/apapadogiannis"},
            "paper": PAPER}


FILES = [
    {"file": "llms.txt", "format": "text/plain", "what": "Guide for AI agents: what this is, what it adds, which file to use"},
    {"file": "data.json", "format": "application/json", "what": "Every number on the page, under plain names"},
    {"file": "months.csv", "format": "text/csv", "what": "One row per month-end: the required-return band, its terms and inputs"},
    {"file": "periods.csv", "format": "text/csv", "what": "One row per period: delivered and required return, and what each model explains"},
    {"file": "census_deaths.csv", "format": "text/csv", "what": "Every cryptoasset that was ever in the top twenty by trading volume and died, with the rule that classified it"},
    {"file": "vintages.csv", "format": "text/csv", "what": "The required return of each month-end as first published; rows are added and never rewritten"},
    {"file": "datapackage.json", "format": "application/json", "what": "Licence, citation and the meaning of every column of the CSV files"},
]

RAW = "https://raw.githubusercontent.com/apapadogiannis/crypto-observatory/main/api/"
# One skill covers every tool and paper of the account. It sends an agent to this guide.
SKILL_FOR_AGENTS = "https://raw.githubusercontent.com/apapadogiannis/apapadogiannis/main/skill/SKILL.md"


def publish(doc: dict, dirs: list[Path]) -> list[dict]:
    m, L, c = doc["meta"], doc["latest"], doc["census"]
    cr = doc["meta"]["credit"]

    months = []
    for x in doc["months"]:
        q, t, i, s = x["required"], x["terms_at_midpoint"], x["inputs"], x["supply"]
        n, tr = x["next_month"] or {}, x["trailing_3y"] or {}
        months.append([x["month_end"], q["lower"], q["midpoint"], q["upper"], q["upper_if_surveyed_owner"],
                       q["upper_if_early_holder"], q["upper_set_by"], t["risk_free"], t["market"], t["concentration"],
                       t["mortality"], i["volatility"], i["beta"], i["correlation"], i["weight_with_funds"],
                       i["weight_surveyed"], i["weight_early_holder"], i["implied_equity_premium"],
                       x["midpoint_with_implied_equity_premium"], s["issuance_rate"], s["fund_and_treasury_share"],
                       n.get("return"), n.get("capm_unexplained"), n.get("mcm_unexplained"),
                       tr.get("excess"), tr.get("capm_unexplained"), tr.get("mcm_unexplained")])
    periods = []
    for p in doc["periods"]:
        reg = p.get("regression") or {}
        periods.append([p[k] for k, _, _ in PERIOD_FIELDS[:24]]
                       + [(reg.get("capm") or {}).get("alpha"), (reg.get("capm") or {}).get("se"),
                          (reg.get("mcm") or {}).get("alpha"), (reg.get("mcm") or {}).get("se")])
    deaths = [[d["asset"], d["name"], d["entered_top_twenty"], d["died"], d["kind"], d["rule"], d["volume_at_end_usd_a_day"],
               d["feed_last_day"]] for d in c["ever_top_twenty_deaths_list"]]
    vintages = [[v[k] for k, _, _ in VINTAGE_FIELDS] for v in doc["vintages"]]
    mo, age = m["model"], m["anchors_age_months"]
    rule_n = c["deaths_by_rule"]

    w = L["worked"]
    whole = next((p for p in doc["periods"] if p["summary"]), None)
    doc["meta"]["credit"]["standing"] = ("One model's answer, from one working paper. The band is a range of inputs, not a "
                                         "confidence interval. The tests of fit have little power: see their standard errors.")
    package = {"name": "crypto-observatory", "title": "Crypto Observatory: required returns, risks and survival",
               "description": DESCRIBE_AS, "homepage": SITE, "repository": REPO, "doi": cr["doi"],
               "version": m["latest_month_end"],
               "licenses": [{"name": LICENCE["name"], "path": LICENCE["url"], "title": "Creative Commons Attribution 4.0"}],
               "licence_note": LICENCE["source_data"],
               "contributors": [{"title": "Agisilaos Papadogiannis", "role": "author",
                                 "path": "https://orcid.org/0009-0002-7753-7052"}],
               "citation": cr["cite_as"], "paper": PAPER, "sources": [{"title": s} for s in m["sources"]],
               "resources": [
                   {"name": "months", "path": "months.csv", "format": "csv", "mediatype": "text/csv",
                    "schema": {"fields": [{"name": n, "type": t, "description": d} for n, t, d in MONTH_FIELDS], "missingValues": [""]}},
                   {"name": "periods", "path": "periods.csv", "format": "csv", "mediatype": "text/csv",
                    "schema": {"fields": [{"name": n, "type": t, "description": d} for n, t, d in PERIOD_FIELDS], "missingValues": [""]}},
                   {"name": "vintages", "path": "vintages.csv", "format": "csv", "mediatype": "text/csv",
                    "schema": {"fields": [{"name": n, "type": t, "description": d} for n, t, d in VINTAGE_FIELDS], "missingValues": [""]}},
                   {"name": "census_deaths", "path": "census_deaths.csv", "format": "csv", "mediatype": "text/csv",
                    "schema": {"fields": [{"name": n, "type": t, "description": d} for n, t, d in DEATH_FIELDS], "missingValues": [""]}},
                   {"name": "data", "path": "data.json", "format": "json", "mediatype": "application/json",
                    "description": "Every number on the page; see llms.txt and the README"}]}

    guide = f"""# Crypto Observatory

> What return should Bitcoin's holders require for the market, concentration and mortality risk
> they carry, and what did Bitcoin deliver? Computed each month with the MCM equation of the paper
> "Bitcoin's Required Return", from public data.

Maintained by Agisilaos Papadogiannis (https://github.com/apapadogiannis). Updated on the third of each month.
Page: {SITE}  Code: {REPO}  Archive: {cr['doi']}
This file is written for AI agents and other programs. People should start at the page.

## Coverage

- Asset: Bitcoin. Other assets are not covered yet.
- {len(doc['months'])} month-ends from {doc['months'][0]['month_end']} to {m['latest_month_end']}; source data to {m['data_to']}.
- Latest required return, {L['month_end']}: {L['required']['midpoint']}% a year at the midpoint, band {L['required']['lower']}% to {L['required']['upper']}%.
  Of the midpoint: risk-free {w['risk_free']}, market {w['market']['midpoint']}, concentration {w['concentration']['midpoint']}, mortality {w['mortality']['midpoint']}.
- Tests of fit to {m['tests_to']} (the equity market series is published with a lag of one to two months).
- Census of cryptoasset deaths taken on {c['census_date']}: {c['assets']} assets, {c['deaths']} deaths. It is not updated monthly.
  Of {c['ever_top_twenty']} assets that were ever in the top twenty by trading volume, {c['ever_top_twenty_deaths']} died.

## What this adds over computing it yourself

A required return is not a statistic that can be read off a price series. It is the output of a
model with inputs that are not in any data feed. Use these files instead of recomputing unless you
want to change the model:

1. The method is a published equation, applied the same way every month:
   required return = risk-free rate + beta x equity premium + risk aversion x variance x holder's weight + mortality.
2. The holder's weight needs facts that are collected by hand: ownership surveys, wealth per owner,
   and Bitcoin held through funds and by public companies. They are in config/model.toml of the
   repository, each with its date and source (surveys to {m['anchors_to']['ownership_survey']}, holdings to {m['anchors_to']['fund_and_treasury_holdings']}).
3. Before every build the code is run on a frozen copy of the paper's inputs (data to 24 May 2026)
   and must reproduce the paper's stored results: its monthly band and its monthly tests. The page and these files
   are published only if it does.
4. Dates are kept honest. A required return is dated at the month-end it is set, and the return it
   is compared with is the following month's. A month in progress is left out.
5. Where the live sources differ from the paper's, the difference is measured and stated in
   data/README.md (for example, 0.1 point on average at the midpoint from the equity series).
6. The census classifies the death of every asset in the Coin Metrics universe by date and kind.
   That classification is the paper's own work and is where the mortality term comes from.
7. vintages.csv keeps what was published for each month-end when it was first computed. No later
   build rewrites it.

## The model's fixed settings

These are choices, not measurements. They are in config/model.toml and in data.json under
`meta.model`. Change one and the midpoint moves; the band is the paper's statement of that range.

- Equity premium {mo['equity_risk_premium']}% a year. The market term is beta times it, scaled by {mo['market_scale'][0]} at the
  lower edge and {mo['market_scale'][1]} at the upper edge.
- Risk aversion {mo['risk_aversion'][0]} at the lower edge and {mo['risk_aversion'][1]} at the upper edge.
- Volatility: exponentially weighted squared monthly log returns, half-life {mo['volatility_halflife_months']} months.
- Beta: trailing {mo['beta_window_months']} months (at least {mo['beta_min_months']}), kept between 0 and {mo['beta_cap']:g}. The equity series
  ends {mo['beta_carried_forward_from']}, so later months carry that month's beta forward.
- Holder's weight: {100 * mo['owner_weight_at_anchor']:.0f}% of an owner's financial assets at the {mo['anchor_date'][:4]} survey, carried to other
  dates by market value, ownership and an assumed path of wealth per owner; never above {100 * mo['weight_cap']:.0f}%.
  Fund and treasury investors are taken to hold {100 * mo['fund_investor_weight']:.1f}% of their wealth in Bitcoin.
- Mortality {mo['mortality'][0]}% to {mo['mortality'][1]}% a year, the same in every month. The upper figure is the paper's:
  {c['paper_counts']['ever_top_twenty_deaths']} deaths among {c['paper_counts']['ever_top_twenty']} assets, {c['paper_counts']['death_rate']}% a year.
- The concentration term at the midpoint is what remains of the midpoint after the other three
  terms, and is not allowed below zero.
- The past is computed with what is known today. The band for an earlier month uses surveys taken
  after it (the {mo['anchor_date'][:4]} survey is carried back to 2012), an assumed wealth path, and for the
  first months a beta carried back from the first one that can be computed. Holders at the time
  could not have computed it. "Delivered against required" before {mo['anchor_date'][:4]} is a comparison with a
  requirement built in hindsight.
- Age of the hand-entered inputs at the latest month-end: the last ownership survey is {age['ownership_survey']} months
  old and the last count of fund and treasury holdings {age['fund_and_treasury_holdings']} months old. Ownership has been
  entered as flat since 2023.

## Files

- data.json: every number on the page. Keys: meta, latest, months, periods, comparison, notes,
  equity_premium, census; the README of the repository describes each. Start here for the latest
  month (`latest`); for a series use the CSV files, which carry a description of every column.
- months.csv: the band, its four terms, the inputs and the next month's outcome, one row per month-end.
- periods.csv: three-year periods and the two summary samples: delivered, required, the gap, and
  what the CAPM and the MCM equation each explain and leave unexplained.
- census_deaths.csv: the {len(deaths)} assets that were ever in the top twenty by trading volume and died,
  with the rule that classified each and how much it still traded.
- vintages.csv: the required return of each month-end as first published. Rows are added, never
  rewritten. Use it to see what the tool said at the time.
- datapackage.json: the licence, the citation and the meaning of every column.
- A skill for an AI assistant: one skill covers this tool and the rest of the author's work, and
  sends the assistant to this guide. {SKILL_FOR_AGENTS}

All files are at {SITE} (for example {SITE}months.csv). In the repository the same
files are under api/.

## How to read the figures

- Figures are percent a year unless the name says otherwise. `next_month_*` figures are percent a month.
- The band has a lower edge, a midpoint and an upper edge because risk aversion and the holder's
  weight are not known exactly. Quote the midpoint with the band, not the midpoint alone.
- `required_*` is what holders should require, set at the month-end. It is not a forecast of what
  Bitcoin will return.
- "Delivered" figures in periods.csv are average monthly returns times twelve. They are arithmetic
  averages, on the same basis as the required return, and not compound or buy-and-hold returns.
  Do not report them as what an investor earned a year.
- A period runs from the first to the last month-end at which a required return is set. The
  returns are those of the following months, so "2018 to 2026" means returns from February 2018.
- `gap` is delivered less required at the midpoint. "Unexplained" is narrower: it also takes out
  what came with the equity market beyond the 4% premium, that is, delivered less required less
  beta x (equity market return less risk-free rate less 4%). The two answer different questions.
- `delivered_compound` in periods.csv is the compound return over the same months, for a reader
  who asks what holding earned. There is no required return on a compound basis in these files.
  Compare `delivered` with `required_mid` (both averages); do not set `delivered_compound` beside
  `required_mid`.
- The identities among the period columns hold to within about one point in the early periods,
  because the required return is converted month by month and the premium is not.
- "Died" in the census is a definition (feed ended, price or volume collapsed without recovery),
  not a delisting. Say "dead by the census definition", not that the asset no longer exists.
  `rule` in census_deaths.csv says which: {rule_n.get('trading dried up', 0)} by trading drying up, {rule_n.get('price below 1% of peak', 0)} by price alone, {rule_n.get('data feed ended', 0)} by the feed
  ending, {rule_n.get('sudden collapse', 0)} sudden collapses. The {rule_n.get('price below 1% of peak', 0)} dead by price alone still traded more than 250,000 dollars a day
  at the census date (`volume_at_end_usd_a_day`): they are counted because a holder at the peak
  lost 99%, not because the asset stopped. Without them the top-twenty death rate would be {c['death_rate_without_price_rule_deaths']}% a
  year, not {next(r['rate'] for r in c['death_rate_by_size'] if r['group'] == 'Ever in the top twenty')}%.
- The census here leaves out one entry the paper's census counts: the Lithuanian litas (ltl), a
  national currency replaced by the euro in 2015. The paper has {c['paper_counts']['ever_top_twenty_deaths']} top-twenty deaths, these
  files {c['ever_top_twenty_deaths']}. {c['mortality_to_be_adjusted']}
  The universe totals ({c['assets']} assets, {c['deaths']} deaths) and the tables by age and by
  size are the paper's and still include it.
- months.csv is recomputed at every build. For what was published at the time, use vintages.csv,
  which starts in November 2026.
- In data.json, `comparison.rows` are required returns of other assets from the same equation,
  not what those assets delivered.
- Standing of the figures: they are one model's answer, from one working paper. The tests of fit
  have little power, as their standard errors show: since 2018 neither this model nor the CAPM is
  rejected. Report a figure as "this model gives", not as a consensus.
  The paper calls the regression intercept alpha; it is reported separately.
- Period averages of the required return are taken after converting each month's annual rate to a
  monthly return, so they differ a little from a plain average of months.csv.
- `explained_*` are shares of the average excess return, not R squared.
- The band is a range of inputs, not a confidence interval.
- The paper's headline for 2026, about 18% a year (90% range 15 to 22%), is the median when the
  uncertain inputs are drawn across their ranges. The midpoint here averages the two edges of the
  band, which weights its corners equally, and stood near 20% at the paper's date. A midpoint here
  is comparable with the paper's monthly band, not with its 18%.
- `latest` is the last complete month-end, not today.
- The equity risk premium is the paper's fixed 4%. `midpoint_with_implied_equity_premium` shows the
  midpoint with a premium implied by stock prices instead.
- An empty cell means the figure does not exist yet or was not computed. It never means zero.

## Do not use this for

- A forecast, a price target or a view on whether to hold Bitcoin. The site reports required returns.
- Any asset other than Bitcoin.
- Cryptoasset deaths after {c['census_date']}.
- Commercial reuse of the underlying Coin Metrics series: see the licence below.
- What an investor earned, from `delivered`: use `delivered_compound`.
- A mismatch between files: every file of one build states the same "data to" date. If two files
  you fetched disagree on it, one is a cached copy; fetch again.

## Source, licence and credit

Sources: {'; '.join(m['sources'])}.

The figures in these files are released under CC BY 4.0 ({LICENCE['url']}).
The licence allows any reuse and has one condition: credit. If you use a figure from these files in
an answer, a report or a data set, name the tool and the paper.

{LICENCE['source_data']}
In months.csv the required returns, their terms and the unexplained figures are computed here. The
columns volatility, beta, correlation, issuance_rate and next_month_return restate Coin Metrics
prices and supply closely; anyone who needs them for commercial use should take them from a source
whose terms allow it.

Cite as: {cr['cite_as']}

And the paper whose method it uses: {PAPER['citation']} {PAPER['doi']}

To describe the source in a sentence: {DESCRIBE_AS}

The same licence and citation are inside data.json (under meta.credit) and in datapackage.json.
The code is under the MIT License.
"""
    out = {"months.csv": table(MONTH_FIELDS, months), "periods.csv": table(PERIOD_FIELDS, periods),
           "census_deaths.csv": table(DEATH_FIELDS, deaths), "vintages.csv": table(VINTAGE_FIELDS, vintages),
           "datapackage.json": json.dumps(package, indent=1, ensure_ascii=False) + "\n", "llms.txt": guide,
           }
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        for name, text in out.items():
            (d / name).write_text(text, encoding="utf-8")
    return FILES
