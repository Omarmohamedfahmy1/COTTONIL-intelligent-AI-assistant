# Cottonil — Phase 9 Independent Code & Evidence Review

**Review date:** 24 October 2026  
**Decision:** **APPROVED FOR PHASE 10 (local MVP / demo scope only), with explicit live-Groq acceptance work outstanding.** Not approved for production or unqualified live reliability claims.

## Inputs and integrity

- Inspected `Cottonil_Phase9_Review.zip`, 3,024,791 bytes, **405** members. SHA-256 `0451c6d0117c9115495e7c750d1e7045d61f537476272b80a03afb9ffe0f821e`, matching the attached verification JSON. ZIP CRC test passed; no path traversal entries were accepted while extracting.
- Included all expected `services/`, `ui/`, `db/`, `scripts/`, `tests/`, docs, logs and **16 original Phase 9 screenshot files**. `.env`, actual Streamlit secrets, original CSVs/ZIP, SQLite database and private customer-level artifacts are absent from the archive.
- Verified `.env.example` contains blank credentials and `.gitignore` has rules for local `.env`, Streamlit secrets and private data. This is a packaging check, not a formal security certification. The private working `.env` was not supplied, inspected or requested.
- Rebuilt the read-only analysis database from the user's previously provided `COTTONIL_Data.zip`, without modifying the original ZIP. The original source SHA-256 was checked during Phase 1 reconciliation.

## Independently executed checks

| Check | Independent result | Notes |
|---|---:|---|
| Phase 9 focused unit tests | **44 / 44 passed** | Since official Groq SDK was unavailable in review runtime, a minimal **test-only Groq ChatCompletion shape shim** outside the project enabled mock-protocol tests. The real SDK/client was **not** exercised. |
| Original Python baseline tests | **8 / 8 passed** | Actual code/tests and reconstructed SQLite source. |
| Original feature tests | **9 / 9 passed** | Actual code/tests. |
| Phase 1 tests | **19 / 19 passed** | Actual code/tests. |
| Database integrity | **83 / 83 passed** | `scripts/validate_db.py`, recreated SQLite. |
| Phase 1 source/KPI reconciliation | **19 / 19 passed** | `scripts/validate_phase1.py --zip ...`, original source file. |
| Offline Phase 9 question evaluation | **73 / 73 passed** | Re-executed `scripts/evaluate_phase9.py` on actual SQLite; **2,357 published numerical fields checked, 0 mismatches**. |
| Additional manual Arabic dialogue | **5 supported turns** | Three-domain two-location comparison; profit follow-up; stock follow-up; preceding-month follow-up; weak churn research question, with correct scope preservation and chosen tool family. |
| Tool registry | **36 operations** | Static inspection and actual dispatch paths; read-only domain adapters, not LLM-authored SQL. |
| Screenshots | **16 inspected** | English/Arabic, connected/offline, blocked/error, charts and narrow viewport. No independent graphical browser run. |

### What is only supported by packaged Codex evidence (not independently rerun)

- **208 / 208 full-suite tests**, **305 / 305 Phase 9 validator**, **8,242 / 8,242 earlier-phase validators**, and **16 / 16 bilingual Streamlit AppTest page runs**. Final logs and structured evidence are included, but they were **not** all executed afresh in this review. The Phase 9 validation script's preservation check requires absent private artifacts, and Streamlit was not installed in this runtime.
- Authenticated real Groq account/model-catalog checks and **actual** live inference requests were made during Codex's development, per submitted logs. **No fresh Groq API inference was performed** in this review, because the API key was not provided and should not be shared. Official `groq` SDK also could not be installed in the isolated environment.
- Original dataset/SQLite and saved customer artifact preservation is supported by packaged local integrity hashes; no private artifact bytes were included for independent private-file comparison.

## Implementation assessment

**Verified positives:**

1. The new connected UI route (`ui/assistant_phase9.py` through `ui/assistant.py`) uses `services.business_assistant` and `services.groq_provider`; this provider uses only the Groq SDK with fixed `https://api.groq.com` origin, redirect-disabled HTTP client and bounded request handling. A frozen *legacy* OpenAI-connected function remains in `assistant_engine.py`, but is not in the new active UI call path. The Groq-hosted default model `openai/gpt-oss-120b` is acceptable; the `openai/` prefix identifies the model maker, not the API host.
2. The registry is an explicit 36-operation approved aggregate allowlist, validating arguments and limiting scope. No arbitrary SQL, file, remote browsing or code-execution tools are exposed to the LLM.
3. Financial/numeric answers and charts are rendered from verified app-owned reports rather than directly from arbitrary model prose. Exact reported financial basis and unsupported net-profit/refund-adjusted claims are maintained.
4. Context and explicitly named pairs are resolved server-side; manual Egyptian Arabic dialogue preserved period and the pair across turns. Offline mode remains functional without credentials.
5. Errors, timeouts, token/call budgets, tool IDs, duplicate arguments, customer privacy restrictions, forecast limitations and experimental churn/value warning behavior have targeted test coverage.
6. CSV output escapes formula-like strings and rejects unknown/private columns. Private customer-level records are excluded from new public tool payloads. This does not equal formal differential privacy or production access control.

**Important live-Groq caveats:**

- The final documented **four-question** sampled model comparison had GPT-OSS 120B completing **4/4** semantically, versus Qwen **2/4**. The respective numeric checks had no mismatches *for evidence that was actually returned*. This sample is too small to establish broad reliability or statistical model superiority.
- Groq quota (429) and malformed/invalid tool request errors remain observed. A real final-source browser interaction recorded an invalid request **after** generating verified local evidence. Distinguish complete answers from partial/error states.
- The final sampled model comparison preceded later source changes concerning type, warehouse, month, horizon, category, retry headers and provenance. Therefore the reported 4/4 is **not** a complete end-to-end regression of every edge of the final live source version. No fresh provider call was performed in this review.
- The Groq implementation deliberately constrains tool discovery using local keyword-based hints, and the frontend supplies verified template-based narrative rather than general free-form LLM writing. This improves factual safety but limits conversational flexibility. Tests should evaluate *answer usefulness and completeness*, not just correct returned numbers.
- The narrow screenshot is from **offline** mode; a real connected 390px test is not documented. Neither production multiuser roles/authentication, screen-reader testing nor formal privacy red-teaming has been completed.

## Independent disposition

**Approve Phase 9 as a functioning, testable Groq-only local MVP implementation and authorize Phase 10: Final Testing, Optimization & Delivery.** This is *not* approval of deployment/production readiness, a claim that all connected requests reliably succeed, or permission to suppress known live errors.

**Mandatory Phase 10 acceptance items:**

1. Correct or gracefully classify final-source live tool/invalid-request failures. Show a prominent **partial answer / incomplete analysis** state without implying complete coverage.
2. Perform a more representative **user-authorized, dollar-capped** Groq evaluation on the *exact final source version*, including 1/3/6 month horizons, branches, mixed retail/POS, categories, warehouses, inventory snapshot dates, Egyptian Arabic joins and multi-step conversations. Separate task-completion, tool-routing, quantitative grounding, latency, and provider-error metrics. Never present a 4/4 sample as global accuracy.
3. Exercise narrow **connected-mode** UI at 390px, not only offline; verify accessible error states, wide tables and legible chart dates. Improve the practical managerial answer narrative and explain data provenance/limits.
4. Confirm that model selection and `.env` remain Groq-only. No OpenAI API calls; no key logging or copying. Keep offline fallback and strict customer privacy. Confirm data isolation; do not assume production authorization.
5. Rerun the entire 208+ test suite and all prior validators after fixes; do not alter approved financial/stock/forecast/customer formulas. No unverified net profit, SKU stock or individual churn decisions.
6. Produce an operator-friendly Windows setup, demo script, source/dataset separation instructions, security audit and explicit remaining limitations. Do not call this local intern demo production-ready.

---

**Review artifact generation:** The independent numeric and test runs are verifiable in the executing conversation/container; the archived Codex logs should not be cited as newly rerun independent tests. No credentials were used.
