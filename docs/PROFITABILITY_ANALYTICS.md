# Phase 5 — Profitability and margin intelligence

This module describes historical recorded results, not net profitability,
operating efficiency, causal explanations or optimized decisions. Phase 6 is
outside its scope. Read this alongside KPI_DICTIONARY.md and DATA_ARCHITECTURE.md.

## Architecture and scope

`services/profitability.py` composes the approved Phase 1 financial foundation
and Phase 4 aggregate services. It adds contribution denominators, outer-merged
gross-profit changes, deterministic ranks and descriptive screens.
`services/profitability_tools.py` exposes a fixed aggregate read-only allowlist.
The profitability page and local assistant use these same services.
`ui/data.py` caches batches for 1,200 seconds by validated scope and DB mtime.
Rank controls operate on cached aggregates, without rerunning financial queries.
No SQL, financial formulas or screening thresholds are defined in the page.

All queries use existing read-only parameterized access. Financial headers and
lines are independently aggregated before merges. Product catalog joins are
unique by product ID. There are no customer-level results or model changes.
No schema/index/database changes were made.

Every global date, location, type and category filter applies to the overview,
products, categories, locations, screening and trends. Location drilldown stays
within the eligible filtered roster, including a selected global location.
Only an explicitly named assistant pair overrides global location and type,
retaining common dates/category and reporting each location's actual type.
An assistant opened from a drilldown still has global scope: name the location
explicitly to request its results. Retail branches and reseller/POS remain distinct.

## Financial definitions

| Metric | Authoritative definition | Attribution / limitation |
|---|---|---|
| Sales | SUM(net_before_tax_EGP) from scoped orders; category uses matching SUM(net_line_EGP) per order | Sale date; excludes tax, before refunds |
| Gross profit | SUM(sales_order_items.margin_EGP) | Sale-line date; before returns and operating expenses |
| Gross margin | 100 × SUM(GP) / SUM(sales) | Weighted totals; zero sales gives unavailable, never average product margins |
| Units | SUM(quantity) on matching sale lines | No return netting |
| Orders | Count of matching distinct orders in approved scoped-order service | Includes anonymous and zero-value recorded orders; categories overlap |
| Company GP contribution | 100 × selected entity GP / company GP over identical dates | Denominator ignores ALL location/type/category filters |
| Scoped GP share | 100 × entity GP / filtered scope GP | Separate denominator and export column |
| Recorded refunds | SUM(refund_amount_EGP), approved returns service | Return date, original sale-line category and original order location |
| GP change | Current GP − immediately preceding equal-day GP | Unavailable unless both windows lie within global recorded coverage |
| GP growth | 100 × (current GP − prior GP) / prior GP | Requires covered periods and strictly positive prior GP |

Contributions retain signs and can exceed 100% when other groups lose money.
Any zero contribution denominator gives unavailable. Negative GP is preserved,
not clipped. Production ratios use the approved `metrics.ratio` function with
explicit undefined-denominator masking. Existing APIs and formulas are unchanged.
Product/category aggregates inherit the foundation's two-decimal rounding;
reconciliation tolerance is 0.02 EGP on this dataset. Audit reports retain actual
residuals rather than asserting exact binary floating-point equality.

Net profit, refund-adjusted revenue and return-adjusted GP remain unavailable.
Refund tax/discount definitions and returned cost alignment are unvalidated.
Do not subtract refunds, payroll, OPEX or purchase orders from GP. Stock remains
monthly location/category data; Phase 5 creates no SKU stock or demand estimates.

## Ranking and descriptive rules

Product rankings support revenue, GP, weighted margin and units, ascending or
descending. Both minimum revenue and minimum units must be met. Minimums are
finite nonnegative numbers, default zero, and affect rankings only. They never
alter scorecards, trends, screens or reconciliation. Ties sort by product ID.
Margin ranking excludes undefined margins. Other bottom ranks include eligible
catalog products without recorded sale lines as zero recorded activity; absence
of sales is not proof of discontinuation or unavailability.

Category GP and margin charts and the full sorted category table show both ends
of performance. Independently ranked revenue and GP leaders make the measures
explicit. Location ranks show all eligible master locations, retaining zero
recorded activity, source type, separate sales growth and GP changes.

Clearly defined default screening thresholds (`ScreeningRules`) are:

| Screen | Rule |
|---|---|
| High revenue / low margin | Revenue ≥ 100,000 EGP and margin < 30% |
| High volume / low margin | Units ≥ 500 and margin < 30% |
| Lower volume / high margin | Units < 100 and margin ≥ 45% |
| High company GP contributors | Positive GP and company contribution ≥ 10% |
| Declining category GP | Covered equal-day comparison with absolute GP change < 0 |

The first three screens require recorded lines and positive revenue. Contributor
screens require recorded lines and positive GP; company shares retain their signed
denominator semantics. Screens can overlap. Defaults are displayed on the page;
validated alternative rules can be supplied through the service/tool API, not
through free-form chat. The scatter uses units, weighted margin, revenue bubble
size and GP color, excluding nonpositive revenue/undefined margins. These screens
are descriptive flags, not evidence of causes, actions or expected improvements.

## Calendar and missing activity

Monthly GP and margin aggregate selected days; complete flags require the full
calendar month within both the selection and global source bounds. Partial months
are named in warnings, retained at their actual totals, and never annualized.
Equal-day comparisons can include partial calendar months, explicitly disclosed;
they do not imply calendar-month or seasonally matched comparisons.
The coverage policy is global MIN/MAX sale date, not a guarantee of location
opening days, uninterrupted operation, or complete recording per location.
Outer merges retain categories/locations that ceased recording sales. No prior
positive GP means unavailable percentage growth; covered absolute changes still
exist. A missing baseline is not invented as zero outside global coverage.
Zero-sales margins and zero-order AOV are unavailable in presentation. Anonymous
orders remain included in revenue/GP/orders, without exposing customer records.

## Local assistant contract

Allowlist: `profit5_products`, `profit5_categories`, `profit5_locations`,
`profit5_screening`, `profit5_leaders`, `profit5_pair`, `profit5_trends`.
Products/categories rank by GP by default; explicit margin requests rank by
weighted margin. Product leader comparisons independently return sales and GP
leaders. Every response carries actual dates, filters, source and financial
limitations. Pair requests need two distinct known IDs or exact unique master
names; missing/unknown/ambiguous pairs ask for clarification. Row limits 1–20
apply to ranked tools; monthly trends return the selected monthly series.

Examples supported in local mode:

- Which products generated the highest gross profit?
- Which branches have the highest gross margin?
- Which products sell a lot but have low margins?
- What are the most profitable categories?
- Compare gross profit BR001 and BR002.
- ايه أكتر المنتجات اللي بتكسب الشركة؟
- إيه الفرق بين أعلى المنتجات مبيعًا وأعلى المنتجات ربحية؟
- قارن ربحية فرعين خلال نفس الفترة. (requests the missing pair)

Dates support global scope, two explicit ISO dates, last month and last 3 months
anchored to the dataset, not today's date. Other recognized temporal phrases
request clarification. This is a bounded keyword grammar, not general language
understanding or Phase 9 conversation. Connected mode retains the existing
engine and does not expose these new tools; no live provider validation is claimed.
There is no arbitrary SQL/tool execution. Tables/exports contain aggregate
product/category/location/time data only. Source product/location names retain
their original language; UI vocabulary is translated English/Arabic with RTL.

## Validation and review

Run `python -m unittest discover -s tests -v` and
`python scripts/validate_phase5.py`, alongside the previous validators and
`scripts/smoke_app.py`. See reports/PHASE_5_REPORT.md for executed commands,
actual counts, timings, limitations and original browser screenshots.
No production-readiness claim or Phase 6 approval is implied.
