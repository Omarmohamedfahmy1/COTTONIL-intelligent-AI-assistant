"""Phase 7 presentation only; models, metrics, selection and bands are services."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from ui.components import style_figure,table,chart
from ui.i18n import t,category_name,ltr
from ui.state import choice

MODES=('f7_overview','f7_models','f7_backtests','f7_uncertainty')


def percent(value,lang):
    return t('unavailable',lang) if value is None or pd.isna(value) else ltr(f'{value:,.2f}%',lang)


def future_chart(result,lang):
    actual=result['history'].tail(12);pred=result['forecasts'];fig=go.Figure()
    if pred.lower.notna().all() and pred.upper.notna().all():
        fig.add_trace(go.Scatter(x=pred.month,y=pred.upper,name=t('upper',lang),line={'width':0},showlegend=False))
        fig.add_trace(go.Scatter(x=pred.month,y=pred.lower,name=t('lower',lang),line={'width':0},fill='tonexty',fillcolor='rgba(12,150,151,.18)',showlegend=False))
    fig.add_trace(go.Scatter(x=actual.month,y=actual.value,name=t('observed',lang),line={'color':'#10263e','width':2}))
    fig.add_trace(go.Scatter(x=[actual.month.iloc[-1],*pred.month],y=[actual.value.iloc[-1],*pred.central],name=t('central',lang),line={'color':'#0c9697','width':3,'dash':'dash'},mode='lines+markers'))
    style_figure(fig,lang,'f7_future_chart')
    fig.update_xaxes(type='category',categoryorder='array',categoryarray=[*actual.month,*pred.month],tickangle=-30,title=t('month',lang));fig.update_yaxes(title=t('units' if result['target']=='units' else 'egp',lang))
    st.plotly_chart(fig,width='stretch',config={'displayModeBar':False},key='f7_future_chart')


def render(ctx):
    lang=ctx.lang
    st.info(t('f7_dates',lang))
    st.caption(t('f7_target',lang,target=category_name(ctx.scope.category,lang) if ctx.scope.category else t('revenue',lang),unit=t('units' if ctx.scope.category else 'egp',lang)))
    a,b=st.columns(2)
    with a:horizon=choice('selectbox',t('f7_horizon',lang),[1,3,6],lang,'f7_horizon',lambda v:str(v))
    with b:mode=choice('selectbox',t('f7_mode',lang),MODES,lang,'f7_mode',lambda v:t(v,lang))
    with st.spinner(t('checking',lang)):result=ctx.get('forecast7',horizon)
    st.subheader(t(mode,lang))
    if result['state']=='unavailable':
        st.warning(t(result['reason'],lang));table(result['history'],lang,'f7_unavailable_history');return
    if result['state']=='experimental':st.warning(t('f7_experimental',lang))
    else:st.caption(t('f7_evaluated',lang))
    st.markdown('<style>.st-key-f7_cards [data-testid="stMetricValue"],.st-key-f7_cards [data-testid="stMetricValue"]>div{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;font-size:1.35rem!important;line-height:1.35;}</style>',unsafe_allow_html=True)
    with st.container(key='f7_cards'):
        a,b,c=st.columns(3)
        a.metric(t('forecast_model',lang),t(result['model'],lang));b.metric(t('f7_state',lang),t(result['state'],lang));c.metric(t('f7_origin',lang),ltr(result['origin'],lang))
        a,b,c=st.columns(3)
        a.metric(t('f7_test_wape',lang),percent(result['metrics']['wape_pct'],lang));b.metric(t('f7_baseline_wape',lang),percent(result['baseline_metrics']['wape_pct'],lang));c.metric(t('f7_test_bias',lang),percent(result['metrics']['bias_pct'],lang))
    st.caption(t('f7_periods',lang,**{key:ltr(result[value],lang) for key,value in [('start','training_start'),('end','training_end'),('validation','validation_end'),('test_start','test_start'),('test_end','test_end')]}))
    st.caption(t('f7_boundary',lang))
    if result['target']=='revenue':st.caption(t('sales_note',lang))
    if mode in ('f7_overview','f7_uncertainty'):
        st.caption(t('f7_context',lang));future_chart(result,lang)
        st.caption(t('f7_band_note',lang))
        if result['test_band_coverage'] is not None:
            st.caption(t('f7_coverage',lang,coverage=ltr(f"{result['test_band_coverage']:.2f}",lang),count=result['test_band_observations']))
        else:st.info(t('f7_no_band',lang))
        table(result['forecasts'],lang,'f7_forecast')
        with st.expander(t('f7_history',lang)):
            frame=result['history'].loc[result['history'].month.between(ctx.scope.start[:7],ctx.scope.end[:7])]
            chart(frame,'month','value',lang,'f7_observed_chart','line',key='f7_display_history');table(frame,lang,'f7_display_history')
        with st.expander(t('f7_audit',lang)):
            audit=result['audit'];st.caption(t('f7_counts',lang,months=audit['months'],missing=audit['missing_months'],zero=audit['zero_months']))
            table(pd.DataFrame({'calendar_month':list(audit['calendar_means']),'value':list(audit['calendar_means'].values())}),lang,'f7_seasonality')
    elif mode=='f7_models':
        st.caption(t('f7_selection',lang));st.caption(t('f7_metrics_note',lang))
        primary=result['comparison'][['forecast_model','stage','wape_pct','mae','bias_pct','selected_model']]
        table(primary,lang,'f7_model_comparison')
        with st.expander(t('p5_full_table',lang)):table(result['comparison'],lang,'f7_models_full')
    else:
        st.caption(t('f7_method',lang));st.caption(t('f7_metrics_note',lang))
        rows=result['backtests'].loc[result['backtests'].forecast_model.eq(result['model']) & result['backtests'].lead.le(horizon)]
        origins=rows.origin.unique().tolist()
        selected=choice('selectbox',t('origin',lang),origins,lang,'f7_origin_view',lambda v:v)
        frame=rows.loc[rows.origin.eq(selected)]
        fig=go.Figure()
        for key,color in [('actual','#10263e'),('predicted','#0c9697')]:fig.add_trace(go.Scatter(x=frame.month,y=frame[key],name=t(key,lang),mode='lines+markers',line={'color':color}))
        style_figure(fig,lang,'f7_backtests');fig.update_xaxes(type='category');fig.update_yaxes(title=t('units' if result['target']=='units' else 'egp',lang))
        st.plotly_chart(fig,width='stretch',config={'displayModeBar':False},key='f7_backtest_plot')
        table(rows[['stage','origin','month','lead','actual','predicted']],lang,'f7_backtest_rows')
        with st.expander(t('p5_full_table',lang)):table(result['split_schedule'],lang,'f7_splits')
