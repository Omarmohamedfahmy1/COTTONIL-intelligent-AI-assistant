# Groq-only Windows setup and safe verification

The active Phase 9 inference provider is **Groq only**, using official Python SDK
`groq` 1.7.0. The default model is `openai/gpt-oss-120b` hosted on Groq. The
`openai/` prefix names the model developer, not an OpenAI API request. The legacy
OpenAI package/file remains frozen for compatibility; it is not the active client.

From PowerShell in the project folder (or the VS Code integrated terminal):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

Use the README's host-pip fallback if the old virtualenv pip cannot use the Windows
certificate store. TLS verification must remain enabled:

```powershell
python -m pip --python .venv install -r requirements-lock.txt
```

Keep the existing local `.env`; **do not overwrite it**. For a new authorized copy,
create it from `.env.example`, then edit it locally in VS Code. Configure
`GROQ_API_KEY` with your private key and `GROQ_MODEL=openai/gpt-oss-120b`. Never
paste the key into a chat, report, screenshot, command history or repository.
Environment variables take priority over `.env`, then optional local Streamlit
secrets. Dotenv interpolation and environment override are disabled. `.env`, all
real `.env.*` files and `.streamlit/secrets.toml` are ignored; `.env.example` is a
blank-key safe template. No OpenAI key is used by Phase 9.

```powershell
git check-ignore .env .streamlit/secrets.toml
.\.venv\Scripts\python.exe -X utf8 scripts/check_groq.py
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

The connection check lists model IDs/account catalog status and elapsed time only;
it does not print the key or request headers and does not make a chat inference.
Listing does not guarantee every completion/tool request will be accepted. If
credentials are absent, live checks explicitly say NOT RUN and local analytics
remain available. The UI defaults to Offline Analytics. Select connected mode,
then explicitly enable Groq for the session before submitting a question. The
optional masked local override is Groq-only; the configured key need not be typed
into the UI. A model-access error offers available Groq candidates without
automatically substituting one. No model changes during a conversation.

## Model access and comparison

The local account authenticated and listed GPT-OSS 120B, Qwen 3.8 27B and GPT-OSS
20B. Only 120B and Qwen were inference-benchmarked; 20B listing is not a tested
recommendation. Initial and final capped evaluations are separate files. See
`reports/PHASE_9_EVALUATION.md` for actual task completion, routing, grounded
numbers, errors, token usage, median/p95 latency and estimated cost. No winner is
asserted from size/vendor claims. Default/configured GPT-OSS 120B is provisional;
the local `.env` is never rewritten based on benchmark results. The final small
sample is evidence for review, not a broad statistical accuracy comparison.

Both candidates use local sequential tool calls, with `parallel_tool_calls=False`.
No built-in browser/code execution or remote MCP is enabled. Structured-output
mode is not combined with tool calling. The adapter has a fixed Groq host and
does not honor a custom external base URL. SDK and transport diagnostic logging
is suppressed. 401/403, invalid request/model, 429, 5xx and network errors are
sanitized. Long retry-after values are surfaced rather than retried early.
Account limits can prevent a multi-step answer even with a valid key; switch to
offline explicitly, wait, or review your Groq account limits. No hidden fallback.

Optional settings and hard bounds: `GROQ_TIMEOUT_SECONDS` 5–40 (default25),
`GROQ_MAX_ROUNDS` 1–4 (4), `GROQ_MAX_TOOLS` 1–8 (8), `GROQ_OUTPUT_TOKENS`
128–2000 (1000), `GROQ_SESSION_CALLS` 1–60 (40), `GROQ_SESSION_TOKENS`
1000–250000 (160000). Changing a model requires restarting/reloading and resetting
the conversation. Reset does not reset usage counters. These demo limits are not
a multi-user billing or production authorization system.

## Local validation and deliberately bounded live evaluation

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_phase9.py
.\.venv\Scripts\python.exe -X utf8 scripts/validate_phase9.py
.\.venv\Scripts\python.exe -X utf8 scripts/run_phase9_checks.py --job regression
.\.venv\Scripts\python.exe -X utf8 scripts/run_phase9_checks.py --job smoke
.\.venv\Scripts\python.exe -X utf8 scripts/run_phase9_checks.py --job environment
```

The following consumes real Groq quota with the configured key. It uses fixed
public business templates and aggregate evidence, caps each model at 32 HTTP
attempts and records sanitized metadata; do not run repeatedly without a budget:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_phase9.py --live --final --interval 65
```

Original data and a read-only populated SQLite DB are needed for integration;
see README for build steps. Never run legacy saved-customer training to verify
Phase 9. `phase9_browser_server.py --port 8520 --no-key` creates an isolated
loopback review child with an empty key environment; it never edits the real
`.env`. Stop only the PID returned by that helper when finished.

## Primary references, checked 2026-10-24

- [Groq Python SDK](https://github.com/groq/groq-python)
- [Local tool support and sequential capabilities](https://console.groq.com/docs/tool-use/overview)
- [Active model catalog/pricing](https://console.groq.com/docs/models)
- [Groq GPT-OSS 120B](https://console.groq.com/docs/model/openai/gpt-oss-120b)
- [Groq Qwen 3.8 27B](https://console.groq.com/docs/model/qwen/qwen3.8-27b)

Documented uncached per-million-token prices used in the dated estimates: GPT-OSS
120B input $0.15/output $0.60; Qwen input $0.80/output $4.00. Estimates use returned
usage, exclude unknown/failed usage and discounts, and are not account invoices.
Catalog/pricing/capabilities can change; check account permissions before changing
models. No external inference provider is part of this setup.
