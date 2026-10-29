"""Deterministic, train-prefix-only monthly candidates and evaluation primitives."""
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from predictive import design

BASELINES=('naive','seasonal_naive','moving_average')
REGRESSORS=('ridge_calendar','ridge_lags','boosted_lags')
MODELS=BASELINES+REGRESSORS
EPS=1e-8


def metrics(actual,predicted):
    a=np.asarray(actual,dtype=float);p=np.asarray(predicted,dtype=float)
    if not len(a) or a.shape!=p.shape or not np.isfinite(a).all() or not np.isfinite(p).all():raise ValueError('Finite aligned observations required')
    e=p-a;den=float(np.abs(a).sum());sden=np.abs(a)+np.abs(p)
    return dict(mae=float(np.abs(e).mean()),rmse=float(np.sqrt(np.mean(e**2))),
        wape_pct=float(np.abs(e).sum()/den*100) if den>EPS else None,
        smape_pct=float(np.divide(200*np.abs(e),sden,out=np.zeros_like(e),where=sden>EPS).mean()),
        bias=float(e.mean()),bias_pct=float(e.sum()/den*100) if den>EPS else None)


def lag_features(history,month):
    """Only values strictly BEFORE month; recursive predictions become future lags."""
    y=np.asarray(history,dtype=float)
    if len(y)<12:raise ValueError('Twelve past months required')
    angle=2*np.pi*(month.month-1)/12
    return [y[-k] for k in (1,2,3,6,12)]+[float(y[-k:].mean()) for k in (3,6,12)]+[y[-1]-y[-2],np.sin(angle),np.cos(angle),len(y)/12]


def supervised(values,months):
    return np.array([lag_features(values[:i],months[i]) for i in range(12,len(values))]),np.asarray(values[12:],dtype=float)


def predict(model,values,months,horizon):
    if model not in MODELS or isinstance(horizon,bool) or not isinstance(horizon,int) or horizon not in (1,3,6):raise ValueError('Unsupported forecast model/horizon')
    y=np.asarray(values,dtype=float);ps=list(pd.PeriodIndex(months,freq='M'))
    if len(y)<24 or len(y)!=len(ps) or not np.isfinite(y).all() or (y<0).any():raise ValueError('Invalid training history')
    future=list(pd.period_range(ps[-1]+1,periods=horizon,freq='M'))
    if model=='naive':return np.repeat(y[-1],horizon)
    if model=='moving_average':return np.repeat(y[-6:].mean(),horizon)
    if model=='seasonal_naive':
        history=list(y);out=[]
        for _ in future:out.append(float(history[-12]));history.append(out[-1])
        return np.array(out)
    if model=='ridge_calendar':
        fitted=Ridge(alpha=8).fit(design(ps,ps[0].ordinal),y)
        return np.maximum(0,fitted.predict(design(future,ps[0].ordinal)))
    x,target=supervised(y,ps)
    fitted=make_pipeline(StandardScaler(),Ridge(alpha=10)) if model=='ridge_lags' else HistGradientBoostingRegressor(max_iter=60,max_leaf_nodes=7,min_samples_leaf=8,l2_regularization=10,random_state=42)
    fitted.fit(x,target);history=list(y);out=[]
    for month in future:
        point=max(0,float(fitted.predict(np.array([lag_features(history,month)]))[0]))
        out.append(point);history.append(point)
    return np.array(out)


def score_rows(rows,stage,horizon):
    frame=rows.loc[rows.stage.eq(stage) & rows.lead.le(horizon)]
    result=[]
    for model,group in frame.groupby('forecast_model'):
        result.append(dict(forecast_model=model,stage=stage,horizon=horizon,observations=len(group),**metrics(group.actual,group.predicted)))
    return pd.DataFrame(result)


def choose(validation,rows,horizon):
    """No test rows consulted. ML requires >=5 folds, >=5% gain and >=60% wins."""
    validation=validation.copy()
    validation['selection_score']=validation.wape_pct.where(validation.wape_pct.notna(),validation.mae)
    base=validation.loc[validation.forecast_model.isin(BASELINES)].sort_values(['selection_score','forecast_model']).iloc[0]
    eligible=[];evidence=[]
    for row in validation.itertuples():
        subset=rows.loc[rows.stage.eq('validation') & rows.lead.le(horizon)]
        wins=[]
        for _,fold in subset.groupby('origin'):
            candidate=fold.loc[fold.forecast_model.eq(row.forecast_model)]
            baseline=fold.loc[fold.forecast_model.eq(base.forecast_model)]
            if len(candidate)==len(baseline)==horizon:wins.append(float(np.abs(candidate.predicted-candidate.actual).sum())<float(np.abs(baseline.predicted-baseline.actual).sum()))
        win_rate=float(np.mean(wins)) if wins else 0
        qualifies=bool(row.forecast_model in REGRESSORS and len(wins)>=5 and row.selection_score<=base.selection_score*.95 and win_rate>=.6)
        evidence.append(dict(forecast_model=row.forecast_model,validation_fold_wins=win_rate,validation_folds=len(wins),ml_gate_passed=qualifies))
        if qualifies:eligible.append((row.selection_score,row.forecast_model))
    selected=min(eligible)[1] if eligible else base.forecast_model
    return selected,str(base.forecast_model),pd.DataFrame(evidence)


def uncertainty(validation,model,horizon):
    frame=validation.loc[validation.stage.eq('validation') & validation.forecast_model.eq(model)]
    widths=[]
    for lead in range(1,horizon+1):
        residual=(frame.loc[frame.lead.eq(lead),'actual']-frame.loc[frame.lead.eq(lead),'predicted']).abs()
        widths.append(float(residual.quantile(.8)) if len(residual)>=5 else None)
    return widths
