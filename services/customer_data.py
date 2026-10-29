"""Internal customer history and fixed descriptive rules. Never return to the UI.

Identifiers exist only inside read-only analysis/model preparation, never public
reports, exports or saved predictions. No names/contact fields are loaded.
"""
from functools import lru_cache
from copy import deepcopy
import numpy as np
import pandas as pd
import db.connection as connection
from db.connection import read
from services import metrics as kpi
from services.filters import filters

K=5
VERSION='phase8-v1'


def version():
    p=connection.DB_PATH.resolve();s=p.stat()
    return str(p),s.st_mtime_ns,s.st_size,VERSION


@lru_cache(maxsize=8)
def _history(branch,location_type,category,stamp):
    first,last=kpi.metadata()
    if not first:return pd.DataFrame(columns=['sales_order_id','order_date','branch_id','customer_id','sales'])
    # Reuse the approved one-row-per-order/category-line contribution logic.
    scope=filters(first,last,branch,location_type,category)
    sql,params=kpi._orders(scope)
    frame=read(sql,params).drop(columns=['sales_channel'])
    frame['order_date']=pd.to_datetime(frame.order_date)
    frame['sales']=pd.to_numeric(frame.sales)
    return frame


def history(branch=None,location_type=None,category=None):
    return _history(branch,location_type,category,version()).copy()


def score_rfm(frame):
    """Fixed thresholds, never future-dependent quantiles or learned labels."""
    result=frame.copy()
    result['r_score']=np.select([result.recency_days.le(30),result.recency_days.le(90),result.recency_days.le(180),result.recency_days.le(270)],[5,4,3,2],default=1)
    result['f_score']=np.minimum(5,result.frequency).astype(int)
    result['m_score']=np.select([result.monetary.le(500),result.monetary.le(1500),result.monetary.le(3000),result.monetary.le(6000)],[1,2,3,4],default=5)
    result['c8_segment']=np.select([result.r_score.le(2),result.m_score.ge(4),result.f_score.ge(4),result.r_score.ge(4)],
        ['c8_inactive','c8_high_spend','c8_frequent','c8_recent'],default='c8_infrequent')
    return result


def features(orders,cutoff,lookback=365):
    """Feature dates [cutoff-365,cutoff); never read label/future rows."""
    cutoff=pd.Timestamp(cutoff)
    known=orders.loc[orders.customer_id.notna() & orders.order_date.lt(cutoff) & orders.order_date.ge(cutoff-pd.Timedelta(days=lookback))].copy()
    columns=['customer_id','frequency','monetary','last_purchase','first_in_window','branches','orders_90','orders_180','recency_days','activity_days','avg_gap_days','prior_90','purchase_delta','r_score','f_score','m_score','c8_segment']
    if known.empty:return pd.DataFrame(columns=columns)
    agg=known.groupby('customer_id').agg(frequency=('sales_order_id','nunique'),monetary=('sales','sum'),last_purchase=('order_date','max'),first_in_window=('order_date','min'),branches=('branch_id','nunique')).reset_index()
    for days in (90,180):
        counts=known.loc[known.order_date.ge(cutoff-pd.Timedelta(days=days))].groupby('customer_id').sales_order_id.nunique()
        agg['orders_'+str(days)]=agg.customer_id.map(counts).fillna(0).astype(int)
    agg['recency_days']=(cutoff-pd.Timedelta(days=1)-agg.last_purchase).dt.days
    agg['activity_days']=(agg.last_purchase-agg.first_in_window).dt.days
    agg['avg_gap_days']=np.where(agg.frequency.gt(1),agg.activity_days/(agg.frequency-1).clip(lower=1),0)
    agg['prior_90']=agg.orders_180-agg.orders_90
    agg['purchase_delta']=agg.orders_90-agg.prior_90
    return score_rfm(agg)


def protected(frame,count='c8_customers'):
    """Suppress entire additive family if any nonzero group is below k.

    Dropping only one row could expose its value through totals/complements.
    No customer identifiers/individual probabilities may cross this boundary.
    """
    if any(c in frame for c in ('customer_id','customer_name_ar','churn_probability','prediction')):
        raise ValueError('Private columns cannot enter a public aggregate')
    if not frame.empty and (frame[count].between(1,K-1)).any():return frame.iloc[:0].copy()
    return deepcopy(frame)
