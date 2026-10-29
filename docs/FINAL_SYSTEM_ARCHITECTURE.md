# Final local-demo architecture — Phase 10

`COTTONIL_Data.zip` → unchanged imported SQLite tables and normalized views/indexes
→ read-only `db/connection.py` → `services/filters.py` / `services/metrics.py`
→ approved executive, sales/branch, profitability, inventory, forecast and
customer services → eight existing `ui/pages` modules and `analytics.py` facade.

No Phase 10 financial, inventory, forecasting or customer-model formulas were
changed. `app.py`, `analytics.py`, `assistant_engine.py`, `predictive.py`, approved
domain services and existing tests are preserved. Database preparation remains
a separate explicit setup action; runtime access is read-only.

## Assistant flow

`ui/assistant.py` / `ui/assistant_phase9.py`
→ server-side guard/entity/date resolver (`assistant_context.py`)
→ bounded orchestrator (`business_assistant.py`)
→ official Groq SDK (`groq_provider.py`), fixed HTTPS host
→ `cottonil_query`, typed operation allowlist (`assistant_registry.py`)
→ existing approved read-only domain services
→ sanitized aggregate evidence
→ independent coverage classification (`assistant_quality.py`)
→ app-owned bilingual summary (`ui/assistant_answers.py`), tables/charts/CSV.

Groq plans local tool calls; it neither queries SQL nor computes reported KPIs.
Its final prose is not displayed. Tools receive server-resolved scopes; a model
cannot redirect branch/date/category/horizon. Matching unique tool-call IDs and
tool-result messages are preserved. Known complete contracts stop without an
unused final inference request, addressing the Phase 9 post-evidence failure
path. Unrecognized open-ended intent stays partial even when some numbers are
valid. Domain completeness is conservative deterministic coverage, not a
general natural-language entailment guarantee.

On recoverable failure, a session-only pending turn retains messages, memoized
public evidence, original scope, DB identity, model, usage counters and expiry.
Manual retry reuses results rather than reexecuting expensive tools. Model,
scope, source or question changes reject replay. Reset clears pending context
but does not reset usage caps. There is no background autonomous retry loop.
Groq rate-limit recovery is bounded and respects Retry-After. No provider/model
fallback exists. Legacy OpenAI code is frozen compatibility code, unreachable
from the active connected UI; do not enable its old entry point.

## Version and performance boundaries

`scripts/evaluate_phase10.py` hashes final Python sources, preserves the original
73 templates and adds 11 coverage cases. Offline and scripted SDK mock modes
use no key/API. Live mode requires explicit approved local budget, matching CLI
cost acknowledgement, exact source fingerprint, attempt/time/cost reservations.
Source changes invalidate an evaluation claim. Numeric adapter checks recompute
through approved services; they are not an independent audit of source finance.
Human managerial usefulness and live model quality remain separate judgments.

Existing caches remain bounded: forecast 32 entries, customer dashboard 16,
customer-data 8 and research 2. Expensive tools are memoized per turn and reused
only through a bounded pending retry. No new global answer cache or ML model was
introduced. `profile_phase10.py` records first/warm local timings, not an SLA.

## Security and retained limits

Fixed TLS origin, no HTTP redirects, disabled SDK retries and debug logging,
strict JSON/argument schema, operation/column allowlists, guarded scope,
bounded payloads/history, sanitized errors and spreadsheet-formula-safe exports
form the application boundary. No arbitrary SQL/code/browser/MCP tools are
exposed. `.env` is ignored and never included in review packages. External
provider prompts contain sanitized business aggregates, not raw customer rows.

Customer summaries have a fixed company window and small-cell/complement
suppression. Cross-module aggregate differencing cannot be ruled out; this is
not formal differential privacy or access control. Prompt heuristics and typed
tools reduce injection impact but do not prove complete semantic security.
There is no authentication/RBAC, multi-user spend ledger or production telemetry.

Gross profit is not net profit; refund-adjusted financials are unsupported.
Stock is monthly category/location, never SKU. Executive legacy and completed
snapshot inventory policies remain distinct. Cover/replenishment are heuristics;
recorded risk is not stockout probability. Forecast bands are empirically
limited and uncalibrated. Customer research remains unreliable. Local Streamlit
UI and testing do not establish production readiness or live Groq acceptance.
