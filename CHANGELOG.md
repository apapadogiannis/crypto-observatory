# Changes

## 1.7.0 (27 November 2026)

New on the site

- Five sections: Compare, Bitcoin, Altcoins, Method, Data. Earlier addresses still open.
- Bitcoin, "Volatility and drawdown": what volatility costs a position held alone, what each holder of the
  equation is paid for it, the band at other volatilities, and what followed similar drawdowns and
  volatility in the record.
- Bitcoin, "Trend and path": a least-squares trend line beside the path the required return implies from
  a price level the reader chooses.
- Altcoins: each asset's history, what moves it, and the monthly comparison with delivered returns that
  Bitcoin has, with its limits stated.
- A mark, a tab icon and a share card; a row under the header that lists the cards of the page in view.
- Bitcoin, Tests: "What tells the equation from a fixed premium", the unexplained return of each model
  and of one constant in 2012-17, since 2018 and over the whole record. The Overview tile gives
  delivered minus required with its standard error.
- "What changed since last month" on Compare and on Bitcoin: the midpoint before and after, and the
  terms and inputs that moved it.
- A glossary ("Words used on this site", address `#glossary`); the three reading rules under the tiles
  of Compare; each asset's tile opens its detail.
- Charts carry a name for screen readers, text meets the contrast standard in light mode, and there is
  a link to skip to the content.

New in the data files (columns are added at the end; none is removed or renamed)

- `months.csv`: `volatility_drag`, `required_compound_lower`, `required_compound_midpoint`,
  `required_compound_upper`, `pay_for_variance_lower`, `pay_for_variance_midpoint`,
  `pay_for_variance_upper`, `drawdown`.
- `assets.csv`, `assets_monthly.csv`: `required_compound_lower_pct_per_year`,
  `required_compound_upper_pct_per_year`.
- `data.json`: `volatility_sensitivity`, `state`, `path`, `assets.tests`, `comparison.gold_inputs`, `strength`,
  `change`.
- `latest.json`: `change_since_previous_month_end`, `next_update_expected`, `bitcoin_volatility_and_compounding`,
  `bitcoin_state_at_month_end`. In `bitcoin_delivered_against_required`, the two month fields are now
  `required_set_from_month_end` and `required_set_to_month_end`, and `returns_from_month` and
  `returns_to_month` give the months of the returns (one month later). The unexplained return of each
  model is added with its standard error.

Corrected

- The compound figure ("required return less half the variance") is what a position held alone and
  never rebalanced would compound at. It is not a requirement, and the site no longer reads it as one.
- The guide for AI agents stated the volatility percentile the wrong way round, gave one name to a
  distance in percent and a distance in standard deviations (the second is now
  `price_against_it_sd`), and answered in three ways whether the other four assets are tested.
- Licence statements now say everywhere that the Bitcoin prices in the data files are Coin Metrics
  community data under CC BY-NC 4.0, to which CC BY 4.0 does not extend.

Robustness

- The d3 library is served from the site itself. Without scripts, or if the library fails to load, the
  page shows a summary and the links to the data.
- A card that cannot be drawn no longer stops the cards after it.
- The monthly update keeps the stored file when a source that feeds one table only cannot be read, and
  stops if any asset's prices end before the month-end being priced.
- The three-year periods cover every month at the start of a new period.
- The build gives the same page from the same data, byte for byte.

## 1.6.0 (25 November 2026)

Five assets compared, the holder weight held at its survey value, a small file for AI assistants.
