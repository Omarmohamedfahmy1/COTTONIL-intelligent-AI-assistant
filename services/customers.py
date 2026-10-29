"""Authoritative aggregate-only Phase 8 customer behavior; no branch ownership."""
from copy import deepcopy
from functools import lru_cache
from time import perf_counter
import numpy as np
import pandas as pd
from services import customer_data as data,metrics as kpi
from services.filters import filters,iso_date,complete_month_bounds
from db.connection import read


def audit():
    orders=data.history();known=orders.loc[orders.customer_id.notna()]
    master=read('SELECT customer_id,customer_segment,joined_date_iso FROM v_customers_normalized')
    joined=known.merge(master[['customer_id','joined_date_iso']],on='customer_id',how='left',validate='many_to_one')
    counts=known.groupby('customer_id').sales_order_id.nunique()
    return dict(registered_customers=len(master),duplicate_master_ids=int(master.customer_id.duplicated().sum()),
        identified_purchasers=int(known.customer_id.nunique()),orders=len(orders),identified_orders=len(known),anonymous_orders=int(orders.customer_id.isna().sum()),
        identified_order_coverage_pct=100*len(known)/len(orders) if len(orders) else None,
        total_sales=float(orders.sales.sum()),identified_sales=float(known.sales.sum()),anonymous_sales=float(orders.loc[orders.customer_id.isna(),'sales'].sum()),
        missing_registered_matches=int(joined.joined_date_iso.isna().sum()),orders_before_registration=int((joined.order_date<pd.to_datetime(joined.joined_date_iso)).sum()),
        source_start=str(orders.order_date.min().date()),source_end=str(orders.order_date.max().date()),registration_start=master.joined_date_iso.min(),registration_end=master.joined_date_iso.max(),
        multiple_location_purchasers=int(known.groupby('customer_id').branch_id.nunique().gt(1).sum()),repeat_purchasers=int(counts.gt(1).sum()),
        registered_never_observed=int((~master.customer_id.isin(known.customer_id)).sum()),master_segments=master.groupby('customer_segment').size().to_dict(),
        limitations='Identified behavior only; anonymous orders never allocated. First purchase means first recorded, not true acquisition. No names loaded. Location filters mean purchasing behavior, not ownership.')


def _group(frame,keys):
    if frame.empty:return pd.DataFrame(columns=[*keys,'c8_customers','c8_orders','c8_revenue'])
    grouped=frame.groupby(keys,observed=True).agg(c8_customers=('customer_id','nunique'),c8_orders=('frequency','sum'),c8_revenue=('monetary','sum')).reset_index()
    return data.protected(grouped)


def cohorts(known,start,end,source_start,source_end,max_age=12):
    """First recorded purchase within selected scope, full calendar cells only."""
    if known.empty:return pd.DataFrame(),pd.DataFrame()
    bounds=complete_month_bounds(max(start,source_start),min(end,source_end))
    if not bounds:return pd.DataFrame(),pd.DataFrame()
    first=known.groupby('customer_id').order_date.min();acquisition=first.dt.to_period('M')
    activity=known.assign(month=known.order_date.dt.to_period('M')).drop_duplicates(['customer_id','month'])
    rows=[];summary=[]
    for cohort in pd.period_range(bounds[0][:7],bounds[1][:7],freq='M'):
        ids=set(acquisition.index[acquisition.eq(cohort)])
        if len(ids)<data.K:continue
        current=known.loc[known.customer_id.isin(ids)];purchases=current.sort_values(['customer_id','order_date','sales_order_id']).copy()
        purchases['purchase_number']=purchases.groupby('customer_id').cumcount()+1
        second=purchases.loc[purchases.purchase_number.eq(2)].set_index('customer_id').order_date
        # Followup is reported, not a survival-adjusted estimate for recent cohorts.
        delays=(second-first.reindex(second.index)).dt.days
        cell_rows=[];suppress=False
        for age in range(max_age+1):
            month=cohort+age;observed=month<=pd.Period(bounds[1][:7],freq='M')
            count=int(activity.loc[activity.customer_id.isin(ids) & activity.month.eq(month),'customer_id'].nunique()) if observed else None
            if count is not None and (0<count<data.K or 0<len(ids)-count<data.K):suppress=True
            cell_rows.append(dict(c8_cohort=str(cohort),c8_age=age,c8_month=str(month),c8_cohort_size=len(ids),c8_active=count,c8_retention_pct=100*count/len(ids) if observed else None,c8_observed=observed))
        if suppress:continue
        rows.extend(cell_rows)
        nsecond=len(second)
        # Protect second-purchase aggregates and their complement as one family.
        if (0<nsecond<data.K) or (0<len(ids)-nsecond<data.K):continue
        summary.append(dict(c8_cohort=str(cohort),c8_customers=len(ids),c8_repeat_customers=nsecond,c8_repeat_rate=100*nsecond/len(ids),
            c8_median_second_days=float(delays.median()) if nsecond>=data.K else None,c8_frequency=len(current)/len(ids),c8_followup_days=(pd.Timestamp(end)-cohort.end_time.normalize()).days))
    return pd.DataFrame(rows),pd.DataFrame(summary)


@lru_cache(maxsize=16)
def _dashboard(start,end,branch,location_type,category,version):
    started=perf_counter();scope=filters(start,end,branch,location_type,category)
    first,last=kpi.metadata();observed_end=min(end,last.isoformat()) if last else end
    all_orders=data.history(branch,location_type,category)
    through=all_orders.loc[all_orders.order_date.le(pd.Timestamp(observed_end))]
    period=through.loc[through.order_date.ge(pd.Timestamp(start))]
    known=through.loc[through.customer_id.notna()].copy();active=period.loc[period.customer_id.notna()].copy()
    n=int(active.customer_id.nunique());stats=dict(c8_registered=kpi.registered_customers(observed_end),c8_identified=n,c8_anonymous_orders=int(period.customer_id.isna().sum()),c8_orders=len(period),
        c8_identified_orders=len(active),c8_identification_pct=100*len(active)/len(period) if len(period) else None,c8_identified_revenue=float(active.sales.sum()),c8_anonymous_revenue=float(period.loc[period.customer_id.isna(),'sales'].sum()))
    global_known=data.history();global_known=global_known.loc[global_known.customer_id.notna() & global_known.order_date.le(pd.Timestamp(observed_end))]
    company_first=global_known.groupby('customer_id').order_date.min()
    purchasers=active.groupby('customer_id').agg(frequency=('sales_order_id','nunique'),monetary=('sales','sum')).reset_index()
    new=int(purchasers.customer_id.map(company_first).ge(pd.Timestamp(start)).sum());repeat=int(purchasers.frequency.gt(1).sum())
    stats.update(c8_new=new,c8_returning=n-new,c8_repeat_customers=repeat,c8_repeat_rate=100*repeat/n if n else None,c8_frequency=len(active)/n if n else None,
        c8_average_spend=float(active.sales.sum()/n) if n else None,c8_revenue_share=100*active.sales.sum()/period.sales.sum() if period.sales.sum()>0 else None)
    # Prevent small scope or binary complement disclosure on this customer page.
    if 0<n<data.K:
        stats={key:value if key=='c8_registered' else None for key,value in stats.items()}
    elif any(0<x<data.K for x in (new,n-new,repeat,n-repeat)):
        for key in ('c8_new','c8_returning','c8_repeat_customers','c8_repeat_rate'):stats[key]=None
    cutoff=pd.Timestamp(observed_end)+pd.Timedelta(days=1)
    rfm=data.features(known,cutoff)
    rfm_public=_group(rfm,['c8_segment'])
    master=read('SELECT customer_id,customer_segment FROM customers')
    descriptive=_group(purchasers.merge(master,on='customer_id',how='left').rename(columns={'customer_segment':'c8_master_segment'}),['c8_master_segment'])
    recency=known.groupby('customer_id').order_date.max().reset_index()
    recency['days']=(pd.Timestamp(observed_end)-recency.order_date).dt.days
    recency['c8_recency_band']=pd.cut(recency.days,[-1,30,90,180,365,float('inf')],labels=['c8_days30','c8_days90','c8_days180','c8_days365','c8_over365'])
    recency_public=data.protected(recency.groupby('c8_recency_band',observed=True).size().rename('c8_customers').reset_index())
    trend=[];small_month=False
    for month,group in period.groupby(period.order_date.dt.to_period('M')):
        identified=group.loc[group.customer_id.notna()];unique=identified.customer_id.nunique();freq=identified.groupby('customer_id').sales_order_id.nunique();repeats=int(freq.gt(1).sum())
        if unique<data.K or (0<repeats<data.K) or (0<unique-repeats<data.K):small_month=True;continue
        trend.append(dict(month=str(month),c8_customers=int(unique),c8_orders=len(identified),c8_frequency=len(identified)/unique,c8_repeat_rate=100*repeats/unique,
            c8_revenue=float(identified.sales.sum()),is_complete_month=month.start_time.date()>=max(pd.Timestamp(start).date(),first) and month.end_time.date()<=pd.Timestamp(observed_end).date()))
    monthly=pd.DataFrame() if small_month else pd.DataFrame(trend)
    retention,cohort_summary=cohorts(known,start,observed_end,first.isoformat(),last.isoformat()) if start<=observed_end else (pd.DataFrame(),pd.DataFrame())
    prior=data.features(known,cutoff-pd.Timedelta(days=90));movement=pd.DataFrame();change=pd.DataFrame()
    if not prior.empty:
        matched=prior[['customer_id','c8_segment','frequency']].rename(columns={'c8_segment':'c8_previous_segment','frequency':'previous_frequency'}).merge(rfm[['customer_id','c8_segment','frequency']],on='customer_id',how='left',validate='one_to_one')
        matched['c8_segment']=matched.c8_segment.fillna('c8_outside_window');matched['frequency']=matched.frequency.fillna(0)
        movement=data.protected(matched.groupby(['c8_previous_segment','c8_segment']).size().rename('c8_customers').reset_index())
        change=data.protected(matched.groupby('c8_previous_segment').agg(c8_customers=('customer_id','size'),c8_previous_frequency=('previous_frequency','mean'),c8_current_frequency=('frequency','mean')).reset_index())
        if not change.empty:change['c8_frequency_change']=change.c8_current_frequency-change.c8_previous_frequency
    return dict(summary=stats,rfm=rfm_public,master_segments=descriptive,recency=recency_public,activity=monthly,retention=retention,cohorts=cohort_summary,movement=movement,segment_change=change,
        meta=dict(start=start,end=end,observed_end=observed_end,cutoff=str(cutoff.date()),rfm_start=str((cutoff-pd.Timedelta(days=365)).date()),privacy_k=data.K,
            scope_policy='Purchasing behavior in selected scope; no exclusive branch ownership. New/returning uses first company-wide recorded purchase; retention uses first recorded scoped purchase.',
            rfm_policy='365-day window ending observed end, independent of display start; fixed descriptive thresholds, not churn probabilities.',small_scope_suppressed=0<n<data.K),elapsed_seconds=perf_counter()-started)


def dashboard(start,end,branch=None,*,location_type=None,category=None):
    return deepcopy(_dashboard(iso_date(start),iso_date(end),branch,location_type,category,data.version()))
