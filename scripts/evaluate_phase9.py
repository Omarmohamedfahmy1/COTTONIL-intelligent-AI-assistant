"""Capped metadata-only benchmark; private prompts/records/key never logged.

Fixed public templates are in phase9_cases.py. Aggregate evidence only.
"""
import argparse,json,sys,time,statistics,hashlib
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from phase9_cases import cases
from services.business_assistant import run,fresh_state
from services.assistant_config import load_settings,Settings
from services.groq_provider import GroqProvider,ProviderError
from services import assistant_registry as ar,metrics as kpi,executive

SCOPE=dict(start='2025-10-01',end='2026-09-30',branch=None,location_type=None,category=None)
PRICES={'openai/gpt-oss-120b':(.15,.60),'qwen/qwen3.8-27b':(.80,4.00)}
def oracle(report,resolved):
    name=report['meta']['tool'];meta=report['meta'];scope=dict(resolved['scope'])
    if name.startswith('customer8_'):
        a,b=meta['period'].split(' to ')
        scope=dict(start=a,end=b,branch=None,location_type=None,category=None)
        original=ar.customers.answer_readonly(name,scope)
    elif name=='company_overview':original=executive.assistant_summary(scope)
    elif name=='sales_seasonality':original=dict(data=ar.sales.records(kpi.seasonality(**scope)))
    elif name=='executive_comparison':original=dict(data=ar.sales.records(executive.summary(**scope)['comparison']))
    elif name=='executive_stock':original=executive.assistant_summary(scope)
    elif name=='category_risk_sales':
        approved=executive.dashboard(**scope)['category_changes'];risk=ar.stock.answer_readonly('inventory6_risk',scope,dict(limit=20))
        import pandas as pd
        original=dict(data=ar.sales.records(approved.merge(pd.DataFrame(risk['data']),on='category',how='left',validate='one_to_one',suffixes=('','_inventory'))))
        if resolved.get('categories'):original['data']=[r for r in original['data'] if r['category'] in resolved['categories']]
    else:
        params={k:meta[k] for k in ('metric','grain','horizon','status','limit') if k in meta}
        if name.endswith('_pair') or name=='two_location_comparison':params.update(branch_a=resolved['pair'][0],branch_b=resolved['pair'][1])
        if name=='forecast7_categories':params['categories']=resolved.get('categories',[])
        group=ar.GROUPS[name];original={'sales':ar.sales,'profit':ar.profit,'stock':ar.stock,'forecast':ar.forecast}[group].answer_readonly(name,scope,params)
    checks=[]
    # Compare every published numerical value to its approved raw service row.
    for i,row in enumerate(report['data']):
        for key,value in row.items():
            if isinstance(value,(int,float)) and not isinstance(value,bool):
                expected=original['data'][i].get(key)
                checks.append(isinstance(expected,(int,float)) and abs(value-expected)<1e-6)
    return dict(checks=len(checks),passed=sum(checks),failed=len(checks)-sum(checks))

def evaluate(rows,*,model=None,interval=0,tag=''):
    source_start={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('services/business_assistant.py','services/groq_provider.py','services/assistant_registry.py','services/assistant_context.py')}
    settings=replace(load_settings(),model=model) if model else Settings()
    states={};results=[];attempts=0;previous=0
    for case in rows:
        if model and attempts>=32:
            results.append(dict(id=case['id'],status='NOT RUN',reason='model HTTP budget reached'));continue
        if model and previous:
            while interval-(time.monotonic()-previous)>0:time.sleep(min(20,interval-(time.monotonic()-previous)))
        state=states.setdefault(case['scenario'],fresh_state());provider=None
        try:
            if model:provider=GroqProvider(settings,max_requests=min(9,32-attempts))
            result=run(case['question'],SCOPE,state,connected=bool(model),settings=settings,provider=provider)
        except ProviderError as e:result=dict(status='error',code=e.code,reports=[],calls=0,elapsed_seconds=0)
        finally:
            if provider:
                attempts+=provider.requests;provider.close()
            previous=time.monotonic()
        actual_tools=[r['meta']['tool'] for r in result['reports']]
        strict_route=set(case['required_tools'])<=set(actual_tools)
        equivalents={'profit5_pair':{'profit5_pair','two_location_comparison'},'two_location_comparison':{'profit5_pair','two_location_comparison'}}
        route=all(bool(equivalents.get(n,{n})&set(actual_tools)) for n in case['required_tools'])
        numeric=[oracle(r,result['resolved']) for r in result['reports']] if result.get('resolved') else []
        row=dict(id=case['id'],scenario=case['scenario'],language=case['language'],status=result['status'],error=result.get('code'),expected_status=case['expected_status'],
            actual_tools=actual_tools,required_tools=case['required_tools'],routing_passed=route,
            strict_routing_passed=strict_route,tool_rejections=sum(e['status']=='rejected' for e in result.get('tool_events',[])),provider_detail=result.get('provider_detail'),
            outcome_passed=result['status']==case['expected_status'],numeric_checks=sum(n['checks'] for n in numeric),numeric_failures=sum(n['failed'] for n in numeric),
            input_tokens=result.get('input_tokens',0),output_tokens=result.get('output_tokens',0),requests=result.get('calls',0),
            http_attempts=provider.requests if provider else 0,rate_limit_errors=provider.rate_limit_errors if provider else 0,
            elapsed_seconds=result.get('elapsed_seconds',0),evidence=[dict(meta=r['meta'],data=r['data']) for r in result['reports']])
        row['task_passed']=row['routing_passed'] and row['outcome_passed'] and row['numeric_failures']==0
        results.append(row)
        print(case['id'],model or 'offline',row['status'],'route',route,'numeric failures',row['numeric_failures'],flush=True)
        filename='phase_9_live_'+model.replace('/','_')+tag+'.json' if model else 'phase_9_offline_benchmark.json'
        (ROOT/'reports'/filename).write_text(json.dumps(dict(model=model or 'offline',results=results,status='RUNNING'),indent=2,ensure_ascii=False),encoding='utf-8')
    executed=[r for r in results if r['status']!='NOT RUN'];latencies=sorted(r['elapsed_seconds'] for r in executed)
    success=sum(r['task_passed'] for r in executed);n=len(executed)
    total_input=sum(r['input_tokens'] for r in executed);total_output=sum(r['output_tokens'] for r in executed)
    price=PRICES.get(model)
    summary=dict(model=model or 'offline',status='COMPLETE',question_templates=len(rows),executed=n,not_run=len(rows)-n,task_passed=success,
        task_success_pct=100*success/n if n else None,routing_passed=sum(r['routing_passed'] for r in executed),
        numeric_checks=sum(r['numeric_checks'] for r in executed),numeric_failures=sum(r['numeric_failures'] for r in executed),
        median_seconds=statistics.median(latencies) if latencies else None,p95_seconds=latencies[min(len(latencies)-1,int(.95*len(latencies)))] if latencies else None,
        input_tokens=total_input,output_tokens=total_output,http_attempts=attempts,rate_limit_errors=sum(r['rate_limit_errors'] for r in executed),
        estimated_usage_cost_usd=(total_input*price[0]+total_output*price[1])/1e6 if price else None,
        pricing='Groq official models/model pages checked 2026-10-24; GPT-OSS120B $0.15/$0.60, Qwen3.8 $0.80/$4.00 per million input/output tokens. Usage estimate only; failed/unknown usage excluded, not a billing receipt.' if model else None,
        source_sha256_at_start=source_start,source_files_changed_during_run=any(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h for n,h in source_start.items()),
        methodology='Strict routing preserved separately; approved general/profit pair tools count as semantically equivalent for requested sales/gross-profit pair metrics. Numeric values recomputed through approved services. Final text is application-owned, not an independent assessment of fluent model prose. Small live sample is not broad reliability proof.',results=results)
    (ROOT/'reports'/filename).write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--final',action='store_true');p.add_argument('--interval',type=float,default=50);a=p.parse_args()
    data=cases();(ROOT/'docs/PHASE_9_BENCHMARK.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    if a.live:
        chosen=[r for r in data if r['id'] in ('M01_1','M01_2','M01_3','M07_1','M07_2','M07_3','S03','S05')]
        if a.final:chosen=[r for r in data if r['id'] in ('M07_1','M07_2','S03','S05')]
        for model in ('openai/gpt-oss-120b','qwen/qwen3.8-27b'):evaluate(chosen,model=model,interval=a.interval,tag='_final' if a.final else '')
    else:evaluate(data)
