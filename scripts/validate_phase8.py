"""Aggregate customer reconciliation, temporal evaluation and privacy checks."""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services import customers as cs,customer_data as cd,customer_models as cm,metrics as kpi
from services.customer_tools import answer_readonly
from services.filters import filters


def validate():
    checks={};observations=[]
    def check(name,actual,expected=True,tolerance=1e-6):
        if actual is None or expected is None:passed=actual is None and expected is None
        elif isinstance(actual,(int,float,np.number)) and isinstance(expected,(int,float,np.number)):passed=abs(float(actual)-float(expected))<=tolerance
        else:passed=bool(actual==expected)
        checks[name]=dict(actual=actual,expected=expected,passed=passed)
    audit=cs.audit()
    for name,expected in [('orders',540000),('registered_customers',85000),('identified_purchasers',74660),('anonymous_orders',102961),('multiple_location_purchasers',64688),('duplicate_master_ids',0),('missing_registered_matches',0),('orders_before_registration',0)]:check('audit:'+name,audit[name],expected)
    check('audit:orders',audit['identified_orders']+audit['anonymous_orders'],audit['orders'])
    check('audit:revenue',audit['identified_sales']+audit['anonymous_sales'],audit['total_sales'],.02)
    scopes=[('company',{}),('retail',dict(branch='BR003')),('pos',dict(branch='BR001')),('retail_type',dict(location_type='Retail branch')),('pos_type',dict(location_type='Point of sale / reseller')),('category',dict(category='Socks')),('location_category',dict(branch='BR003',category='Socks'))]
    for name,scope in scopes:
        started=time.perf_counter();report=cs.dashboard('2025-10-01','2026-09-30',**scope);elapsed=time.perf_counter()-started
        summary=report['summary'];expected=kpi.overview('2025-10-01','2026-09-30',**scope)
        check(name+':identified',summary['c8_identified'],expected['customers'])
        check(name+':orders',summary['c8_orders'],expected['orders'])
        check(name+':anonymous',summary['c8_anonymous_orders'],expected['anonymous_orders'])
        check(name+':revenue',summary['c8_identified_revenue']+summary['c8_anonymous_revenue'],expected['sales'],.02)
        if summary['c8_new'] is not None:check(name+':new_returning',summary['c8_new']+summary['c8_returning'],summary['c8_identified'])
        if summary['c8_repeat_rate'] is not None:check(name+':repeat_rate',summary['c8_repeat_rate'],100*summary['c8_repeat_customers']/summary['c8_identified'])
        check(name+':frequency',summary['c8_frequency'],summary['c8_identified_orders']/summary['c8_identified'])
        context=dict(start='2025-10-01',end='2026-09-30',**scope)
        tool=answer_readonly('customer8_summary',context);check(name+':assistant_parity',tool['data'][0]['c8_identified'],summary['c8_identified'])
        for key,frame in report.items():
            if not isinstance(frame,pd.DataFrame):continue
            check(name+':private_columns:'+key,not bool(set(frame)&{'customer_id','customer_name_ar','churn_probability','risk_band','future_revenue'}))
            if not frame.empty and 'c8_customers' in frame:check(name+':minimum_group:'+key,bool(frame.c8_customers.ge(5).all()))
        for i,row in enumerate(report['retention'].itertuples(index=False)):
            if row.c8_observed:check(name+':retention:'+str(i),row.c8_retention_pct,100*row.c8_active/row.c8_cohort_size)
            else:check(name+':censor:'+str(i),pd.isna(row.c8_retention_pct))
        observations.append(dict(case=name,scope=scope,summary=summary,elapsed_seconds=elapsed,aggregate_tables={key:value.to_dict('records') for key,value in report.items() if isinstance(value,pd.DataFrame)}))
    empty=cs.dashboard('2030-01-01','2030-02-01');check('empty:customers',empty['summary']['c8_identified'],0);check('empty:activity',empty['activity'].empty)
    started=time.perf_counter();models=cm.research();model_seconds=time.perf_counter()-started
    check('model:individual_suppression',models['individual_predictions_published'],False)
    schedule=models['schedule'];check('model:past_features',bool((schedule.c8_feature_end<schedule.c8_cutoff).all()))
    check('model:train_purge',schedule.loc[schedule.c8_stage.eq('train'),'c8_value_end'].max()<schedule.loc[schedule.c8_stage.eq('validation'),'c8_cutoff'].min())
    check('model:validation_purge',schedule.loc[schedule.c8_stage.eq('validation'),'c8_value_end'].max()<schedule.loc[schedule.c8_stage.eq('test'),'c8_cutoff'].min())
    check('model:labels_observed',schedule.c8_value_end.max()<=audit['source_end'])
    for i,row in enumerate(models['classification'].to_dict('records')):
        prefix='classification:'+str(i)
        check(prefix+':confusion_total',row['c8_tn']+row['c8_fp']+row['c8_fn']+row['c8_tp'],row['c8_samples'])
        check(prefix+':prevalence',(row['c8_fn']+row['c8_tp'])/row['c8_samples'],row['c8_prevalence'])
        for key in ('c8_roc_auc','c8_average_precision','c8_brier','c8_ece','c8_precision','c8_recall'):check(prefix+':range:'+key,0<=row[key]<=1)
    validation=models['value_comparison'].loc[models['value_comparison'].c8_stage.eq('validation')]
    selected,baseline=cm.choose_value(validation);check('value:validation_selection',selected,models['selected_value']);check('value:baseline',baseline,models['value_baseline'])
    check('model:state',models['state'],'c8_unreliable');check('model:constant_fallback',models['selected_churn'],'c8_prevalence_model')
    forecast=models['value_forecast'];check('value:horizon',(pd.Timestamp(forecast['c8_prediction_end'])-pd.Timestamp(forecast['c8_prediction_start'])).days,364)
    check('value:future_start',forecast['c8_prediction_start']>audit['source_end'])
    for name in ('customer8_churn','customer8_value'):
        tool=answer_readonly(name,dict(start='2020-01-01',end='2020-12-31',branch='BR001'))
        check(name+':company_override',tool['meta']['company_wide']);check(name+':suppressed_individual',tool['meta']['individual_predictions_published'],False)
    for key,value in models.items():
        if isinstance(value,pd.DataFrame):check('model:privacy:'+key,not bool(set(value)&{'customer_id','customer_name_ar','churn_probability','future_revenue'}))
    started=time.perf_counter();cs.dashboard('2025-10-01','2026-09-30');warm_dashboard=time.perf_counter()-started
    started=time.perf_counter();cm.research();warm_models=time.perf_counter()-started
    serial_models={k:v.to_dict('records') if isinstance(v,pd.DataFrame) else v for k,v in models.items()}
    return dict(passed=all(c['passed'] for c in checks.values()),checks=checks,audit=audit,observations=observations,models=serial_models,
        performance=dict(research_total_seconds=model_seconds,research_fit_evaluation_seconds=models['elapsed_seconds'],warm_dashboard_seconds=warm_dashboard,warm_research_seconds=warm_models),
        timing_method='perf_counter on local original DB; OS/SQLite caches may be warm; concurrent validations can affect timings. No production SLA.',
        private_predictions_written=False,saved_legacy_artifacts_overwritten=False,external_llm_called=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,default=ROOT/'reports/phase_8_validation.json');a=p.parse_args()
    result=validate();a.report.write_text(json.dumps(json.loads(json.dumps(result,default=lambda v:v.item()).replace('NaN','null')),indent=2),encoding='utf-8')
    print('Phase 8 checks:',sum(c['passed'] for c in result['checks'].values()),'/',len(result['checks']))
    print('Churn:',result['models']['state'],result['models']['selected_churn']);print('Value:',result['models']['value_state'],result['models']['selected_value']);print(result['performance'])
    raise SystemExit(0 if result['passed'] else 1)
