"""Executive orchestration over approved KPIs; no replacement financial formulas.

Thresholds are descriptive management screening rules, not predictive signals.
All public entry points validate the same Phase 1 scope. No customer rows leave
this service. See docs/EXECUTIVE_DASHBOARD.md for scope and comparison policy.
"""
from calendar import monthrange
from datetime import date
import pandas as pd
from services import metrics as kpi
from services.filters import filters, predicate
from db.connection import read

DECLINE_PCT = -10.0
CATEGORY_CHANGE_PCT = 25.0
CATEGORY_BASELINE_EGP = 10000.0
HIGH_RISK = .7
ATTENTION_RISK = .4
COMPARISON_METRICS = ('sales','gross_profit','orders','aov','customers','branches','gross_margin_pct')


def _args(scope):
    return {'start':scope.start,'end':scope.end,'branch':scope.branch,
            'location_type':scope.location_type,'category':scope.category}


def _period(start, end):
    return f'{start} → {end}'


def comparison(current, previous, covered):
    """Use approved growth_percent; margin absolute change is percentage points.

    Incomplete coverage suppresses previous values AND both changes. Zero or
    negative previous denominators suppress percentage change, not valid absolute
    changes. Empty-period AOV and zero-sales margins are undefined, not zero.
    """
    rows=[]
    for key in COMPARISON_METRICS:
        def value(values):
            if (key=='aov' and not values['orders']) or (key=='gross_margin_pct' and not values['sales']):
                return None
            return values[key]
        now,before=value(current),value(previous) if covered else None
        change=now-before if now is not None and before is not None else None
        percent=kpi.growth_percent(now,before,covered) if change is not None else None
        state='unavailable' if change is None else ('positive' if change>0 else 'negative' if change<0 else 'unchanged')
        rows.append({'metric':key,'current':now,'previous':before,'absolute_change':change,
                     'percentage_change':percent,'state':state})
    return pd.DataFrame(rows)


def summary(start, end, branch=None, *, location_type=None, category=None):
    """Shared light executive scorecards for dashboard and local assistant."""
    scope=filters(start,end,branch,location_type,category)
    values=kpi.overview(**_args(scope))
    growth=kpi.sales_growth(**_args(scope))
    ps,pe=growth['previous_start'],growth['previous_end']
    previous=kpi.overview(ps,pe,scope.branch,location_type=scope.location_type,category=scope.category)
    month,stock=kpi.inventory_snapshot(scope.end,scope.branch,location_type=scope.location_type,category=scope.category)
    inventory=kpi.inventory_summary(stock) if month else dict.fromkeys(
        ('stock_units','stock_value','high_risk_categories','estimated_30d_replenishment_units'))
    # Network and registered master are intentionally company-wide, not purchasers.
    network=kpi.branches().retail_location_type.value_counts().to_dict()
    current=dict(values,growth_pct=growth['growth_pct'],**inventory)
    if not values['orders']:
        current['aov']=None
    if not values['sales']:
        current['gross_margin_pct']=None
    current['registered_customers']=kpi.registered_customers(scope.end)
    return {'current':current,'previous':previous,'growth':growth,'stock_month':month,'stock':stock,
            'network':network,'scope':scope,'comparison':comparison(values,previous,growth['comparable_coverage']),
            'current_period':_period(scope.start,scope.end),'previous_period':_period(ps,pe)}


def monthly_performance(scope):
    """Header/scoped-line sales + separate item GP, joined at month grain only."""
    monthly=kpi.sales_monthly(**_args(scope))
    condition,params=predicate(scope,'i',include_category=True)
    profits=read(f'''SELECT substr(i.order_date,1,7) month,
        SUM(i.margin_EGP) gross_profit FROM sales_order_items i
        WHERE {condition} GROUP BY 1 ORDER BY 1''',params)
    return monthly.merge(profits,on='month',how='left',validate='one_to_one')


def category_changes(current, previous, covered):
    """Include disappeared categories as zero current sales, only when covered."""
    result=current[['category','sales']].merge(previous[['category','sales']].rename(columns={'sales':'previous_sales'}),
        on='category',how='outer',validate='one_to_one')
    for column in ('sales','previous_sales'):
        result[column]=pd.to_numeric(result[column]).fillna(0)
    result['growth_pct']=pd.Series([kpi.growth_percent(c,p,covered) for c,p in zip(result.sales,result.previous_sales)],dtype=float)
    return result


def insight_rules(growth, branches, stock, changes, partial_months):
    """Machine-readable evidence only; UI translates fixed templates, never AI."""
    alerts=[]
    if not growth['comparable_coverage']:
        alerts.append({'code':'coverage_unavailable','severity':'warning'})
    elif growth['growth_pct'] is None:
        alerts.append({'code':'zero_baseline','severity':'info'})
    elif growth['growth_pct']<=DECLINE_PCT:
        alerts.append({'code':'revenue_decline','severity':'warning','value':growth['growth_pct']})
    negative=branches[branches.growth_pct.lt(0)]
    if not negative.empty:
        alerts.append({'code':'negative_locations','severity':'warning','count':len(negative),
                       'value':float(negative.growth_pct.min())})
    high=stock[stock.risk_score.ge(HIGH_RISK)]
    if not high.empty:
        alerts.append({'code':'inventory_attention','severity':'warning','count':len(high)})
    unusual=changes[changes.previous_sales.ge(CATEGORY_BASELINE_EGP) & changes.growth_pct.abs().ge(CATEGORY_CHANGE_PCT)]
    for row in unusual.sort_values('growth_pct').head(5).itertuples():
        alerts.append({'code':'category_change','severity':'info','category':row.category,'value':row.growth_pct,
                       'previous_sales':row.previous_sales,'sales':row.sales})
    if partial_months:
        alerts.append({'code':'partial_months','severity':'info','count':partial_months})
    if stock.empty:
        alerts.append({'code':'stock_unavailable','severity':'warning'})
    if not alerts:
        alerts.append({'code':'no_threshold_alert','severity':'info'})
    return alerts


def dashboard(start,end,branch=None,*,location_type=None,category=None):
    result=summary(start,end,branch,location_type=location_type,category=category)
    scope=result['scope'];args=_args(scope)
    monthly=monthly_performance(scope)
    categories=kpi.category_performance(**args)
    previous_categories=kpi.category_performance(result['growth']['previous_start'],result['growth']['previous_end'],
        scope.branch,location_type=scope.location_type,category=scope.category)
    changes=category_changes(categories,previous_categories,result['growth']['comparable_coverage'])
    # Explicit branch keyword: executive rankings honor selected location, unlike
    # the independent all-location benchmark page. Active locations only.
    branches=kpi.branch_performance(**args)
    branches['gross_profit_contribution_pct']=kpi.ratio(branches.gross_profit,result['current']['gross_profit'],100) if result['current']['gross_profit'] else None
    first,last=kpi.metadata()
    partial=int((~monthly.is_complete_month).sum())
    # Empty months can still have a partial selection; expose the boundary policy.
    a,b=date.fromisoformat(scope.start),date.fromisoformat(scope.end)
    partial_boundary=a.day!=1 or b.day!=monthrange(b.year,b.month)[1] or (first and a<first) or (last and b>last)
    result.update({'monthly':monthly,'categories':categories,'category_changes':changes,'branches':branches,
        'products':kpi.product_performance(**args,sort='units',limit=8),'channels':kpi.sales_channel(**args),
        'partial_months':partial,'partial_boundary':bool(partial_boundary),
        'attention':result['stock'].loc[result['stock'].risk_score.ge(ATTENTION_RISK) | result['stock'].suggested_30d_replenishment.gt(0)].copy()})
    result['alerts']=insight_rules(result['growth'],branches,result['stock'],changes,partial or int(bool(partial_boundary)))
    return result


def assistant_summary(context):
    """Verified extra local report; legacy engine and its allowlist stay intact."""
    result=summary(**context)
    row=result['current'].copy()
    row['stock_month']=result['stock_month']
    return {'meta':{'tool':'executive_summary','period':f"{result['scope'].start} to {result['scope'].end}",
        'branch_id':result['scope'].branch or 'all','category':result['scope'].category,
        'location_type':result['scope'].location_type,'previous_period':result['previous_period'],
        'comparable_coverage':result['growth']['comparable_coverage'],
        'source':'Same executive scorecards service as dashboard; registered master is company-wide'},
        'data':[row],'plot':None}
