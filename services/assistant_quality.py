"""Independent answer coverage and app-owned facts; no financial calculation."""
import math
from services.assistant_request import output_issues,missing_metrics,complete_requested_selection
from services.assistant_capabilities import CAPABILITIES
from services.assistant_findings import coverage

EQUIVALENT={'profit5_pair':{'profit5_pair','two_location_comparison'},
            'two_location_comparison':{'profit5_pair','two_location_comparison'},
            'sales4_products':{'sales4_products','profit5_products'},'profit5_products':{'sales4_products','profit5_products'},
            'sales4_trends':{'sales4_trends','profit5_trends'},'profit5_trends':{'sales4_trends','profit5_trends'}}
def domain(tool):
    if tool.startswith('inventory6_') or tool=='executive_stock':return 'inventory'
    if tool.startswith('forecast7_'):return 'forecast'
    if tool.startswith('customer8_'):return 'customers'
    if tool.startswith('profit5_'):return 'profitability'
    return 'sales'

def domains(tool):
    if tool=='category_risk_sales':return {'sales','inventory'}
    if tool in ('company_overview','two_location_comparison'):return {'sales','profitability'}
    if CAPABILITIES[tool].domain in ('sales','profitability') and CAPABILITIES[tool].metrics&{'gross_profit','gross_margin_pct'}:return {'sales','profitability'}
    return {domain(tool)}

def assess(reports,required,resolved,status='supported',code=None):
    from services.assistant_shape import validate_shape
    tools={r['meta']['tool'] for r in reports}
    missing=[name for name in required if not EQUIVALENT.get(name,{name})&tools]
    requested=sorted({d for name in required for d in domains(name)})
    requested=sorted(set(requested)|set(resolved.get('request',{}).get('domains',[])))
    returned=sorted({d for name in tools for d in domains(name)})
    reasons=[]
    if resolved.get('request',{}).get('capability_limitations'):reasons.append('unsupported_basis')
    if resolved.get('calendar_coverage') and not resolved['calendar_coverage']['complete']:reasons.append('incomplete_calendar_year')
    if missing:reasons.append('missing_domains')
    if set(requested)-set(returned):reasons.append('missing_domains')
    scope_issues=[issue for r in reports for issue in output_issues(r,resolved)]
    uncovered=missing_metrics(reports,resolved)
    shape_issues=validate_shape([r for r in reports if not output_issues(r,resolved)],resolved)
    if shape_issues:reasons.append('incomplete_answer_shape')
    answer_coverage=coverage([r for r in reports if not output_issues(r,resolved)],resolved.get('request',{}))
    if answer_coverage['missing_answer_components']:reasons.append('incomplete_answer_components')
    if scope_issues:reasons.append('scope_mismatch')
    if resolved.get('request',{}).get('unresolved_constraints'):reasons.append('unsupported_parameters')
    if uncovered:reasons.append('missing_metrics')
    if resolved.get('request',{}).get('unsupported_aggregation'):reasons.append('unsupported_aggregation')
    if resolved.get('request',{}).get('unsupported_risk_metric'):reasons.append('unsupported_risk_metric')
    if not required:reasons.append('unverified_intent')
    if any(r['meta'].get('truncated') and not complete_requested_selection(r,resolved) for r in reports):reasons.append('truncated_rows')
    if any(r['meta'].get('partial_coverage') for r in reports):reasons.append('incomplete_category_coverage')
    if any(r['meta'].get('partial_metrics') for r in reports):reasons.append('incomplete_metric_coverage')
    if any(r['meta'].get('state')=='experimental' or any(row.get('state')=='experimental' for row in r['data']) for r in reports if r['meta']['tool'].startswith('forecast7_')):reasons.append('forecast_experimental')
    if any(row.get('state')=='unavailable' for r in reports if r['meta']['tool'].startswith('forecast7_') for row in r['data']):reasons.append('unavailable_category_forecasts')
    if resolved.get('forecast_accuracy') and any(n in required for n in ('forecast7_growth','forecast7_categories')):reasons.append('category_evaluation_scope')
    unavailable=[r['meta']['tool'] for r in reports if not r['data'] or r['meta'].get('state')=='unavailable' or (r['meta']['tool'].startswith('forecast7_') and all(row.get('state')=='unavailable' for row in r['data']))]
    if unavailable:reasons.append('unavailable_evidence')
    first,last=resolved.get('source_start'),resolved.get('source_end')
    scope=resolved.get('scope',{})
    financial=bool(set(resolved.get('request',{}).get('metrics',[]))&{'sales','gross_profit','gross_margin_pct','orders','aov','units','growth_pct','customers'})
    if financial and not resolved.get('request',{}).get('forecast') and first and last and (scope.get('start','')<first or scope.get('end','')>last):reasons.append('incomplete_source_window')
    outside=bool(first and (scope.get('end','')<first or scope.get('start','')>last))
    if outside:reasons.append('outside_source')
    for report in reports:
        meta=report['meta']
        if meta['tool'].startswith('customer8_') and meta['tool'] not in ('customer8_churn','customer8_value'):
            if resolved.get('pair') or resolved.get('product_ids') or scope.get('branch') or scope.get('category') or scope.get('location_type') or meta.get('period')!=scope.get('start','')+' to '+scope.get('end',''):
                reasons.append('privacy_scope_override')
    if status=='blocked':state='unavailable' if code=='unavailable' else 'blocked'
    elif status=='unsupported':state='partial' if 'facts' in answer_coverage['supported_answer_components'] else 'unsupported'
    elif status=='clarify' and not reports:state='unavailable' if code=='no_evidence' else 'clarification'
    elif status=='limited':state='budget_exhausted'
    elif status=='error':state='partial' if reports else 'provider_error'
    elif outside or (reports and len(unavailable)==len(reports)):state='unavailable'
    elif reasons:state='partial'
    elif reports:state='full'
    else:state='clarification'
    return dict(answer_state=state,capability_limitations=resolved.get('request',{}).get('capability_limitations',[]),requested_domains=requested,returned_domains=returned,
        missing_operations=missing,coverage_reasons=sorted(set(reasons)),numeric_evidence_available=bool(reports),
        semantic_complete=state=='full',unavailable_operations=unavailable,scope_issues=sorted(set(scope_issues)),shape_issues=shape_issues,missing_metrics=uncovered,**answer_coverage)

def facts(reports):
    """Every value is a direct public service cell; never LLM text or new math."""
    result=[]
    priorities=('sales','gross_profit','gross_margin_pct','orders','stock_units','c8_identified','c8_repeat_rate',
        'c8_registered','c8_roc_auc','c8_predicted_revenue','central','wape_pct','max_recorded_risk','avg_sales')
    for i,report in enumerate(reports):
        meta=report['meta'];tool=meta['tool'];rows=report['data'];count=0
        for index,row in enumerate(rows):
            if row.get('metric') in ('sales','gross_profit','gross_margin_pct'):
                for column,branch in (('location_a',meta.get('branch_a')),('location_b',meta.get('branch_b'))):
                    value=row.get(column)
                    if isinstance(value,(int,float)) and math.isfinite(value):
                        result.append(dict(evidence_id=report.get('evidence_id',f'E{i+1}'),tool=tool,row=index,key=column,
                            metric=row['metric'],value=value,entity=branch,unit=meta.get('units',{}).get(row['metric'],'see metric'),
                            period=meta['period'],classification=meta.get('classification','recorded')))
                if row['metric']=='gross_profit':break
                continue
            keys=[k for k in priorities if isinstance(row.get(k),(int,float)) and not isinstance(row[k],bool) and math.isfinite(row[k])]
            for key in keys[:2 if tool!='company_overview' else 3]:
                result.append(dict(evidence_id=report.get('evidence_id',f'E{i+1}'),tool=tool,row=index,key=key,metric=key,
                    value=row[key],entity=row.get('month') or row.get('category') or row.get('branch_id') or meta.get('branch_id','all'),
                    unit=meta.get('units',{}).get(key,meta.get('unit','see metric')),period=meta['period'],
                    classification=meta.get('classification','recorded')))
            count+=1
            if count>=1:break
        if tool=='inventory6_pair' and rows:
            row=rows[0]
            for column,branch in (('stock_units_a',meta.get('branch_a')),('stock_units_b',meta.get('branch_b'))):
                value=row.get(column)
                if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
                    result.append(dict(evidence_id=report.get('evidence_id',f'E{i+1}'),tool=tool,row=0,key=column,metric='stock_units',
                        value=value,entity=f"{branch} / {row.get('category','')}",unit='units',period=meta['period'],classification=meta.get('classification','recorded')))
    unique=[];seen=set()
    for fact in result:
        signature=(fact['metric'],fact['entity'],fact['period'],fact['value'])
        if signature not in seen:unique.append(fact);seen.add(signature)
    return unique[:12]
