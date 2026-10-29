"""Phase 7 authoritative evaluated forecasts; no writes or inventory replacement."""
from copy import deepcopy
from functools import lru_cache
from datetime import date
from time import perf_counter
import numpy as np
import pandas as pd
import db.connection as connection
from services import metrics as kpi
from services.filters import filters,complete_month_bounds,iso_date,predicate
from db.connection import read
from services import forecast_models as models

MODEL_VERSION='phase7-v1'
HORIZONS=(1,3,6)
MIN_MONTHS=60


def monthly_history(branch=None,location_type=None,category=None,as_of=None):
    first,last=kpi.metadata()
    if as_of:last=min(last,date.fromisoformat(iso_date(as_of))) if last else None
    if first is None or last is None:return pd.DataFrame(columns=['month','value','recorded_month']),None
    bounds=complete_month_bounds(first,last)
    if not bounds:return pd.DataFrame(columns=['month','value','recorded_month']),None
    scope=filters(*bounds,branch,location_type,category)
    frame=kpi.company_sales_fully_observed_months(branch,category,location_type=location_type)
    frame=frame.loc[frame.month.between(bounds[0][:7],bounds[1][:7])].copy()
    # Only activity PRESENCE is needed, not financial/customer/order KPI joins.
    # Audited line/header relationships make a matching category sale-line an
    # observation, including a recorded zero quantity. Targets still come from
    # the unchanged approved monthly aggregation above.
    condition,params=predicate(scope,'i' if category else 'o',include_category=bool(category))
    source='sales_order_items i' if category else 'sales_orders o'
    observations=read(f'SELECT DISTINCT substr(order_date,1,7) month FROM {source} WHERE {condition}',params)
    frame['recorded_month']=frame.month.isin(observations.month)
    # The approved aggregate fills absent months with zero. Forecasting does not
    # assume that absence proves zero demand: restore those observations to NaN.
    frame['value']=pd.to_numeric(frame.value).where(frame.recorded_month)
    return frame.reset_index(drop=True),bounds


def evaluate(history,horizon=3):
    """Chronological validation selection, followed by untouched locked-model test.

    Validation origins every three months, forecasting six steps, finish BEFORE
    the final twelve months. Final test has two disjoint six-month origins; the
    second trains on earlier test actuals only after time has advanced. Neither
    test block affects selection, features, hyperparameters or error-band widths.
    """
    started=perf_counter()
    if isinstance(horizon,bool) or not isinstance(horizon,int) or horizon not in HORIZONS:raise ValueError('Horizon must be 1, 3 or 6 months')
    frame=history.copy();months=pd.PeriodIndex(frame.month,freq='M')
    if months.has_duplicates or not months.is_monotonic_increasing:raise ValueError('Unique ordered months required')
    if len(months) and list(months)!=list(pd.period_range(months[0],months[-1],freq='M')):raise ValueError('Missing calendar rows must be explicit')
    result=dict(state='unavailable',reason='f7_insufficient',history=frame,forecasts=pd.DataFrame(columns=['month','central','lower','upper']),
        comparison=pd.DataFrame(),backtests=pd.DataFrame(),horizon=horizon,model=None,baseline=None,metrics=None,baseline_metrics=None,
        band_widths=[],test_band_coverage=None,model_version=MODEL_VERSION)
    missing=int(frame.value.isna().sum())
    y=frame.value.to_numpy(dtype=float)
    result['audit']=dict(months=len(frame),missing_months=missing,zero_months=int(frame.value.eq(0).sum()),nonzero_months=int(frame.value.gt(0).sum()))
    if missing:result['reason']='f7_missing';return result
    if len(frame)<MIN_MONTHS:return result
    if not np.isfinite(y).all() or (y<0).any():raise ValueError('Nonnegative finite target values required')
    n=len(y);boundary=n-12
    if not np.any(y[:boundary]>models.EPS):result['reason']='f7_zero';return result
    sparse=bool(np.count_nonzero(y[:boundary])<24 or np.mean(y[:boundary]>0)<.5)
    candidates=models.BASELINES if sparse else models.MODELS
    origins=list(range(max(36,n-36),boundary-5,3));rows=[];splits=[]
    for origin in origins:
        splits.append(dict(stage='validation',training_end=str(months[origin-1]),origin=str(months[origin-1]),target_start=str(months[origin]),target_end=str(months[origin+5])))
        for model in candidates:
            prediction=models.predict(model,y[:origin],months[:origin],6)
            for lead,p in enumerate(prediction,1):rows.append(dict(stage='validation',origin=str(months[origin-1]),month=str(months[origin+lead-1]),lead=lead,forecast_model=model,actual=float(y[origin+lead-1]),predicted=float(p)))
    validation=pd.DataFrame(rows)
    scores=models.score_rows(validation,'validation',horizon)
    selected,baseline,gates=models.choose(scores,validation,horizon)
    # Frozen selection and band widths: compute BEFORE reading/scoring test targets.
    widths=models.uncertainty(validation,selected,horizon)
    selection=dict(model=selected,baseline=baseline,band_widths=widths)
    for origin in (boundary,boundary+6):
        splits.append(dict(stage='test',training_end=str(months[origin-1]),origin=str(months[origin-1]),target_start=str(months[origin]),target_end=str(months[origin+5])))
        for model in candidates:
            prediction=models.predict(model,y[:origin],months[:origin],6)
            for lead,p in enumerate(prediction,1):rows.append(dict(stage='test',origin=str(months[origin-1]),month=str(months[origin+lead-1]),lead=lead,forecast_model=model,actual=float(y[origin+lead-1]),predicted=float(p)))
    backtests=pd.DataFrame(rows);test_scores=models.score_rows(backtests,'test',horizon)
    test=test_scores.set_index('forecast_model').loc[selected].to_dict();base_test=test_scores.set_index('forecast_model').loc[baseline].to_dict()
    state='available'
    if sparse or len(origins)<5 or test['wape_pct'] is None or test['wape_pct']>35 or abs(test['bias_pct'] or 0)>20 or (selected in models.REGRESSORS and test['wape_pct']>(base_test['wape_pct'] or 0)*1.1):state='experimental'
    future_start=perf_counter();central=models.predict(selected,y,months,horizon);predict_seconds=perf_counter()-future_start
    future=pd.DataFrame(dict(month=pd.period_range(months[-1]+1,periods=horizon,freq='M').astype(str),central=central))
    future['lower']=[max(0,p-w) if w is not None else None for p,w in zip(central,widths)]
    future['upper']=[p+w if w is not None else None for p,w in zip(central,widths)]
    held=backtests.loc[backtests.stage.eq('test') & backtests.forecast_model.eq(selected) & backtests.lead.le(horizon)]
    coverage=[]
    for row in held.itertuples():
        w=widths[row.lead-1]
        if w is not None:coverage.append(max(0,row.predicted-w)<=row.actual<=row.predicted+w)
    comparisons=pd.concat([scores,test_scores],ignore_index=True).merge(gates,on='forecast_model',validate='many_to_one')
    comparisons['selected_model']=comparisons.forecast_model.eq(selected);comparisons['selected_baseline']=comparisons.forecast_model.eq(baseline)
    outlier_limit=float(np.quantile(y,.75)+3*(np.quantile(y,.75)-np.quantile(y,.25)))
    result.update(state=state,reason='f7_experimental' if state=='experimental' else 'f7_evaluated',forecasts=future,
        comparison=comparisons,backtests=backtests,split_schedule=pd.DataFrame(splits),model=selected,baseline=baseline,
        selection=selection,metrics=test,baseline_metrics=base_test,band_widths=widths,
        test_band_coverage=float(np.mean(coverage)*100) if coverage else None,test_band_observations=len(coverage),
        training_start=str(months[0]),training_end=str(months[-1]),validation_end=str(months[boundary-1]),
        test_start=str(months[boundary]),test_end=str(months[-1]),origin=str(months[-1]),validation_origins=len(origins),sparse=sparse,
        training_and_evaluation_seconds=perf_counter()-started,final_fit_predict_seconds=predict_seconds)
    result['audit']['descriptive_high_outlier_months']=frame.loc[frame.value.gt(outlier_limit),'month'].tolist()
    result['audit']['calendar_means']=frame.assign(calendar_month=frame.month.str[-2:]).groupby('calendar_month').value.mean().to_dict()
    return result


@lru_cache(maxsize=32)
def _cached(branch,location_type,category,horizon,as_of,path,mtime,size,version):
    frame,bounds=monthly_history(branch,location_type,category,as_of)
    result=evaluate(frame,horizon)
    result.update(target='units' if category else 'revenue',unit='units' if category else 'EGP',branch=branch,location_type=location_type,category=category,bounds=bounds)
    return result


def forecast_report(branch=None,*,location_type=None,category=None,horizon=3,as_of=None):
    if isinstance(horizon,bool) or not isinstance(horizon,int) or horizon not in HORIZONS:raise ValueError('Horizon must be 1, 3 or 6')
    if as_of:as_of=iso_date(as_of)
    path=connection.DB_PATH.resolve();stamp=path.stat()
    return deepcopy(_cached(branch,location_type,category,horizon,as_of,str(path),stamp.st_mtime_ns,stamp.st_size,MODEL_VERSION))


def category_outlook(branch=None,location_type=None,categories=None,horizon=3):
    catalog=kpi.read('SELECT DISTINCT category_en FROM products_catalog ORDER BY 1').category_en.tolist()
    categories=catalog if categories is None else categories
    if not categories or len(categories)!=len(set(categories)) or any(c not in catalog for c in categories):raise ValueError('Known distinct categories required')
    rows=[]
    for category in categories:
        result=forecast_report(branch,location_type=location_type,category=category,horizon=horizon)
        recent=float(result['history'].value.tail(horizon).sum(min_count=1))
        expected=float(result['forecasts'].central.sum()) if not result['forecasts'].empty else None
        rows.append(dict(category=category,state=result['state'],origin=result.get('origin'),forecast_model=result['model'],
            forecast_start=result['forecasts'].month.iloc[0] if expected is not None else None,
            forecast_end=result['forecasts'].month.iloc[-1] if expected is not None else None,
            recent_actual_units=recent,forecast_units=expected,forecast_vs_recent_pct=kpi.growth_percent(expected,recent) if expected is not None else None,
            test_wape_pct=result['metrics']['wape_pct'] if result['metrics'] else None))
    return pd.DataFrame(rows)
