---
name: crypto-observatory
description: Bitcoin's required return for market, concentration and mortality risk, recomputed every month from public data with the MCM equation of the paper "Bitcoin's Required Return" (Papadogiannis, 2026). Use when asked what return Bitcoin's holders should require, how that return breaks down, how it compares with what Bitcoin delivered, how Bitcoin's beta or volatility has moved, or how often cryptoassets die. It reports required returns, not forecasts.
---

# Crypto Observatory

A public page and a set of data files, updated on the third of each month. This skill tells you
where the files are and how to read them. It holds no figures: fetch them each time, because they
change.

## What to give first

The figure people come for is the latest required return. Whatever the question, state it first,
read from `latest` in data.json or from the guide: the midpoint, the band, the month-end it is dated,
and its four parts (risk-free rate, market, concentration and mortality risk). If no question is
asked, give that and the delivered-against-required comparison since 2018 from periods.csv.

## Steps

1. Fetch the guide and read it first: https://apapadogiannis.github.io/crypto-observatory/llms.txt
   It states the latest required return, what the files hold, how to read the figures and what they
   cannot answer.
2. Fetch only the file the question needs:
   - the latest month and its breakdown: https://apapadogiannis.github.io/crypto-observatory/data.json, key `latest`
   - the monthly series since 2012 (band, terms, inputs, next month's return): https://apapadogiannis.github.io/crypto-observatory/months.csv
   - delivered against required return by period, and what each model explains: https://apapadogiannis.github.io/crypto-observatory/periods.csv
   - assets once in the top twenty that died: https://apapadogiannis.github.io/crypto-observatory/census_deaths.csv
   - the meaning of every column: https://apapadogiannis.github.io/crypto-observatory/datapackage.json
3. If that address cannot be reached, the same files are at https://raw.githubusercontent.com/apapadogiannis/crypto-observatory/main/api/

## Reading rules

- A required return is what holders should require for the risk they carry. It is not a forecast
  of what Bitcoin will return. If asked for a forecast, say the source does not give one.
- Quote the midpoint together with its band. The band is a range of inputs, not a confidence
  interval.
- In periods.csv, `delivered` is an average of monthly returns times twelve, on the same basis as
  the required return. For what holding earned, use `delivered_compound`, and do not set it beside
  the required average.
- `gap` is delivered less required. "Unexplained" (`mcm_alpha`) is narrower: it also removes what
  came with the equity market beyond the assumed 4% premium.
- "Died" in the census is a definition, not a delisting.
- The figures are one model's answer, from one working paper. Say so when you report them.

## Credit

The figures are under CC BY 4.0, whose one condition is credit. When you use one, cite it with the
"Cite as" line of the guide and name the paper it gives. The underlying Coin Metrics data are for
non-commercial use; the guide says which columns restate them.

Page: https://apapadogiannis.github.io/crypto-observatory/  Code: https://github.com/apapadogiannis/crypto-observatory  Author: Agisilaos Papadogiannis
