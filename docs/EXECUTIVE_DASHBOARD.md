# Executive dashboard contract — Phase 3

`services/executive.py` composes the approved `services/metrics.py` functions;
`ui/pages/overview.py` only formats their results. The approved database, KPI
foundation, predictive models and assistant engine remain unchanged.

## Scorecards and source

Revenue before refunds, gross profit before returns/OPEX, margin, orders, AOV,
identified purchasers and active locations come from `metrics.overview` with
the same validated date/location/type/category scope. Growth comes from
`metrics.sales_growth`. Empty-order AOV and zero-sales margin are displayed as
unavailable in the executive layer (the compatibility API's zero remains intact).
This distinction also applies to the extra local executive assistant report.

Recorded units/value and high-risk category count come from
`metrics.inventory_snapshot` then `metrics.inventory_summary`. Missing snapshots
produce unavailable values, not zero inventory. This is sales-location stock,
excluding warehouses, aggregated by category at the latest recorded month no
later than the selected end month. It is not a day-level or exact SKU balance.
The selected start date does not constrain stock. Monthly timing is unverified,
including final partial source months. A category can be missing in a chosen
snapshot; there is no synthetic carry-forward across months.

Registered customers come from `registered_customers(end)` and are company-wide,
not a selected location/category count. The company network comes from the
location master: 52 retail branches and 28 reseller/POS locations. These counts
are separate from active scoped sales locations and identified purchasers.

Financial source, refund limitations and non-additive category order/customer
counts remain as documented in [KPI_DICTIONARY.md](KPI_DICTIONARY.md).

## Comparison policy

The previous window ends the day before the current start and contains exactly
the same number of inclusive calendar days. This is neither a year-on-year nor
a seasonal adjustment unless the selected dates happen to align that way.
Both windows must lie wholly between recorded dataset MIN/MAX sale dates using
the approved `sales_growth.comparable_coverage` policy. This verifies dataset
date bounds, not operational uptime or completeness at every location/day.
There is no new per-location opening-date completeness claim.

For seven core measures, comparison rows contain current, previous, absolute
change, percentage change and direction. Insufficient date coverage suppresses
previous displayed values and both changes. Percent change uses the approved
`growth_percent` function and is unavailable for a nonpositive prior baseline.
Absolute change can still exist with a zero baseline if coverage and both
measures are valid. Empty-period AOV or zero-sales margin is undefined.
Margin absolute change is in percentage points; its percent-change column is
relative to the previous percentage. Directions are positive/negative/unchanged/
unavailable, without implying a cause or desirability.

Partial selection months, initial October 2018 and final October 2026 must not
be treated as full calendar months. Monthly charts show selected days and list
incomplete months. Comparable equal-day windows may still include partial
calendar months; their descriptive nature is disclosed rather than silently
removing data. No period growth is invented outside source coverage.

## Aggregate design and location rankings

Monthly revenue/orders use `sales_monthly`. Monthly gross profit is a separate
read-only, parameterized aggregation of scoped `sales_order_items.margin_EGP`
using the approved predicate. Those results join only at month grain with
one-to-one validation. No item/header join can multiply sales. Category,
channel, product and location data come from approved KPI functions.

Executive location rankings honor the selected location/type/category/date.
They contain only locations with current-period orders. Zero-order locations
and disappeared locations are absent, which is explicitly disclosed; negative
growth alerts consequently do not cover ceased-selling locations. Revenue and
gross-profit rankings are separate. Growth ranking omits undefined baselines.
Gross-profit contribution uses the approved `ratio` against scoped GP and is
unavailable if its denominator is zero. Rankings do not measure efficiency or
explain operational causes. The existing full Branch Performance page retains
its documented all-location benchmark scope. Navigation to it preserves filters.

## Explainable signals

These fixed descriptive rules are not a learned model or LLM prose:

| Signal | Rule/evidence |
|---|---|
| Revenue decline | Comparable sales growth at or below −10% |
| Negative locations | Count of current active locations with defined growth below 0%; show minimum |
| High stock risk | Count of category mean source risk scores at or above 0.70 |
| Category change | Absolute sales-growth percentage at least 25%, prior sales at least 10,000 EGP, comparable coverage; show up to five sorted by signed growth ascending |
| Coverage/zero baseline | Explain missing comparison/growth |
| Partial months | Explicit boundary/calendar coverage warning |
| Missing stock | Explain unavailable recorded snapshot |
| No threshold | No rule triggered, not assurance of business health |

Category-change calculations include disappeared categories as zero current
sales when the prior window is covered. New categories with zero prior sales
do not receive an invented percentage growth. Stock attention lists source
category mean risk at least 0.40 **or** positive existing 30-day replenishment.
Averaging across locations can hide individual shortages. Replenishment remains
the approved recent-90-day run-rate heuristic, not ML, forecast or purchase order.

## Assistant boundary

The existing offline company-overview response retains its original report and
appends a verified `executive_summary` report from `services.executive.summary`,
the very same service used by dashboard scorecards. It includes growth, stock,
registered count and source snapshot month, without customer records. No new
free-form intent, model or engine allowlist is added. The optional connected
provider still has the original overview/inventory tools; the extra Phase 3
executive report is guaranteed in local mode only. No live LLM grounding claim
is made. Phase 9 conversational behavior is out of scope.

## Validation entry points

`tests/test_phase3.py` covers service math policies/thresholds, real-data scopes,
monthly/category/location/channel reconciliation, partial and empty windows,
assistant consistency and actual AppTest navigation. `scripts/validate_phase3.py`
records 151 executable assertions, aggregate residuals, shared assistant values
and measured service timings. It never writes customer-level results. All
historical tests remain intact. Browser evidence and exact executed results
belong in `reports/PHASE_3_REPORT.md`.
