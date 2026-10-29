"""Phase 3 presentation only; all metrics and signals come from services."""
import pandas as pd
import streamlit as st
from ui.components import metric,chart,table,financial_notes,money
from ui.i18n import t,category_name,ltr


def open_branches():
    st.session_state.page='Branch Performance'


def comparison_table(frame,lang):
    display=frame.copy()
    def formatted(value,key,change=False):
        if value is None or pd.isna(value):return t('unavailable',lang)
        if key in ('sales','gross_profit','aov'):return money(value,lang,False)
        if key=='gross_margin_pct':return f'{ltr(f"{value:,.2f}",lang)} '+t('pp',lang) if change else f'{ltr(f"{value:.2f}",lang)}%'
        return ltr(f'{value:+,.0f}' if change else f'{value:,.0f}',lang)
    for col in ('current','previous','absolute_change'):
        display[col]=[formatted(v,key,col=='absolute_change') for v,key in zip(frame[col],frame.metric)]
    display['percentage_change']=frame.percentage_change.map(lambda v:t('unavailable',lang) if pd.isna(v) else ltr(f'{v:+.2f}%',lang))
    table(display,lang,'executive_comparison')


def render(ctx):
    lang=ctx.lang
    data=ctx.get('executive');values=data['current']
    st.subheader(t('executive_scorecards',lang))
    groups=[('sales','gross_profit','orders'),('gross_margin_pct','aov','customers'),
            ('branches','growth_pct','stock_units'),('stock_value','high_risk_categories')]
    for keys in groups:
        for col,key in zip(st.columns(len(keys)),keys):
            with col:
                value=values[key]
                if key=='gross_margin_pct' and not values['sales']:value=None
                if key=='aov' and not values['orders']:value=None
                kind='money' if key in ('sales','gross_profit','aov','stock_value') else 'pct' if key in ('growth_pct','gross_margin_pct') else 'number'
                metric(key,value,lang,kind)
    st.caption(t('stock_month',lang)+': '+ltr(data['stock_month'] or t('unavailable',lang),lang))
    st.caption(t('network_note',lang,retail=data['network'].get('Retail branch',0),pos=data['network'].get('Point of sale / reseller',0),registered=f"{values['registered_customers']:,}"))
    st.caption(t('registered_scope',lang));st.caption(t('identified_note',lang))
    financial_notes(ctx);st.caption(t('refund_note',lang))
    if not values['orders']:st.info(t('empty',lang))
    st.subheader(t('period_comparison',lang))
    st.caption(t('current_period',lang,period=ltr(data['current_period'],lang)))
    st.caption(t('previous_period_note',lang,period=ltr(data['previous_period'],lang)))
    st.caption(t('comparison_policy',lang))
    if not data['growth']['comparable_coverage']:st.warning(t('coverage_unavailable',lang))
    comparison_table(data['comparison'],lang)
    st.subheader(t('executive_insights',lang));st.caption(t('alert_rules',lang))
    for alert in data['alerts']:
        variables={k:v for k,v in alert.items() if k not in ('code','severity')}
        if 'value' in variables:variables['value']=ltr(f"{variables['value']:+.2f}",lang)
        if 'category' in variables:variables['category']=category_name(variables['category'],lang)
        getattr(st,alert['severity'])(t(alert['code'],lang,**variables))
    st.subheader(t('executive_trends',lang));st.caption(t('partial_chart_note',lang))
    monthly=data['monthly']
    partial=monthly.loc[~monthly.is_complete_month,'month'].tolist()
    if partial:st.warning(t('partial_month_list',lang,months=ltr(', '.join(partial),lang)))
    chart(monthly,'month','sales',lang,'monthly_sales','line',key='overview_monthly')
    a,b=st.columns(2)
    with a:chart(monthly,'month','orders',lang,'monthly_orders','line',key='executive_orders')
    with b:chart(monthly,'month','gross_profit',lang,'monthly_profit','line',key='executive_profit')
    a,b=st.columns(2)
    with a:chart(data['categories'],'category','sales',lang,'category_sales',key='executive_categories')
    with b:chart(data['channels'],'channel','sales',lang,'channels',key='overview_channels')
    a,b=st.columns(2)
    with a:chart(data['branches'].head(8).iloc[::-1],'branch','sales',lang,'top_locations',horizontal=True,key='overview_branches')
    with b:chart(data['products'].iloc[::-1],'product_id','units',lang,'top_products',horizontal=True,key='overview_products')
    st.subheader(t('location_snapshot',lang));st.caption(t('ranking_scope',lang))
    branches=data['branches']
    columns=['branch','retail_location_type','sales','aov']
    st.caption(t('executive_units_note',lang))
    a,b=st.columns(2)
    with a:
        st.markdown('#### '+t('best_locations',lang));table(branches[columns].head(5),lang,'executive_best')
    with b:
        st.markdown('#### '+t('lowest_locations',lang));table(branches[columns].sort_values('sales').head(5),lang,'executive_lowest')
    a,b=st.columns(2)
    with a:
        st.markdown('#### '+t('growth_ranking',lang))
        table(branches[['branch','retail_location_type','growth_pct']].dropna(subset=['growth_pct']).sort_values('growth_pct',ascending=False).head(5),lang,'executive_growth')
    with b:
        st.markdown('#### '+t('profit_ranking',lang))
        table(branches[['branch','retail_location_type','gross_profit','gross_profit_contribution_pct']].sort_values('gross_profit',ascending=False).head(5),lang,'executive_profit')
    st.button(t('open_branches',lang),key='executive_open_branches',on_click=open_branches)
    st.subheader(t('executive_inventory',lang))
    month,stock=data['stock_month'],data['stock']
    st.caption(t('stock_note',lang,month=ltr(month or t('unavailable',lang),lang)))
    st.caption(t('stock_scope_detail',lang));st.caption(t('replenishment_note',lang))
    metric('estimated_30d_replenishment_units',values['estimated_30d_replenishment_units'],lang)
    if stock.empty:st.warning(t('stock_unavailable',lang))
    else:
        chart(stock,'category','risk_score',lang,'risk_chart',key='executive_risk')
        st.markdown('#### '+t('attention_categories',lang))
        if data['attention'].empty:st.info(t('no_attention',lang))
        else:table(data['attention'],lang,'executive_attention')
        with st.expander(t('all_stock_categories',lang)):
            table(stock,lang,'overview_stock')
