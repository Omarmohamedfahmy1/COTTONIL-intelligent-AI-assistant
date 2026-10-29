# Sales and location analytics — Phase 4 contract

This is an incremental extension of the approved Phase 1 KPI foundation,
Phase 2 presentation architecture and Phase 3 Executive Dashboard. It is a
local historical-data application, not a production system. Phase 5 is excluded.

## Architecture and single metric source

`services/sales_branch.py` orchestrates `services/metrics.py` and reuses
`services/executive.py` comparison/category-change helpers. The approved files
and formulas are unchanged. `services/sales_branch_tools.py` exposes a small
fixed local read-only tool allowlist. `ui/data.py` caches results by validated
scope, database mtime and local selector/grain. The two pages and shared
`ui/sales_branch_components.py` perform presentation only. Bilingual copy is in
`ui/sales_branch_i18n.py`, merged into the existing localization catalog.

The additional SQL uses fixed authored templates and bound values through the
read-only database connection. No user-authored SQL is accepted. Reusing the
foundation's internal `_orders`, `_period_covered` and `predicate` is deliberate:
it preserves its validated scope and date policy. These private helper interfaces
are a maintenance coupling; a later authorized API cleanup could make them public.

## Measures and aggregation grain

| Measure | Source and grain |
|---|---|
| Revenue | Approved order header net-before-tax once per scoped order; category scope uses summed matching line contributions before joining to headers |
| Orders | Count each matching order once per time bucket/location; category order counts overlap |
| Units | Sum scoped line quantity, not order count or money |
| GP | Sum scoped line margin, before returns and OPEX; never net profit |
| AOV | Approved ratio of scoped bucket sales / matching orders; unavailable with no orders |
| Identified purchasers | Distinct non-null IDs within a location/window; never sum as company-unique customers |
| Gross margin | Approved GP/revenue percentage; unavailable for zero sales in detail/pair presentation |
| Scoped category contribution | Category sales / current filtered sales; unavailable for zero denominator |
| Company contribution | Selected category/location sales / company sales for same dates, **all** locations/types/categories; unavailable for zero denominator |

Header/scoped-line order values are grouped to **day** before joining separate
day-level line GP/units. The join validates one-to-one dates, preventing revenue
multiplication. Daily values roll up into Monday-start weeks, calendar months
or years. AOV is recomputed from the approved ratio after aggregation, never an
average of daily AOV. Distinct customer counts are deliberately absent from this
rollup rather than incorrectly summing daily distinct counts.

Zero-recorded-order days are inserted only within the intersection of selected
dates and global source coverage. This is a recording fact, not proof a location
was open. No synthetic days outside recorded dataset coverage are supplied.
Week labels can precede the selection because they identify the Monday bucket.
Every bucket carries `is_complete_period`; edge weeks/months/years can be partial.
Out-of-coverage periods return empty trends and zero observed totals rather than
invented activity. Complete-period status does not guarantee operational uptime.

The operational product master is used, never the separate public catalog.
Product tables include products with no matching lines as zero recorded units/
sales, with an explicit recorded-line flag and unavailable zero-sales margin.
These are not assertions about discontinuation or inventory availability.
The UI ranks products independently by units or revenue; existing assistant
profit/margin ranking capability remains available through approved source KPIs.
Category-month views aggregate item-grain contributions using the unique
operational product key. Customer/order counts must not be summed across categories.

## Dates, period growth and seasonality

Equal-day previous-period comparisons reuse the approved executive comparison
function and sales-growth service; an additional units row follows the same
coverage policy. Both windows must be within global first/last recorded dates.
Incomplete coverage suppresses prior displayed values and both changes.
Nonpositive previous denominators suppress percent change. Empty-order AOV and
zero-sales margin are unavailable. Margin changes are percentage points; direction
does not imply quality or causality. This is not a seasonal adjustment.

Monthly YoY compares a **full selected calendar month** to the same complete
calendar month one year earlier. MoM compares that full month to the previous
complete calendar month. Earlier baselines can lie outside the selected range
but retain location/type/category. Both require global source coverage and
positive prior sales for a defined growth percentage. Partial October 2026 is
not given full-month YoY/MoM growth. Leap February uses its actual calendar
length rather than clipping a multi-month window to misleading equal-day dates.
Months absent from the current monthly KPI result are not invented as YoY rows.

Seasonality uses the **unchanged** `metrics.seasonality`: complete selected
calendar months only, with contributing month counts shown. Its averages omit
months absent from the underlying monthly order result; they are not an
opening-day-adjusted estimator. A small number of contributing months is not
evidence of a stable seasonal cause. Charts show historical observations, not
forecasts, and no new ML model is introduced.

## Location master, ranks and no-recorded-sales report

The roster left-joins current KPIs to **all eligible master locations**. Eligibility
uses global type; benchmark data use global dates/category but intentionally
ignore the selected global location. This preserves the established comparison
scope and is disclosed next to controls. Units come from a separate branch-level
line aggregation. Previous sales are independently collected for all eligible
locations, including ones with no current orders.

`recorded_orders` is based on order count, not revenue. A zero-value order still
counts as recorded. The separate no-recorded-orders master report is not a closure
report and does not infer staffing, operational availability or causes.
Positive covered prior sales and zero current orders can produce verified −100%
growth. Both-zero baselines have unavailable percentage growth.

Revenue, GP, AOV, units, customers and other volume/contribution ranks use locations
with current recorded orders. Growth ranking includes all locations with defined
growth, including zero-current-order locations with covered positive baselines.
Ascending/descending selectors provide lowest/highest views; undefined values
are excluded, ties use branch ID ascending. The primary table keeps location names
and selected metric visible in six or fewer columns. An expandable table retains
all metrics and exports; wide details intentionally scroll horizontally.

Revenue and GP leaders are reported with their actual values as different
measures. No operational efficiency/causal conclusion follows. Orders per listed
employee remains an **unverified staffing productivity proxy**, not labor efficiency:
the employee list is not date-adjusted, hours worked or an operational staffing
snapshot. Missing staff denominators are unavailable. Cross-location distinct
customer counts overlap and are not additive to company-unique purchasers.

## Drilldown and explicit local pair

Drilldown's local location selector is within the global type. It replaces only
the global location for that view; dates, type and category remain. It shows
core KPIs, sales/orders/units/GP/AOV trends, period comparisons, category/product
performance, channels and category-change evidence. Global filters remain intact.

The pair's two **distinct** local selectors deliberately override **both global
location and global type**, retain common dates/category, and permit Retail/POS
comparisons. Actual types and IDs are displayed. Each side uses the same approved
overview and previous-window definitions. A pair is not a difference-in-differences
experiment or causal explanation. Margin/AOV/growth can be unavailable. The
left/right type order follows user selection, including reversed Retail/POS order.
Monthly trends and category distributions are separate per location. Global
filter state is not overwritten. Assistant entry points retain global context;
explicit named-location/pair questions request local scopes.

## Explainable attention rules

Rules are numerical screening thresholds, not validated anomaly detection:

- Significant location decline: defined comparable sales growth ≤ −10%, including
  zero-current-order cases with a positive prior baseline.
- Declining categories: growth ≤ −10% and previous sales ≥ 10,000 EGP.
- Unusual category changes: absolute growth ≥ 25% and previous sales ≥ 10,000 EGP.
- No-recorded-order locations: matching current order count = 0.
- Revenue leader versus GP leader: show actual names and amounts, without causes.

Category-change evidence includes disappeared categories as zero current sales.
New categories with zero prior sales do not receive fabricated percentage growth.
Tables expose numerical source evidence and definitions, including prior sales.

## Local assistant scope

The new fixed allowlist consists of `sales4_trends`, `sales4_products`,
`location_ranking`, `declining_locations`, `location_detail`,
`two_location_comparison`. It calls the exact same services as the UI, accepts
only validated identifiers/grains/ranking options, and returns aggregate records.
Legacy engine/core/executive behavior is preserved; no arbitrary SQL, new planner
or Phase 9 conversational memory is introduced. Local reports state actual
dates, type/category and scope overrides. No individual customer records are used.

Supported narrow examples include monthly/daily/weekly/yearly trends; highest/
lowest location revenue; declining locations; product volume/revenue (and retained
profit/margin ranking); and comparisons naming two known IDs or unique exact
source names. Missing/ambiguous pairs request clarification. Ranking questions
retain the disclosed all-location benchmark scope. Single named-location detail
must be compatible with the global type; explicit pair comparison may cross types.

The bounded date resolver supports global dates, two explicit ISO dates, “last
month”/“الشهر الماضي”, and “last 3 months”/“آخر 3 شهور”. Relative dates anchor to
the dataset's last recorded date, not the host clock. Last month means the previous
calendar month; last three months end at the latest complete recorded month.
For this dataset they resolve to September 2026 and July–September 2026.
Unrecognized supported-tool temporal forms request clarification where detected;
this remains keyword routing, not general natural-language understanding. Actual
report dates must be checked. Broad/multipart/follow-up interpretation is not
claimed. Connected mode retains the original engine tools and does not expose
the extra local Phase 4 allowlist to the provider; no live provider call was tested.

## Reproduction and evidence

Run `python -m unittest discover -s tests -v`, the original audit/reconciliation
scripts, `scripts/validate_phase3.py` and `scripts/validate_phase4.py` using the
existing virtual environment and local original database. The Phase 4 validator
records aggregate assertions and per-service `perf_counter` timings. No source
tables/indexes, dataset files, models or private predictions are modified.
See `reports/PHASE_4_REPORT.md` for actual commands, outcomes, screenshots,
measurement conditions, limitations and the explicit stop before Phase 5.
