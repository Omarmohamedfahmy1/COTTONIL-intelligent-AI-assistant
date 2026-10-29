# Local deployment and operator guide — Phase 10

This is an HVIA Task 3 historical-data demonstration. It has no authentication,
role authorization, production monitoring or formal differential privacy. Keep it
on loopback; do not expose it as an enterprise service. Independent final review
and live Groq acceptance remain separate gates.

## Reproduce on Windows

Use CPython 3.12 and PowerShell in the extracted project root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
$datasetZip = 'C:\private\COTTONIL_Data.zip'
.\.venv\Scripts\python.exe scripts/build_db.py --zip $datasetZip
.\.venv\Scripts\python.exe scripts/prepare_phase1_db.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false
```

The dataset is intentionally absent from the review ZIP. Obtain the original
authorized ZIP separately. Existing databases are protected by the importer;
do not use `--force` against approved local data. No dataset, saved prediction or
customer model rebuild is needed for a working existing installation. Explicit
interpreter paths avoid PowerShell activation-policy changes. `START_WINDOWS.bat`
is the existing alternative launcher; the commands above give explicit control.

## Offline demonstration and Groq

Select **Offline analytics / تحليلات محلية**. No API key is required. For a
guaranteed zero-key browser review without modifying `.env`:

```powershell
.\.venv\Scripts\python.exe scripts/phase9_browser_server.py --port 8530 --no-key
```

This starts an isolated child on loopback and prints its PID/port. Stop only that
owned process when done. The ordinary app loads `.env` with python-dotenv,
`override=False, interpolate=False`; an existing process environment takes
precedence. Set `GROQ_API_KEY` privately and `GROQ_MODEL=openai/gpt-oss-120b`.
Never paste a key into a support ticket, screenshot or terminal command.
`.env`, `.env.*` except `.env.example`, and `.streamlit/secrets.toml` are ignored.
Do not replace an existing `.env`. `.env.example` contains blank credentials.

Connected mode requires an explicit UI enable checkbox or ephemeral password
field. This is session consent, not a dollar budget. Groq is the only active
provider; legacy OpenAI code exists only for historical compatibility and is not
called by the active interface. The SDK uses fixed HTTPS `api.groq.com`, normal
certificate checks, no redirects and no automatic model fallback.

## Answer states and recovery

Complete means recognized task-contract coverage with approved local evidence,
not a guarantee that an unrestricted natural-language question was understood.
Partial preserves verified figures but warns about missing domains, truncation,
unconfirmed open-ended intent or a fixed customer privacy scope. Unavailable
does not imply zero real business activity. Provider error, clarification,
restricted request and usage-budget exhaustion have separate bilingual labels.

Known tasks stop once all required tools return, avoiding an unused final model
paragraph. Model-authored business prose is never displayed. The evidence tables
retain actual dates, units, snapshot, source and limitations.

Retry appears only for a pending recoverable connected turn. It reuses local
tool results and preserves matching tool-call IDs, period and usage counters.
429 respects Retry-After, including HTTP dates. Retry is bounded by the original
four rounds/eight tools/nine physical-request allowance, two manual retries,
five-minute validity and active-turn time. Changes to question, filters, model
or DB identity invalidate retry. Clear removes conversation and pending work,
but retains session usage counts. Stop acts between requests; it cannot cancel
an HTTP request already in progress. An explicit new question starts a new turn.

401/403: check the local key/account without displaying it. 404/model access:
verify the configured model privately; the app does not switch automatically.
400: inspect sanitized code and retained evidence; use bounded retry, then
offline analytics. 429: wait for the reported delay; do not repeatedly clear the
conversation to evade limits. Network/TLS: fix trust/network configuration;
never disable certificate verification. Large tables scroll inside their frame.

## Validation without paid requests

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/run_phase10_checks.py --job environment
.\.venv\Scripts\python.exe -X utf8 scripts/run_phase10_checks.py --job full
.\.venv\Scripts\python.exe -X utf8 scripts/run_phase10_checks.py --job regression
.\.venv\Scripts\python.exe -X utf8 scripts/run_phase10_checks.py --job evaluation
.\.venv\Scripts\python.exe -X utf8 scripts/run_phase10_checks.py --job smoke
.\.venv\Scripts\python.exe -X utf8 scripts/profile_phase10.py
```

The regression runner uses this installation's original dataset location; on
another workstation run `validate_phase1.py --zip $datasetZip --report <new path>`
and the other validator commands recorded in the execution JSON files. Historical
Phase 0–9 reports are preserved. AppTest is not browser visual acceptance.
Approved historical forecasting/customer validators may refit existing research
in memory; they do not retrain or overwrite saved customer artifacts. Profiling
is one local cold-ish/warm sample with the OS cache left intact, not an SLA.

## Future explicitly approved live evaluation

**No Phase 10 paid test budget was authorized or used.** Do not run the following
until the human approves an exact dollar limit and current pricing. Keep a
non-secret budget file in ignored `outputs/`, with `approved:true`,
`approval_reference`, positive `max_usd` (maximum 100), `max_http_attempts` (1–100),
`wall_seconds` (1–3600), `model:"openai/gpt-oss-120b"`,
`input_usd_per_million`, `output_usd_per_million`, and `source_fingerprint`.
Approval must apply to the exact final Python source fingerprint:

```powershell
.\.venv\Scripts\python.exe -c "import hashlib,json; from scripts.evaluate_phase10 import source_hashes; print(hashlib.sha256(json.dumps(source_hashes(),sort_keys=True).encode()).hexdigest())"
# Only after explicit user approval; replace the limit with that approved amount:
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_phase10.py --mode live --budget outputs/approved-budget.json --approved-cost-limit <approved-dollar-limit>
```

The evaluator reserves a deliberately high 200k input/2k output token estimate
for every physical attempt, including failed/unknown-usage requests and model
listing. It fails closed before requests that would exceed the reservation,
attempt or wall-clock limits; an in-flight request may finish after the deadline.
This is conservative application accounting, not a provider billing guarantee.
Choose up-to-date approved prices and an account-side spend cap where available.
Unrun cases remain NOT RUN. Model use/latency/cost metadata never establishes
broad reliability. Mock mode uses scripted plans, not actual language inference.

## Business and privacy limits

Revenue is ex-tax before refunds; gross profit is not net profit. Refund financial
basis and operating costs are unavailable. Stock is monthly category/location,
not SKU; closing balances must not be summed across months. Executive legacy and
Phase 6 completed-snapshot policies differ. Replenishment/cover are heuristics.
Forecast origin follows historical coverage; bands are uncalibrated. Customer
churn and revenue research remain unreliable and unsuitable for individual
decisions. The assistant uses fixed company-wide customer windows, allowlisted
aggregate columns and small-cell suppression. This reduces disclosure risk but
does not prevent every cross-query inference or provide role-based access/DP.
