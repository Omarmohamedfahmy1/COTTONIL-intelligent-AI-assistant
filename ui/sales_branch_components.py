"""Reusable Phase 4 presentation, no financial calculations."""
import pandas as pd
import plotly.express as px
import streamlit as st
from types import SimpleNamespace
from ui.components import metric,chart,table,financial_notes,style_figure,money
from ui.i18n import t,data_value,category_name,ltr,TEXT
from ui.pages.overview import comparison_table
from ui.state import choice


def cards(data,lang):
    for keys in [('sales','gross_profit','orders'),('units','aov','growth_pct')]:
        for col,key in zip(st.columns(3),keys):
            with col:metric(key,data['current'][key],lang,'money' if key in ('sales','gross_profit','aov') else 'pct' if key=='growth_pct' else 'number')
    financial_notes(SimpleNamespace(lang=lang,scope=data['scope']))
    if not data['current']['orders']:st.info(t('empty',lang))


def period_comparison(data,lang):
    g=data['growth'];s=data['scope']
    st.subheader(t('s4_comparisons',lang))
    st.caption(t('current_period',lang,period=ltr(f'{s.start} → {s.end}',lang)))
    st.caption(t('previous_period_note',lang,period=ltr(f"{g['previous_start']} → {g['previous_end']}",lang)))
    st.caption(t('comparison_policy',lang))
    if not g['comparable_coverage']:st.warning(t('coverage_unavailable',lang))
    comparison_table(data['comparison'],lang)


def grouped_chart(frame,x,y,group,lang,title,key):
    if frame.empty:st.info(t('empty',lang));return
    frame=frame.copy()
    if group=='category':frame[group]=frame[group].map(lambda v:category_name(v,lang))
    if x=='category':frame[x]=frame[x].map(lambda v:category_name(v,lang))
    labels={k:t(k,lang) for k in frame if k in TEXT}
    fig=px.line(frame,x=x,y=y,color=group,markers=True,labels=labels,color_discrete_sequence=['#0c9697','#244660','#91b4c5','#6a9c89']) if x in ('month','period') else px.bar(frame,x=x,y=y,color=group,barmode='group',labels=labels,color_discrete_sequence=['#0c9697','#244660'])
    style_figure(fig,lang,title)
    if x in ('month','period'):
        ticks=frame[x].drop_duplicates().tolist();ticks=ticks[::max(1,len(ticks)//6)]
        fig.update_xaxes(type='category',tickmode='array',tickvals=ticks,ticktext=ticks)
    st.plotly_chart(fig,width='stretch',config={'displayModeBar':False},key=key)


def signals(data,lang):
    st.caption(t('s4_rules',lang))
    declined=data['declining_categories']
    unusual=data['unusual_categories']
    st.markdown('#### '+t('s4_declines',lang));table(declined,lang,'s4_declines')
    with st.expander(t('s4_unusual',lang)):
        table(unusual,lang,'s4_unusual')


def product_views(data,lang,key):
    st.subheader(t('s4_products',lang))
    by=choice('selectbox',t('s4_product_rank',lang),['units','sales'],lang,key+'_product_rank',lambda v:t(v,lang))
    products=data['products'].sort_values([by,'product_id'],ascending=[False,True])
    a,b=st.columns(2)
    with a:chart(products.head(8).iloc[::-1],'product_id',by,lang,'s4_top',horizontal=True,key=key+'_top')
    with b:chart(products.sort_values([by,'product_id']).head(8).iloc[::-1],'product_id',by,lang,'s4_bottom',horizontal=True,key=key+'_bottom')
    st.caption(t('s4_product_note',lang));table(products,lang,key+'_products')


def sales_body(data,lang,key,full=True):
    cards(data,lang)
    st.caption(t('s4_scope',lang))
    frame=data['trends']
    partial=int((~frame.is_complete_period.astype(bool)).sum())
    if partial:st.warning(t('s4_partial',lang,count=partial))
    chart(frame,'period','sales',lang,'monthly_sales','line',key=key+'_revenue')
    a,b=st.columns(2)
    with a:chart(frame,'period','orders',lang,'orders','line',key=key+'_orders')
    with b:chart(frame,'period','units',lang,'units','line',key=key+'_units')
    a,b=st.columns(2)
    with a:chart(frame,'period','gross_profit',lang,'s4_gp_trend','line',key=key+'_gp')
    with b:chart(frame,'period','aov',lang,'aov','line',key=key+'_aov')
    with st.expander(t('s4_trend_table',lang)):table(frame,lang,key+'_trends')
    period_comparison(data,lang)
    if full:
        st.subheader(t('s4_yoy',lang));st.caption(t('s4_yoy_note',lang))
        chart(data['yoy'],'month','yoy_growth_pct',lang,'s4_yoy','line',key=key+'_yoy')
        table(data['yoy'],lang,key+'_yoy')
        st.subheader(t('s4_seasonality',lang));st.caption(t('s4_season_note',lang))
        chart(data['seasonality'],'calendar_month','avg_sales',lang,'seasonality',key=key+'_season')
        table(data['seasonality'],lang,key+'_season')
    st.subheader(t('s4_categories',lang))
    st.caption(t('s4_denominator',lang,value=ltr(f"{data['company_sales']:,.2f}",lang)))
    table(data['categories'],lang,key+'_categories')
    st.markdown('#### '+t('s4_category_changes',lang));table(data['category_changes'],lang,key+'_category_changes')
    if not data['category_monthly'].empty:
        options=data['category_monthly'].category.drop_duplicates().tolist()
        selected=choice('selectbox',t('s4_category_select',lang),options,lang,key+'_category',lambda v:category_name(v,lang))
        chart(data['category_monthly'].loc[data['category_monthly'].category.eq(selected)],'month','sales',lang,'s4_category_trend','line',key=key+'_category_trend')
    signals(data,lang)
    chart(data['channels'],'channel','sales',lang,'channels',key=key+'_channels')
    table(data['channels'],lang,key+'_channels')
    product_views(data,lang,key)


def pair_table(frame,lang):
    display=frame.copy()
    def value(v,key):
        if pd.isna(v):return t('unavailable',lang)
        if key in ('sales','gross_profit','aov'):return money(v,lang,False)
        if key in ('gross_margin_pct','growth_pct'):return ltr(f'{v:.2f}%',lang)
        return ltr(f'{int(v):,}',lang)
    for col in ('location_a','location_b'):
        display[col]=[value(v,k) for v,k in zip(frame[col],frame.metric)]
    table(display,lang,'b4_pair')
