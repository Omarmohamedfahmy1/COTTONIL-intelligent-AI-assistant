"""Leakage-aware monthly forecasting and customer scoring.
Forecast: seasonal-naive vs ridge trend+month effects, last 12 FULL months as holdout.
Customer model: train 2024-10 cutoff -> next 180/365d labels; evaluate on 2025-10,
score 2026-10. Churn=NO observed purchase in next 180d for identified
customers with a transaction in prior 365d. CLV is future 365d SALES
(not accounting profit or full lifetime); explicitly labeled proxy.
"""
from __future__ import annotations
from datetime import date, timedelta
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import roc_auc_score, average_precision_score, mean_absolute_error
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from analytics import DB, read

OUT = DB.parent


def design(periods, origin):
    t=np.array([p.ordinal-origin for p in periods],dtype=float)
    seasonal=np.zeros((len(t),12))
    for i,p in enumerate(periods):seasonal[i,p.month-1]=1
    return np.column_stack([t/12,seasonal])


def forecast(months: pd.DataFrame, horizon=6):
    """Train/baseline on a univariate monthly series; no future feature leakage."""
    df=months.copy();df['period']=pd.PeriodIndex(df.month,freq='M')
    df=df.sort_values('period').reset_index(drop=True)
    y=df.value.to_numpy(dtype=float)
    if len(y)<36:raise ValueError('At least 36 complete monthly observations are needed')
    n=len(y);split=n-12;ps=list(df.period)
    origin=ps[0].ordinal
    X=design(ps,origin)
    ridge=Ridge(alpha=8.0).fit(X[:split],y[:split])
    pred_ridge=np.maximum(0,ridge.predict(X[split:]))
    pred_seasonal=np.maximum(0,y[split-12:n-12])
    denom=max(1,float(np.abs(y[split:]).sum()))
    e_ridge=float(np.abs(y[split:]-pred_ridge).sum()/denom*100)
    e_seas=float(np.abs(y[split:]-pred_seasonal).sum()/denom*100)
    winner='Seasonal naive (previous year)' if e_seas<=e_ridge else 'Ridge trend + seasonality'
    future=pd.period_range(ps[-1]+1,periods=horizon,freq='M')
    if winner.startswith('Seasonal'):
        history=list(y); yp=[]
        for k in range(horizon):
            yp.append(max(0,float(history[-12])))
            history.append(yp[-1])
    else:
        fitted=Ridge(alpha=8.0).fit(X,y)
        yp=np.maximum(0,fitted.predict(design(list(future),origin))).tolist()
    return dict(model=winner,validation_wape_pct=round(min(e_ridge,e_seas),2),
                ridge_wape_pct=round(e_ridge,2),seasonal_naive_wape_pct=round(e_seas,2),
                evaluated_months=ps[split].strftime('%Y-%m')+' to '+ps[-1].strftime('%Y-%m'),
                actual=df[['month','value']].to_dict('records'),
                predicted=[{'month':str(m),'value':round(float(v),2)} for m,v in zip(future,yp)])


def load_orders():
    df=read('''SELECT customer_id, order_date, net_before_tax_EGP, branch_id
       FROM sales_orders WHERE customer_id IS NOT NULL ORDER BY order_date''')
    df['order_date']=pd.to_datetime(df.order_date)
    df['sales']=df.net_before_tax_EGP.astype(float)
    return df[['customer_id','order_date','sales','branch_id']]


def customer_features(df, as_of, horizon=365):
    cutoff=pd.Timestamp(as_of)
    prior=df[(df.order_date<=cutoff)&(df.order_date>cutoff-pd.Timedelta(days=365))].copy()
    # Only known purchasers active in past 365 days, avoids claiming all 85k are eligible.
    agg=prior.groupby('customer_id').agg(
        orders_365=('sales','size'),spend_365=('sales','sum'),
        avg_order=('sales','mean'),last_order=('order_date','max'),
        first_seen_365=('order_date','min'), branches_365=('branch_id','nunique')).reset_index()
    last90=prior[prior.order_date>cutoff-pd.Timedelta(days=90)].groupby('customer_id').size()
    last180=prior[prior.order_date>cutoff-pd.Timedelta(days=180)].groupby('customer_id').size()
    agg['orders_90']=agg.customer_id.map(last90).fillna(0)
    agg['orders_180']=agg.customer_id.map(last180).fillna(0)
    agg['recency_days']=(cutoff-agg.last_order).dt.days
    agg['span_365_days']=(agg.last_order-agg.first_seen_365).dt.days
    cols=['orders_365','spend_365','avg_order','branches_365','orders_90','orders_180','recency_days','span_365_days']
    fut=df[(df.order_date>cutoff)&(df.order_date<=cutoff+pd.Timedelta(days=horizon))].groupby('customer_id').agg(future_orders=('sales','size'),future_spend=('sales','sum'))
    agg['future_spend']=agg.customer_id.map(fut.future_spend).fillna(0)
    fut180=df[(df.order_date>cutoff)&(df.order_date<=cutoff+pd.Timedelta(days=180))].groupby('customer_id').size()
    agg['churn_label']=(agg.customer_id.map(fut180).fillna(0)==0).astype(int)
    return agg,cols


def build_customer_models(write=True):
    df=load_orders()
    # Train labels through October 2025, evaluate out of sample through October 2026.
    tr,features=customer_features(df,'2024-10-18')
    va,_=customer_features(df,'2025-10-18')
    latest,_=customer_features(df,'2026-10-18')
    clf=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=15,l2_regularization=4,learning_rate=0.07,random_state=42)
    clf.fit(tr[features].to_numpy(),tr.churn_label.to_numpy())
    va_churn=clf.predict_proba(va[features].to_numpy())[:,1]
    auc=float(roc_auc_score(va.churn_label,va_churn)) if va.churn_label.nunique()==2 else None
    ap=float(average_precision_score(va.churn_label,va_churn)) if va.churn_label.nunique()==2 else None
    # Sales proxy, not literal infinite-horizon CLV; fit on log-scaled future sales.
    reg=HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=15,l2_regularization=4,learning_rate=0.07,random_state=42)
    reg.fit(tr[features].to_numpy(),np.log1p(tr.future_spend.to_numpy()))
    va_future=np.maximum(0,np.expm1(reg.predict(va[features].to_numpy())))
    mae=float(mean_absolute_error(va.future_spend.to_numpy(),va_future))
    baseline=float(mean_absolute_error(va.future_spend.to_numpy(),np.full(len(va),tr.future_spend.mean())))
    # Refit after evaluation using TRAIN + later cohort whose labels fully observed.
    mixed=pd.concat([tr,va],ignore_index=True)
    clf.fit(mixed[features].to_numpy(),mixed.churn_label.to_numpy())
    reg.fit(mixed[features].to_numpy(),np.log1p(mixed.future_spend.to_numpy()))
    scores=latest[['customer_id','orders_365','spend_365','recency_days']].copy()
    scores['churn_probability']=clf.predict_proba(latest[features].to_numpy())[:,1].round(4)
    scores['next_365d_sales_proxy_EGP']=np.maximum(0,np.expm1(reg.predict(latest[features].to_numpy()))).round(2)
    scores['risk_band']=pd.cut(scores.churn_probability,bins=[-0.01,.4,.7,1.01],labels=['Low','Medium','High'])
    metrics={
        'prediction_as_of':'2026-10-18','training_as_of':'2024-10-18',
        'validation_as_of':'2025-10-18',
        'train_customers':len(tr),'validation_customers':len(va),'scored_customers':len(latest),
        'churn_definition':'No observed purchase in next 180 days among identified customers with a purchase in previous 365 days',
        'churn_validation_roc_auc':round(auc,4) if auc is not None else None,
        'churn_validation_average_precision':round(ap,4) if ap is not None else None,
        'churn_validation_prevalence':round(float(va.churn_label.mean()),4),
        'sales_proxy_definition':'Predicted purchase revenue in next 365 days for an identified recent customer. Not literal lifetime CLV and not profit.',
        'sales_proxy_validation_mae_EGP':round(mae,2),
        'sales_proxy_baseline_mae_EGP':round(baseline,2),
        'limitations':'Synthetic/task data, identification bias, cross-cohort temporal validation only; not calibrated for real-world retention decisions.'}
    if write:
        scores.to_csv(OUT/'customer_predictions.csv',index=False)
        (OUT/'customer_model_metrics.json').write_text(json.dumps(metrics,indent=2,ensure_ascii=False),encoding='utf-8')
    return scores,metrics


def customer_results():
    path=OUT/'customer_predictions.csv';meta=OUT/'customer_model_metrics.json'
    if not path.is_file() or not meta.is_file():
        return None,None
    return pd.read_csv(path),json.loads(meta.read_text(encoding='utf-8'))

if __name__=='__main__':
    scores,metrics=build_customer_models()
    print(json.dumps(metrics,ensure_ascii=False,indent=2))
