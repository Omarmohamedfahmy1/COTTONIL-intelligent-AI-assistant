"""Typed witnesses for answer components, using public tool cells only.

No financial formulas, LLM prose, cross-grain ranking or individual predictions.
"""
import math
from services.assistant_capabilities import CAPABILITIES

def number(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)

def ranked_sets(reports,request):
    wanted=request.get('ranking_metrics',[])
    if len(wanted)<2:return None
    selected=[];scope=None
    for metric in wanted:
        report=next((r for r in reports if r.get('meta',{}).get('metric')==metric and
            CAPABILITIES.get(r['meta'].get('tool')) and CAPABILITIES[r['meta']['tool']].role=='products'),None)
        if not report:return None
        rows=report.get('data',[]);meta=report['meta'];limit=request.get('parameters',{}).get('limit')
        if not all(k in meta for k in ('period','branch_id','category','location_type')):return None
        if not rows or not limit or len(rows)!=min(limit,meta.get('total_rows',len(rows))):return None
        if any(not row.get('product_id') or not number(row.get(metric)) for row in rows):return None
        ids=[row['product_id'] for row in rows]
        if len(ids)!=len(set(ids)):return None
        signature=tuple(str(meta.get(k)) for k in ('period','branch_id','category','location_type'))
        if scope is not None and scope!=signature:return None
        scope=signature;selected.append(dict(metric=metric,ids=ids))
    return selected

def forecast_evaluation(reports):
    for r in reports:
        m=r.get('meta',{})
        if m.get('tool')!='forecast7_accuracy' or m.get('state')=='unavailable':continue
        if m.get('state') not in ('available','experimental') or (m.get('target'),m.get('unit')) not in (('revenue','EGP'),('units','units')):continue
        if not all(number(m.get(k)) for k in ('test_wape_pct','baseline_test_wape_pct','test_observations')):continue
        if not m.get('test_start') or not m.get('test_end') or not m.get('horizon') or m['test_observations']<=0:continue
        selected=[row for row in r.get('data',[]) if row.get('stage')=='test' and row.get('forecast_model')==m.get('model')]
        baseline=[row for row in r.get('data',[]) if row.get('stage')=='test' and row.get('forecast_model')==m.get('baseline')]
        if not selected or not baseline:continue
        if not any(number(row.get('wape_pct')) and math.isclose(row['wape_pct'],m['test_wape_pct'],rel_tol=1e-8) for row in selected):continue
        if not any(number(row.get('wape_pct')) and math.isclose(row['wape_pct'],m['baseline_test_wape_pct'],rel_tol=1e-8) for row in baseline):continue
        return m
    return None

def customer_evaluation(reports):
    for r in reports:
        m=r.get('meta',{})
        if m.get('tool')!='customer8_churn' or m.get('state') not in ('c8_unreliable','c8_evaluated_research'):continue
        row=next((row for row in r.get('data',[]) if row.get('c8_model')==m.get('selected') and row.get('c8_stage')=='test_pooled'),None)
        if row and all(number(row.get(k)) for k in ('c8_roc_auc','c8_average_precision','c8_brier','c8_ece','c8_prevalence','c8_samples')):
            return dict(meta=m,row=row)
    return None

def typed_support(reports,request,cells,pair):
    supported=set();asked=request.get('answer_components',[])
    if request.get('metric_bundle_size')==len(request.get('metrics',[])):supported.add('metric_bundle')
    if ranked_sets(reports,request):supported.add('ranking_membership')
    if pair:supported.add('noncausal_description')
    if pair and not any(r.get('meta',{}).get('truncated') or any(metric in row and not number(row[metric]) for row in r.get('data',[]) for metric in request.get('metrics',[])) for r in reports):supported.add('group_extreme')
    if cells and any(c['metric']=='c8_customers' for c in cells):supported.add('inference_limit')
    evaluation=forecast_evaluation(reports)
    if evaluation:
        supported.update(('forecast_evaluation','forecast_reliability'))
        coverage=evaluation.get('test_band_coverage_pct')
        if evaluation.get('uncertainty') and number(coverage) and 0<=coverage<=100:supported.add('forecast_uncertainty')
    if customer_evaluation(reports):supported.add('customer_reliability')
    if request.get('answer_shape')=='series':
        from services.assistant_shape import series_rows
        rows,issues=series_rows(reports,request)
        if rows and not issues:supported.update(['series']+['series_'+v for v in request.get('series_extrema',[])])
    if supported & set(asked) & {'forecast_evaluation','forecast_uncertainty','customer_reliability','noncausal_description'}:
        supported.add('description')
    return supported
