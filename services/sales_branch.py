"""Phase 4 read-only sales/location orchestration over the approved KPI foundation."""
from calendar import monthrange
from dataclasses import replace
from datetime import date,timedelta
import pandas as pd
from db.connection import read
from services import metrics as kpi
from services.filters import filters,predicate,previous_period
from services.executive import comparison,category_changes

GRAINS=('daily','weekly','monthly','yearly')
RANK_METRICS={'sales','gross_profit','growth_pct','aov','orders','units','customers','company_sales_share_pct','orders_per_listed_employee'}
DECLINE_PCT=-10.0
CHANGE_PCT=25.0
MIN_CATEGORY_BASELINE=10000.0


def args(scope):
    return dict(start=scope.start,end=scope.end,branch=scope.branch,location_type=scope.location_type,category=scope.category)


def covered(scope):
    ps,pe=previous_period(scope.start,scope.end)
    return kpi._period_covered(scope.start,scope.end) and kpi._period_covered(ps,pe)


def period_summary(scope):
    current=kpi.overview(**args(scope))
    growth=kpi.sales_growth(**args(scope))
    previous=kpi.overview(growth['previous_start'],growth['previous_end'],scope.branch,
        location_type=scope.location_type,category=scope.category)
    rows=comparison(current,previous,growth['comparable_coverage'])
    before=previous['units'] if growth['comparable_coverage'] else None
    change=current['units']-before if before is not None else None
    rows=pd.concat([rows,pd.DataFrame([dict(metric='units',current=current['units'],previous=before,
        absolute_change=change,percentage_change=kpi.growth_percent(current['units'],before) if before is not None else None,
        state='unavailable' if change is None else 'positive' if change>0 else 'negative' if change<0 else 'unchanged')])],ignore_index=True)
    display=dict(current,growth_pct=growth['growth_pct'])
    if not display['orders']:display['aov']=None
    if not display['sales']:display['gross_margin_pct']=None
    return dict(scope=scope,current=display,growth=growth,comparison=rows)


def sales_trends(start,end,branch=None,*,location_type=None,category=None,grain='monthly'):
    """Separate day-grain header and line sums, then aggregate at a fixed grain.

    Zero-recorded-order days are filled only within global recorded date bounds.
    Distinct purchasers are NOT summed through periods. Weekly labels are Mondays.
    """
    if grain not in GRAINS:raise ValueError('Unsupported time grain')
    scope=filters(start,end,branch,location_type,category)
    source,params=kpi._orders(scope)
    orders=read(f'''WITH scoped AS ({source}) SELECT order_date day,SUM(sales) sales,
        COUNT(*) orders FROM scoped GROUP BY order_date''',params)
    condition,params=predicate(scope,'i',include_category=True)
    lines=read(f'''SELECT order_date day,SUM(quantity) units,SUM(margin_EGP) gross_profit
        FROM sales_order_items i WHERE {condition} GROUP BY order_date''',params)
    first,last=kpi.metadata()
    columns=['period','sales','orders','units','gross_profit','aov','is_complete_period']
    if first is None:return pd.DataFrame(columns=columns)
    lo,hi=max(scope.start,str(first)),min(scope.end,str(last))
    if lo>hi:return pd.DataFrame(columns=columns)
    days=pd.DataFrame({'day':pd.date_range(lo,hi).strftime('%Y-%m-%d')})
    frame=days.merge(orders,on='day',how='left',validate='one_to_one').merge(lines,on='day',how='left',validate='one_to_one')
    for c in ('sales','orders','units','gross_profit'):frame[c]=pd.to_numeric(frame[c]).fillna(0)
    dates=pd.to_datetime(frame.day)
    if grain=='daily':frame['period']=frame.day
    elif grain=='weekly':frame['period']=(dates-pd.to_timedelta(dates.dt.weekday,unit='D')).dt.strftime('%Y-%m-%d')
    else:frame['period']=dates.dt.strftime('%Y-%m' if grain=='monthly' else '%Y')
    result=frame.groupby('period',as_index=False)[['sales','orders','units','gross_profit']].sum()
    result[['orders','units']]=result[['orders','units']].astype(int)
    result['aov']=kpi.ratio(result.sales,result.orders).where(result.orders.gt(0))
    def complete(label):
        a=date.fromisoformat(label if grain in ('daily','weekly') else label+'-01' if grain=='monthly' else label+'-01-01')
        b=a if grain=='daily' else a+timedelta(days=6) if grain=='weekly' else a.replace(day=monthrange(a.year,a.month)[1]) if grain=='monthly' else date(a.year,12,31)
        return lo<=str(a)<=str(b)<=hi
    result['is_complete_period']=result.period.map(complete)
    return result


def yearly_comparison(scope):
    """Full calendar-month YoY only, same month one year earlier; no leap clipping."""
    now=kpi.sales_monthly(**args(scope))
    if now.empty:return pd.DataFrame(columns=['month','sales','previous_year_sales','yoy_growth_pct','yoy_comparable'])
    # Query full prior calendar months; mark coverage using the same source bounds.
    first=date.fromisoformat(scope.start).replace(day=1)
    last=date.fromisoformat(scope.end)
    ps=f'{first.year-1:04d}-{first.month:02d}-01'
    pe=f'{last.year-1:04d}-{last.month:02d}-{monthrange(last.year-1,last.month)[1]:02d}'
    previous=kpi.sales_monthly(ps,pe,scope.branch,location_type=scope.location_type,category=scope.category).set_index('month')
    result=now[['month','sales']].copy();rows=[]
    for row in now.itertuples():
        key=f'{int(row.month[:4])-1:04d}'+row.month[4:]
        a=key+'-01';b=key+f'-{monthrange(int(key[:4]),int(key[5:]))[1]:02d}'
        comparable=bool(row.is_complete_month and kpi._period_covered(a,b))
        before=float(previous.loc[key,'sales']) if key in previous.index and comparable else 0.0 if comparable else None
        rows.append((before,kpi.growth_percent(row.sales,before) if before is not None else None,comparable))
    result[['previous_year_sales','yoy_growth_pct','yoy_comparable']]=pd.DataFrame(rows,index=result.index)
    month_before=first-timedelta(days=1)
    recent=kpi.sales_monthly(str(month_before.replace(day=1)),scope.end,scope.branch,
        location_type=scope.location_type,category=scope.category).set_index('month')
    mom=[]
    for row in now.itertuples():
        end_previous=date.fromisoformat(row.month+'-01')-timedelta(days=1)
        start_previous=end_previous.replace(day=1)
        comparable=bool(row.is_complete_month and kpi._period_covered(str(start_previous),str(end_previous)))
        key=str(start_previous)[:7]
        before=float(recent.loc[key,'sales']) if key in recent.index and comparable else 0.0 if comparable else None
        mom.append((before,kpi.growth_percent(row.sales,before) if before is not None else None))
    result[['previous_month_sales','mom_growth_pct']]=pd.DataFrame(mom,index=result.index)
    return result


def product_roster(scope):
    active=kpi.product_performance(**args(scope),sort='sales',limit=10000)
    master=read('SELECT product_id,product_name_ar product,category_en category FROM products_catalog')
    if scope.category:master=master[master.category.eq(scope.category)]
    result=master.merge(active.drop(columns=['product','category']),on='product_id',how='left',validate='one_to_one',indicator=True)
    result['has_recorded_lines']=result.pop('_merge').eq('both')
    for c in ('sales','units','gross_profit'):result[c]=pd.to_numeric(result[c]).fillna(0)
    result['units']=result.units.astype(int)
    result['gross_margin_pct']=pd.to_numeric(result.gross_margin_pct).where(result.sales.ne(0))
    return result


def category_months(scope):
    condition,params=predicate(scope,'i',include_category=True)
    return read(f'''SELECT substr(i.order_date,1,7) month,p.category_en category,
        SUM(i.net_line_EGP) sales,SUM(i.quantity) units,SUM(i.margin_EGP) gross_profit
        FROM sales_order_items i JOIN products_catalog p ON p.product_id=i.product_id
        WHERE {condition} GROUP BY 1,2 ORDER BY 1,2''',params)


def sales_analysis(start,end,branch=None,*,location_type=None,category=None,grain='monthly'):
    scope=filters(start,end,branch,location_type,category)
    result=period_summary(scope)
    categories=kpi.category_performance(**args(scope))
    company=kpi.overview(scope.start,scope.end)
    categories['scoped_sales_share_pct']=kpi.ratio(categories.sales,result['current']['sales'],100) if result['current']['sales'] else None
    categories['company_sales_share_pct']=kpi.ratio(categories.sales,company['sales'],100) if company['sales'] else None
    g=result['growth']
    previous=kpi.category_performance(g['previous_start'],g['previous_end'],scope.branch,location_type=scope.location_type,category=scope.category)
    changes=category_changes(categories,previous,g['comparable_coverage'])
    result.update(trends=sales_trends(**args(scope),grain=grain),categories=categories,
        category_changes=changes,category_monthly=category_months(scope),products=product_roster(scope),
        channels=kpi.sales_channel(**args(scope)),seasonality=kpi.seasonality(**args(scope)),
        yoy=yearly_comparison(scope),company_sales=company['sales'],
        declining_categories=changes.loc[changes.previous_sales.ge(MIN_CATEGORY_BASELINE) & changes.growth_pct.le(DECLINE_PCT)].copy(),
        unusual_categories=changes.loc[changes.previous_sales.ge(MIN_CATEGORY_BASELINE) & changes.growth_pct.abs().ge(CHANGE_PCT)].copy())
    return result


def location_roster(start,end,*,location_type=None,category=None):
    """All eligible master locations; no orders is a recording fact, not closure."""
    scope=filters(start,end,location_type=location_type,category=category)
    active=kpi.branch_performance(**args(scope))
    master=kpi.branches().rename(columns={'branch_name_ar':'branch','governorate_ar':'governorate'})
    if location_type:master=master[master.retail_location_type.eq(location_type)]
    # Reuse existing active-location financial KPIs and names, add zero-order master rows.
    frame=master.merge(active.drop(columns=['branch','governorate','retail_location_type','previous_sales','growth_pct']),on='branch_id',how='left',validate='one_to_one')
    condition,params=predicate(scope,'i',include_category=True)
    units=read(f'SELECT branch_id,SUM(quantity) units FROM sales_order_items i WHERE {condition} GROUP BY branch_id',params)
    frame=frame.merge(units,on='branch_id',how='left',validate='one_to_one')
    ps,pe=previous_period(scope.start,scope.end)
    source,params=kpi._orders(replace(scope,start=ps,end=pe))
    previous=read(f'WITH scoped AS ({source}) SELECT branch_id,SUM(sales) previous_sales FROM scoped GROUP BY branch_id',params)
    frame=frame.merge(previous,on='branch_id',how='left',validate='one_to_one')
    # Staffing master is not time-adjusted; never label it actual labor efficiency.
    for c in ('orders','sales','customers','gross_profit','units','previous_sales','listed_employees'):
        frame[c]=pd.to_numeric(frame[c]).fillna(0)
    for c in ('orders','customers','units'):frame[c]=frame[c].astype(int)
    frame['recorded_orders']=frame.orders.gt(0)
    frame['aov']=pd.to_numeric(frame.aov).where(frame.recorded_orders)
    frame['gross_margin_pct']=pd.to_numeric(frame.gross_margin_pct).where(frame.sales.ne(0))
    comparable=covered(scope)
    frame['growth_pct']=pd.Series([kpi.growth_percent(c,p,comparable) for c,p in zip(frame.sales,frame.previous_sales)],dtype=float)
    staffing=read('SELECT branch_id,COUNT(*) n FROM employees GROUP BY branch_id').set_index('branch_id').n
    frame['listed_employees']=frame.branch_id.map(staffing).fillna(0).astype(int)
    frame['orders_per_listed_employee']=kpi.ratio(frame.orders,frame.listed_employees).where(frame.listed_employees.gt(0))
    company=kpi.overview(scope.start,scope.end)
    frame['company_sales_share_pct']=kpi.ratio(frame.sales,company['sales'],100) if company['sales'] else None
    frame['significant_decline']=frame.growth_pct.le(DECLINE_PCT)
    return frame


def rank_locations(frame,metric='sales',ascending=False):
    if metric not in RANK_METRICS:raise ValueError('Unsupported location rank')
    if not isinstance(ascending,bool):raise ValueError('Ascending must be boolean')
    eligible=frame if metric=='growth_pct' else frame[frame.recorded_orders]
    return eligible.dropna(subset=[metric]).sort_values([metric,'branch_id'],ascending=[ascending,True]).reset_index(drop=True)


def branch_detail(start,end,branch,*,location_type=None,category=None):
    if not branch:raise ValueError('A location is required')
    return sales_analysis(start,end,branch,location_type=location_type,category=category)


def compare_two(start,end,branch_a,branch_b,*,category=None):
    """Local pair ignores global branch/type, but retains common dates/category."""
    if branch_a==branch_b:raise ValueError('Choose two distinct locations')
    a=filters(start,end,branch_a,category=category);b=filters(start,end,branch_b,category=category)
    if not branch_a or not branch_b:raise ValueError('Two known locations are required')
    left,right=period_summary(a),period_summary(b)
    keys=('sales','gross_profit','gross_margin_pct','orders','aov','growth_pct','units','customers')
    table=pd.DataFrame({'metric':keys,'location_a':[left['current'][k] for k in keys],'location_b':[right['current'][k] for k in keys]})
    trends=[];categories=[]
    for scope in (a,b):
        f=sales_trends(**args(scope),grain='monthly');f['branch_id']=scope.branch;trends.append(f)
        f=kpi.category_performance(**args(scope));f['branch_id']=scope.branch;categories.append(f)
    return {'left':left,'right':right,'table':table,'monthly':pd.concat(trends,ignore_index=True),
        'categories':pd.concat(categories,ignore_index=True),
        'locations':kpi.branches().set_index('branch_id',drop=False).loc[[branch_a,branch_b]].reset_index(drop=True)}
