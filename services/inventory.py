"""Phase 6 recorded monthly category balances and explicitly labelled heuristics.

Uses the approved read-only connection/filter/quantity foundation; never changes
financial KPIs or interprets transfers as a full movement ledger.
"""
from calendar import monthrange
from dataclasses import dataclass,asdict
from datetime import date,timedelta
import math
import pandas as pd
import numpy as np
from db.connection import read
from services.filters import filters,predicate
from services import metrics as kpi

STATUSES=('Completed','In transit','Partially received')
RISK_HIGH=.7
RISK_MEDIUM=.4
CONCENTRATION_PCT=25
STOCK_CHANGE_PCT=25


@dataclass(frozen=True)
class Planning:
    lookback_days:int=90
    horizon_days:int=30
    low_cover_days:int=14
    high_cover_days:int=120
    high_stock_units:int=500
    slow_daily_units:float=1

    def __post_init__(self):
        for key,lo,hi in (('lookback_days',7,365),('horizon_days',1,180),('low_cover_days',1,365),('high_cover_days',1,730),('high_stock_units',1,100000000)):
            value=getattr(self,key)
            if isinstance(value,bool) or not isinstance(value,int) or not lo<=value<=hi:raise ValueError('Invalid planning parameter: '+key)
        if self.high_cover_days<self.low_cover_days:raise ValueError('High cover must be >= low cover')
        if isinstance(self.slow_daily_units,bool) or not isinstance(self.slow_daily_units,(int,float)) or not math.isfinite(self.slow_daily_units) or self.slow_daily_units<0:raise ValueError('Invalid slow daily units')


def month_end(month):
    a=date.fromisoformat(month+'-01');return a.replace(day=monthrange(a.year,a.month)[1])


def month_cutoff(end):
    end=date.fromisoformat(str(end))
    return str(end if end==month_end(str(end)[:7]) else end.replace(day=1)-timedelta(days=1))[:7]


def warehouses():
    return read('SELECT warehouse_id,warehouse_label,warehouse_kind FROM warehouses ORDER BY warehouse_id')


def _stock_predicate(scope,kind,warehouse=None):
    if kind not in ('Branch','Warehouse'):raise ValueError('Unsupported stock location kind')
    if kind=='Branch' and warehouse:raise ValueError('Warehouse selector requires warehouse scope')
    if warehouse and warehouse not in set(warehouses().warehouse_id):raise ValueError('Unknown warehouse')
    clauses=['s.stock_location_type=?'];params=[kind]
    if scope.category:clauses.append('s.product_category=?');params.append(scope.category)
    if kind=='Branch':
        if scope.branch:clauses.append('s.stock_location_id=?');params.append(scope.branch)
        if scope.location_type:
            clauses.append('EXISTS (SELECT 1 FROM branches b WHERE b.branch_id=s.stock_location_id AND b.retail_location_type=?)');params.append(scope.location_type)
    elif warehouse:clauses.append('s.stock_location_id=?');params.append(warehouse)
    return ' AND '.join(clauses),params


def stock_rows(scope,kind='Branch',warehouse=None,month=None):
    condition,params=_stock_predicate(scope,kind,warehouse)
    cutoff=month_cutoff(scope.end)
    available=read(f'SELECT DISTINCT year_month FROM monthly_stock s WHERE {condition} AND year_month<=? ORDER BY 1',[*params,cutoff]).year_month.tolist()
    chosen=month if month is not None else available[-1] if available else None
    if month is not None and month not in available:chosen=None
    columns=['month','location_id','stock_kind','category','stock_units','stock_value','recorded_risk','location','retail_location_type','risk_label']
    if not chosen:return None,pd.DataFrame(columns=columns),available
    frame=read(f'''SELECT s.year_month month,s.stock_location_id location_id,s.stock_location_type stock_kind,
         s.product_category category,s.closing_units stock_units,s.closing_stock_value_EGP stock_value,
         s.stockout_risk_score recorded_risk FROM monthly_stock s WHERE {condition} AND year_month=?''',[*params,chosen])
    master=kpi.branches().rename(columns={'branch_id':'location_id','branch_name_ar':'location'}) if kind=='Branch' else warehouses().rename(columns={'warehouse_id':'location_id','warehouse_label':'location'})
    if kind=='Warehouse':master['retail_location_type']='Warehouse'
    frame=frame.merge(master[['location_id','location','retail_location_type']],on='location_id',how='left',validate='many_to_one')
    if frame.recorded_risk.isna().any() or not frame.recorded_risk.between(0,1).all():raise ValueError('Invalid recorded risk data')
    frame['risk_label']=np.select([frame.recorded_risk.ge(RISK_HIGH),frame.recorded_risk.ge(RISK_MEDIUM)],['High','Medium'],default='Low')
    return chosen,frame,available


def category_totals(frame):
    result=frame.groupby('category',as_index=False).agg(stock_units=('stock_units','sum'),stock_value=('stock_value','sum'),
        mean_recorded_risk=('recorded_risk','mean'),max_recorded_risk=('recorded_risk','max'),recorded_locations=('location_id','nunique'),
        high_risk_combinations=('risk_label',lambda x:int(x.eq('High').sum())))
    return result


def add_estimates(frame,scope,month,planning):
    """Matched branch/category demand at snapshot month-end; never warehouse demand."""
    frame=frame.copy()
    end=month_end(month) if month else date.fromisoformat(scope.end)
    start=end-timedelta(days=planning.lookback_days-1)
    window_complete=bool(month and kpi._period_covered(str(start),str(end)))
    window=dict(start=str(start),end=str(end),days=planning.lookback_days,complete=window_complete)
    for col in ('sold_units','daily_units','cover_days','estimated_replenishment'):frame[col]=float('nan')
    if month and len(frame) and frame.stock_kind.eq('Branch').all():
        demand_scope=filters(str(start),str(end),scope.branch,scope.location_type,scope.category)
        condition,params=predicate(demand_scope,'i',include_category=True)
        sold=read(f'''SELECT i.branch_id location_id,p.category_en category,SUM(i.quantity) sold_units
            FROM sales_order_items i JOIN products_catalog p ON p.product_id=i.product_id
            WHERE {condition} GROUP BY 1,2''',params)
        frame=frame.drop(columns='sold_units').merge(sold,on=['location_id','category'],how='left',validate='one_to_one')
        frame['sold_units']=pd.to_numeric(frame.sold_units).fillna(0)
        if window_complete:
            frame['daily_units']=frame.sold_units/planning.lookback_days
            frame['cover_days']=frame.stock_units/frame.daily_units.replace(0,np.nan)
            frame['estimated_replenishment']=np.ceil((frame.daily_units*planning.horizon_days-frame.stock_units).clip(lower=0))
    frame['low_cover']=frame.cover_days.lt(planning.low_cover_days)
    frame['slow_moving_proxy']=frame.stock_units.ge(planning.high_stock_units) & frame.daily_units.lt(planning.slow_daily_units)
    frame['high_cover_proxy']=frame.stock_units.gt(0) & frame.cover_days.ge(planning.high_cover_days)
    frame['replenishment_attention']=frame.estimated_replenishment.gt(0)
    totals=frame.groupby('category').stock_units.transform('sum')
    frame['category_location_share_pct']=kpi.ratio(frame.stock_units,totals,100).where(totals.ne(0))
    return frame,window


def distribution(frame):
    if frame.empty:return pd.DataFrame(columns=['category','stock_units','recorded_locations','max_location_share_pct','min_cover_days','max_cover_days','concentration_flag','imbalance_candidate'])
    result=frame.groupby('category',as_index=False).agg(stock_units=('stock_units','sum'),recorded_locations=('location_id','nunique'),
        max_location_share_pct=('category_location_share_pct','max'),min_cover_days=('cover_days','min'),max_cover_days=('cover_days','max'))
    result['concentration_flag']=result.recorded_locations.ge(2) & result.max_location_share_pct.ge(CONCENTRATION_PCT)
    return result


def history(scope,kind='Branch',warehouse=None):
    condition,params=_stock_predicate(scope,kind,warehouse)
    return read(f'''SELECT year_month month,SUM(closing_units) stock_units,SUM(closing_stock_value_EGP) stock_value,
        AVG(stockout_risk_score) mean_recorded_risk,MAX(stockout_risk_score) max_recorded_risk,
        SUM(CASE WHEN stockout_risk_score>=? THEN 1 ELSE 0 END) high_risk_combinations
        FROM monthly_stock s WHERE {condition} AND year_month BETWEEN ? AND ? GROUP BY 1 ORDER BY 1''',
        [RISK_HIGH,*params,scope.start[:7],month_cutoff(scope.end)])


def category_changes(current,previous):
    a=category_totals(current)[['category','stock_units']];b=category_totals(previous)[['category','stock_units']]
    result=a.merge(b.rename(columns={'stock_units':'previous_stock_units'}),on='category',how='outer',validate='one_to_one')
    result['stock_unit_change']=result.stock_units-result.previous_stock_units
    result['stock_change_pct']=kpi.ratio(result.stock_unit_change,result.previous_stock_units,100).where(result.previous_stock_units.gt(0))
    result['notable_stock_change']=result.stock_change_pct.abs().ge(STOCK_CHANGE_PCT)
    return result


def network_distribution(sales_data,warehouse_data):
    """Displayed scoped sales-location stock versus explicitly separate warehouses.

    No warehouse-to-branch allocation is implied. Missing observations or different
    snapshot months make a combined share unavailable, rather than invented zero.
    """
    a=sales_data['categories'][['category','stock_units']].rename(columns={'stock_units':'sales_location_stock_units'})
    b=warehouse_data['categories'][['category','stock_units']].rename(columns={'stock_units':'warehouse_stock_units'})
    frame=a.merge(b,on='category',how='outer',validate='one_to_one')
    total=frame.sales_location_stock_units+frame.warehouse_stock_units
    same_month=bool(sales_data['month'] and sales_data['month']==warehouse_data['month'])
    frame['displayed_warehouse_share_pct']=kpi.ratio(frame.warehouse_stock_units,total,100).where(total.gt(0) & total.notna()) if same_month else None
    frame['warehouse_concentration_candidate']=frame.displayed_warehouse_share_pct.ge(80)
    return frame


def dashboard(start,end,branch=None,*,location_type=None,category=None,kind='Branch',warehouse=None,planning=None):
    scope=filters(start,end,branch,location_type,category);planning=planning or Planning()
    if not isinstance(planning,Planning):raise ValueError('Planning object required')
    month,raw,available=stock_rows(scope,kind,warehouse)
    rows,window=add_estimates(raw,scope,month,planning)
    previous_month=str(date.fromisoformat(month+'-01')-timedelta(days=1))[:7] if month else None
    _,previous,_=stock_rows(scope,kind,warehouse,previous_month) if month else (None,raw.copy(),[])
    categories=category_totals(rows)
    dist=distribution(rows)
    dist['imbalance_candidate']=dist.recorded_locations.ge(2) & dist.min_cover_days.lt(planning.low_cover_days) & dist.max_cover_days.ge(planning.high_cover_days)
    summary=dict(stock_units=int(rows.stock_units.sum()),stock_value=float(rows.stock_value.sum()),
        high_risk_combinations=int(rows.risk_label.eq('High').sum()),high_risk_categories=int(categories.high_risk_combinations.gt(0).sum()),
        low_cover_combinations=int(rows.low_cover.sum()),estimated_replenishment=float(rows.estimated_replenishment.sum(min_count=1)))
    if kind=='Warehouse' or not window['complete']:summary['low_cover_combinations']=None
    if month is None:summary={key:None for key in summary}
    return dict(scope=scope,kind=kind,warehouse=warehouse,month=month,available_months=available,
        rows=rows,categories=categories,distribution=dist,summary=summary,window=window,planning=asdict(planning),
        history=history(scope,kind,warehouse),category_changes=category_changes(rows,previous),
        high_risk_rows=rows.loc[rows.risk_label.eq('High')].copy(),low_cover_rows=rows.loc[rows.low_cover].copy(),
        slow_rows=rows.loc[rows.slow_moving_proxy | rows.high_cover_proxy].copy())


def compare_two(start,end,a,b,*,category=None,planning=None):
    if not a or not b or a==b:raise ValueError('Two distinct known sales locations required')
    left=dashboard(start,end,a,category=category,planning=planning);right=dashboard(start,end,b,category=category,planning=planning)
    if left['month']!=right['month']:raise ValueError('No common latest snapshot; comparison unavailable')
    frame=pd.concat([left['rows'],right['rows']],ignore_index=True)
    return dict(month=left['month'],rows=frame,locations=kpi.branches().set_index('branch_id',drop=False).loc[[a,b]].reset_index(drop=True))


def transfer_analysis(start,end,branch=None,*,location_type=None,category=None,warehouse=None,status=None):
    scope=filters(start,end,branch,location_type,category)
    if status is not None and status not in STATUSES:raise ValueError('Unknown transfer status')
    if warehouse and warehouse not in set(warehouses().warehouse_id):raise ValueError('Unknown warehouse')
    clauses=['t.transfer_date BETWEEN ? AND ?'];params=[scope.start,scope.end]
    if branch:clauses.append('t.destination_branch_id=?');params.append(branch)
    if location_type:clauses.append('EXISTS (SELECT 1 FROM branches b WHERE b.branch_id=t.destination_branch_id AND b.retail_location_type=?)');params.append(location_type)
    if warehouse:clauses.append('t.source_warehouse_id=?');params.append(warehouse)
    if status:clauses.append('t.transfer_status=?');params.append(status)
    if category:
        clauses.append('EXISTS (SELECT 1 FROM inventory_transfer_items l JOIN sku_variants v ON v.sku_id=l.sku_id JOIN products_catalog p ON p.product_id=v.product_id WHERE l.transfer_id=t.transfer_id AND p.category_en=?)');params.append(category)
    condition=' AND '.join(clauses)
    headers=read(f'''SELECT t.transfer_id,substr(t.transfer_date,1,7) month,t.source_warehouse_id,t.destination_branch_id,
        t.transfer_status,t.transport_cost_EGP transport_cost FROM inventory_transfers t WHERE {condition}''',params)
    lines=read(f'''SELECT t.transfer_id,p.category_en category,SUM(l.quantity_units) transfer_units
        FROM inventory_transfers t JOIN inventory_transfer_items l ON l.transfer_id=t.transfer_id
        JOIN sku_variants v ON v.sku_id=l.sku_id JOIN products_catalog p ON p.product_id=v.product_id
        WHERE {condition}'''+(' AND p.category_en=?' if category else '')+' GROUP BY 1,2',[*params,*([category] if category else [])])
    quantities=lines.groupby('transfer_id',as_index=False).transfer_units.sum()
    events=headers.merge(quantities,on='transfer_id',how='left',validate='one_to_one')
    events['transfer_units']=pd.to_numeric(events.transfer_units).fillna(0)
    def grouped(keys):
        return events.groupby(keys,as_index=False).agg(transfer_count=('transfer_id','count'),transfer_units=('transfer_units','sum'),transport_cost=('transport_cost','sum'))
    return dict(events=events,monthly=grouped(['month','transfer_status']),statuses=grouped(['transfer_status']),
        sources=grouped(['source_warehouse_id']),destinations=grouped(['destination_branch_id']),
        categories=lines.groupby('category',as_index=False).transfer_units.sum(),
        summary=dict(transfer_count=len(events),transfer_units=float(events.transfer_units.sum()),transport_cost=float(headers.transport_cost.sum())))
