"""Phase 5 presentation; formulas, thresholds and ranks stay in services."""
from dataclasses import asdict, replace
import pandas as pd
import plotly.express as px
import streamlit as st
from services import profitability as profit
from ui.components import chart,table,financial_notes,metric,money,style_figure
from ui.i18n import t,category_name,ltr,TEXT
from ui.state import choice
from ui.pages.overview import comparison_table

MODES=('p5_overview','p5_products','p5_categories','p5_locations','p5_screening')
PRODUCT_COLUMNS=['product_id','product','category','sales','units','gross_profit','gross_margin_pct','company_gp_share_pct','scoped_gp_share_pct']


def trends(frame,lang,prefix):
    st.caption(t('partial_chart_note',lang))
    partial=frame.loc[~frame.is_complete_period,'period'].tolist()
    if partial:st.warning(t('partial_month_list',lang,months=ltr(', '.join(partial),lang)))
    chart(frame,'period','gross_profit',lang,'p5_monthly_gp','line',key=prefix+'_gp')
    chart(frame,'period','gross_margin_pct',lang,'p5_monthly_margin','line',key=prefix+'_margin')


def full_table(frame,lang,key):
    with st.expander(t('p5_full_table',lang)):table(frame,lang,key)


def render(ctx):
    lang=ctx.lang;data=ctx.get('profit5');values=data['current']
    st.subheader(t('p5_overview',lang))
    for keys in (('sales','gross_profit','gross_margin_pct'),('units','orders','company_gp_share_pct')):
        for col,key in zip(st.columns(3),keys):
            with col:
                if key=='company_gp_share_pct':
                    value=values[key]
                    st.metric(t(key,lang),t('unavailable',lang) if value is None else ltr(f'{value:,.2f}%',lang))
                else:metric(key,values[key],lang,'money' if key in ('sales','gross_profit') else 'pct' if key=='gross_margin_pct' else 'number')
    financial_notes(ctx)
    st.caption(t('p5_denominator',lang,value=money(data['company_gross_profit'],lang,False)))
    st.info(t('p5_unavailable_financials',lang))
    mode=choice('selectbox',t('p5_mode',lang),MODES,lang,'p5_mode',lambda v:t(v,lang))
    if mode in ('p5_products','p5_categories','p5_screening'):
        partial=data['monthly'].loc[~data['monthly'].is_complete_period,'period'].tolist()
        if partial:st.warning(t('partial_month_list',lang,months=ltr(', '.join(partial),lang)))
    if not values['orders']:st.info(t('empty',lang))
    if mode=='p5_overview':
        trends(data['monthly'],lang,'p5_overview')
        st.subheader(t('period_comparison',lang));st.caption(t('p5_change_note',lang))
        st.caption(t('previous_period_note',lang,period=ltr(data['growth']['previous_start']+' → '+data['growth']['previous_end'],lang)))
        if not data['growth']['comparable_coverage']:st.warning(t('coverage_unavailable',lang))
        comparison_table(data['comparison'],lang)
        st.subheader(t('p5_refunds',lang));st.write(money(values['refunds'],lang,False));st.caption(t('p5_refund_note',lang))
    elif mode=='p5_products':
        rank=choice('selectbox',t('s4_product_rank',lang),profit.RANKS,lang,'p5_rank',lambda v:t(v,lang))
        a,b=st.columns(2)
        with a:minimum_sales=st.number_input(t('p5_min_revenue',lang),min_value=0.0,value=0.0,step=1000.0,key='p5_min_revenue')
        with b:minimum_units=st.number_input(t('p5_min_units',lang),min_value=0,value=0,step=10,key='p5_min_units')
        st.caption(t('p5_threshold_note',lang))
        for ascending,title in ((False,'p5_top'),(True,'p5_bottom')):
            ranked=profit.rank_products(data['products'],rank,ascending,minimum_sales,minimum_units).head(10)
            st.subheader(t(title,lang))
            chart(ranked.iloc[::-1],'product_id',rank,lang,title,horizontal=True,key=title+'_chart')
            cols=list(dict.fromkeys(['product_id','product',rank,'gross_profit','gross_margin_pct','units']))
            table(ranked[cols],lang,title)
        full_table(data['products'][PRODUCT_COLUMNS],lang,'p5_products_all')
        st.subheader(t('p5_leaders',lang));st.caption(t('p5_leaders_note',lang))
        table(profit.leaders(data['products'])[['rank_basis','product_id','product','sales','gross_profit']],lang,'p5_product_leaders')
    elif mode=='p5_categories':
        frame=data['categories'].sort_values(['gross_profit','category'],ascending=[False,True])
        st.subheader(t('p5_categories',lang));st.caption(t('p5_leaders_note',lang))
        chart(frame,'category','gross_profit',lang,'p5_category_gp',key='p5_category_gp')
        chart(frame,'category','gross_margin_pct',lang,'p5_category_margin',key='p5_category_margin')
        table(frame[['category','sales','gross_profit','gross_margin_pct','company_gp_share_pct']],lang,'p5_categories')
        leaders=[]
        for key in ('sales','gross_profit'):
            if not frame.empty:
                row=frame.sort_values([key,'category'],ascending=[False,True]).iloc[0].to_dict();row['rank_basis']=key;leaders.append(row)
        if leaders:table(pd.DataFrame(leaders)[['rank_basis','category','sales','gross_profit']],lang,'p5_category_leaders')
        monthly=data['category_monthly']
        if not monthly.empty:
            selected=choice('selectbox',t('s4_category_select',lang),sorted(monthly.category.unique()),lang,'p5_category',lambda v:category_name(v,lang))
            chart(monthly.loc[monthly.category.eq(selected)],'month','gross_profit',lang,'p5_monthly_gp','line',key='p5_category_trend')
        show_changes(data['category_changes'],lang,'p5_category_changes','category')
        st.subheader(t('p5_declining_categories',lang));table(data['declining_categories'],lang,'p5_declining_categories')
    elif mode=='p5_locations':
        frame=data['locations'].sort_values(['gross_profit','branch_id'],ascending=[False,True])
        st.subheader(t('p5_locations',lang));st.caption(t('p5_locations_note',lang))
        table(frame[['branch','retail_location_type','sales','gross_profit','gross_margin_pct','company_gp_share_pct']],lang,'p5_locations')
        full_table(frame[['branch_id','branch','retail_location_type','sales','gross_profit','gross_margin_pct','company_gp_share_pct','growth_pct','recorded_orders']],lang,'p5_locations_all')
        show_changes(data['location_changes'],lang,'p5_location_changes','branch_id')
        st.caption(t('p5_drill_note',lang))
        if not frame.empty:
            names=frame.set_index('branch_id').branch.to_dict()
            selected=choice('selectbox',t('p5_drill',lang),frame.branch_id.tolist(),lang,'p5_location',lambda v:v+' · '+names[v])
            local=replace(ctx,scope=replace(ctx.scope,branch=selected)).get('profit5')
            st.subheader(selected+' · '+names[selected]);trends(local['monthly'],lang,'p5_location')
            table(local['categories'][['category','sales','gross_profit','gross_margin_pct','company_gp_share_pct']],lang,'p5_location_categories')
            table(profit.rank_products(local['products']).head(10)[['product_id','product','sales','gross_profit','gross_margin_pct']],lang,'p5_location_products')
    else:screening(data,lang)


def show_changes(frame,lang,title,key):
    st.subheader(t(title,lang));st.caption(t('p5_change_note',lang))
    table(frame[[key,'gross_profit','previous_gross_profit','gp_change','gp_growth_pct','comparable_coverage']],lang,title)


def screening(data,lang):
    rules=profit.ScreeningRules()
    st.subheader(t('p5_screening',lang));st.caption(t('p5_rules',lang,**asdict(rules)))
    frame=data['products'];visible=frame.loc[frame.sales.gt(0) & frame.has_recorded_lines].copy()
    if visible.empty:st.info(t('empty',lang))
    else:
        fig=px.scatter(visible,x='units',y='gross_margin_pct',size='sales',color='gross_profit',hover_name='product_id',
            hover_data=['product','sales','gross_profit'],size_max=45,color_continuous_scale=['#10263e','#0c9697'],
            labels={key:t(key,lang) for key in visible if key in TEXT})
        style_figure(fig,lang,'p5_scatter')
        st.plotly_chart(fig,width='stretch',config={'displayModeBar':False},key='p5_scatter')
    st.caption(t('p5_scatter_note',lang))
    for key,group in profit.screen_products(frame,rules).items():
        st.subheader(t(key,lang));ranked=group.sort_values(['gross_profit','product_id'],ascending=[False,True])
        table(ranked[['product_id','product','sales','units','gross_margin_pct','company_gp_share_pct']],lang,key)
    st.subheader(t('p5_declining_categories',lang));st.caption(t('p5_change_note',lang))
    table(data['declining_categories'],lang,'p5_screen_declines')
