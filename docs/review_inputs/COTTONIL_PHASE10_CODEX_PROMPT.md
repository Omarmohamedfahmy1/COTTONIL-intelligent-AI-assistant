# PHASE 10 — FINAL QUALITY GATES, OPTIMIZATION & DELIVERY

Phase 9 is independently APPROVED **for progression to Phase 10 as a local demo MVP**, with the live-Groq caveats listed in the independent review. Implement **PHASE 10 ONLY**. Read the full roadmap, the Phase 9 independent review and the Phase 9 methodology/evaluation first.

## Non-negotiable foundations

- **Groq is the EXCLUSIVE live LLM API provider**, using the existing local `GROQ_API_KEY`, official Groq Python SDK and `GROQ_MODEL` (default `openai/gpt-oss-120b` hosted by Groq). An OpenAI-developed model hosted on Groq is allowed; calling the OpenAI API is prohibited. Preserve the legacy code for approved compatibility, but never reactivate it for connected inference.
- Do not expose, print, commit, transmit in reports or place any real credential in screenshots/logs. Do not overwrite the existing `.env`.
- Preserve the complete Phase 0–9 KPI/data/report semantics, read-only SQLite, model gates, original data, training artifacts and historical reports. No new ML training or unapproved accounting definitions.
- Keep the bilingual Arabic RTL/English LTR Streamlit UI, offline mode and all eight modules. Do not introduce a production-readiness claim.

## 1. Fix known Phase 9 live-Groq weaknesses

- Investigate the preserved real invalid-request/tool-use failure that occurred after verified local evidence, and the documented 429/rate-limit interruptions.
- Reproduce failures safely using mocks and local unit tests first. Correct schema, tool sequencing, argument handling, error reporting and backoff as appropriate to the official Groq SDK/model. Do not simply suppress error states or secretly switch models/providers.
- Explicitly distinguish full answer, partial verified evidence, clarification, unavailable, provider error and budget exhaustion. The interface must NEVER mislabel incomplete multi-domain evidence as a complete management answer.
- Improve graceful recovery/manual retry of failed connected turns without duplicate expensive tool calls, unsafe state mutation, or silently discarding verified evidence. Preserve usage/cost caps.
- Review scoped query coverage and entity/time resolution: Arabic `وBR002` and `و BR002`, branch versus POS, dates, month-end snapshots, one/three/six-month forecast horizons, categories, warehouses, customer privacy, follow-up context.

## 2. Human-quality managerial answers with verified evidence

- Improve local app-owned, bilingual response assembly so a manager receives a useful concise summary: question interpreted, period/location scope, central findings, comparisons, table/chart, methodology/source and important caveats.
- All NUMBERS must be retrieved from approved services; no raw unverified LLM financial prose, invented causes, unsupported net profit, or arbitrary SQL.
- Separate recorded facts, descriptive alerts, heuristic stock-cover/replenishment, evaluated forecasts/uncalibrated ranges and unreliable customer churn/value research.
- Assess task completeness and meaningful managerial usefulness independently of numeric correctness.

## 3. Live Groq acceptance evaluation: EXPLICIT COST SAFETY

- Do not spend additional paid quota without an explicit, locally configured test budget and the user's approval. Support a dry-run/mock evaluation when live testing is not authorized. Never include real credentials in an evaluation report.
- Once authorized, benchmark the EXACT FINAL SOURCE after the fixes. Define a reproducible fixed set of at least 20 diverse bilingual management tasks if service limits permit, including: simple KPIs; retail versus POS branch comparisons; sales + profitability + stock multi-tool questions; warehouse inventory; snapshot cutoff; revenue versus unit forecasts at horizons 1/3/6; privacy refusal; unreliable churn/value disclosures; ambiguous names; partial/outside-coverage periods; Egyptian-Arabic multi-turn follow-ups.
- Limit HTTP attempts, rounds, wall-clock duration and expected total cost; stop when budget/quota is exceeded and mark cases NOT RUN rather than passed. Retain status/error/usage metadata and per-question requested versus returned domains.
- Report separate semantic-completeness %, routing %, number of verified numeric values and mismatches, incomplete/partial %, rate limits, model errors, median/p95 latency, input/output tokens and estimated costs. Do NOT claim broad reliability from small or non-independent samples.
- Retain GPT-OSS as default unless reproducible final-source evidence justifies a change. No automatic model fallback or OpenAI calls.

## 4. UI, accessibility, performance

- Inspect all eight modules and assistant page/dialog in English LTR and Arabic RTL using real Streamlit startup and AppTest.
- Conduct actual browser review on desktop 1440px and narrow 390px, **including connected Groq mode** if authorized and operational. Capture raw evidence without editing. Check multi-turn chat, tool/error states, tables, charts, dates, keyboard access where possible, responsiveness and long conversations.
- Profile cold-ish and warm scoped analytics, expensive forecasting/customer analysis, large tables and assistant tool workflows. Document timings, avoid needless reruns and cap caches safely. No false production SLA.
- Improve navigation, explanations and clarity for nontechnical management. Keep Navy/Teal design consistent and all data-source limitations visible.

## 5. Security, stability and reproducibility

- Audit the active provider call graph, fixed HTTPS Groq origin, SDK transport, HTTPS redirects, prompt injection, tool and argument allowlists, scope overrides, duplicate tool IDs, SQL safety, CSV injection, secret redaction and replay/reset behavior.
- Review customer small-cell suppression and cross-module differencing; explicitly state why this is not production-grade differential privacy or user/role authorization.
- Preserve read-only data, source hashes, protected legacy services, formulas, previous screens, models, artifacts and tests.
- Ship safe `.env.example`, `.gitignore`, dependency lock, documented Windows setup instructions and a zero-key offline demonstration path.

## 6. Full regression evidence

- Preserve and rerun all existing 208 automated tests, plus new Phase 10 tests covering corrected faults and complete/partial-answer states.
- Rerun baseline 83, KPI 19, executive 151, sales 329, profitability 1,161, inventory 4,617, forecasting 523, customer 1,359 and Phase 9 checks 305 (or accurately report any intended additions/changes).
- Rerun the 73 offline question evaluation and 2,357 numeric checks, or report actual updated totals and explain differences. All published numeric mismatches should be zero.
- Test startup and all eight pages in both languages. Execute actual browser validation separately from headless AppTest. Keep failures, skips, process exit codes, timestamps and performance measurements honest.
- Never state live Groq integration passed if only mocks or model-list authentication ran.

## 7. Deliverables

Create or update:
- `docs/DEPLOYMENT_AND_OPERATOR_GUIDE.md` (local setup, .env, Groq configuration, safe launch/troubleshooting, offline fallback and non-production warning)
- `docs/DEMO_SCRIPT.md` (credible short Arabic and English managerial walk-through and expected scopes)
- `docs/FINAL_SYSTEM_ARCHITECTURE.md` (data → authoritative analytics → tool dispatcher → Groq → verified UI, security and known limits)
- `reports/PHASE_10_REPORT.md` (exact changes, commands, tests, regression results, UI screenshots, performance, live evaluation, issues and limitations)
- `reports/PHASE_10_ACCEPTANCE_MATRIX.md` (each functional/nonfunctional requirement with PASS/PARTIAL/FAIL/NOT RUN and evidence)
- `reports/PHASE_10_DELIVERY_MANIFEST.md` (versioned source list, approved demos, SHA-256/manifest, exclusions, data setup instructions)
- A lightweight secure `Cottonil_Phase10_Review.zip` containing source/tests/docs/reports/sanitized images only, excluding datasets, SQLite DB, .env, secrets, customer-level predictions and model artifacts.

Document outstanding production work (authentication/RBAC, true privacy protection, monitoring, deployment, data provenance, forecast uncertainty and churn unreliability). Do not market the local demo as a production enterprise system.

**STOP after Phase 10 implementation and validation. Await independent final review.**
