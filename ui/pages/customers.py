"""Aggregate-only customer presentation; every definition and model is a service."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from ui.components import chart,table,money,style_figure
from ui.i18n import t,ltr
from ui.state import choice

MODES=('c8_overview','c8_rfm','c8_cohorts','c8_repeat','c8_value','c8_churn','c8_limitations')


def card(key,value,lang,kind='number'):
    if value is None or pd.isna(value):display=t('unavailable',lang)
    elif kind=='money':display=money(value,lang)
    elif kind=='float':display=ltr(f'{value:,.2f}',lang)
    elif kind=='pct':display=ltr(f'{value:,.2f}%',lang)
    else:display=ltr(f'{int(value):,}',lang)
    st.metric(t(key,lang),display)


def render(ctx):
    lang=ctx.lang
    st.info(t('c8_scope_note',lang));st.caption(t('c8_privacy_note',lang));st.caption(t('value_note',lang))
    mode=choice('selectbox',t('c8_view',lang),MODES,lang,'c8_mode',lambda v:t(v,lang))
    st.subheader(t(mode,lang))
    st.markdown('<style>.st-key-c8_cards [data-testid="stMetricValue"],.st-key-c8_cards [data-testid="stMetricValue"]>div{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;font-size:1.35rem!important;}</style>',unsafe_allow_html=True)
    if mode in ('c8_value','c8_churn','c8_limitations'):
        result=ctx.get('customer8_models')
        if result['state']=='unavailable':st.warning(t(result['reason'],lang));return
        st.info(t('c8_model_note',lang,origin=ltr(result['origin'],lang)))
        st.warning(t(result['value_state'] if mode=='c8_value' else result['state'],lang))
        if mode=='c8_value':
            st.caption(t('c8_value_note',lang))
            forecast=result['value_forecast']
            with st.container(key='c8_cards'):
                a,b=st.columns(2)
                with a:card('c8_eligible',forecast['c8_eligible'],lang)
                with b:card('c8_predicted_revenue',forecast['c8_predicted_revenue'],lang,'money')
            table(pd.DataFrame([forecast]),lang,'c8_value_forecast')
            primary=result['value_comparison'][['c8_model','c8_stage','c8_cutoff','mae','wape_pct','bias_pct']]
            table(primary,lang,'c8_value_models')
            with st.expander(t('c8_extra',lang)):table(result['value_comparison'],lang,'c8_value_full');table(result['value_segments'],lang,'c8_value_segments')
        elif mode=='c8_churn':
            st.caption(t('c8_churn_note',lang))
            pooled=result['classification'].loc[result['classification'].c8_stage.eq('test_pooled')]
            table(pooled[['c8_model','c8_samples','c8_roc_auc','c8_average_precision','c8_brier','c8_ece']],lang,'c8_churn_comparison')
            calibration=result['calibration']
            if not calibration.empty:
                fig=go.Figure()
                fig.add_trace(go.Scatter(x=[0,1],y=[0,1],name=t('c8_calibration_reference',lang),line={'color':'#bcc9d1','dash':'dot'}))
                fig.add_trace(go.Scatter(x=calibration.c8_mean_probability,y=calibration.c8_observed_rate,name=t('c8_observed_rate',lang),mode='markers',marker={'color':'#0c9697','size':12}))
                style_figure(fig,lang,'c8_calibration_chart');fig.update_xaxes(range=[0,1],title=t('c8_mean_probability',lang));fig.update_yaxes(range=[0,1],title=t('c8_observed_rate',lang))
                st.plotly_chart(fig,width='stretch',config={'displayModeBar':False},key='c8_calibration')
            with st.expander(t('c8_extra',lang)):table(result['classification'],lang,'c8_churn_full');table(calibration,lang,'c8_calibration_data')
        else:
            st.warning(t('c8_churn_note',lang));st.warning(t('c8_value_note',lang));st.caption(t('c8_dependence_note',lang))
            table(result['uncertainty'],lang,'c8_uncertainty');table(result['dependence'],lang,'c8_dependence')
        st.caption(t('c8_dependence_note',lang))
        with st.expander(t('c8_extra',lang)):table(result['schedule'],lang,'c8_schedule')
        return
    result=ctx.get('customer8')
    if mode=='c8_overview':
        summary=result['summary']
        with st.container(key='c8_cards'):
            keys=[('c8_registered','number'),('c8_identified','number'),('c8_repeat_rate','pct'),('c8_frequency','float'),('c8_average_spend','money'),('c8_anonymous_orders','number')]
            for offset in (0,3):
                columns=st.columns(3)
                for column,(key,kind) in zip(columns,keys[offset:offset+3]):
                    with column:card(key,summary[key],lang,kind)
        chart(result['activity'],'month','c8_customers',lang,'c8_activity_chart','line',key='c8_activity')
        st.caption(t('c8_recency_note',lang))
        chart(result['recency'],'c8_recency_band','c8_customers',lang,'c8_recency_band',key='c8_recency')
        with st.expander(t('c8_extra',lang)):table(pd.DataFrame([summary]),lang,'c8_summary');table(result['master_segments'],lang,'c8_master_segments')
    elif mode=='c8_rfm':
        st.caption(t('c8_rfm_note',lang,end=ltr(result['meta']['observed_end'],lang)))
        chart(result['rfm'],'c8_segment','c8_customers',lang,'c8_rfm',horizontal=True,key='c8_rfm')
        table(result['rfm'],lang,'c8_rfm')
        st.caption(t('c8_movement_note',lang));table(result['segment_change'],lang,'c8_segment_changes')
        with st.expander(t('c8_extra',lang)):table(result['movement'],lang,'c8_movement')
    elif mode=='c8_cohorts':
        st.caption(t('c8_cohort_note',lang));frame=result['retention']
        if not frame.empty:
            pivot=frame.pivot(index='c8_cohort',columns='c8_age',values='c8_retention_pct')
            fig=go.Figure(go.Heatmap(z=pivot.to_numpy(dtype=float),x=[str(v) for v in pivot.columns],y=pivot.index.tolist(),colorscale=[[0,'#eff7f7'],[1,'#0c9697']],zmin=0,zmax=100,hoverongaps=False))
            style_figure(fig,lang,'c8_cohorts');fig.update_xaxes(title=t('c8_age',lang),type='category');fig.update_yaxes(type='category')
            st.plotly_chart(fig,width='stretch',config={'displayModeBar':False},key='c8_cohort_heatmap')
        table(frame,lang,'c8_retention')
    else:
        st.caption(t('c8_cohort_note',lang));st.caption(t('c8_movement_note',lang))
        chart(result['activity'],'month','c8_repeat_rate',lang,'c8_repeat','line',key='c8_repeat_chart')
        table(result['activity'],lang,'c8_monthly_repeat');table(result['cohorts'],lang,'c8_second_purchase');table(result['segment_change'],lang,'c8_repeat_changes')
