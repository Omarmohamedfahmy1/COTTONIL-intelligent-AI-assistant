# Phase 7: evaluated demand and revenue forecasting

This is a historical HVIA dataset implementation, not a live company system or a
production-readiness claim. The forecasting service is read-only. Approved
financial KPIs, Phase 6 velocity/cover/replenishment calculations, and customer
churn/CLV models remain unchanged. Phase 8 is outside this implementation.

## Targets and data preparation

`services.forecasting.forecast_report` is the shared source for the forecasting
dashboard and bounded local assistant. Its target is determined by scope:

| Scope | Monthly target | Unit |
|---|---|---|
| Company / selected location / Retail or POS type, without category | Approved order-header `net_before_tax` revenue | EGP |
| Selected category / location-category / type-category | Approved sale-line quantity | Units |

Revenue is before refunds and excludes tax. These are forecasts of recorded
sales, not net profit or latent unconstrained demand. Returns, stockouts, lost
sales, future promotions, future stock and operating expenses are not modeled.
No SKU-level demand or SKU on-hand claim is supported. A POS/reseller location is
not relabeled a retail branch. See `KPI_DICTIONARY.md` and `DATA_ARCHITECTURE.md`.

Source order coverage is **2018-10-19 through 2026-10-18**. The first and last
partial calendar months are excluded. Current eligible history is **95 months,
2018-11 through 2026-09**; October 2026 is not training data. The optional explicit
`as_of` service parameter caps coverage and removes a partial cutoff month.
For example, `as_of='2026-09-15'` ends training in August 2026.

Targets reuse `metrics.company_sales_fully_observed_months`. Its zero-filled
aggregation is supplemented with a parameterized activity-presence query from
the same scoped header/line sources. A month with a matching record and zero
value remains recorded zero; a month with no matching records is **unknown**,
restored to a missing value. It is not fabricated as zero demand. Any missing
month makes the scope unavailable. Pre-opening gaps are not silently trimmed.
At least **60 consecutive fully observed months** are required. This conservative
policy intentionally excludes many thin/new location-category combinations.

Audits expose observed/missing/zero month counts, descriptive calendar means and
high outlier months (above Q3 + 3 IQR). Outliers are not removed. Descriptive
summaries can include all eligible history; they are never selection features.
The validator reconciles scoped totals with approved overview aggregations.

## Candidates and features

| Candidate | Implementation / assumption |
|---|---|
| Last-observation naive | Last complete month's value at every future lead |
| Seasonal naive | Same calendar month one year earlier |
| Moving average | Constant average of the last six observed months |
| Calendar Ridge | Existing trend/month design, refitted within each window; alpha 8 |
| Lagged Ridge | StandardScaler + Ridge alpha 10; scaler fitted only on training rows |
| Lagged histogram boosting | 60 iterations, 7 leaves, minimum 8 observations/leaf, L2 10, seed 42 |

Lag regressions use lags 1/2/3/6/12, trailing means 3/6/12, previous-month change,
calendar sine/cosine and elapsed time. Each supervised row uses only its strictly
earlier observations. Multi-step predictions recursively append **predictions**,
never the actual future targets. Each fold refits independently. Nonnegative
predictions are clipped at zero. No tuning against the final test was performed.
The existing `predictive.py` legacy API remains for compatibility; its older
forecast output is not the evaluated Phase 7 dashboard/assistant source.

## Chronology and selection

The final 12 eligible months are reserved before selection. Validation starts
at index `max(36, n-36)`, advances every three months, forecasts six months, and
finishes before the test boundary. For the current 95-month history there are
seven origins: September 2023 through March 2025, three months apart. The last
validation predictions end September 2025. Validation windows overlap at longer
horizons, so residuals/fold wins are dependent observations.

Each requested horizon H=1,3,6 uses only the first H leads for scoring/selection.
The best baseline minimizes validation WAPE (MAE if its denominator is undefined).
A regression can replace it only with at least five validation folds, at least
5% lower validation error, and strict wins in at least 60% of folds. Otherwise
the baseline is used. Model selection, baseline and empirical band widths are
frozen **before** evaluating the test targets. Tests mutate held-out values to
verify that the frozen selection/bands do not change.

The final test has two disjoint six-month blocks:

| Origin / training end | Available test window |
|---|---|
| 2025-09 | 2025-10 through 2026-03 |
| 2026-03 | 2026-04 through 2026-09 |

The second origin may train on the first block's now-past actuals. It never sees
its own future actuals. Each horizon scores only its first H leads in each block:
**2, 6 or 12 test observations** for H=1,3,6. Thus an H=1 score does not cover all
12 months. All candidate test scores are shown for transparency; they do not
change the selected model. The final forecast refits that locked model on all
currently eligible history, including the formerly held-out months now in the
past. Test error is an evaluation of that procedure, not final-fit accuracy.

Sparse history is determined from the pre-test prefix only: fewer than 24
positive months or fewer than half positive months. Only baselines are evaluated
and results are experimental. All-zero pre-test data is unavailable. Other
experimental gates are fewer than five validation origins, undefined test WAPE,
test WAPE over 35%, absolute percentage bias over 20%, or a selected regression
more than 10% worse than its locked baseline on test. These are explicit
engineering screening thresholds, not proof of business reliability.

## Metrics and empirical uncertainty

For actual a, prediction p and error e=p-a:

| Metric | Formula / interpretation |
|---|---|
| MAE | mean(abs(e)); EGP or units |
| RMSE | sqrt(mean(e²)); penalizes large errors |
| WAPE % | 100 × sum(abs(e)) / sum(abs(a)) |
| sMAPE % | mean(200 × abs(e)/(abs(a)+abs(p))); both-zero term is zero |
| Bias | mean(e); positive means overforecast |
| Bias % | 100 × sum(e)/sum(abs(a)) |

WAPE and bias percentage are unavailable when the denominator is <=1e-8; no
infinite or fabricated percentage is emitted. sMAPE can be unstable on thin
series and should be read with MAE and WAPE.

Per lead, at least five **validation-only** absolute residuals are required.
The empirical width is their 80th percentile. Lower=max(0,central-width),
upper=central+width. Missing widths remain unavailable. These are uncalibrated
empirical error bands, **not confidence intervals**. No distribution, independent
residual or future coverage guarantee is asserted. Reported held-out coverage is
descriptive on only two test origins per lead. Current company H=3 coverage is
66.67% (6 points) and H=6 coverage is 50% (12 points), despite the 80th-percentile
construction. Reviewers should not interpret these bands as validated 80%
coverage. Bands across categories cannot be summed as a company interval.

## Services, UI and assistant

```python
from services.forecasting import forecast_report, category_outlook
revenue = forecast_report(horizon=3)
branch = forecast_report('BR001', horizon=3)
units = forecast_report(category='Socks', horizon=3)
outlook = category_outlook(categories=['Socks', 'Men boxers'], horizon=3)
```

The dictionary includes state/reason, target/unit, origin, history, forecasts,
candidate comparison, backtest rows/split schedule, selected/baseline metrics,
band widths/coverage, descriptive audit and timing. Future consumers must check
`state`, target/unit, actual origin and missing bands. Horizon must be integer
1/3/6; booleans, floats and unsupported values are rejected. Filters use the
existing validated parameterized scope logic. Results are independent copies.

The existing Demand Forecasting page now has overview, model comparison,
backtests and uncertainty views, aggregate CSV downloads, and global
location/type/category controls plus horizon. English LTR and Arabic RTL share
the same service. The global **date filter controls only historical display**;
it does not silently redefine model history or origin. The chart uses the last
12 eligible source months for context, followed by H estimates. A separate
expandable history chart/table follows the selected display dates.

The local assistant allowlists `forecast7_values`, `forecast7_accuracy`,
`forecast7_growth`, `forecast7_categories`. Fixed bilingual patterns support
company/BRxxx sales, known category pairs/outlook and model accuracy. Ambiguous
categories, unsupported horizons, historical-origin requests, net profit and SKU
claims ask for clarification. Inventory questions retain Phase 6 routing.
The default horizon is three; explicit 'next month' means one month after the
**dataset origin**, not the computer date. Metadata gives scope, origin,
target/unit, forecast dates, model, state and uncertainty limitations. Category
'growth' compares next-H estimated units with last-H recorded units; it is not
observed or guaranteed growth. Connected provider mode is unchanged; no Phase 9
conversational expansion or live LLM call is included.

## Reproducibility, performance and boundaries

No new dependency is required. The in-process LRU cache has 32 entries, keyed by
scope, horizon, explicit cutoff, database path/mtime/size and model version.
Streamlit's existing data cache avoids per-rerun fitting. Returned copies prevent
callers mutating cached evidence. No trained models or private predictions are
serialized. A database content replacement preserving both mtime and size would
require cache clearing/restart; do not mutate the read-only source in place.

Run from the project root using the existing Windows environment/database:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/validate_phase7.py --report reports/phase_7_forecast_validation_final.json
.\.venv\Scripts\python.exe scripts/smoke_app.py --report reports/phase_7_smoke_final.json
.\.venv\Scripts\python.exe scripts/verify_phase7.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

See `reports/PHASE_7_REPORT.md` and the final JSON for actual scope/horizon
results and measured timings. Timing includes warm OS/SQLite caches and local
machine contention; it is not a production SLA. Category activity uses a simple
DISTINCT-month presence query rather than expensive customer/order KPI joins.

Phase 6 replenishment remains a historical velocity heuristic. A separately
authorized future integration would need validated matching category/location
units, origin/snapshot alignment, state/quality handling, uncertainty review and
reconciliation before using forecasts. No purchase orders, optimized allocation,
SKU forecasts, new dashboards or Phase 8 work are implemented here.
