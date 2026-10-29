"""Local contract audit. No live mode and no credential serialization."""
import copy,json,argparse
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from groq.types.chat import ChatCompletion
from services import business_assistant as ba,assistant_registry as registry,metrics as kpi
from services.assistant_config import Settings,DEFAULT_MODEL
from services.filters import complete_month_bounds
from services.assistant_context import shift_months
from datetime import date

class ScriptedProvider:
    def __init__(self,operations):self.operations=operations;self.sent=[]
    def models(self):return [DEFAULT_MODEL]
    def complete(self,messages,tools):
        self.sent.append(copy.deepcopy(messages))
        calls=[dict(id='audit_'+str(i),type='function',function=dict(name='cottonil_query',arguments=json.dumps(dict(operation=name,parameters=args)))) for i,(name,args) in enumerate(self.operations)] if len(self.sent)==1 else []
        return ChatCompletion.model_validate(dict(id='audit',object='chat.completion',created=0,model='scripted-mock',choices=[dict(index=0,finish_reason='tool_calls' if calls else 'stop',message=dict(role='assistant',content=None if calls else '{}',tool_calls=calls or None))]))

def fixture_context():
    first,last=kpi.metadata();end=date.fromisoformat(complete_month_bounds(first,last)[1]);start=shift_months(end.replace(day=1),-11)
    return dict(start=str(start),end=str(end),branch=None,category=None,location_type=None)

def operation_cases():
    branches=kpi.branches().branch_id.tolist();a,b=branches[2],branches[9]
    cats=kpi.read('SELECT DISTINCT category_en FROM products_catalog ORDER BY 1').category_en.tolist()
    warehouses=kpi.read('SELECT warehouse_id FROM warehouses ORDER BY 1').warehouse_id.tolist();wh=warehouses[0]
    return {
      'company_overview':'Show company sales', 'executive_comparison':'Compare company sales with previous period',
      'executive_stock':'Executive recorded inventory', 'sales_seasonality':'Show company sales seasonality',
      'sales4_trends':'Monthly company sales', 'sales4_products':'Highest company product sales',
      'location_ranking':'Highest sales branches', 'declining_locations':'Declining company branches',
      'two_location_comparison':f'Compare sales {a} and {b}', 'location_detail':f'Sales {a}',
      'profit5_products':'Highest company gross profit products','profit5_categories':'Company gross profit categories',
      'profit5_locations':'Highest gross margin locations','profit5_screening':'Screening high volume low margin products',
      'profit5_leaders':'Company product profitability leaders','profit5_pair':f'Compare gross profit {a} and {b}',
      'profit5_trends':'Monthly company gross profit', 'inventory6_stock':'Company recorded stock',
      'inventory6_risk':'Company inventory risk','inventory6_cover':'Company stock cover',
      'inventory6_replenishment':'Company replenishment','inventory6_warehouse':f'Warehouse inventory {wh}',
      'inventory6_transfers':f'Recorded transfers {wh}','inventory6_pair':f'Compare stock {a} and {b}',
      'forecast7_values':'Forecast company revenue next 3 months','forecast7_accuracy':'Forecast company revenue next 3 months and model accuracy',
      'forecast7_growth':'Forecast company categories expected to grow', 'forecast7_categories':f'Forecast {cats[0]} and {cats[1]}',
      'customer8_summary':'Show customer summary','customer8_segments':'Show customer RFM segments',
      'customer8_cohorts':'Show customer cohort retention','customer8_repeat':'Show customer purchase frequency over time',
      'customer8_changes':'Show customer segment changes','customer8_churn':'Show customer churn research',
      'customer8_value':'Show customer revenue research','category_risk_sales':'Company category sales and inventory risk'}

def trace(question,scope,state=None,*,mode='offline',operations=None):
    state=state if state is not None else ba.fresh_state();previous={k:copy.deepcopy(state.get(k)) for k in ('scope','pair','product_ids','categories','warehouse','horizon','request','clarification_context')}
    raw=[];actual=[];resolved=None
    try:resolved=ba.resolve(question,scope,copy.deepcopy(state)) if not ba.guard(question) else None
    except ValueError:pass
    plan=ba.plan_offline(question,resolved) if resolved else []
    selected=operations if operations is not None else plan
    provider=ScriptedProvider(selected) if mode=='mock' else None
    original=registry.execute
    def execute(name,args,context):
        raw.append(dict(operation=name,arguments=copy.deepcopy(args)))
        return original(name,args,context)
    def adapter(module):
        original_answer=module.answer_readonly
        def answer(name,context,*args,**kwargs):
            actual.append(dict(operation=name,scope=copy.deepcopy(context),parameters=copy.deepcopy(args[0]) if args else {}))
            return original_answer(name,context,*args,**kwargs)
        return answer
    with ExitStack() as stack:
        stack.enter_context(patch.object(registry,'execute',side_effect=execute))
        for module in (registry.sales,registry.profit,registry.stock,registry.forecast,registry.customers):stack.enter_context(patch.object(module,'answer_readonly',side_effect=adapter(module)))
        stack.enter_context(patch.object(ba,'GroqProvider',side_effect=AssertionError('Audit cannot use a live provider')))
        result=ba.run(question,scope,state,connected=mode=='mock',provider=provider,settings=Settings(api_key='fake-audit-key'))
    request=result.get('resolved',{}).get('request',resolved.get('request',{}) if resolved else {})
    coverage=[dict(operation=r['meta']['tool'],metadata={k:v for k,v in r['meta'].items() if k in ('period','branch_id','branch_a','branch_b','product_ids','category','location_type','snapshot','origin','target','unit','state','reason','returned_rows','truncated','scope_policy')},columns=sorted({k for row in r['data'] for k in row}),sample_aggregate_rows=r['data'][:2]) for r in result['reports']]
    diagnostic=dict(question=question,previous_context=previous,resolved_intent=request.get('intent'),requested_metrics=request.get('metrics',[]),resolved_entities_and_filters=dict(entities=request.get('entities'),filters=request.get('filters'),dates=request.get('date_period')),required_aggregation=request.get('aggregation'),required_capabilities=request.get('required_capabilities',[]),deterministic_plan=plan,model_selected_tools=[n for n,_ in selected] if mode=='mock' else [],model_selection_origin='scripted mock; not real language understanding' if mode=='mock' else 'none; local deterministic execution',actual_tool_requests=raw,actual_tool_arguments=actual,returned_evidence_coverage=coverage,final_answer_state=result['answer_state'],missing_metrics=result.get('missing_metrics',[]),missing_operations=result.get('missing_operations',[]),failure_reasons=result.get('tool_failures',[]),code=result['code'],root_cause_if_incorrect=None)
    return result,diagnostic

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('offline','mock'),default='offline');p.add_argument('--output',required=True);a=p.parse_args()
    cases=operation_cases();scope=fixture_context();traces=[]
    assert set(cases)==set(registry.GROUPS)
    for expected,question in cases.items():
        result,entry=trace(question,scope,mode=a.mode);reached=expected in [r['meta']['tool'] for r in result['reports']]
        entry.update(expected_operation=expected,operation_reached=reached)
        if not reached:entry['root_cause_if_incorrect']='Inspect plan, validation and evidence failure; execution alone does not require nonempty data.'
        traces.append(entry)
    Path(a.output).write_text(json.dumps(dict(mode=a.mode,paid_requests=0,real_nlu_verified=False,traces=traces),indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(operations=len(traces),reached=sum(t['operation_reached'] for t in traces),not_reached=[t['expected_operation'] for t in traces if not t['operation_reached']]),indent=2))

if __name__=='__main__':main()
