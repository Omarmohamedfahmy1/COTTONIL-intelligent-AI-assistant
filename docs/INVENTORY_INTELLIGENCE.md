# Phase 6 — Recorded inventory and heuristic replenishment

This module supports historical category/location inventory decisions. It does
not establish SKU on-hand, exact inventory age, actual shortages, net profit,
confirmed dead stock, or a complete inventory movement ledger. No new ML model,
automatic purchase order or Phase 7 implementation is included.

## Actual audited source schema

The read-only audit is reproducible with `python scripts/audit_inventory.py`.
`reports/phase_6_inventory_audit.json` contains full column/type metadata,
counts, monthly coverage and relationship checks. The 17 audit checks passed.

| Table | Rows | Grain / relevant columns |
|---|---:|---|
| monthly_stock | 142,784 | One `year_month, stock_location_type, stock_location_id, product_category`; `closing_units, closing_stock_value_EGP, stockout_risk_score` |
| warehouses | 12 | `warehouse_id`; label, kind, governorate, capacity master fields |
| branches | 80 | `branch_id`; source name and retail/reseller-POS type |
| inventory_transfers | 36,500 | `transfer_id, transfer_date, source_warehouse_id, destination_branch_id, transfer_status, transport_cost_EGP` |
| inventory_transfer_items | 109,614 | `transfer_line_id, transfer_id, sku_id, quantity_units` |
| sku_variants | 695 | `sku_id → product_id`; size/color/price multiplier |
| products_catalog | 139 | Operational `product_id → category_en`; separate public reference catalog is not used |
| sales_orders | 540,000 | Order header/date/location; existing authoritative order/financial source |
| sales_order_items | 1,138,536 | Sale line, order/date/location, SKU/product, quantity and approved financial fields |

Stock has 97 month labels, October 2018 through October 2026. Each recorded month
contains 1,472 rows: 92 locations × 16 categories (80 sales locations and 12
warehouses). The audit found no duplicate stock grains, master IDs or transfer
line/header IDs; no orphan transfer headers/lines, source/destination locations
or SKU/product category mappings; no unknown stock categories or locations;
no out-of-range/null recorded risk, negative stock or invalid transfer quantities.
All recorded transfer headers have lines. These checks validate these specific
source relationships; they do not establish real-world recording completeness.

Transfers cover 2018-10-19 through 2026-10-18. Recorded statuses are:

| Status | Headers | Recorded header transport cost (EGP) |
|---|---:|---:|
| Completed | 33,640 | 26,674,690 |
| In transit | 2,145 | 1,697,950 |
| Partially received | 715 | 570,530 |

Line quantities are recorded transfer quantities, not independently verified
received quantities. Even Completed is only the recorded status. Partial receipts
cannot be inferred from full transfer quantities. No missing movements are filled.

## Snapshot and filtering policy

Stock balances are never summed across months. The new module uses a conservative
day-specific policy: select the latest eligible recorded month whose calendar
month-end is on or before the selected end date. Thus 2026-10-18 selects September
2026; 2026-09-30 also selects September. This avoids presenting an undated monthly
closing balance as known before its period ends. Actual capture timestamps remain
unknown; calendar eligibility is not a guarantee of recording completeness.

The global start date does not determine the selected stock balance. It filters
monthly history labels and transfer transaction dates. The chosen snapshot can
precede start. Monthly history retains absent months as absent, without inventing
zero balances, and does not sum monthly balances into a period stock total.
Adjacent-month changes require observations in both immediately adjacent months.
Missing observations remain unavailable, not zero; a recorded zero is retained.

Sales-location scope honors global branch, retail/POS type and category filters.
Local drilldown stays within the eligible filtered roster. Warehouses are a
separate explicitly labelled view: warehouse controls override global branch and
retail/POS type while retaining end date and category. No warehouse is treated as
a retail location. Transfers instead retain global destination branch/type,
category and both dates, with separate optional source-warehouse/status selectors.

Explicit two-location comparisons override global branch/type only, retaining
shared dates/category and reporting actual source types. Two distinct known IDs
or unique exact source names are required. Their latest eligible snapshots must
match; otherwise comparison is unavailable. Missing category observations remain
unavailable in the side-by-side table.

## Recorded risk and descriptive attention

Recorded risk scores are source fields, not calculated shortage probabilities.
Per-row bands: high ≥0.7; medium ≥0.4 and <0.7; low <0.4. Category risk displays
the unweighted recorded-row mean, maximum, and count of high-risk location/category
rows. The new category count means **categories with at least one high-risk
location**, deliberately different from the frozen Executive's category-mean rule.
No category average is assumed to describe every location.

Attention signals are descriptive evidence, not validated causes or instructions:

| Signal | Explicit rule |
|---|---|
| High recorded risk | Source score ≥0.7 on a specific location/category row |
| Low approximate cover | Defined cover <14 days by default |
| High-cover candidate | Positive stock and defined cover ≥120 days |
| High-stock/low-sales proxy | Stock ≥500 units and defined recorded sales <1 unit/day |
| Sales-location concentration | One location has ≥25% of filtered category units, with ≥2 recorded locations |
| Imbalance candidate | A category with ≥2 recorded locations has both cover <low threshold and cover ≥120 days |
| Replenishment attention | Positive location/category heuristic replenishment |
| Notable stock change | Absolute adjacent-month unit change ≥25%, with positive previous-month recorded units |
| Displayed warehouse concentration | Warehouse share ≥80% of the two displayed balance pools at the same snapshot |

Shares use only the displayed filtered stock pool. A selected branch can therefore
change the displayed warehouse-versus-sales-location comparison. This is explicitly
disclosed, not labelled company-wide when filtered. Warehouse/sales-location stock
shares require both observations, a common snapshot and positive combined units.
No warehouse-to-branch allocation, supply route, sufficiency or cause is inferred.

## Sales velocity, cover and replenishment

Default parameters: lookback 90 calendar days, horizon 30 days, low cover 14 days.
The lookback ends at the selected snapshot month's calendar end, not today's date
or global start. It includes both endpoints. All source line quantities for the
matching sales location and category are aggregated; anonymous orders remain in
sales quantities and customer records are never returned.

The complete lookback must lie within global MIN/MAX recorded sale dates. If not,
velocity, cover, replenishment and the low-cover count are unavailable. This is a
global date-coverage rule, not a guarantee of operating days or local completeness.
A fully covered window with no matching recorded sales yields zero recorded units
and zero daily rate, not proof of absent true demand.

```
daily recorded sales = matching sale-line quantity / lookback calendar days
approximate cover = recorded closing units / daily sales, if daily sales > 0
estimated replenishment = max(0, ceil(daily sales × horizon days − recorded stock))
```

Zero sales makes cover unavailable, not infinite or zero. A fully covered zero-sales
window yields zero replenishment; positive sales with recorded zero stock gives
zero cover and a positive estimate. Warehouse rates, cover and replenishment are
unavailable because branch sales cannot be attributed to a warehouse. There is no
warehouse demand forecast or stock aging claim.

The UI validates integer lookback 7–365 days, horizon 1–180 days, and low-cover
threshold 1–120 days. The service additionally validates high cover (1–730 days,
not less than low cover), positive high-stock threshold, and finite nonnegative
slow daily sales. Rules are displayed, and numeric assumptions accompany assistant
tables. Local assistant questions use disclosed defaults; direct tool APIs can
receive validated planning parameters. Local page controls do not silently alter
other modules or the assistant's default assumptions.

No lead time, safety stock, unrecorded returns, shrinkage, reservations, inbound
receipts, capacity allocation or supplier constraints are invented. Replenishment
is calculated per location/category; deficits are summed without netting another
location's surplus or assuming unrecorded redistribution.

### Compatibility with approved calculations

`services/metrics.py`, `analytics.py`, `predictive.py`, `assistant_engine.py`, the
database and approved Executive/Sales/Profitability services are unchanged. The
Executive's legacy monthly stock policy, averaged category-risk count and pooled
30-day category estimate remain unchanged for backward compatibility. The new
Inventory page/local tools use explicit Phase 6 semantics instead of relabelling
the old outputs as equivalent. Approved financial definitions are untouched.

At September 2026, both stock paths give 321,711 sales-location units and
63,173,576 EGP. The legacy mean-risk category count is zero; the new count is
14 categories with at least one high-risk location (29 high-risk combinations).
The legacy category-pooled estimate is zero; location/category deficits total
3,124 estimated units. These are different descriptive methods, not an unexplained
reconciliation error. The new coverage window is snapshot-anchored, whereas the
legacy helper anchors its fixed 90-day window to the selected end date.

## Transfer accounting and category mapping

Category mappings follow audited unique `line.sku_id → sku_variants.product_id →
products_catalog.category_en`. Stock itself remains category-level. Transfer
headers are filtered by date, source warehouse, destination branch/type, status
and category-EXISTS. Line quantities aggregate to transfer/category first;
matching category quantities then aggregate once to transfer before a one-to-one
header merge. Summaries/trends/status/source/destination quantities reconcile.

Transport costs are summed once per matching header, never repeated per line.
With a category filter, the cost is the **full header cost of transfers containing
that category**, not an allocated category cost; it is not additive across
categories. Category tables contain quantities only, so they cannot imply an
unsupported category transport-cost allocation. All statuses are retained unless
explicitly filtered. Stock and transfers are separate balance and event analyses.

## Architecture and assistant

- `services/inventory.py`: monthly selection, grouped balances, recorded risk,
  velocity/cover/replenishment, distribution, trends and transfer orchestration.
- `services/inventory_tools.py`: fixed read-only aggregate allowlist, validated
  parameters and bounded bilingual routing. No arbitrary SQL or new LLM planner.
- `ui/data.py`: scope/DB-mtime/parameter caches (1,200 seconds), including pair
  and transfer queries. `ui/pages/inventory.py` renders seven existing-module
  subviews with reusable localized cards, charts, tables and aggregate exports.
- `ui/inventory_i18n.py`: Arabic/English vocabulary. Source names retain their
  recorded language. Financial or heuristic formulas are not defined in the UI.
- `scripts/audit_inventory.py`, `scripts/validate_phase6.py`, `tests/test_phase6.py`:
  schema, reconciliation/performance, fixtures, parsing and real UI verification.

Allowlist: `inventory6_stock`, `inventory6_risk`, `inventory6_cover`,
`inventory6_replenishment`, `inventory6_warehouse`, `inventory6_transfers`,
`inventory6_pair`. Every report includes selected dates, snapshot where relevant,
filters, source, planning assumptions, row limit and full eligible row count.
Ranked/list reports return at most 20 rows; totals are separately disclosed.
Missing pair IDs prompt clarification. Relative “last month” and “last 3 months”
use dataset coverage; other supported date grammar uses shared filters/two ISO
dates. This is limited local routing, not Phase 9 conversation. Connected mode
retains its original tools and has not been validated against a live provider.

Examples: “Show stock levels in BR001”; “Which locations have low inventory
coverage?”; “Show warehouse stock by category”; “Which warehouse-to-branch
transfers were recorded last month?”; “قارن المخزون بين فرعين” (requests IDs);
“ايه الفئات اللي مخزونها ممكن ميكفيش؟”; “إيه الكميات المقترحة لإعادة التوريد؟”.

## Validation and limitations

See reports/PHASE_6_REPORT.md for executed commands, exact results, timings,
preservation evidence and original browser screenshots. New known-answer tests
cover zero/absent balances, zero/partial demand windows, leap-month selection,
retail/POS/warehouse scopes, risk means versus maxima, deficits, transfer statuses,
join multiplication, SKU category mappings, pair comparability and both languages.

Historical provenance and local recording completeness remain unverified.
No exact daily stock timestamp, continuous movement ledger, SKU balances, precise
aging, validated economic safety-stock policy, purchase-order integration or ML
demand forecast is available. Native browser/device/screen-reader matrices and
live LLM tests are separate from the in-app browser evidence. No production
readiness or independent approval is claimed.

**STOP: Phase 6 only. Await independent approval before Phase 7.**
