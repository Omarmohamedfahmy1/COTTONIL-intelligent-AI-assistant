# Cottonil Intelligent BI & AI Business Assistant — Phase 10

Phase 10 adds explicit answer-completeness states, evidence-preserving bounded
retry, app-owned bilingual management summaries and final local validation.
See the [operator guide](docs/DEPLOYMENT_AND_OPERATOR_GUIDE.md),
[demo script](docs/DEMO_SCRIPT.md), [final architecture](docs/FINAL_SYSTEM_ARCHITECTURE.md)
and [Phase 10 report](reports/PHASE_10_REPORT.md).
Groq remains the only active LLM provider. No additional paid evaluation was
authorized; final live Groq acceptance is NOT RUN. This remains a local demo.

HVIA Task 3 Streamlit MVP, restored from the supplied archive and tested against
its original dataset. The existing eight sections and shared analytics are retained.
This is a local demo, not a production system. See
[reports/PHASE_0_BASELINE.md](reports/PHASE_0_BASELINE.md) for the approved baseline.
The approved metric foundation is recorded in [reports/PHASE_1_REPORT.md](reports/PHASE_1_REPORT.md).
The approved UI shell is recorded in [reports/PHASE_2_REPORT.md](reports/PHASE_2_REPORT.md).
The approved Executive Dashboard is recorded in [reports/PHASE_3_REPORT.md](reports/PHASE_3_REPORT.md).
Current sales/location work and executed results are in [reports/PHASE_4_REPORT.md](reports/PHASE_4_REPORT.md).
See [sales and location analytics](docs/SALES_BRANCH_ANALYTICS.md) for ranking,
two-location scope, time coverage and the bounded local assistant tools.
The [executive dashboard contract](docs/EXECUTIVE_DASHBOARD.md) documents comparison,
stock-scope and alert policies. No financial formulas or predictive models were replaced.
The [KPI dictionary](docs/KPI_DICTIONARY.md) and
[data architecture](docs/DATA_ARCHITECTURE.md) define the shared business foundation.

## Windows setup (PowerShell)

Tested on Windows with CPython 3.12.0. From a clean checkout:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
$datasetZip = 'C:\path\to\COTTONIL_Data.zip'
.\.venv\Scripts\python.exe scripts/build_db.py --zip $datasetZip
.\.venv\Scripts\python.exe scripts/prepare_phase1_db.py
.\.venv\Scripts\python.exe scripts/validate_db.py --report reports/phase_4_data_audit.json
.\.venv\Scripts\python.exe scripts/validate_phase1.py --zip $datasetZip --report reports/phase_4_phase1_reconciliation.json
.\.venv\Scripts\python.exe scripts/validate_phase3.py --report reports/phase_4_executive_validation.json
.\.venv\Scripts\python.exe scripts/validate_phase4.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/smoke_app.py --report reports/phase_4_smoke.json
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Activation is optional; explicit interpreter paths avoid PowerShell activation
policy problems. `requirements.txt` retains the MVP's supported dependency ranges;
`requirements-lock.txt` pins the tested full dependency set for Python 3.12/Windows.
The optional OpenAI SDK is installed but no key is needed for offline use/tests.
Allow several minutes for package installation and database import. Keep roughly
2 GB free for indexed database, temporary rebuild, journal and dependencies.

If old pip fails TLS certificate validation, update it using an existing recent
host pip, which uses Windows certificate trust, without disabling TLS checks:

```powershell
python -m pip --python .venv install -r requirements-lock.txt
```

This fallback was executed successfully using host pip 26.2.1 after venv pip
23.2.1 failed certificate validation. It requires that `python` resolves to the
host Python with that recent pip. Corporate certificate issues may still need
local trust-store configuration.

The original ZIP used here was
`C:\Users\Acer\Downloads\Cottonil_project\COTTONIL\COTTONIL_Data.zip`.
It may remain anywhere outside the checkout; pass its actual location to `--zip`.
Database defaults to `data/cottonil.db`, relative to the project, matching
`analytics.py`. Existing DBs are protected; use `--force` for an intentional atomic
rebuild. Import reads the original ZIP directly and never extracts or modifies it.
For an existing Phase 0 database, run `scripts/prepare_phase1_db.py` before Phase 1
tests. It adds normalized date views and indexes without changing source rows.
New full dataset imports install the same schema automatically; the explicit
prepare step is safe to repeat and also runs SQLite `ANALYZE`.
Do not interrupt an active build. If a crash leaves a `.building` file, confirm
the old process exited before inspecting/removing that temporary file and retrying.

The batch alternative is `START_WINDOWS.bat "C:\path\to\COTTONIL_Data.zip"`.
It installs locked dependencies, builds a missing database, validates, then launches.
The launcher itself has been inspected; use the tested PowerShell commands above.

## Eight existing sections

1. Executive Overview: recorded revenue, gross profit, orders, identified customers, AOV.
2. Sales Analytics: monthly sales, channels, seasonality, product rankings, CSV exports.
3. Branch Performance: all-location rankings, growth, AOV and roster staffing proxy.
4. Inventory Intelligence: monthly category snapshots and approximate run-rate replenishment.
5. Demand Forecasting: seasonal naive versus Ridge, chronological holdout, six-month estimates.
6. Profitability Analysis: product/category gross profit and gross margins.
7. Customer Intelligence: activity, optional saved sales-value proxy and weak-churn disclosure.
8. AI Business Assistant: fixed offline intents and optional provider-backed tool orchestration.

The UI has Arabic RTL / English LTR presentation, localized charts/tables/exports,
session-persistent filters and a Navy/Teal design. Change language in the sidebar;
language and page also persist in URL parameters. Date/location/type/category
values persist during navigation and language changes; a browser restart resets
filters to their defaults. Source product/location names remain as recorded.
Built-in date-picker/accessibility chrome can follow browser locale rather than
the application switch. See the Phase 2 report for exact visual coverage/limitations.

Use **Ask the assistant** on any page to open the same assistant in a dialog.
Closing it preserves the underlying page and filters. Offline mode supports fixed
verified intents with localized report text; it is not free-form conversational AI.

## Architecture and data conventions

`app.py` is the existing Streamlit entry point. `analytics.py` preserves the MVP API
and re-exports authoritative metrics from `services/metrics.py`.
`services/filters.py` validates dates, locations, location types and categories;
`db/connection.py` owns read-only access. These functions serve UI and assistant.
Executive growth also comes from the shared service.
`predictive.py` holds the existing forecast/customer experiments.
`assistant_engine.py` restricts tool dispatch to eight analytical functions.
Category revenue counts only matching lines, with order counts calculated once per
matching order. The Phase 2 global controls use all four validated filters.
Branch benchmark charts deliberately include all matching locations; forecast
models use all complete historical months; customer research remains company-wide.
Each affected screen explains its scope exception.

`app.py` is a small shell. `ui/state.py` owns navigation/filter state;
`ui/i18n.py` owns translated copy/enums; `ui/theme.py` owns styling;
`ui/components.py` owns reusable cards/charts/tables/exports; `ui/data.py` is a
cached adapter over the unchanged services; `ui/pages/` holds the eight screens;
`ui/assistant.py` presents the existing engine on the assistant page or in a dialog.
No authoritative metric formula, database architecture or model was changed.
Restart Streamlit after upgrading source/localization modules so old imported
modules do not remain in a running development session.

The importer retains the MVP numeric column affinities (REAL money/ratios, INTEGER
counts/units, TEXT identifiers/dates), converts blank CSV fields to NULL, and adds
indexes. Dates in original tables remain untouched; the auditor parses ISO dates,
M/D/YYYY and monthly dates to report chronological ranges. All 23 business tables,
the dictionary and separate public catalog are loaded. The 238-row public catalog
is never joined as a replacement for the 139-row operational catalog.
`_source_metadata` records source ZIP SHA-256. Four additive views expose normalized
dates without rewriting raw tables. There are no declared foreign keys;
explicit anti-joins and unique/non-null key checks validate relationships.
`PRAGMA foreign_key_check` by itself cannot establish integrity here.

`validate_db.py` opens SQLite read-only and exits nonzero on failed checks.
Its JSON report contains schema, aggregate counts, dates and test results, no
customer records. Real-data tests explicitly skip when the default DB is absent.
Custom `--db` paths are supported by the import/audit CLIs; app and integration
tests use the default database.

## Optional private customer artifacts and AI mode

The supplied MVP includes `data/customer_predictions.csv` and
`data/customer_model_metrics.json`; they were restored locally for baseline tests
but are ignored and must remain private. A clean checkout runs without them and
shows a warning in the customer model section. Optional `python predictive.py`
regenerates them from the local database; it is not needed for startup and is not
run by the launcher. The baseline report distinguishes inherited metrics from
freshly executed checks. Never use the prior near-random churn scores for actions.
The current customer screen presents aggregate cohort size, research errors and
recency bands. Customer IDs, names and individual prediction records are not shown
or exported. Aggregate table exports also exclude the known private source fields.

`.env.example` is documentation: no dotenv loader is installed. For optional LLM
mode set `$env:OPENAI_API_KEY` and optionally `$env:COTTONIL_LLM_MODEL` before launch,
or use the app's password input. No real API key or remote LLM call was used in
Phase 2 verification; provider failures were tested using a mock.
The tool allowlist/read-only SQL constrain data access; they do not guarantee that
an LLM's prose never invents values. Provider response grounding needs later tests.

## Guardrails and limits

- Revenue excludes tax and is before returns; item margin is gross profit before
  returns/operating expenses, never net profit. Metrics live in `services/metrics.py`.
  Refund-adjusted revenue is unavailable because its tax/discount basis is not
  verified; recorded refunds remain a separate return-date metric.
- Stock is monthly location/category, including warehouses in the source, never
  SKU on-hand. Current inventory UI aggregates branch stock only. Replenishment is
  a rough category heuristic, not a purchase order or validated forecast.
- Historical data provenance is unverified; it is not live. October 2026 sales
  are incomplete and its stock label does not prove a complete month-end balance.
- Anonymous orders are excluded from identified-customer modeling. Prior churn
  ROC-AUC around 0.499 does not support reliable individual risk scores.
- No authentication/roles or production deployment is included. Run locally.
- Keep ZIP/CSVs, databases, secrets and customer-level outputs outside Git. Ignore
  rules cover the local environment, datasets and output directories. Check
  `git status --short` before committing; already tracked/force-added files bypass
  ignore protection. No commits or publishing were performed.

The Executive Overview now includes scoped scorecards, equal-day comparisons,
monthly sales/orders/gross-profit trends, category/channel/product charts,
revenue/growth/gross-profit location snapshots, monthly stock attention and
deterministic management signals. The local assistant appends the same verified
executive scorecards. Connected mode keeps the original tools; no live LLM
verification is claimed. Registered master/network captions are company-wide;
stock ignores the selected start date and uses the last recorded end month.

Phase 4 adds daily/weekly/monthly/yearly sales, complete-month MoM/YoY and
seasonality, operational product/category analysis, location rankings and a
separate no-recorded-orders master report. Drilldown replaces only the selected
location within global type. Explicit two-location selectors retain dates and
category while overriding global location/type, with Retail/POS disclosure.
The assistant entry retains global context; named-location/pair questions use
verified local tools. Relative dates are dataset-anchored, not based on today.
The compact location table keeps names and the selected metric visible; every
metric remains available in an expandable, exportable detail table.

Phase 5 extends Profitability Analysis with six scorecards, product ranks with
minimum revenue/units, weighted category margins, company GP contributions,
location drilldown, equal-day GP changes, monthly GP/margin and descriptive
volume/margin screens. Recorded refunds remain separate; net profit and adjusted
profit remain unavailable. The new fixed local assistant tools share the same
services. Connected mode retains its existing tool set.

See [profitability definitions](docs/PROFITABILITY_ANALYTICS.md) and
[Phase 5 evidence](reports/PHASE_5_REPORT.md). With the existing Windows virtual
environment and local database, run from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/validate_phase5.py
.\.venv\Scripts\python.exe scripts/smoke_app.py --report reports/phase_5_smoke.json
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
```

Phase 6 expands Inventory Intelligence with separate sales-location/warehouse
balances, risk maxima and individual high-risk rows, snapshot-anchored velocity,
approximate cover and location/category replenishment, distribution candidates,
monthly balance trends, recorded transfers by status and verified local tools.
Stock remains monthly category-level. The new conservative snapshot policy and
location/category estimates differ explicitly from the unchanged legacy
Executive helper; see [inventory methodology](docs/INVENTORY_INTELLIGENCE.md)
and [Phase 6 evidence](reports/PHASE_6_REPORT.md).

```powershell
.\.venv\Scripts\python.exe scripts/audit_inventory.py
.\.venv\Scripts\python.exe scripts/validate_phase6.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/smoke_app.py --report reports/phase_6_smoke_final.json
```

Phase 7 expands the existing Demand Forecasting page with evaluated monthly
revenue/category-unit forecasts, six candidate models, chronological validation
and held-out tests, baseline fallback, experimental/unavailable states and
uncalibrated empirical error bands. The dashboard and bounded bilingual local
assistant share the read-only forecasting service. Eligible history ends in
September 2026; global dates change the historical display, not training origin.
Phase 6 replenishment and existing customer models remain unchanged.

See [forecast methodology](docs/DEMAND_FORECASTING.md) and
[Phase 7 results](reports/PHASE_7_REPORT.md).

```powershell
.\.venv\Scripts\python.exe scripts/validate_phase7.py --report reports/phase_7_forecast_validation_final.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/smoke_app.py --report reports/phase_7_smoke_final.json
.\.venv\Scripts\python.exe scripts/verify_phase7.py
```

Phase 8 adds aggregate customer purchasing summaries, fixed descriptive RFM,
first-recorded-purchase cohorts, repeat behavior and chronologically evaluated
churn/365-day customer revenue research. The actual models remain unreliable;
no individual probabilities, customer records or automatic risk recommendations
are exposed. Saved customer artifacts, forecasting models and inventory/financial
logic remain unchanged. See [customer methodology](docs/CUSTOMER_INTELLIGENCE.md)
and [Phase 8 evidence](reports/PHASE_8_REPORT.md).

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/validate_phase8.py --report reports/phase_8_validation_final.json
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 scripts/smoke_app.py --report reports/phase_8_smoke_final.json
.\.venv\Scripts\python.exe -X utf8 scripts/verify_phase8.py
```

**STOP: Phase 8 only. Wait for independent review and explicit Phase 9 approval.**

## Phase 9 — Groq-only grounded business assistant

See [assistant architecture and limits](docs/AI_BUSINESS_ASSISTANT.md) and [secure Groq setup](docs/GROQ_SETUP.md). The existing ignored local .env is loaded securely; GROQ_API_KEY is used only by the official Groq SDK. GROQ_MODEL defaults to openai/gpt-oss-120b hosted on Groq. No OpenAI API request is made by the active UI. The legacy SDK remains installed only for frozen compatibility code.

The UI defaults to Offline Analytics. Groq requests require explicit session enablement. Conversation scopes, dates and pair follow-ups are bounded; numerical cards/tables/charts come from approved local tools. Customer tools use a fixed company privacy scope. See reports/PHASE_9_REPORT.md and reports/PHASE_9_EVALUATION.md for actual tests, model comparisons and limitations. STOP before Phase 10 pending independent review.
