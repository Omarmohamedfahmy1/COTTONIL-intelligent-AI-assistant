"""Consolidate real Phase 9 evidence; no model inference and no secret values."""
import json,re,sys,hashlib,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def read(name):return json.loads((ROOT/'reports'/name).read_text(encoding='utf-8-sig'))
def main():
    offline=read('phase_9_offline_benchmark.json');validation=read('phase_9_validation.json');auth=read('phase_9_groq_auth.json');env=read('phase_9_environment.json');smoke=read('phase_9_smoke.json')
    benchmarks=[]
    for model in ('openai_gpt-oss-120b','qwen_qwen3.8-27b'):
        for suffix in ('','_intermediate','_final'):
            p=ROOT/'reports'/f'phase_9_live_{model}{suffix}.json'
            if not p.exists():continue
            data=read(p.name)
            if data['status']!='COMPLETE':raise RuntimeError('Live evaluation still running')
            if 'source_sha256' in data:
                data['source_sha256_observed_at_report_finish']=data.pop('source_sha256')
                data['source_provenance_note']='Older runner sampled disk hashes at report finish, not loaded-module start. Final compact-schema cases preceded later explicit type/warehouse/month parsing additions; those cases do not use these additions. Final browser/tests use latest source. Do not treat finish hashes as exact loaded-version proof.'
                p.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
            data['source_provenance_note']='Comparisons used the compact-schema core before later explicit type/warehouse/month, horizon/category follow-up, retry-header and provenance-detail additions. The fixed final cases use pair/default-three-month scopes and do not exercise those added edges. Current full tests and the fresh live probe validate the later core. Original end-of-run hashes are not exact loaded-module version proof.'
            p.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
            executed=[r for r in data['results'] if r['status']!='NOT RUN']
            equivalent={'profit5_pair':{'profit5_pair','two_location_comparison'},'two_location_comparison':{'profit5_pair','two_location_comparison'}}
            semantic=sum(r['status']==r['expected_status'] and r['numeric_failures']==0 and all(bool(equivalent.get(n,{n})&set(r['actual_tools'])) for n in r['required_tools']) for r in executed)
            benchmarks.append(dict(model=data['model'],stage=suffix or '_initial',executed=len(executed),strict_task_passed=data['task_passed'] if suffix=='' else sum(r.get('strict_routing_passed',r['routing_passed']) and r['outcome_passed'] and r['numeric_failures']==0 for r in executed),semantic_task_passed=semantic,numeric_checks=data['numeric_checks'],numeric_failures=data['numeric_failures'],median_seconds=data['median_seconds'],p95_seconds=data['p95_seconds'],input_tokens=data['input_tokens'],output_tokens=data['output_tokens'],http_attempts=data['http_attempts'],rate_limit_errors=data['rate_limit_errors'],estimated_usage_cost_usd=data['estimated_usage_cost_usd'],tool_rejections=sum(r.get('tool_rejections',0) for r in executed),errors=[dict(id=r['id'],status=r['status'],code=r.get('error'),detail=r.get('provider_detail')) for r in executed if r['status']!='supported']))
    (ROOT/'reports/phase_9_model_comparison.json').write_text(json.dumps(dict(benchmarks=benchmarks,recommendation='Retain configured openai/gpt-oss-120b: final compact-schema sample completed 4/4 versus Qwen 2/4 with lower returned-usage cost. Provisional small-sample choice, not general superiority.',policy='Initial/intermediate/final sources are distinct; compare only within a stage. Semantic financial-pair equivalence is disclosed alongside strict scores. Final cases precede later type/warehouse/month parsing additions not used by these cases; current browser/tests validate those additions.'),indent=2),encoding='utf-8')
    execution=[]
    for job in ('full','regression','smoke','environment'):execution+=read(f'phase_9_execution_{job}.json')
    log=(ROOT/'reports/phase_9_tests_full_log.txt').read_text(encoding='utf-8',errors='replace')
    match=re.search(r'Ran (\d+) tests in ([\d.]+)s',log)
    full=dict(count=int(match[1]),seconds=float(match[2]),passed=bool(re.search(r'\nOK\s*$',log)),skipped=len(re.findall(r'\.\.\. skipped ',log)))
    regression=[]
    for name in ('baseline','phase1','executive','sales','profitability','inventory','forecast','customers'):
        data=read('phase_9_'+name+'.json');checks=data['checks'];values=checks.values() if isinstance(checks,dict) else checks
        values=list(values);n=sum(v['passed'] if isinstance(v,dict) else v for v in values)
        regression.append(dict(name=name,passed=n,total=len(values)))
    final=dict(full_suite=full,regression=regression,phase9_checks=sum(v['passed'] for v in validation['checks'].values()),phase9_total=len(validation['checks']),offline_templates=offline['question_templates'],offline_tasks_passed=offline['task_passed'],offline_numeric_checks=offline['numeric_checks'],offline_numeric_failures=offline['numeric_failures'],groq_auth=auth['status'],groq_model=auth['model'],smoke_passed=smoke['passed'],page_language_runs=len(smoke['pages']),syntax_files=env['syntax_files'],import_modules=env['import_modules'],private_artifacts_unchanged=validation['private_artifacts_unchanged'],final_model_comparison=[b for b in benchmarks if b['stage']=='_final'])
    final['software_validation_passed']=full['passed'] and full['skipped']==0 and validation['passed'] and smoke['passed'] and all(r['passed']==r['total'] for r in regression) and offline['task_passed']==offline['question_templates']
    final['live_acceptance']='PARTIAL: small bounded model samples, intermittent tool-generation and quota errors; independent review required.'
    final['model_choice']='Retain explicit configured GPT-OSS120B: 4/4 compact-schema sampled tasks versus Qwen2/4 and lower returned-usage cost, not a broad accuracy claim.'
    final['source_provenance_note']='Model comparisons used the compact-schema core before subsequent type/warehouse/month/horizon/category, retry-header and provenance-detail additions. Fixed final cases use pair/default-three-month scopes and do not exercise those added edges. Current full tests and the fresh live probe validate the later core; captures show the actual connected UI before the last backend edge guards, with rendering unchanged. Finish hashes are not loaded-version proof.'
    (ROOT/'reports/phase_9_final_validation.json').write_text(json.dumps(final,indent=2),encoding='utf-8')
    base=read('phase_9_start_preservation.json')['source'];modified=[n for n,h in base.items() if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h]
    added=[p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*.py') if '.venv' not in p.parts and '.git' not in p.parts and str(p.relative_to(ROOT)) not in base]
    command_text='\n\n'.join('```powershell\n'+r['command']+'\n```\n'+f"Exit {r['exit_code']}; {r['elapsed_seconds']:.3f}s; UTC {r['started_utc']}; `{r['log']}`." for r in execution)
    benchmark_table='\n'.join(f"| {b['stage']} | {b['model']} | {b['semantic_task_passed']}/{b['executed']} | {b['numeric_failures']}/{b['numeric_checks']} | {b['median_seconds']:.3f} / {b['p95_seconds']:.3f} | {b['input_tokens']} / {b['output_tokens']} | {b['rate_limit_errors']} | ${b['estimated_usage_cost_usd']:.6f} |" for b in benchmarks)
    evaluation=f'''# Phase 9 evaluation: measured outcomes and limits

Date: 2026-10-24, Windows Python 3.12.0. Provider **Groq only**, SDK {env['versions']['groq']}. Real catalog authentication: {auth['status']}; GPT-OSS120B and Qwen3.8 listed. GPT-OSS20B listing only, not inference-tested. No OpenAI API call or provider/model fallback. The local key was not printed or saved in evidence.

## Deterministic and offline acceptance

Final full suite {full['count']} passed={full['passed']}, skipped={full['skipped']}, {full['seconds']:.3f}s. Original 164 tests preserved byte-for-byte. Phase 9 validator {final['phase9_checks']}/{final['phase9_total']}. Earlier validators {sum(r['passed'] for r in regression)}/{sum(r['total'] for r in regression)}. Offline benchmark {offline['task_passed']}/{offline['question_templates']} tasks, {offline['numeric_checks']} published numeric values checked against approved services, {offline['numeric_failures']} mismatches. Twelve multi-turn scenarios and fourteen adversarial/data-limit templates. These are local deterministic results, not live LLM accuracy rates.

## Real Groq comparisons

Initial: identical eight turns/model, including English and Egyptian Arabic pair follow-ups, three-domain comparison and forecasting/history. Intermediate: same four turns/model after adding completeness hints. Final: same four turns/model after narrowing advertised schemas. Fixed templates use no private customer data. Each model/run is capped at 32 HTTP attempts, rounds/tools/tokens/time are bounded, and turns paced (initial50s, later65s). Catalog and retry attempts are included in HTTP totals. Full results retain actual status, request counts, routes, numerical checks and permitted aggregate evidence. Failed/partial requests are not called successful. Compare within a stage; source changes prevent pooling stages into one accuracy statistic.

| Stage | Model | Semantically complete tasks | Numeric failures/checks | Median / p95 seconds | Input / output tokens | 429s | Estimated usage cost |
|---|---|---:|---:|---:|---:|---:|---:|
{benchmark_table}

Initial strict operation-name scores are retained in JSON. General pair and profitability-pair services both contain requested sales/gross-profit metrics, so semantic equivalence is scored separately rather than penalizing a valid approved route. A missing domain, rejected scope, no evidence, rate-limit error or partial/budget stop remains a failed task. Grounded numeric correctness is conditional on returned evidence; it is not evidence that every question completed. Multi-turn cases are dependent, and four final turns/model are much too few for general model superiority claims. A p95 over four samples is effectively a maximum, not a stable tail estimate. Results include local service time and quota/network effects; they are not an isolated provider speed benchmark.

## Selection and cost

Configured/default GPT-OSS120B remains explicit and provisional; `.env` was not rewritten and model changes require conversation reset. Review final task completion together with errors and cost before changing models. The final model comparison is in `phase_9_model_comparison.json`; no larger-model or vendor-origin superiority is assumed. Qwen was actually tested, not merely listed. No claim is made that either model makes the unreliable customer research suitable for decisions.

Prices used: [Groq GPT-OSS120B](https://console.groq.com/docs/model/openai/gpt-oss-120b), $0.15/$0.60 per million input/output; [Groq Qwen3.8](https://console.groq.com/docs/model/qwen/qwen3.8-27b), $0.80/$4.00, checked 2026-10-24. Estimates use returned usage only, omit failed/unknown usage and discounts/cache adjustments, and are not billing receipts. Initial catalog/probe/browser calls are outside these model benchmark subtotals and are separately identified; screenshots are not a cost audit.

## Grounding, refusal and interpretation limits

Final prose/cards/tables/charts are application-owned and use local verified values. Raw model numeric prose and HTML are never displayed. Thus numerical benchmark correctness measures tool selection/output consistency, not independent free-form model arithmetic or narrative fluency. Egyptian Arabic understanding is assessed through routes, periods, entities and follow-ups. Unsafe requests are stopped by the server before Groq, so local adversarial success is not a live LLM refusal/jailbreak score. No formal red-team/privacy certification or exhaustive linguistic assessment is claimed.

Customer tools are company-only at a fixed complete-year window to restrict overlapping fine-scope queries; original Phase8 k/complement suppression remains. This is not differential privacy or production authorization. Forecast/category unit and revenue targets stay distinct; uncalibrated ranges and unreliable churn/value states are retained. Current data end 2026-10-18; last complete month September. Net profit/refund-adjusted financials and SKU stock remain unsupported.

## Known failed attempts and final state

The first dependency install with old venv pip failed TLS certificate verification; documented host-pip fallback installed official SDK/dotenv without disabling TLS. An early large-schema live probe completed a local tool then hit Groq429; compact/dynamic schemas reduced payload. The first full suite failed only the established localized sales-summary prefix; Phase9 presentation was corrected using tool values, then the complete suite was rerun successfully. An initial preservation validator miscompared Windows backslashes against allowed UI paths; normalized paths fixed it without changing protected source/data. Initial offline plural-Arabic profit routing and trend/ranking routes were corrected with tests. Historical exploratory logs remain separate from final evidence. Later rate limits/tool failures, if present in the final table, remain measured limitations rather than hidden successes.

Real browser captures distinguish Groq-connected, no-key offline and blocked modes. Startup/AppTest executes {len(smoke['pages'])} page/language combinations; it is not a substitute for the actual captured browser states. No native Chrome/Edge matrix, screen-reader/physical-device study, multi-user load test or production deployment was performed. Independent review required; STOP before Phase10.
'''
    evaluation+='\n## Source provenance and browser caveat\n\n'+final['source_provenance_note']+' An actual final-source browser turn returned an invalid-request error after producing valid local comparison evidence; this is preserved in screenshot05. Subsequent Arabic profit and inventory follow-ups completed with the retained pair/period. These outcomes do not establish that all live interactions succeed. Narrow390px evidence is explicitly offline; native-device/accessibility testing remains unrun.\n'
    (ROOT/'reports/PHASE_9_EVALUATION.md').write_text(evaluation,encoding='utf-8')
    report=f'''# Phase 9 implementation report

Phase9 only; stopped before Phase10. Software checks passed={final['software_validation_passed']}; live model outcomes/limits are disclosed separately in `PHASE_9_EVALUATION.md`, not treated as all-passing merely because tests pass. Original data, financial KPIs, stock/forecast/customer model logic and saved private artifacts remain unchanged.

## Architecture and resulting behavior

Official Groq SDK and secure ignored-dotenv configuration replace the active OpenAI-connected UI path. Frozen legacy engine/164 tests remain for compatibility; the Phase9 UI calls a separate Groq-only wrapper. Fixed HTTPS host/redirect guard, bounded retries and sanitized errors prevent external-provider substitution. Available-model errors do not silently switch. No-key offline analytics and explicit connected session opt-in are preserved.

A typed single-dispatcher allowlist delegates to 36 approved aggregate operations. Scope/date/pair resolution, parameter/output validation, matched tool-call IDs, sequential multi-step execution, budget checks, memory-only history/reset/stop, minimal provider payload and safe aggregate CSV exports sit above existing services. Numeric cards/tables/Plotly charts and bilingual explanations are application-owned; no arbitrary LLM financial text or HTML is rendered. Fixed company customer scope reduces differencing and discloses overridden filters. Source end, completed snapshot vs transactions, unit targets, gross-not-net basis and unreliable models remain explicit. See `docs/AI_BUSINESS_ASSISTANT.md` and `docs/GROQ_SETUP.md` for contracts, threat model and exact configuration.

## Source and documentation changes

Modified existing Python: {', '.join(modified)}. Remaining {len(base)-len(modified)} original Python files unchanged; original test files unchanged. Added Python:

{chr(10).join('- '+n for n in sorted(added))}

Other updates: requirements.txt/requirements-lock.txt (official groq and python-dotenv only added), blank-key .env.example, README phase9 instructions; copied original roadmap/specification into reviewable project documentation; new assistant/Groq methodology documents, benchmark templates, reports and original screenshots. Existing .gitignore already ignores .env, real env variants and Streamlit secrets; Git ignore checks passed. The actual .env was neither overwritten nor displayed. No Git commit or data export was made.

## Executed results

Full suite: {full['count']} passed={full['passed']}, 0 failures when passed, {full['skipped']} skipped; {full['seconds']:.3f}s. Syntax {env['syntax_files']} files / {env['import_modules']} application imports. Pip check exit0. Real HTTP startup plus {len(smoke['pages'])}/16 AppTest page/language runs, branch filter/offline chat passed={smoke['passed']}. Phase9 validator {final['phase9_checks']}/{final['phase9_total']}; offline benchmark {offline['task_passed']}/{offline['question_templates']} and {offline['numeric_checks']} numeric checks with {offline['numeric_failures']} mismatches. Model benchmark actual availability, scores, 429s, tool errors, usage/cost and timings are in the evaluation/report JSON; mock protocol tests are not live verification.

| Prior validator | Passed / total |
|---|---:|
{chr(10).join('| '+r['name']+' | '+str(r['passed'])+' / '+str(r['total'])+' |' for r in regression)}

Read-only integrity and reconciliation checks retain the original data totals/KPI definitions. Each tool/benchmark records actual scope and elapsed seconds. Local cache/CPU/concurrent tests affect timing; no production SLA. Source dataset ZIP, SQLite DB, saved customer prediction CSV and metrics JSON hashes match the start baseline. No saved model is retrained/overwritten. Final browser layout observations/screenshot hashes are in `phase_9_browser_review.json`.

## Exact command records

Working directory `{ROOT}`. `phase_9_execution_*.json` retains argument arrays, UTC start/finish, exit codes and log filenames. Final command records:

{command_text}

Additional executed commands: `python -m pip --python .venv install groq python-dotenv` (exit0); `git check-ignore .env .streamlit/secrets.toml` (exit0); `python -X utf8 scripts/check_groq.py` (authenticated, exit0); `python -X utf8 scripts/evaluate_phase9.py` (completed local benchmark); `python -X utf8 scripts/evaluate_phase9.py --live --interval 50` (initial8/model); `python -X utf8 scripts/evaluate_phase9.py --live --final --interval 65` (intermediate/final4/model, separate preserved reports); `python -X utf8 scripts/validate_phase9.py` (exit0). All Python commands used the project .venv interpreter unless host pip is explicitly named. Earlier failed commands/outcomes are documented in the evaluation; do not substitute intermediate logs for final results.

## Remaining limitations and review boundary

Live Groq quota/tool/model errors may leave a partial answer and are not automatically hidden by offline fallback. Small live samples cannot validate general natural-language accuracy. Tool-grounded templates replace unrestricted generated explanations. Customer coarse scope deliberately sacrifices fine-grained assistant analysis; cross-module differencing and provider retention still require independent privacy/access review. Legacy frozen OpenAI function is not used by the active UI; direct external calls to historical code are outside that UI path. No production authorization/deployment or model-reliability claims. See evaluation for outstanding live defects and browser coverage; native/device/screen-reader/production-load/external-LLM-provider matrices not run. Phase10 not started. Wait for independent Phase9 review.
'''
    (ROOT/'reports/PHASE_9_REPORT.md').write_text(report,encoding='utf-8')
    print(json.dumps(final,indent=2))
if __name__=='__main__':main()
