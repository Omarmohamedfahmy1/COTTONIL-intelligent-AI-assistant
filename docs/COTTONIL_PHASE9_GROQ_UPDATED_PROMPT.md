# Codex implementation prompt — Cottonil Phase 9 (GROQ API ONLY; MODEL PROVIDER FLEXIBLE)

Phase 8 of the Cottonil Intelligent Business Intelligence & AI Assistant System has been independently APPROVED with documented limitations. Implement **PHASE 9 ONLY** according to `COTTONIL_CODEX_IMPLEMENTATION_ROADMAP.md` and the requirements below. Stop before Phase 10.

## NON-NEGOTIABLE LLM PROVIDER POLICY

**GROQ CLOUD IS THE EXCLUSIVE API/INFERENCE PROVIDER FOR PHASE 9. Model origin is not restricted: models developed by OpenAI (such as GPT-OSS), Qwen or others are permitted ONLY when served by Groq using the user’s GROQ_API_KEY.**

- The user already owns a **Groq API key**. Integrate the official **Groq Python SDK** (`groq`, `from groq import Groq`) using `GROQ_API_KEY` from a local environment variable or ignored local `.env`/Streamlit secret. Use Groq's chat-completions API with local function/tool calling and an application-controlled tool loop.
- **Primary candidate/default: `openai/gpt-oss-120b`**, an OpenAI-developed open-weight model HOSTED ON GROQ. Its `openai/` model-ID prefix indicates the model developer, **not** an OpenAI API request. Use `GROQ_MODEL` to configure it. The Groq catalog currently lists this as a production model with local tool calling and a 131K-token context; verify actual account access and current capabilities before use.
- **Benchmark the alternative `qwen/qwen3.8-27b`** where available; it is a Groq-hosted preview model with multilingual/tool-use capability. Optional lower-cost candidate: `openai/gpt-oss-20b` hosted on Groq. Choose the final model using a disclosed bilingual executive-question benchmark (Arabic/Egyptian dialect, English, multi-step tool accuracy, grounding, latency and measured token cost), not solely model size or vendor name. Do not claim GPT-OSS is empirically more accurate than Qwen for Cottonil until tested.
- Do not connect to `api.openai.com`, use an OpenAI API key, instantiate an OpenAI SDK client for Phase 9 inference, or silently switch to an external provider. Groq's API path may contain `/openai/v1` for compatibility; this is STILL GROQ when the host is `api.groq.com`. Use the official Groq Python SDK and the GROQ_API_KEY exclusively.
- Disable/replace the legacy OpenAI-connected assistant path. Preserve needed legacy files for backwards compatibility, but confirm the Phase 9 UI cannot send inference requests to OpenAI endpoints. Model developers are allowed to be OpenAI, Alibaba/Qwen or others if the model is hosted by Groq.
- If the configured model is unavailable, produce a clear model-access error and offer available Groq-hosted alternatives **without silently switching models**. Retain the offline verified-analytics mode. Do not silently change model/provider mid-conversation.
- Never hard-code, print, commit, send in chat, include in screenshots, or write the real API key to a report/log. Add safe `.env.example` with `GROQ_API_KEY=` and `GROQ_MODEL=openai/gpt-oss-120b`; ensure `.env`, `.streamlit/secrets.toml`, and real credentials are ignored by Git.
- The user should configure the actual key **locally**, not send it to Codex's prompt or chat. If the key is already configured, use it through the environment without displaying it. Don't overwrite or inspect secret values beyond confirming presence.
- If `GROQ_API_KEY` is missing, **offline/local analytics mode remains usable**; explicitly label Groq live verification as NOT RUN rather than pretending mocks contacted Groq. If configured, perform limited, clearly bounded real Groq API tests, record outcomes without secrets, and respect the user's account rate limits.
- Update `requirements.txt` with the official `groq` SDK (and `python-dotenv` only if genuinely required). Keep dependency changes minimal. If a preexisting `openai` package is needed by frozen legacy code, leaving it installed is acceptable, but **Phase 9 must never use it for inference**.

## 1. OBJECTIVE

Build a professional, grounded, bilingual **Groq-powered AI Business Assistant** for Cottonil managers, answering Arabic (including Egyptian colloquial Arabic) and English questions across all eight existing dashboard modules. The assistant must support follow-up questions, comparisons, safe cross-module reasoning, verified numeric results, evidence tables/charts, and honest limits. Preserve the Navy/Teal responsive UI, RTL/LTR localization, and approved financial/data services.

The LLM is an **intent/planning, tool-selection and explanation layer**, NOT the source of company figures and NOT an arbitrary SQL generator. Only approved local analytics functions calculate business numbers.

## 2. AUDIT FIRST; PRESERVE APPROVED IMPLEMENTATION

Before making changes, inspect `assistant_engine.py`, `ui/assistant.py`, all Phase 3–8 `services/*_tools.py`, the Phase 1 financial services, existing global filters and session state, the KPI dictionary, historical date coverage, the Phase 8 privacy policy and the roadmap. Inventory which operations are only supported in bounded offline mode versus current connected mode. Design the integration around existing audited services instead of rewriting them.

Preserve original datasets, read-only SQLite data, approved KPI formulas, Phase 6 stock and replenishment logic, Phase 7 evaluated forecasts, Phase 8 customer models/labels and saved private customer artifacts byte-for-byte. Do not add Phase 10 functionality.

## 3. GROQ CLIENT, CONFIGURATION AND CONNECTION CHECK

Implement a small `GroqProvider`/client adapter module and central configuration layer:

- `GROQ_API_KEY` (secret, mandatory only for Groq-connected mode)
- `GROQ_MODEL` (default `openai/gpt-oss-120b`; compare Groq-hosted Qwen and GPT-OSS 20B when accessible)
- Optional documented bounded settings for request timeout, maximum output tokens, maximum tool rounds, total tool calls, context length/message count, and per-session call/token limits.
- Use `Groq(api_key=..., timeout=..., max_retries=...)` or equivalent supported SDK arguments and `client.chat.completions.create(model=..., messages=..., tools=..., tool_choice=...)`.
- Query/validate available models and account permissions using the Groq model-listing API when feasible. Do not assume every Groq model supports the same JSON, reasoning, structured-output or parallel-call options. In particular, GPT-OSS 120B does NOT list parallel tool calling in Groq's current support table, so begin with safe sequential local tool rounds, then consider parallel execution only with compatible models and tested ordering. Do NOT combine strict structured-output mode with tool-use parameters in a single request where Groq does not support that combination.
- Use supported API parameters only. Handle 400 invalid model/request, 401/403 credentials, 429 rate limits, and 5xx/network/timeouts gracefully. Use bounded exponential backoff for retryable errors and respect `retry-after`; never retry indefinitely.
- Provide an explicit **Connected: Groq** vs **Offline: Verified Analytics** status in the UI. No hidden calls or silent provider substitution.
- Do not train/fine-tune or download heavyweight local LLMs.

## 4. UNIFIED READ-ONLY TOOL REGISTRY

Expose typed, documented, parameterized approved local analytic tools, reusing Phase 1–8 foundations rather than copying calculations. Organize capabilities:

- Executive: overview, KPI and comparable period performance.
- Sales Analytics: trends, products, categories, revenue, orders and seasonality.
- Branch Performance: rankings, growth, location detail, two-location comparisons, zero-recorded-activity explanations.
- Profitability: gross profit, revenue, weighted margin, profitability rankings, descriptive low-margin screens.
- Inventory: latest eligible month-end snapshot, location/category units, warehouses, recorded risk, coverage/heuristics, transfers/statuses and category/location replenishment estimates.
- Forecasts: Phase 7 revenue vs unit-demand targets, horizons, model/baseline scores, forecast origin, reliability state, uncalibrated residual bands and category outlook.
- Customers: aggregate identified/anonymous purchases, RFM, cohorts, retention and repeat trends; unreliable churn and next-365-day customer-revenue research ONLY with explicit unreliability and **no individual predictions or actions**.

Every tool has strict schemas, parameter validation and a whitelist of outputs. Validate allowed date formats and ranges, category IDs/names, unique branch IDs/type, known warehouses, requested month, forecast horizon (1/3/6 only), ranking sort/order, bounds and maximum rows. Return small aggregate-only JSON-safe summaries with provenance and typed units. Use read-only parameterized SQL through approved services. **Never allow model-authored SQL/Python/shell code, file access, write queries, external URLs or unrestricted database execution.**

## 5. REAL MULTI-STEP GROQ TOOL CALLING

Implement a robust local orchestration loop using the official Groq SDK:

1. Send system/business rules, recent bounded session context and approved tool schemas to Groq.
2. Receive an assistant message that may contain zero, one or several structured `tool_calls`.
3. Validate model-requested tool names/JSON argument structure against server-side schemas and allowlists; reject invalid or unsafe requests before any execution.
4. Execute approved tools locally (optionally safe parallel execution if supported and verified), assign each result to the corresponding `tool_call_id`, and append the assistant tool-call message plus matching tool results in the correct chat format.
5. Continue until the model returns a supported final response OR the configured tool-round, count, time or token budget is reached.
6. If a tool fails, expose a sanitized structured error without raw SQL, customer IDs, stack traces, credentials or hidden service internals; permit bounded correction/retry or offer clarification.

Ground the final business statements against actual tool outputs. Prefer deterministic data cards/tables/charts built by the application from validated result objects, rather than trusting arbitrary Markdown tables/numbers generated by the LLM. Add unit tests for malformed JSON, unknown tools, mismatched tool-call IDs, empty outputs, repeated loops and budget exhaustion.

## 6. EGYPTIAN ARABIC, ENGLISH AND SESSION CONTEXT

Support fluent Egyptian Arabic, Modern Standard Arabic and English, including mixed Arabic/English/IDs, and natural follow-up questions such as:

- "قارن مبيعات BR001 وBR002 آخر 3 شهور" → "طب الأرباح؟" → "والمخزون عندهم؟" → "طب الشهر اللي قبله؟"
- "قارن المخزون بين BR001 وBR002" and "قارن المخزون بين BR001 و BR002" (regression for the known Arabic `و` spacing defect).
- "What were the highest-profit products in Alexandria last quarter?" (resolve exact locations/scope; clarify ambiguous city/branch mapping).
- "For those categories, compare current recorded inventory risk and historical sales."

Maintain bounded **session-only** history of entity scopes, periods, comparison pair, categories and resolved tool evidence. Allow reset/clear chat. Respect current Streamlit global filters unless the user's explicit request overrides them; disclose overrides. Resolve relative periods against **historical database coverage** rather than computer time, and show actual dates. Current source orders end 2026-10-18; October 2026 is partial. Phase 7 last fully observed forecast month is September 2026. For stock, use Phase 6 conservative latest **completed** snapshot policy where appropriate, never silently substitute the Executive legacy policy. Ask a targeted clarification when a named place, category, period or pair is genuinely ambiguous.

## 7. CROSS-MODULE FACTUAL REASONING

Answer single-domain and combined questions, including:

- "ايه إجمالي المبيعات ومجمل الربح آخر 3 شهور؟"
- "أنهي الفروع مبيعاتها أعلى لكن هامش ربحها أقل؟"
- "قارن مبيعات وأرباح ومخزون BR001 وBR002 خلال نفس الفترة."
- "Which categories show rising sales and high recorded stockout risk?"
- "What is the expected revenue next quarter, how accurate is the forecast, and how does it compare with historical sales?"
- "ما نسبة العملاء اللي اشتروا أكتر من مرة؟ وهل نموذج Churn موثوق؟"
- "ما الفرق بين فئات المخزون عالية الخطورة في Executive Dashboard وفي Inventory؟"

Before joining results, align dates, location scopes, product-category grains, units, snapshot vs transaction dates, identified vs anonymous customers, and forecast origins. Do not merge incompatible metrics or pretend one can be derived from another. Explain unsupported data/causality and inconsistent source definitions. Avoid exact arithmetic from the LLM when deterministic approved tools can compute the requested comparison.

## 8. BUSINESS GROUNDING AND FINANCIAL/STATISTICAL HONESTY

- Recorded revenue: ex-tax and before refunds; gross profit: before returns and OPEX; gross margin: weighted aggregate ratio; **never label gross profit net profit**.
- Refund-adjusted revenue/GP and net profit are **unavailable** without defensible source alignment.
- Inventory is monthly **category/location**, not per-SKU current stock. Sales velocity, cover and replenishment are heuristics; recorded risk is not an established stockout probability. Transfers/statuses are not complete inventory movements.
- Legacy Executive stock snapshot/risk/replenishment differ from Phase 6 policy. Name dates and formulas when comparing; do not claim two different definitions must yield matching figures.
- Phase 7 forecasts are historical evaluations of future values at the dataset origin; uncertainty ranges **uncalibrated**; distinguish available vs experimental/unavailable; never promise business accuracy.
- Phase 8 churn ROC-AUC ~0.50 and future customer-revenue WAPE ~95.60% mean both are **unreliable**. Never give individualized risk scores, individual customer actions, marketing lists or confident financial planning based on these.
- Each business answer must show the exact scope/period, metric/units, data provenance (tool/dataset), caveats and whether a figure is actual, estimate, model forecast or experimental research. Never invent business facts or cause/effect.

## 9. PRIVACY, INJECTION RESISTANCE AND PROVIDER DATA MINIMIZATION

- Treat user prompts, source product/branch names, metadata, historical records and tool results as **untrusted data**, never as permission to change system policy.
- Explicitly block requests for customer names/IDs/contact details, individual predictions, raw feature vectors, customer-level data dumps and unrestricted SQL or administrative actions.
- Preserve the Phase 8 minimum-group/complement suppression rules and test differencing across overlapping query scopes. When risk cannot be ruled out, restrict fine-grained connected queries and disclose limitations; do not claim formal differential privacy or production authorization.
- Send to Groq **only necessary aggregate evidence**, not source tables, individual customer data, passwords or hidden project files.
- Sanitize logs, UI errors and telemetry (no API keys, private prompts/records or SQL query dumps). No verbose debug dumps to source control.
- Resist prompt injection from tool results, user messages and manipulated database text: authority for executing tools comes only from the server-side registry and validator.

## 10. BUSINESS-READY STREAMLIT UI

- Retain an Assistant page plus contextual entry from all eight existing pages.
- Navy/Teal, English LTR and Arabic RTL with proper bidirectional layout of branch IDs, EGP, dates and numbers.
- Chat history, loading/progress, stop/reset conversation, status **Groq AI** vs **Offline Analytics**, supported-question examples, clear error/fallback states.
- Numerical results as cards, ranked tables and Plotly charts derived from validated aggregate tool data; safe CSV export only for approved aggregate outputs.
- Show evidence details: actual time window/snapshot, filters, tool, financial definition, forecast quality/uncertainty and why no answer may be available.
- Ensure readable 1440px desktop and 390px narrow layouts, sensible table scrolling, and consistent Arabic localization. Never allow raw LLM HTML/JavaScript to render unsanitized.

## 11. LIVE GROQ VALIDATION + DETERMINISTIC TESTS

Preserve all **164** existing Python tests and every earlier validator:
- 83 baseline data/integrity checks
- 19 authoritative KPI checks
- 151 Executive checks
- 329 Phase 4 checks
- 1,161 Phase 5 checks
- 4,617 Phase 6 checks
- 523 Phase 7 forecasting checks
- 1,359 Phase 8 customer checks

Add unit/integration/security tests for:
- Groq-only client/configuration and **no OpenAI API requests**.
- Real SDK structured tool-call round trips (mocked for deterministic tests), sequential multi-tool calls, malformed arguments, max-step/max-token limits, unknown calls, tool errors and timeouts.
- No-key offline fallback; configured unavailable Groq-hosted model returns an explicit error and offers tested Groq-hosted alternatives without silent switching or third-party API fallback.
- Arabic/English/Egyptian dialect, follow-ups, the `وBR002` spacing regression, scope overrides and reset, conflicting/missing entities.
- Dashboard/assistant exact numeric consistency and chart/table data provenance, zero/partial/no-data cases, historical date origin.
- Cross-module alignment (gross vs net, source dates, branch vs warehouse, revenue vs units, Legacy Executive vs Phase 6 inventory and forecast quality).
- Privacy and tiny cohorts, prompt injection, raw SQL/data extraction attempts and no credentials/customer records in logs.
- All existing eight pages in both languages and safe analytics exports.

Create a reusable benchmark of at least **50 bilingual executive questions**, including at least 12 multi-turn/cross-module scenarios and at least 10 adversarial/privacy/data-limit scenarios. Store question templates and expected **tool-grounded** answers/checks, not fabricated numerical outputs. Report tool-routing accuracy, grounded numeric correctness, supported/clarification/unsupported outcomes, follow-up resolution and latency. Do not invent pass rates.

**Groq-hosted model selection:** Verify the account can access `openai/gpt-oss-120b`, then compare it with `qwen/qwen3.8-27b` and optionally `openai/gpt-oss-20b` using the SAME representative, tool-grounded Arabic/Egyptian-English/cross-module evaluation cases when permissions and test budgets allow. Record each model's real ID, model availability, task success/grounded numeric correctness, multi-turn/tool-call error rate, refusal/clarification quality, median and p95 latency, input/output usage and estimated cost where documented. Choose GPT-OSS 120B provisionally as the primary default, but prefer a better-scoring Groq-hosted alternative if test evidence supports it and the selection is recorded. No external provider is permitted. If model comparison is unrun, disclose that the default is a candidate, not a proven winner.

**Live test rule:** Because the user has a Groq key, once it is safely available as `GROQ_API_KEY`, run a capped test set of real Groq calls (for example, 8–15 varied prompts including Egyptian Arabic, multi-turn and cross-module), in addition to any deliberately budgeted model comparison. Track actual model ID, number of calls, input/output token usage when provided, rate-limit errors, latency, tool-selection/numeric-grounding results, and cost estimate only if supportably priced. Never include the key, request headers or sensitive user data in logs. If the key isn't configured in the environment, don't request it in chat; report LIVE TESTS NOT RUN and provide precise local setup instructions. Mock tests must not be described as live verification.

Run the complete 164+ test suite, every prior/new numerical validator, real Streamlit startup and all eight pages in Arabic and English. Test the connected **Groq** experience in actual browser when the key is configured. Include desktop 1440px and mobile-width 390px screenshots, covering connected Arabic dialogue, multi-turn pair, cross-module grounded answer, evidence table/chart, no-key offline fallback and blocked unsafe question. Clearly mark any screenshots from mock/offline mode instead of mislabeling them as live Groq.

## 12. PERFORMANCE / OPERATIONS

Bound tool rounds (default suggested max 4), tool executions per question (suggested max 8), row/series sizes, network timeouts, retry counts and prompt history. Respect Groq 429 and account limits. Avoid repeated expensive analytics and unnecessary model calls; batch compatible independent data fetches only when model/provider supports it. Cache safe aggregates based on validated scopes and DB identity; never cache secrets in public outputs. Benchmark connected turn latency and server-side analytical latency separately. Do not promise production-scale performance.

## 13. DOCUMENTATION / REPORTING

Create:
- `docs/AI_BUSINESS_ASSISTANT.md`
- `docs/GROQ_SETUP.md` — Windows/VS Code local setup, environment variables, `.env.example`, installation, Groq model permissions, **comparison of GPT-OSS 120B vs Qwen where tested**, and safe test steps, **no actual API key**.
- `reports/PHASE_9_REPORT.md`
- `reports/PHASE_9_EVALUATION.md` and machine-readable results/evidence where useful.

Document exact architecture, allowed tool contracts, Groq model/SDK version, model selection and comparison evidence (or explicit untested status), provider-only compliance evidence, model availability status, offline fallback, orchestration, dates/filters, privacy threat model, prompt injection restrictions, accuracy/limitations, connected vs mocked outcomes, model costs/rate limits if actually checked, timings, screenshots, files added/modified, executed commands with exit codes and all skipped/unrun validations. Note that full independent evaluation is required before Phase 10.

## HARD STOP CONDITIONS

1. **Use GROQ ONLY as the inference/API provider and the user's GROQ_API_KEY. Groq-hosted OpenAI-developed models (`openai/gpt-oss-120b`, etc.) ARE ALLOWED; any request to OpenAI API endpoints or external inference providers is NOT allowed. No hidden provider/model fallback.**
2. Implement Phase 9 ONLY; no Phase 10/deployment/production-readiness claims.
3. No source-data mutation, new financial formulas, edits to saved customer research artifacts or prior approved forecasting/inventory models.
4. No unrestricted SQL, customer-level disclosure, fabricated metrics or unsupported model-based decisions.
5. Never expose, commit or log the Groq key.
6. If live Groq testing cannot be performed due to missing credentials/limits, document it honestly; do not invent successful live tests.
7. STOP after implementation, tests and reports. Wait for independent Phase 9 review before Phase 10.
