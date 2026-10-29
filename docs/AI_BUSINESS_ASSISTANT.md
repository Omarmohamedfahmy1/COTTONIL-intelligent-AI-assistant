# Phase 9: grounded bilingual business assistant

Scope: local historical Cottonil task data. Phase 9 only; independent review is
required before Phase 10. This is not a production access-control system.

## Architecture

`ui/assistant.py` retains the earlier offline compatibility functions and contextual
entry point. Its `render` delegates to `ui/assistant_phase9.py`; its active
`run_llm` delegates exclusively to `services/business_assistant.py`. The frozen
`assistant_engine.py` is retained byte-for-byte for historical compatibility; its
legacy OpenAI-connected function is not imported/called by the active UI. There
are no Phase 9 OpenAI SDK clients or OpenAI endpoint requests.

`assistant_config.py` loads the root ignored `.env` without overriding an existing
environment, with interpolation disabled. Environment takes priority over optional
Streamlit secrets, then defaults. Secrets are excluded from Settings repr and are
never serialized. `groq_provider.py` uses official `groq.Groq`, a fixed verified
HTTPS `api.groq.com` origin, a host-checking request hook, disabled redirects,
SDK retries zero and at most two application attempts per request. Retry-after
over three seconds is returned as a rate-limit error instead of retrying early.
Network/request errors are fixed codes; raw provider bodies/headers are not shown.
SDK/HTTP debug logs are suppressed. No external provider or model fallback occurs.

`assistant_context.py` resolves dates and entities into session-only scope. A
strict server-owned registry in `assistant_registry.py` delegates to the approved
Phase 1–8 services. A compact single `cottonil_query` SDK function accepts an
enumerated operation and validated parameters, avoiding repetition of dozens of
scope schemas. Recognized questions advertise only their relevant approved subset; open-ended questions retain the full registry. Tools execute sequentially, including several calls returned in
one message. Model-supplied SQL, Python, shell, URLs and file operations have no
execution path.

## Contracts and limits

The 36 operations cover executive totals/comparable periods/legacy stock;
sales products/trends; location rankings/detail/pairs; gross profitability;
Phase 6 completed stock, risk, cover/replenishment, warehouses and transfers;
Phase 7 values, accuracy and category unit outlook; and seven aggregate Phase 8
customer tools. `category_risk_sales` aligns approved Executive category changes
and Phase 6 category risk using a one-to-one category merge. It does not introduce
a new financial formula, stockout probability or causal explanation.

The complete machine-readable function contract is `assistant_registry.schemas()`.
Unknown operations/fields, malformed/duplicate-key/nonfinite JSON, invalid types,
boolean integer limits, incompatible scopes, unknown branches/categories/warehouses,
duplicate pair members and unsupported horizons are rejected. Rows are 1–20;
forecast horizons 1/3/6; trend grains daily/weekly/monthly/yearly; inventory month
is strict YYYY-MM. The actual selected completed snapshot is disclosed and may
precede the cutoff. Explicit pair scope overrides global branch/type while retaining
dates/category, using the existing approved service policy. Model-authored scope
arguments must agree with the server-resolved scope. Selected product/category
metrics preserve original service ranking semantics.

Output columns and metadata use a compile-time whitelist. Product/branch free-text
names are not sent as provider evidence; public product/location IDs and known
categories suffice. Tool results are JSON-safe aggregate rows with exact period,
scope, source, actual/heuristic/forecast/research classification and typed units.
Truncation is explicit; a top table does not reconcile the entire company by
being summed. Each tool result is matched to its SDK tool-call ID. Duplicate or
reused IDs stop the turn before that batch executes. Identical calls are memoized
within a turn; repeated loops, tool count, request count, time and token budgets
stop work. Failed tools return fixed sanitized correction instructions.

Default limits: four model rounds, eight tool calls, 1,000 output tokens, 25-second
network timeout, 100-second cooperative turn deadline, eight recent history
messages, 40 model requests and 160,000 conservative token reservations per
browser session. Configurable ceilings are in `assistant_config.py`; per-turn
HTTP attempts are capped at nine including catalog/retries. Actual token usage
is recorded separately from conservative reservations. Budgets may stop before
all desired evidence is obtained. An individual approved analytical call is not
preempted mid-query; this is not a hard process-level wall-clock guarantee.

## Grounding and explanations

Groq plans/selects tools and is asked for a final evidence-reference object. Raw
model prose, Markdown tables, HTML, reasoning and invented numbers are never
rendered. The application owns bilingual factual summaries, numeric cards,
evidence tables and Plotly charts, using approved tool values. This deliberate
restriction sacrifices unrestricted model-written explanations for verifiable
figures and explicit limitations. The model can still select an irrelevant tool
or fail to understand an unsupported request; canonical multi-domain requests
have a coverage check and incomplete evidence is labeled partial, not complete.
This is not a claim of arbitrary-language semantic correctness.

English, Arabic and Egyptian follow-ups share session pair/category/date context.
`وBR002` and `و BR002` resolve identically. Dates anchor to source orders ending
2026-10-18, with September 2026 the last complete calendar month. “Last 3 months”
means July–September 2026; “last quarter” means the last completed source quarter.
“The month before” shifts the current conversational start to the preceding month
and retains the prior domain. Ambiguous cities, unknown IDs and unsupported date
phrases ask for clarification. A changed dashboard scope clears conversational
overrides. Reset clears history/scope/model binding but retains usage counters;
changing configured models requires reset. Stop is cooperative between bounded
requests and cannot cancel an already billable HTTP request.

## Business and privacy rules

Revenue is ex-tax and before refunds. Gross profit is before returns/OPEX and is
never net profit. Refund-adjusted figures remain unavailable. Customer counts
are identified purchasers, distinct from the company-wide registered master.
Inventory is monthly category/location, not SKU. Phase 6 completed snapshots and
Executive legacy snapshot/risk/replenishment policies differ and are named rather
than forced to reconcile. Cover/replenishment are heuristics; transfers are not
complete stock movements. Forecast revenue EGP and category demand units are
different targets; origins, reliability and uncalibrated ranges remain visible.
Phase 8 churn/value studies remain unreliable and cannot justify individual
actions or dependable financial planning.

Phase 9 customer tools deliberately override fine-grained filters with the latest
complete company-wide 12-month window (currently 2025-10-01–2026-09-30); research
retains its original mature historical schedule. Repeated branch/date/category
requests therefore cannot obtain overlapping fine-scope customer tables through
this assistant. Underlying Phase 8 k=5/complement/family suppression is preserved;
tiny identified-count financial cells are additionally blanked. No raw features,
customer IDs/names/contact data, individual predictions or saved models enter
Groq, UI exports or reports. Existing Phase 8 dashboard filtering is unchanged.
Cross-module inference and arbitrary repeated access are not formally prevented:
this is not differential privacy, authentication, authorization or production
privacy certification. Source provenance and identification bias remain limits.

Unsafe prompts are blocked before provider construction and are not kept in
assistant history. Prompts/tool text never grant tool authority. CSV exports
contain whitelisted aggregates and neutralize spreadsheet formula prefixes.
Session history stays in Streamlit memory and has no persistent transcript log.
Fixed public benchmark templates are logged by ID; ordinary user prompts and raw
provider errors are not telemetry. Groq necessarily receives the accepted current
question, bounded session context and necessary aggregate evidence: do not put
private personal material in questions. Provider retention/account controls
require separate review. No claim of a formal external security audit is made.

## Verification

See `reports/PHASE_9_REPORT.md`, `PHASE_9_EVALUATION.md`, the public 73-template
`PHASE_9_BENCHMARK.json`, full test logs, regression JSON and original browser
screenshots. Deterministic/mock tests are distinct from live Groq calls. Numeric
benchmark checks compare published values to approved services, rather than
grading invented expected figures or the model's unsupported prose. The benchmark
is finite and does not certify production safety or general model reliability.
