"""Fixed final-source evaluation. Default OFFLINE. Live needs explicit approval + budget.

Mock mode supplies scripted tool plans, NOT evidence of LLM routing/Arabic accuracy.
No prompts, environment values or provider bodies are recorded by this evaluator.
"""
import argparse,hashlib,json,statistics,sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from phase9_cases import cases as previous_cases
from evaluate_phase9 import oracle as legacy_oracle,SCOPE
from services.business_assistant import run,fresh_state,plan_offline
from services.assistant_config import Settings,load_settings
from services.groq_provider import GroqProvider,ProviderError
from services.assistant_context import resolve
from groq.types.chat import ChatCompletion

def oracle(report,resolved):
    # Phase 9's generic oracle did not pass an explicit warehouse selection.
    # Compare the same approved warehouse scope, not all warehouses combined.
    if report['meta']['tool'] in ('inventory6_warehouse','inventory6_transfers') and resolved.get('warehouse'):
        from services import inventory_tools
        meta=report['meta'];params={'warehouse':resolved['warehouse'],'limit':meta.get('limit',20)}
        expected=inventory_tools.answer_readonly(meta['tool'],resolved['scope'],params)['data']
        checks=[]
        for i,row in enumerate(report['data']):
            for key,value in row.items():
                if isinstance(value,(int,float)) and not isinstance(value,bool):
                    target=expected[i].get(key)
                    checks.append(isinstance(target,(int,float)) and abs(value-target)<1e-6)
        return dict(checks=len(checks),passed=sum(checks),failed=len(checks)-sum(checks))
    return legacy_oracle(report,resolved)

def source_hashes():
    return {str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
        for d in ('services','ui','db','scripts','tests') for p in sorted((ROOT/d).rglob('*.py')) if '__pycache__' not in p.parts} | {
        n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('app.py','analytics.py','assistant_engine.py','predictive.py')}

def cases():
    rows=previous_cases()
    extras=[('Retail branches sales',['location_ranking']),('POS sales',['company_overview']),
        ('Warehouse inventory WH01 2026-08',['inventory6_warehouse']),
        ('Recorded inventory from 2026-10-01 to 2026-10-18',['inventory6_stock']),
        ('sales and repeat customers',['customer8_summary','company_overview'])]
    for horizon in (1,3,6):
        extras.extend([(f'Forecast revenue next {horizon} months',['forecast7_values']),
            (f'توقع فئة Socks next {horizon} months',['forecast7_values'])])
    for i,(q,tools) in enumerate(extras):rows.append(dict(id=f'F{i+1:02}',scenario=f'F{i+1:02}',language='Arabic' if 'توقع' in q else 'English',question=q,required_tools=tools,expected_status='supported'))
    return rows

def authorize(config,approved_limit=None):
    """Fail closed, before constructing SDK or loading a credential."""
    amount=config.get('max_usd',0)
    if config.get('approved') is not True or not isinstance(amount,(int,float)) or not 0<amount<=100:
        raise ValueError('Explicit user approval and a positive bounded cost limit are required')
    if approved_limit is None or approved_limit!=amount or not config.get('approval_reference'):
        raise ValueError('CLI cost acknowledgement and local approval reference must match')
    for name,low,high in [('max_http_attempts',1,100),('wall_seconds',1,3600)]:
        value=config.get(name)
        if not isinstance(value,int) or not low<=value<=high:raise ValueError('Invalid evaluation limit')
    for name in ('input_usd_per_million','output_usd_per_million'):
        value=config.get(name)
        if not isinstance(value,(int,float)) or not 0<value<=1000:raise ValueError('Explicit approved current pricing is required')
    if config.get('model')!='openai/gpt-oss-120b':raise ValueError('Default model only; no silent fallback')
    return config

class Budget:
    def __init__(self,config):self.config=config;self.started=time.monotonic();self.attempts=0;self.reserved=0
    def reserve(self):
        c=self.config
        # Reserve a deliberately high 200k input tokens plus max 2k completion,
        # even for model-list/errors; retain reservations when usage is unknown.
        charge=(200000*c['input_usd_per_million']+2000*c['output_usd_per_million'])/1e6
        if self.attempts>=c['max_http_attempts'] or time.monotonic()-self.started>=c['wall_seconds'] or self.reserved+charge>c['max_usd']:
            raise ProviderError('request_budget')
        self.attempts+=1;self.reserved+=charge

class BudgetProvider(GroqProvider):
    def __init__(self,settings,budget):self.budget=budget;super().__init__(settings)
    def _request(self,fn):
        def reserved():self.budget.reserve();return fn()
        return super()._request(reserved)

class MockProvider:
    def __init__(self,operations):self.operations=operations;self.requests=0
    def models(self):return ['openai/gpt-oss-120b']
    def complete(self,messages,tools):
        self.requests+=1
        calls=[dict(id=f'mock_{i}',type='function',function=dict(name='cottonil_query',arguments=json.dumps(dict(operation=n,parameters=a)))) for i,(n,a) in enumerate(self.operations)]
        return ChatCompletion.model_validate(dict(id='mock',object='chat.completion',created=0,model='MOCK',
            choices=[dict(index=0,finish_reason='tool_calls' if calls else 'stop',message=dict(role='assistant',content=None,tool_calls=calls or None))]))

def evaluate(mode='offline',config=None):
    source=source_hashes();settings=load_settings() if mode=='live' else Settings()
    if mode=='live' and settings.model!=config['model']:raise ValueError('Configured model differs from approved model')
    budget=Budget(config) if mode=='live' else None
    states={};results=[];started=time.perf_counter();path=ROOT/f'reports/phase_10_{mode}_evaluation.json'
    for case in cases():
        state=states.setdefault(case['scenario'],fresh_state());provider=None
        if budget and (budget.attempts>=config['max_http_attempts'] or time.monotonic()-budget.started>=config['wall_seconds']):
            results.append(dict(id=case['id'],status='NOT RUN',reason='Evaluation budget/time exhausted'));continue
        if mode=='mock':
            try:operations=plan_offline(case['question'],resolve(case['question'],SCOPE,state))
            except ValueError:operations=[]
            provider=MockProvider(operations)
        elif mode=='live':provider=BudgetProvider(settings,budget)
        try:result=run(case['question'],SCOPE,state,connected=mode!='offline',settings=settings,provider=provider)
        finally:
            if mode=='live':provider.close()
        numeric=[oracle(r,result['resolved']) for r in result['reports']] if result.get('resolved') else []
        tools={r['meta']['tool'] for r in result['reports']}
        equivalents={'profit5_pair':{'profit5_pair','two_location_comparison'},'two_location_comparison':{'profit5_pair','two_location_comparison'}}
        routing=all(bool(equivalents.get(n,{n})&tools) for n in case['required_tools'])
        expected='clarify' if mode!='offline' and case['expected_status']=='unsupported' else case['expected_status']
        results.append(dict(id=case['id'],scenario=case['scenario'],language=case['language'],status=result['status'],
            answer_state=result['answer_state'],semantic_complete=result['semantic_complete'],error=result.get('code'),
            requested_domains=result.get('requested_domains',[]),returned_domains=result.get('returned_domains',[]),
            required_tools=case['required_tools'],actual_tools=sorted(tools),routing_passed=routing,
            expected_status=expected,outcome_passed=result['status']==expected,
            numeric_checks=sum(n['checks'] for n in numeric),numeric_failures=sum(n['failed'] for n in numeric),
            input_tokens=result.get('input_tokens',0),output_tokens=result.get('output_tokens',0),
            http_attempts=getattr(provider,'requests',0) if mode=='live' else 0,
            rate_limit_errors=getattr(provider,'rate_limit_errors',0) if mode=='live' else 0,
            provider_detail=result.get('provider_detail'),
            elapsed_seconds=result.get('elapsed_seconds',0),coverage_reasons=result.get('coverage_reasons',[]),
            evidence_scopes=[{k:r['meta'][k] for k in ('tool','period','snapshot','target','unit','horizon','origin','classification','branch_id','branch_a','branch_b') if k in r['meta']} for r in result['reports']]))
        path.write_text(json.dumps(dict(status='RUNNING',mode=mode,results=results),indent=2,ensure_ascii=False),encoding='utf-8')
        print(case['id'],mode,result['answer_state'],flush=True)
        if budget and result.get('code')=='request_budget':
            budget.attempts=config['max_http_attempts']
    executed=[r for r in results if r['status']!='NOT RUN'];n=len(executed);latencies=sorted(r['elapsed_seconds'] for r in executed)
    summary=dict(mode=mode,started_source_sha256=source,source_changed=source_hashes()!=source,
        finished_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.perf_counter()-started,
        case_count=len(results),executed=n,not_run=len(results)-n,
        routing_passed=sum(r['routing_passed'] for r in executed),outcome_passed=sum(r['outcome_passed'] for r in executed),
        semantic_completeness_pct=100*sum(r['semantic_complete'] for r in executed)/n if n else None,
        partial_pct=100*sum(r['answer_state']=='partial' for r in executed)/n if n else None,
        numeric_checks=sum(r['numeric_checks'] for r in executed),numeric_failures=sum(r['numeric_failures'] for r in executed),
        provider_errors=sum(r.get('error') not in (None,'unavailable') and r['status']=='error' for r in executed),
        rate_limits=sum(r.get('rate_limit_errors',0) for r in executed),
        median_seconds=statistics.median(latencies) if n else None,p95_seconds=latencies[min(n-1,int(.95*n))] if n else None,
        input_tokens=sum(r['input_tokens'] for r in executed),output_tokens=sum(r['output_tokens'] for r in executed),
        http_attempts=budget.attempts if budget else 0,reserved_cost_usd=budget.reserved if budget else 0,
        live_acceptance='EXECUTED, limited fixed sample only' if mode=='live' else 'NOT RUN: no authorized dollar limit; offline/mock are not live model evidence',
        methodology='Scripted mock plans are not independent routing or language evaluation. Numerical oracle reuses approved underlying services (adapter consistency, not independent accounting audit). Semantic completeness is conservative contract coverage, not human usefulness scoring. Reserved cost is a conservative estimate, not a billing guarantee.',results=results)
    if budget:summary['estimated_usage_cost_usd']=(summary['input_tokens']*config['input_usd_per_million']+summary['output_tokens']*config['output_usd_per_million'])/1e6
    path.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    return summary

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['offline','mock','live'],default='offline');p.add_argument('--budget');p.add_argument('--approved-cost-limit',type=float);a=p.parse_args()
    config=None
    if a.mode=='live':
        if not a.budget:p.error('No live requests without explicit approved local budget')
        config=authorize(json.loads(Path(a.budget).read_text(encoding='utf-8')),a.approved_cost_limit)
        fingerprint=hashlib.sha256(json.dumps(source_hashes(),sort_keys=True).encode()).hexdigest()
        if config.get('source_fingerprint')!=fingerprint:p.error('Budget approval must pin this exact final source fingerprint')
    result=evaluate(a.mode,config)
    return int(result['source_changed'] or result['numeric_failures']>0 or result['outcome_passed']<result['executed'] or result['routing_passed']<result['executed'])
if __name__=='__main__':raise SystemExit(main())
