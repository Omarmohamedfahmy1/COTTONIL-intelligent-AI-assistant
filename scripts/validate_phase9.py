"""Reusable aggregate-only Phase 9 deterministic/live evaluation (no secret dumps)."""
import argparse,json,sys,time,hashlib,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.business_assistant import run,fresh_state
from services.assistant_config import load_settings
from services import assistant_registry as registry
from services.assistant_context import resolve,guard
SCOPE=dict(start='2025-10-01',end='2026-09-30',branch=None,location_type=None,category=None)
def validate():
    checks={}
    def check(name,condition):checks[name]=dict(passed=bool(condition))
    baseline=json.loads((ROOT/'reports/phase_9_start_preservation.json').read_text())
    permitted={'ui/assistant.py','ui/i18n.py'};changed=[]
    for name,digest in baseline['source'].items():
        same=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
        normalized=name.replace('\\','/')
        if not same:changed.append(normalized)
        check('preserve:'+normalized,same or normalized in permitted)
    private=[]
    for name,digest in baseline['private'].items():
        path=Path(name)
        with path.open('rb') as f:same=hashlib.file_digest(f,'sha256').hexdigest()==digest
        private.append(same);check('private_artifact:'+path.name,same)
    for path in ('.env','.streamlit/secrets.toml'):
        result=subprocess.run(['git','check-ignore',path],cwd=ROOT,capture_output=True)
        check('git_ignored:'+path,result.returncode==0)
    settings=load_settings();secret=settings.api_key
    public=[p for folder in ('services','ui','scripts','tests','docs','reports') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.md','.json','.txt')]
    hits=[str(p.relative_to(ROOT)) for p in public if secret and secret in p.read_text(encoding='utf-8-sig',errors='replace')]
    check('real_key_not_in_public_files',not hits)
    for operation in registry.GROUPS:
        check('tool_whitelisted:'+operation,operation in registry.GROUPS)
        try:registry.validate(operation,dict(limit=21));rejected=False
        except ValueError:rejected=True
        check('bounded_rows:'+operation,rejected)
    dataset=json.loads((ROOT/'docs/PHASE_9_BENCHMARK.json').read_text())
    benchmark=json.loads((ROOT/'reports/phase_9_offline_benchmark.json').read_text())
    check('benchmark_at_least_50',len(dataset)>=50)
    check('multiturn_at_least_12',len({r['scenario'] for r in dataset if r['id'].startswith('M')})>=12)
    check('adversarial_at_least_10',sum(r['id'].startswith('A') for r in dataset)>=10)
    for row in benchmark['results']:
        check('question:'+row['id'],row['task_passed'])
        check('numeric:'+row['id'],row['numeric_failures']==0)
    original_tests=[(name,digest) for name,digest in baseline['source'].items() if name.replace('\\','/').startswith('tests/')]
    check('all_original_164_tests_unmodified',bool(original_tests) and all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in original_tests))
    check('only_permitted_original_ui_edits',set(changed)<=permitted)
    check('old_openai_connected_not_imported_by_ui','from assistant_engine import offline_reply,run_llm' not in (ROOT/'ui/assistant.py').read_text())
    return dict(passed=all(c['passed'] for c in checks.values()),checks=checks,changed_original_python=changed,
        private_artifacts_unchanged=all(private),public_secret_scan_files=len(public),secret_findings=hits,
        limitations='No formal differential privacy, production authorization, live multi-user load, native-browser matrix or external security audit. Legacy OpenAI function retained frozen for historical byte compatibility, unreachable from Phase 9 UI.',
        provider_policy='Only official Groq SDK in active connected path; fixed HTTPS Groq origin and redirect rejection.',
        benchmark=dict(templates=benchmark['question_templates'],task_passed=benchmark['task_passed'],numeric_checks=benchmark['numeric_checks'],numeric_failures=benchmark['numeric_failures']))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live-probe',action='store_true');p.add_argument('--report',type=Path,default=ROOT/'reports/phase_9_validation.json');a=p.parse_args()
    if a.live_probe:
        result=run('قارن مبيعات BR001 وBR002 آخر 3 شهور',SCOPE,fresh_state(),connected=True,settings=load_settings())
        summary={k:v for k,v in result.items() if k!='reports'};summary['tools']=[r['meta']['tool'] for r in result['reports']]
        summary['evidence']=[dict(meta=r['meta'],data=r['data']) for r in result['reports']]
        (ROOT/'reports/phase_9_probe_final.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({k:v for k,v in summary.items() if k!='evidence'},indent=2,ensure_ascii=False))
        raise SystemExit(0 if result['status']=='supported' else 1)
    else:
        result=validate();a.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('Phase 9',sum(c['passed'] for c in result['checks'].values()),'/',len(result['checks']),'passed');raise SystemExit(0 if result['passed'] else 1)
