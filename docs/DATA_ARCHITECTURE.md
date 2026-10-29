# Phase 1 data architecture

The Streamlit MVP and eight screens remain in place. Dependency direction:

```text
app.py / assistant_engine.py / predictive.py
                    |
             analytics.py (compatibility exports)
                    |
       services/metrics.py + services/filters.py
                    |
          db/connection.py (read-only SQLite)
                    |
             data/cottonil.db (ignored)
```

`db/schema.py` contains additive schema preparation. Existing databases are
prepared explicitly with `python scripts/prepare_phase1_db.py`. Full dataset builds
apply the same schema before atomically publishing the generated database. The app
does not create schema, write the database or silently repair source records.

## Important relationships and grain

| Table | Grain/key | References |
|---|---|---|
| sales_orders | One `sales_order_id` | branch_id → branches; nullable customer_id → customers |
| sales_order_items | One `sales_line_id`, many per order | sales_order_id → orders; product_id → products_catalog; sku_id → sku_variants; source branch/date match header |
| products_catalog | One internal product_id | Operational catalog, 139 products |
| sku_variants | One sku_id | product_id → internal catalog |
| branches | One branch_id | Includes retail branches and reseller/POS |
| customers | One customer_id | Registered master, not purchasing cohort |
| sales_returns | One return_id | sales_line_id → returned line; sales_order_id and sku_id must match that line |
| sales_payments / delivery_shipments | Payment/shipment event | order ID; never joined to item facts to calculate additive revenue |
| monthly_stock | month × location ID × category | Location may be one of 80 sales locations or 12 warehouses; no SKU key |

The full source schema, other operational relationships and counts remain in
`reports/phase_0_data_audit.json`. Current Phase 1 evidence is in
`reports/phase_1_reconciliation.json`. No dimensional star-schema rewrite or
precomputed customer facts were added.

## Additive normalization and indexes

Raw tables and original archives remain unchanged. Four views expose normalized
ISO dates alongside raw fields:

- `v_customers_normalized.joined_date_iso`
- `v_branches_normalized.opening_date_iso`
- `v_employees_normalized.hire_date_iso`
- `v_import_shipments_normalized.shipment_date_iso`

These source fields use M/D/YYYY. Other day-grain fact dates are already ISO;
`year_month`/`pay_month` remain YYYY-MM labels. Validation compares every distinct
source date and its view result with Python parsing; invalid/NULL source dates
are reported rather than filled with invented values. Dates in query filters are
strict ISO or Python date objects. Source timestamps/time zones are not available.

Five unique indexes protect order IDs, line IDs, operational product IDs,
sales-location IDs and customer IDs against duplicate join targets. NULL keys and
foreign references still require explicit validation; foreign keys have not been
retroactively declared. Existing Phase 0 indexes remain.

Six additional indexes support `(branch_id,order_date)` on orders and lines,
`(product_id,order_date)` on lines, `(category_en,product_id)` on products,
`(return_date,sales_order_id)` on returns, and stock location/type/month/category.
`ANALYZE` on an existing prepared database records query planner statistics;
SQLite internal statistics are excluded from business-table audits.

## Join safeguards and scope

Unfiltered revenue comes directly from order headers. Category revenue first
aggregates matching lines by order and joins that contribution once to the header.
Order/customer/location counts then use that one-row-per-order relation. Product
and category profitability use lines joined to the unique operational dimension.
Location profit is aggregated independently and merged with revenue one-to-one.
Stock and payments never join to sales facts to compute revenue.

Registered-customer count is cumulative company-wide by registration date, using
the normalized view. It has no implied branch/category ownership. Current app
filters still expose date and sales location only; the additional location-type
and category filters are service/assistant capabilities for later UI work.

`db/connection.py` opens SQLite `mode=ro`, enables `query_only`, binds parameters
and closes each connection. SQL is developer-authored; users/LLMs cannot supply
SQL through assistant tools. Scope values are checked against master data and
sorting choices are allowlisted. This does not establish production authentication
or guarantee provider-generated prose; those remain separate later work.
