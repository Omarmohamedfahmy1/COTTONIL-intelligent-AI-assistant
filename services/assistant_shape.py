"""Answer-shape witnesses over verified public cells; no KPI calculations."""
from datetime import date,timedelta
from calendar import monthrange
import math

def numeric(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)

def expected_periods(request):
    scope=request.get('scope',{});start=date.fromisoformat(scope['start']);end=date.fromisoformat(scope['end'])
    grain=request.get('parameters',{}).get('grain','monthly');periods=[]
    if grain not in ('monthly','yearly'):return None
    point=start.replace(day=1) if grain=='monthly' else start.replace(month=1,day=1)
    while point<=end:
        periods.append(point.isoformat()[:7] if grain=='monthly' else str(point.year))
        if grain=='monthly':point=date(point.year+point.month//12,point.month%12+1,1)
        else:point=date(point.year+1,1,1)
    return periods

def series_rows(reports,request):
    rows={};issues=[];expected=expected_periods(request)
    for report in reports:
        if report['meta']['tool'] not in ('sales4_trends','profit5_trends'):continue
        for row in report.get('data',[]):
            period=row.get('period') or row.get('month')
            if period is None:issues.append('series_period_identity');continue
            period=str(period)
            existing=rows.setdefault(period,{})
            for key,value in row.items():
                if key in existing and existing[key]!=value:issues.append('series_conflict')
                existing[key]=value
    if not rows:issues.append('series_unavailable')
    if expected is not None and set(rows)!=set(expected):issues.append('series_period_coverage')
    for row in rows.values():
        if any(not numeric(row.get(metric)) for metric in request.get('metrics',[])):issues.append('series_metric_coverage')
        if row.get('is_complete_period') is False:issues.append('series_partial_period')
    return [(period,rows[period]) for period in sorted(rows)],sorted(set(issues))

def validate_shape(reports,resolved):
    from services.assistant_request import complete_requested_selection
    request=resolved.get('request',{});issues=[]
    if request.get('answer_shape')=='series':
        _,issues=series_rows(reports,request)
    if request.get('ranking_metrics') and request.get('parameters',{}).get('limit'):
        for metric in request['ranking_metrics']:
            candidates=[r for r in reports if r['meta'].get('metric')==metric]
            if not any(complete_requested_selection(r,resolved) and all(numeric(row.get(m)) for row in r['data'] for m in request['metrics']) for r in candidates):
                issues.append('ranking_selection_coverage')
    if request.get('answer_shape')=='pair':
        for metric in request.get('metrics',[]):
            # Inventory category pairs have their own strict coverage contract.
            if metric not in ('sales','gross_profit','gross_margin_pct','orders','aov','units','growth_pct','customers'):continue
            rows=[row for r in reports for row in r['data'] if row.get('metric')==metric]
            if not any(numeric(row.get('location_a')) and numeric(row.get('location_b')) for row in rows):issues.append('pair_metric_coverage')
    return sorted(set(issues))

def extrema(reports,request):
    """Select all tied period identities from verified cells; no new measures."""
    rows,issues=series_rows(reports,request);result=[]
    for metric in request.get('metrics',[]):
        valid=[(period,row[metric]) for period,row in rows if numeric(row.get(metric))]
        if not valid:continue
        for direction in request.get('series_extrema',[]):
            bound=(max if direction=='highest' else min)(value for _,value in valid)
            result.append(dict(metric=metric,direction=direction,periods=[p for p,v in valid if v==bound],value=bound))
    return result,issues
