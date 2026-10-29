"""Reproducible monthly target audit, forecast reconciliation and performance."""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services import forecasting as fc,forecast_models as fm,metrics as kpi
from services.forecast_tools import answer_readonly


def validate():
    checks={};cases=[];master=kpi.branches()
    retail=master.query("retail_location_type=='Retail branch'").branch_id.iloc[0]
    pos=master.query("retail_location_type=='Point of sale / reseller'").branch_id.iloc[0]
    def check(name,actual,expected,tolerance=1e-6):
        checks[name]=dict(actual=float(actual),expected=float(expected),passed=abs(float(actual)-float(expected))<=tolerance)
    scopes=[('company',{}),('retail_location',dict(branch=retail)),('pos_location',dict(branch=pos)),
        ('retail_type',dict(location_type='Retail branch')),('pos_type',dict(location_type='Point of sale / reseller')),
        ('category_units',dict(category='Socks')),('location_category',dict(branch=retail,category='Socks'))]
    for name,scope in scopes:
        history,bounds=fc.monthly_history(**scope)
        base=kpi.overview(*bounds,scope.get('branch'),location_type=scope.get('location_type'),category=scope.get('category'))
        metric='units' if scope.get('category') else 'sales'
        check(name+':target_total',history.value.sum(),base[metric],.02)
        check(name+':last_month',history.month.iloc[-1]=='2026-09',True,0)
        check(name+':partial_october_excluded','2026-10' not in set(history.month),True,0)
        for horizon in fc.HORIZONS:
            started=time.perf_counter();result=fc.forecast_report(**scope,horizon=horizon);seconds=time.perf_counter()-started
            key=name+':H'+str(horizon)
            observation=dict(case=name,scope=scope,horizon=horizon,state=result['state'],reason=result['reason'],audit=result['audit'],elapsed_seconds=seconds)
            if result['state']!='unavailable':
                forecasts=result['forecasts'];rows=result['backtests'];splits=result['split_schedule']
                check(key+':horizon',len(forecasts),horizon,0)
                expected=pd.period_range(pd.Period(result['origin'],freq='M')+1,periods=horizon,freq='M').astype(str).tolist()
                check(key+':months',forecasts.month.tolist()==expected,True,0)
                check(key+':chronology',(splits.training_end<splits.target_start).all(),True,0)
                check(key+':test_reserved',splits.loc[splits.stage.eq('validation'),'target_end'].lt(result['test_start']).all(),True,0)
                check(key+':selection_locked',result['selection']['model']==result['model'],True,0)
                check(key+':predictions_nonnegative',forecasts.central.ge(0).all(),True,0)
                held=rows.loc[rows.stage.eq('test') & rows.forecast_model.eq(result['model']) & rows.lead.le(horizon)]
                independently=fm.metrics(held.actual,held.predicted)
                for field in ('mae','rmse','wape_pct','smape_pct','bias','bias_pct'):
                    if independently[field] is not None:check(key+':metric:'+field,result['metrics'][field],independently[field])
                for lead,row in enumerate(forecasts.itertuples(),1):
                    if result['band_widths'][lead-1] is not None:
                        calibration=rows.loc[rows.stage.eq('validation') & rows.forecast_model.eq(result['model']) & rows.lead.eq(lead)]
                        width=(calibration.actual-calibration.predicted).abs().quantile(.8)
                        check(key+':band:'+str(lead),result['band_widths'][lead-1],width)
                        check(key+':range:'+str(lead),row.lower<=row.central<=row.upper,True,0)
                tool=answer_readonly('forecast7_values',dict(start='2020-01-01',end='2020-12-31',**scope),dict(horizon=horizon))
                for i,row in enumerate(tool['data']):check(key+':assistant:'+str(i),row['central'],forecasts.central.iloc[i],.000001)
                check(key+':assistant_origin',tool['meta']['origin']==result['origin'],True,0)
                observation.update(origin=result['origin'],training_start=result['training_start'],training_end=result['training_end'],
                    validation_end=result['validation_end'],test_start=result['test_start'],test_end=result['test_end'],
                    selected_model=result['model'],baseline=result['baseline'],test_metrics=result['metrics'],baseline_metrics=result['baseline_metrics'],
                    comparison=result['comparison'].to_dict('records'),forecasts=forecasts.to_dict('records'),
                    empirical_test_band_coverage_pct=result['test_band_coverage'],band_test_observations=result['test_band_observations'],
                    fit_evaluate_seconds=result['training_and_evaluation_seconds'],final_fit_predict_seconds=result['final_fit_predict_seconds'])
            else:check(key+':unavailable_not_fabricated',result['forecasts'].empty,True,0)
            cases.append(observation)
    started=time.perf_counter();outlook=fc.category_outlook(horizon=3);outlook_seconds=time.perf_counter()-started
    check('category_outlook_count',len(outlook),16,0)
    for row in outlook.itertuples():
        if row.forecast_units is not None and not pd.isna(row.forecast_units):
            direct=fc.forecast_report(category=row.category,horizon=3)
            check('outlook:'+row.category,row.forecast_units,direct['forecasts'].central.sum())
    # Independent synthetic held-out mutation demonstrates frozen selection/bands.
    fake=pd.DataFrame(dict(month=pd.period_range('2018-01',periods=96,freq='M').astype(str),value=100+np.arange(96)*2+10*np.sin(np.arange(96))))
    original=fc.evaluate(fake,3);fake.loc[84:,'value']*=50;changed=fc.evaluate(fake,3)
    check('untouched_test_selection',original['selection']==changed['selection'],True,0)
    prior,_=fc.monthly_history(as_of='2026-09-15');check('asof_partial_september_excluded',prior.month.iloc[-1]=='2026-08',True,0)
    sample=fc.forecast_report(horizon=3);started=time.perf_counter();fc.forecast_report(horizon=3);cached_seconds=time.perf_counter()-started
    return dict(passed=all(c['passed'] for c in checks.values()),checks=checks,cases=cases,
        category_outlook=outlook.to_dict('records'),category_outlook_seconds=outlook_seconds,warm_report_seconds=cached_seconds,
        raw_source_coverage=[str(v) for v in kpi.metadata()],latest_eligible_month='2026-09',model_version=fc.MODEL_VERSION,
        timing_method='perf_counter; scope/horizon in-memory model/data-version cache, OS/SQLite cache may be warm. Timings are not production or cold-disk claims.',
        no_customer_data_or_serialized_models_written=True,llm='Not called; bounded local tools only')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,default=ROOT/'reports/phase_7_forecast_validation.json');args=parser.parse_args()
    result=validate();text=json.dumps(result,default=lambda x:x.item()).replace('NaN','null')
    args.report.write_text(json.dumps(json.loads(text),indent=2),encoding='utf-8')
    print('Phase 7 checks:',sum(c['passed'] for c in result['checks'].values()),'/',len(result['checks']))
    for case in result['cases']:print(case['case'],case['horizon'],case['state'],case.get('selected_model'),round(case['elapsed_seconds'],4),'seconds')
    print('Category outlook seconds',result['category_outlook_seconds'],'warm report seconds',result['warm_report_seconds'])
    raise SystemExit(0 if result['passed'] else 1)
