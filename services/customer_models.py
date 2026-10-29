"""Phase 8 aggregate research: purged annual cohorts, never individual scoring files.

Saved legacy models/outputs are neither read as truth nor overwritten. All fits
are in memory; only aggregate metrics leave this module. Selection uses validation
only. Testing is locked, chronological and assessed for customer dependence.
"""
from copy import deepcopy
from functools import lru_cache
from time import perf_counter
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier,HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression,Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss,precision_score,recall_score,confusion_matrix
from threadpoolctl import threadpool_limits
from services import customer_data as data
from services.forecast_models import metrics as revenue_metrics
from services import metrics as kpi

FEATURES=['recency_days','frequency','monetary','branches','orders_90','orders_180','activity_days','avg_gap_days','purchase_delta']
CLASSIFIERS=('c8_prevalence_model','c8_recency_model','c8_rfm_rule','c8_logistic','c8_hist_classifier')
VALUES=('c8_mean_value','c8_median_value','c8_past_spend','c8_rfm_value','c8_ridge_value','c8_hist_value')
MIN_COHORT=100


def labeled_cohort(orders,cutoff,source_last,horizon=365):
    """Explicit exclusive boundaries; reject censored labels, never fill them zero."""
    if horizon not in (180,365):raise ValueError('Supported research label horizons are 180/365 days')
    cutoff=pd.Timestamp(cutoff);end=cutoff+pd.Timedelta(days=horizon)
    if end>pd.Timestamp(source_last)+pd.Timedelta(days=1):raise ValueError('Label horizon not fully observed')
    frame=data.features(orders,cutoff)
    future=orders.loc[orders.customer_id.notna() & orders.order_date.ge(cutoff) & orders.order_date.lt(end)]
    revenue=future.groupby('customer_id').sales.sum()
    frame['future_revenue']=frame.customer_id.map(revenue).fillna(0)
    future180=orders.loc[orders.customer_id.notna() & orders.order_date.ge(cutoff) & orders.order_date.lt(cutoff+pd.Timedelta(days=180))]
    if cutoff+pd.Timedelta(days=180)>pd.Timestamp(source_last)+pd.Timedelta(days=1):raise ValueError('Churn outcome censored')
    frame['churn_label']=(~frame.customer_id.isin(future180.customer_id)).astype(int)
    frame['cutoff']=str(cutoff.date())
    return frame


def classification_metrics(actual,probability):
    y=np.asarray(actual,dtype=int);p=np.asarray(probability,dtype=float)
    if not len(y) or len(y)!=len(p) or not np.isin(y,[0,1]).all() or not np.isfinite(p).all() or ((p<0)|(p>1)).any():raise ValueError('Aligned binary labels and finite probabilities required')
    pred=(p>=.5).astype(int);tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
    bins=np.minimum((p*10).astype(int),9);ece=0;calibration=[]
    for bin_id in range(10):
        mask=bins==bin_id;n=int(mask.sum())
        if not n:continue
        expected=float(p[mask].mean());observed=float(y[mask].mean());ece+=n/len(y)*abs(expected-observed)
        calibration.append(dict(c8_probability_bin=f'{bin_id/10:.1f}â€“{(bin_id+1)/10:.1f}',c8_customers=n,c8_mean_probability=expected,c8_observed_rate=observed))
    both=len(np.unique(y))==2
    values=dict(c8_samples=len(y),c8_prevalence=float(y.mean()),c8_roc_auc=float(roc_auc_score(y,p)) if both else None,
        c8_average_precision=float(average_precision_score(y,p)) if both else None,c8_brier=float(brier_score_loss(y,p)),c8_ece=float(ece),
        c8_precision=float(precision_score(y,pred,zero_division=0)),c8_recall=float(recall_score(y,pred,zero_division=0)),c8_tn=int(tn),c8_fp=int(fp),c8_fn=int(fn),c8_tp=int(tp),c8_threshold=.5)
    return values,data.protected(pd.DataFrame(calibration))


def _fit_class(name,train):
    if name=='c8_prevalence_model':return float(train.churn_label.mean())
    if name=='c8_rfm_rule':return None
    cols=['recency_days'] if name=='c8_recency_model' else FEATURES
    model=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=15,l2_regularization=4,learning_rate=.07,random_state=42) if name=='c8_hist_classifier' else make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=500,random_state=42))
    return model.fit(train[cols].to_numpy(dtype=float),train.churn_label.to_numpy())


def _class_predict(name,model,frame):
    if name=='c8_prevalence_model':return np.repeat(model,len(frame))
    if name=='c8_rfm_rule':return np.clip(1-(frame.r_score+frame.f_score+frame.m_score).to_numpy(dtype=float)/15,.01,.99)
    cols=['recency_days'] if name=='c8_recency_model' else FEATURES
    return model.predict_proba(frame[cols].to_numpy(dtype=float))[:,1]


def churn_gate(metric,baseline):
    return bool(metric['c8_samples']>=MIN_COHORT and metric['c8_roc_auc'] is not None and metric['c8_roc_auc']>=.60 and
        metric['c8_average_precision']>=metric['c8_prevalence']+.03 and metric['c8_brier']<=baseline['c8_brier']*.95 and metric['c8_ece']<=.05)


def _fit_value(name,train):
    if name=='c8_mean_value':return float(train.future_revenue.mean())
    if name=='c8_median_value':return float(train.future_revenue.median())
    if name=='c8_past_spend':return None
    if name=='c8_rfm_value':return train.groupby('c8_segment').future_revenue.mean().to_dict(),float(train.future_revenue.mean())
    model=make_pipeline(StandardScaler(),Ridge(alpha=100)) if name=='c8_ridge_value' else HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=15,l2_regularization=4,learning_rate=.07,random_state=42)
    target=train.future_revenue.to_numpy() if name=='c8_ridge_value' else np.log1p(train.future_revenue.to_numpy())
    return model.fit(train[FEATURES].to_numpy(dtype=float),target)


def _value_predict(name,model,frame):
    if name in ('c8_mean_value','c8_median_value'):return np.repeat(model,len(frame))
    if name=='c8_past_spend':return frame.monetary.to_numpy(dtype=float)
    if name=='c8_rfm_value':return frame.c8_segment.map(model[0]).fillna(model[1]).to_numpy(dtype=float)
    prediction=model.predict(frame[FEATURES].to_numpy(dtype=float))
    return np.maximum(0,np.expm1(np.clip(prediction,-20,20)) if name=='c8_hist_value' else prediction)


def choose_value(validation):
    naive=validation.loc[validation.c8_model.isin(VALUES[:4])].sort_values(['mae','c8_model']).iloc[0]
    regressions=validation.loc[validation.c8_model.isin(VALUES[4:]) & validation.mae.le(naive.mae*.95)].sort_values(['mae','c8_model'])
    return (regressions.iloc[0].c8_model if not regressions.empty else naive.c8_model),str(naive.c8_model)


def cluster_auc_range(frame,probabilities,repeats=80):
    """Customer-cluster bootstrap preserves repeated test-customer dependence.

    Descriptive conditional range, not population/temporal generalization proof.
    """
    _,codes=np.unique(frame.customer_id.astype(str),return_inverse=True);n=int(codes.max()+1);rng=np.random.default_rng(42);values=[]
    for _ in range(repeats):
        weights=np.bincount(rng.integers(0,n,size=n),minlength=n)[codes]
        if len(np.unique(frame.churn_label.to_numpy()[weights>0]))==2:values.append(roc_auc_score(frame.churn_label,probabilities,sample_weight=weights))
    return (float(np.quantile(values,.025)),float(np.quantile(values,.975))) if values else (None,None)


def evaluate(orders,source_last):
    started=perf_counter();origin=pd.Timestamp(source_last)+pd.Timedelta(days=1)
    cutoffs=[origin.replace(year=origin.year-offset) for offset in (5,4,3,2,1)]
    if orders.empty or pd.Timestamp(orders.order_date.min())>cutoffs[0]-pd.Timedelta(days=365):return dict(state='unavailable',reason='c8_model_insufficient')
    cohorts=[labeled_cohort(orders,c,source_last) for c in cutoffs]
    if any(len(c)<MIN_COHORT or c.churn_label.nunique()<2 for c in cohorts):return dict(state='unavailable',reason='c8_model_insufficient')
    train=pd.concat(cohorts[:2],ignore_index=True);validation=cohorts[2];test=pd.concat(cohorts[3:],ignore_index=True)
    schedule=[]
    for i,cutoff in enumerate(cutoffs):
        schedule.append(dict(c8_stage='train' if i<2 else 'validation' if i==2 else 'test',c8_cutoff=str(cutoff.date()),
            c8_feature_start=str((cutoff-pd.Timedelta(days=365)).date()),c8_feature_end=str((cutoff-pd.Timedelta(days=1)).date()),
            c8_churn_end=str((cutoff+pd.Timedelta(days=179)).date()),c8_value_end=str((cutoff+pd.Timedelta(days=364)).date()),c8_samples=len(cohorts[i])))
    classification=[];calibration=[];class_models={};validation_scores={};test_probabilities={}
    value_rows=[];value_models={};test_values={}
    with threadpool_limits(limits=1):
        for name in CLASSIFIERS:
            model=_fit_class(name,train);class_models[name]=model
            probability=_class_predict(name,model,validation);score,_=classification_metrics(validation.churn_label,probability);validation_scores[name]=score
            classification.append(dict(c8_model=name,c8_stage='validation',c8_cutoff=str(cutoffs[2].date()),**score))
        base=validation_scores['c8_prevalence_model']
        qualified=[name for name in CLASSIFIERS[1:] if churn_gate(validation_scores[name],base)]
        selected=min(qualified,key=lambda n:validation_scores[n]['c8_brier']) if qualified else 'c8_prevalence_model'
        # Frozen selection before any test scoring; no post-test model switching.
        for name in CLASSIFIERS:
            probability=_class_predict(name,class_models[name],test);test_probabilities[name]=probability
            score,cal=classification_metrics(test.churn_label,probability)
            classification.append(dict(c8_model=name,c8_stage='test_pooled',c8_cutoff='pooled',**score))
            if name==selected and not cal.empty:calibration=cal.to_dict('records')
            for cutoff,group in test.groupby('cutoff',sort=True):
                indices=group.index.to_numpy();score,_=classification_metrics(group.churn_label,probability[indices]);classification.append(dict(c8_model=name,c8_stage='test',c8_cutoff=cutoff,**score))
        for name in VALUES:
            model=_fit_value(name,train);value_models[name]=model
            score=revenue_metrics(validation.future_revenue,_value_predict(name,model,validation))
            value_rows.append(dict(c8_model=name,c8_stage='validation',c8_cutoff=str(cutoffs[2].date()),c8_samples=len(validation),**score))
        chosen_value,value_baseline=choose_value(pd.DataFrame(value_rows))
        for name in VALUES:
            prediction=_value_predict(name,value_models[name],test);test_values[name]=prediction
            value_rows.append(dict(c8_model=name,c8_stage='test_pooled',c8_cutoff='pooled',c8_samples=len(test),**revenue_metrics(test.future_revenue,prediction)))
            for cutoff,group in test.groupby('cutoff',sort=True):value_rows.append(dict(c8_model=name,c8_stage='test',c8_cutoff=cutoff,c8_samples=len(group),**revenue_metrics(group.future_revenue,prediction[group.index.to_numpy()])))
        metrics=pd.DataFrame(classification);values=pd.DataFrame(value_rows)
        selected_test=metrics.loc[metrics.c8_model.eq(selected) & metrics.c8_stage.eq('test_pooled')].iloc[0].to_dict()
        baseline_test=metrics.loc[metrics.c8_model.eq('c8_prevalence_model') & metrics.c8_stage.eq('test_pooled')].iloc[0].to_dict()
        reliable=selected!='c8_prevalence_model' and churn_gate(selected_test,baseline_test) and all(churn_gate(row._asdict(),metrics.loc[metrics.c8_model.eq('c8_prevalence_model') & metrics.c8_cutoff.eq(row.c8_cutoff) & metrics.c8_stage.eq('test')].iloc[0].to_dict()) for row in metrics.loc[metrics.c8_model.eq(selected) & metrics.c8_stage.eq('test')].itertuples(index=False))
        state='c8_evaluated_research' if reliable else 'c8_unreliable'
        value_test=values.loc[values.c8_model.eq(chosen_value) & values.c8_stage.eq('test_pooled')].iloc[0]
        base_value_test=values.loc[values.c8_model.eq(value_baseline) & values.c8_stage.eq('test_pooled')].iloc[0]
        value_state='c8_evaluated_research' if value_test.mae<=base_value_test.mae*1.1 and value_test.wape_pct is not None and value_test.wape_pct<=60 and abs(value_test.bias_pct or 0)<=20 else 'c8_unreliable'
        cohort_history=pd.concat(cohorts,ignore_index=True)
        latest=data.features(orders,origin)
        final_value=_fit_value(chosen_value,cohort_history)
        latest_value=_value_predict(chosen_value,final_value,latest)
    # Seen/unseen-customer diagnostics do not export identity membership.
    known_ids=set(train.customer_id)|set(validation.customer_id);seen=test.customer_id.isin(known_ids).to_numpy();dependence=[]
    for label,mask in [('c8_seen',seen),('c8_unseen',~seen)]:
        group=test.loc[mask]
        if len(group)>=data.K:
            score,_=classification_metrics(group.churn_label,test_probabilities['c8_hist_classifier'][mask]);dependence.append(dict(c8_membership=label,**score))
    uncertainty=[]
    for name in sorted(set([selected,'c8_hist_classifier'])):
        low,high=cluster_auc_range(test,test_probabilities[name]);uncertainty.append(dict(c8_model=name,c8_auc_lower=low,c8_auc_upper=high,c8_bootstrap_repeats=80))
    by_segment=[]
    for segment,group in test.groupby('c8_segment'):
        if len(group)>=data.K:by_segment.append(dict(c8_segment=segment,c8_customers=int(group.customer_id.nunique()),c8_samples=len(group),**revenue_metrics(group.future_revenue,test_values[chosen_value][group.index.to_numpy()])))
    aggregate_forecast=dict(c8_eligible=len(latest),c8_predicted_revenue=float(latest_value.sum()) if len(latest)>=data.K else None,
        c8_prediction_start=str(origin.date()),c8_prediction_end=str((origin+pd.Timedelta(days=364)).date()),c8_model=chosen_value,c8_state=value_state)
    return dict(state=state,reason='c8_model_note',selected_churn=selected,selected_value=chosen_value,value_baseline=value_baseline,value_state=value_state,
        classification=metrics,calibration=pd.DataFrame(calibration),value_comparison=values,value_segments=data.protected(pd.DataFrame(by_segment)),schedule=pd.DataFrame(schedule),
        dependence=pd.DataFrame(dependence),uncertainty=pd.DataFrame(uncertainty),value_forecast=aggregate_forecast,
        sample=dict(training_rows=len(train),training_unique=int(train.customer_id.nunique()),validation_rows=len(validation),test_rows=len(test),test_unique=int(test.customer_id.nunique()),
            test_seen_fraction=float(seen.mean()),training_validation_overlap=int(len(set(train.customer_id)&set(validation.customer_id)))),
        origin=str(origin.date()),elapsed_seconds=perf_counter()-started,individual_predictions_published=False,
        privacy='All identifiers and prediction arrays are in-memory only; returned data are aggregate metrics. No saved legacy artifact read/write.')


@lru_cache(maxsize=2)
def _cached(version):
    first,last=kpi.metadata()
    if not last:return dict(state='unavailable',reason='c8_model_insufficient')
    return evaluate(data.history(),last.isoformat())


def research():return deepcopy(_cached(data.version()))
