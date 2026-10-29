# Authoritative KPI dictionary — Phase 1

Implementation: `services/metrics.py`; validated scope/date policy:
`services/filters.py`; read-only access: `db/connection.py`. `analytics.py` is a
compatibility API used by the eight existing screens, assistant and models.
No UI or assistant independently defines revenue, profit, AOV, margin or growth.
Values describe the supplied historical task dataset; provenance is unverified.

```python
from analytics import overview, sales_growth, registered_customers
overview('2026-01-01', '2026-09-30', location_type='Retail branch', category='Socks')
sales_growth('2026-01-01', '2026-09-30', branch='BR001')
registered_customers('2026-10-18')  # Company-wide master count; no activity filter.
```

## Common rules applying to each metric below

- Sales dates: inclusive ISO `start <= order_date <= end`. Filters accept a date
  object or strict `YYYY-MM-DD`; malformed dates and reversed ranges raise
  `ValueError`. Valid dates outside source coverage return empty/zero results.
- Optional intersection: a known `branch` ID, exact `location_type` (`Retail branch`
  or `Point of sale / reseller`), and exact internal product `category_en`.
  Unknown values or a branch/type conflict raise `ValueError`. A valid category
  with no sales returns zero/empty. Warehouse is not a sales location type.
- `branch` is the legacy API name for **any of the 80 sales locations**, including
  52 retail branches and 28 reseller/POS locations. `branches` in overview is a
  legacy output name for active sales locations, not just retail branches.
- Category filtering applies to matching line revenue/profit/units. An order with
  multiple categories is counted once **within each category**; its full header
  revenue must not be assigned to each matching line or category. Order counts
  overlap across categories but are additive across disjoint date/location scopes.
  Identified-customer and active-location counts are generally non-additive across
  scopes. Money and units are additive across disjoint line scopes.
- All currently recorded sales statuses are included (`Completed`, `Delivered`,
  `Partially returned`). There is no inferred exclusion for cancellation or refund.
  If new statuses appear, review this definition rather than assume their meaning.
- Currency is recorded EGP, without inflation/exchange adjustments. SQLite REAL
  retains the source decimal values with floating-point residuals. Aggregation
  uses unrounded values; grouped monetary displays round to 2 decimals. Tests use
  documented tolerances instead of requiring binary-exact equality.
- Empty additive aggregates/counts are zero. AOV and gross margin are displayed as
  zero for a zero denominator (a display convention, not evidence of profitability).
  Growth with no positive previous sales or insufficient comparable coverage is
  `None` (NaN in branch tables). Do not display undefined growth as 0%.

## Sales, profit and activity

Each row uses the common scope unless an explicit exception is stated.

| KPI / API output | Formula and source | Date attribution and aggregation grain | Assumptions and limitations |
|---|---|---|---|
| Total Sales / Revenue (`overview.sales`) | `SUM(sales_orders.net_before_tax_EGP)`; under a category filter, `SUM(sales_order_items.net_line_EGP)` for matching lines | Original order date. One header per order without category; line contributions with category, aggregated to order **before** header joins | Excludes tax, after discounts, **before refunds**. Never add payments, gross header sales, PO values or refunds as extra revenue. Both grains reconcile against the dataset |
| Recorded refunds (`refunds`) | `SUM(sales_returns.refund_amount_EGP)` | Return event date, original sales location from `sales_orders`; category from returned `sales_line_id`, one return at a time | Sales in the selected range and refunds in the range can belong to different original-sale cohorts. Tax/discount basis is unverified; a refund is not automatically an ex-tax revenue reversal |
| Refund-adjusted revenue (`refund_adjusted_sales`) | **Unavailable: `None`** | No authoritative formula enabled | 28,452/28,500 refunds differ from prorated original line net by > EGP 0.02. The data do not establish a compatible ex-tax adjustment basis. Do not call `sales - recorded refunds` validated adjusted revenue |
| Gross Profit (`gross_profit`) | `SUM(sales_order_items.margin_EGP)`; source check `net_line_EGP - quantity * unit_cost_EGP` | Sale/order date; individual lines, matching scope | Before returns, payroll, operating expenses and other adjustments. No inferred refund COGS reversal. **Not net profit** |
| Gross Margin % (`gross_margin_pct`) | `100 * gross_profit / sales`; never mean of product/branch percentages | Same date range, scope and revenue basis as the two totals | Zero-denominator display convention above. Overview uses full precision; product/category displayed ratios round to 2 decimals |
| Orders (`orders`) | Count of `sales_orders` in scope; for category, count of orders having a matching line | Order date; one per `sales_order_id` | Includes anonymous orders. Mixed-category counts overlap between categories; do not sum them into a company count |
| Average Order Value (`aov`) | `sales / orders` | Order date; scoped revenue per matching order | With category, this is average **category revenue contribution per matching order**, not the full basket value. Before refunds/ex-tax |
| Identified purchasing customers (`customers`) | `COUNT(DISTINCT customer_id)` among matching orders | Order date; distinct IDs over the entire selected scope | NULL IDs excluded. Not all registered customers; the same purchaser across locations/months is counted once in a combined scope |
| Anonymous orders (`anonymous_orders`) | Count of matching orders with NULL `customer_id` | Order date; order grain | Anonymous orders remain in revenue/order/unit KPIs but cannot support identified-customer behavior or model cohorts |
| Registered Customers (`registered_customers(as_of)`) | Count of master customers with normalized `joined_date_iso <= as_of` from `v_customers_normalized` | Registration date; cumulative company-wide master population | No branch/category/location filters: the master does not assign registration ownership to these dimensions. Includes customers who have never purchased. A separate function keeps this scope distinct from purchasing customers |
| Active Locations (`branches`) | `COUNT(DISTINCT branch_id)` in matching sales orders | Order date; distinct sales-location IDs | Includes retail and reseller/POS unless type-filtered. Not number of configured/open stores, warehouses, or proof a location was operational all period |
| Units (`units`) | `SUM(sales_order_items.quantity)` | Order date; matching sales lines | Units sold before returns, not inventory movements or on-hand quantity |
| Sales Growth % (`sales_growth.growth_pct`, branch `growth_pct`) | `100*(current sales - previous sales)/previous sales` | Immediately preceding **equal number of inclusive days**, same branch/type/category filters | Current and previous ranges must both lie within recorded sales coverage and previous sales must be >0. Otherwise unavailable. Equal day windows can cross partial calendar months; no claim of equal trading/calendar composition. Coverage bounds do not prove all source days are complete |
| Product profitability (`product_performance`) | Per-product sums of line `net_line_EGP`, `margin_EGP`, `quantity`; margin = ratio of summed profit to summed sales | Order date; product ID + internal name/category | Pre-return gross profitability only. Internal 139-product catalog is the only join target, not public 238-row catalog. Default top-100 output is truncated; use `limit=1000` to reconcile all products |
| Category profitability (`category_performance`) | Same sums grouped by internal `products_catalog.category_en`; weighted total-margin ratio | Order date; category | Add monetary totals across disjoint categories, not percentages or overlapping order/customer counts |
| Branch/location profitability (`branch_performance`) | Revenue from one row per matching order; profit separately summed from matching lines; join aggregated frames by branch with `one_to_one` validation | Order date; sales location | Explicit keyword `branch=` filters results. Legacy positional `selected` highlights a branch but intentionally leaves all locations for the existing benchmark screen. Returns active locations only. No OPEX allocation or net-profit inference |
| Roster productivity proxy (`orders_per_listed_employee`) | Orders / count of employee master rows for the sales location | Selected order dates divided by current supplied roster count | Not verified attendance, current staffing, working hours or labor productivity. Missing/zero roster denominator gives NaN |

## Monthly and inventory metrics

| Metric / API | Formula and source | Dates, grain and filters | Limitations |
|---|---|---|---|
| Monthly sales / orders / purchasers (`sales_monthly`) | Same scoped order contributions and distinct-customer definitions grouped by `substr(order_date,1,7)` | Selected dates; month with optional branch/type/category intersection | Boundary months may contain only the selected days; `is_complete_month` describes whether the **entire calendar month** lies inside both the selection and source min/max coverage |
| Complete-month seasonality (`seasonality`) | Mean of monthly sales grouped by calendar-month number; count of observed complete months | Uses only `sales_monthly.is_complete_month=True` | First source month (2018-10) and last (2026-10) excluded. No seasonality inference from partial months; no causal claim |
| Model input (`company_sales_fully_observed_months`) | Company/location revenue by complete month, or unit sum for a specified category | All full months inside source coverage, optionally branch/type/category; preserves existing model API | Complete first/last months are retained when coverage starts day 1/ends calendar month-end. Missing monthly buckets fill with zero under the existing task-data completeness assumption, not verified absence of business activity. Category target is **units**, not revenue |
| Recorded stock units (`inventory_snapshot.stock_units`) | `SUM(monthly_stock.closing_units)` | Latest matching month label <= selected end's YYYY-MM. Grain is sales-location × category × month; optional sales location/type/category | Existing service includes `stock_location_type='Branch'` (all 80 sales locations), excludes warehouses. Never aggregate multiple month snapshots as inventory. A month label does not establish an actual observation timestamp; mid-month/as-of precision is unknown |
| Recorded stock value (`stock_value`) | Sum of `closing_stock_value_EGP` for the same snapshot/scope | Same as stock units | Recorded valuation, not independently reconciled accounting value or SKU quantities |
| Recorded category risk (`risk_score`, `risk_label`) | Mean recorded location/category `stockout_risk_score`; rounded to 3 decimals, High >=0.7, Medium >=0.4, else Low | Same month and selected sales-location scope, grouped by category | Unvalidated source score. Mean across locations can hide a single location's problem; not an individual SKU stockout prediction |
| Snapshot summary (`inventory_summary`) | Sum stock units, stock value and estimated replenishment from one scoped snapshot; count categories labeled High by the shared risk definition | Exactly one category-aggregated snapshot, same filters as `inventory_snapshot` | Dashboard and assistant use the same helper; the risk count refers to aggregated categories, not individual locations or SKUs. Replenishment remains separately named as estimated |
| Recent category sales (`sold_90d`) | Sum of matching item quantities from end−89 days through end | 90 inclusive calendar days, same branch/type/category | Before returns; a partial source history still uses the 90-day denominator, so early-history run-rate estimates are weak. Not observed inventory consumption |
| Daily run-rate (`daily_run_rate`) | `sold_90d/90` | Category × selected sales-location scope | Historical rate, not forecasted demand |
| Approximate cover (`approx_cover_days`) | `stock_units / daily_run_rate` | Current selected snapshot with recent run-rate | NaN when run-rate is zero. Different source timing/aggregation grains mean this is a rough proxy, not a stock-ledger measure |
| Replenishment estimate (`suggested_30d_replenishment`) | `max(0, ceil(daily_run_rate*30 - stock_units))` | Category × selected sales-location scope | Future 30-day run-rate estimate. Not recorded demand, a new ML forecast, SKU recommendation, lead-time optimization or purchase order |

## Excluded/inapplicable financial measures

Net profit, tax-compatible refund-adjusted revenue, return-adjusted gross profit,
SKU on-hand stock, precise stock aging and reliable per-customer churn risk are
not supported by this foundation. Purchase order commitments are not matched COGS;
payroll/OPEX cannot be subtracted indiscriminately without allocation/timing rules.

## Reconciliation and consumer contract

Company/date/branch/location/category totals use the same functions in UI and
assistant. Assistant `company_overview` forwards validated filters to `overview`;
the Executive page uses `overview` plus `sales_growth`, not UI formulas. Existing
branch benchmarks intentionally compare all locations and disclose that exception.
Saved customer-model summaries remain company-wide and disclose their separate scope.

Unique dimension/header/line indexes plus source relationship tests protect joins.
Returns join headers by order ID and returned lines by line ID, never all lines of
a returned order. Header-to-line reconciliation checks gross/net/discount per
order at EGP 0.02 tolerance, and line-margin formula at EGP 0.06 tolerance.
All-source company/branch/category monetary reconciliation uses EGP 0.02 aggregate
tolerance. The Phase 0 validator's broader EGP 1/200 checks remain as inherited
checks, supplemented by these stricter Phase 1 tests.
