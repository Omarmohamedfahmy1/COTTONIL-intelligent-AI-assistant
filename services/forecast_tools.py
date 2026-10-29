"""Bounded read-only Phase 7 forecasts; no free-form planner or provider calls."""
import re
from services import forecasting as fc,metrics as kpi
from services.filters import filters
from services.sales_branch_tools import records

ALLOWED=('forecast7_values','forecast7_accuracy','forecast7_growth','forecast7_categories')


def answer_readonly(name,context,params=None):
    if name not in ALLOWED:raise ValueError('Unsupported forecast tool')
    params=params or {};scope=filters(**context);horizon=params.get('horizon',3)
    if isinstance(horizon,bool) or not isinstance(horizon,int) or horizon not in fc.HORIZONS:raise ValueError('Supported horizons: 1, 3, 6')
    meta=dict(tool=name,period=f'{scope.start} to {scope.end}',branch_id=scope.branch or 'all',location_type=scope.location_type,
        category=scope.category,horizon=horizon,source='Verified Phase 7 evaluated monthly forecasting services',
        history_policy='Selected dates are display scope only. Train on all eligible history through latest complete SOURCE month; next means after this data origin, not host date.',
        uncertainty='80th percentile absolute validation errors by lead; uncalibrated empirical ranges, not confidence intervals',model_version=fc.MODEL_VERSION)
    if name in ('forecast7_growth','forecast7_categories'):
        categories=params.get('categories')
        if name=='forecast7_categories' and (not categories or len(categories)!=2):raise ValueError('Two known distinct categories required')
        frame=fc.category_outlook(scope.branch,scope.location_type,categories,horizon)
        if name=='forecast7_growth':frame=frame.sort_values(['forecast_vs_recent_pct','category'],ascending=[False,True],na_position='last')
        meta.update(category=None,target='units',unit='units',scope_policy='Category outlook/pair explicitly overrides global category; global location/type retained; growth compares next H estimates with preceding H actual complete months')
        if name=='forecast7_categories':meta['categories']=list(categories)
    else:
        result=fc.forecast_report(scope.branch,location_type=scope.location_type,category=scope.category,horizon=horizon)
        meta.update(state=result['state'],reason=result['reason'],origin=result.get('origin'),target=result['target'],unit=result['unit'],
            model=result['model'],baseline=result['baseline'],test_wape_pct=result['metrics']['wape_pct'] if result['metrics'] else None,
            baseline_test_wape_pct=result['baseline_metrics']['wape_pct'] if result['baseline_metrics'] else None,
            test_observations=result['metrics'].get('observations') if result['metrics'] else None,
            test_start=result.get('test_start'),test_end=result.get('test_end'),test_band_coverage_pct=result['test_band_coverage'],
            training_start=result.get('training_start'),training_end=result.get('training_end'))
        if not result['forecasts'].empty:meta.update(forecast_start=result['forecasts'].month.iloc[0],forecast_end=result['forecasts'].month.iloc[-1])
        frame=result['comparison'] if name=='forecast7_accuracy' else result['forecasts']
    meta['rows_returned']=len(frame)
    return dict(meta=meta,data=records(frame),plot=None)


def dispatch(question,context,category_names=None):
    q=question.casefold()
    if not any(w in q for w in ('forecast','expected sales','expected demand','expected to grow','model performed','forecast accuracy','توقع','متوقع','النموذج','دقته')):return None
    # Phase 6 replenishment stays a separate heuristic, even if phrased as prediction.
    if any(w in q for w in ('replenish','توريد','stock','inventory','مخزون')):return None
    if any(w in q for w in ('sku','صنف','net profit','صافي الربح')):return {'clarify':'f7_unsupported_target'}
    horizon=1 if any(w in q for w in ('next month','الشهر الجاي','الشهر القادم')) else 3
    found=re.findall(r'(?<!\d)([0-9]+|[١٣٦])\s*(?:months?|شهور|أشهر|شهر)',q)
    if found:
        if len(found)!=1:return {'clarify':'f7_horizon_request'}
        horizon=int(found[0].translate(str.maketrans('١٣٦','136')))
        if horizon not in fc.HORIZONS:return {'clarify':'f7_horizon_request'}
    if re.search(r'\b\d{4}\b',q) or any(w in q for w in ('last year','last month','today','yesterday','الماضي','السنة الماضية')):return {'clarify':'f7_origin_request'}
    scope=filters(**context);master=kpi.branches()
    ids=[v.upper() for v in re.findall(r'\bBR\d{3}\b',question,re.I)]
    if len(set(ids))>1 or any(v not in set(master.branch_id) for v in ids):return {'clarify':'invalid_scope'}
    if ids:
        try:scope=filters(scope.start,scope.end,ids[0],scope.location_type,scope.category)
        except ValueError:return {'clarify':'invalid_scope'}
    catalog=kpi.read('SELECT DISTINCT category_en FROM products_catalog ORDER BY 1').category_en.tolist()
    matches=[]
    for category in catalog:
        aliases=[category,(category_names or {}).get(category,'')]
        if any(alias and re.search(r'(?<!\w)'+re.escape(alias.casefold())+r'(?!\w)',q) for alias in aliases):matches.append(category)
    if any(w in q for w in ('compare','قارن','مقارنة')):
        if len(matches)!=2:return {'clarify':'f7_two_categories'}
        return answer_readonly('forecast7_categories',vars(scope),dict(horizon=horizon,categories=matches))
    if len(matches)>1:return {'clarify':'f7_two_categories'}
    if matches:scope=filters(scope.start,scope.end,scope.branch,scope.location_type,matches[0])
    if any(w in q for w in ('expected to grow','categories grow','الفئات المتوقع نموها')):
        return answer_readonly('forecast7_growth',vars(scope),dict(horizon=horizon))
    if any(w in q for w in ('accuracy','model performed','best model','دقته','النموذج')):name='forecast7_accuracy'
    else:name='forecast7_values'
    if any(w in q for w in ('category demand','الطلب','فئة')) and not scope.category:return {'clarify':'f7_category_request'}
    return answer_readonly(name,vars(scope),dict(horizon=horizon))
