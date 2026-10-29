"""Phase 6 views; calculations remain exclusively in inventory services."""
from dataclasses import replace
import pandas as pd
import plotly.express as px
import streamlit as st
from services import inventory as inv,metrics as kpi
from services.inventory_tools import answer_readonly
from ui.components import chart,table,metric,style_figure
from ui.i18n import t,ltr,TEXT
from ui.state import choice

MODES=('i6_overview','i6_locations','i6_warehouses','i6_risk','i6_coverage','i6_transfers','i6_trends')
DETAIL=['location_id','location','retail_location_type','category','stock_units','stock_value','recorded_risk','risk_label','sold_units','daily_units','cover_days','estimated_replenishment']


def full(frame,lang,key):
    with st.expander(t('p5_full_table',lang)):table(frame,lang,key)


def render(ctx):
    lang=ctx.lang
    st.caption(t('i6_snapshot_policy',lang))
    mode=choice('selectbox',t('i6_mode',lang),MODES,lang,'i6_mode',lambda v:t(v,lang))
    with st.expander(t('i6_planning',lang)):
        a,b,c=st.columns(3)
        with a:lookback=st.number_input(t('i6_lookback',lang),min_value=7,max_value=365,value=90,key='i6_lookback')
        with b:horizon=st.number_input(t('i6_horizon',lang),min_value=1,max_value=180,value=30,key='i6_horizon')
        with c:low_cover=st.number_input(t('i6_low_cover',lang),min_value=1,max_value=120,value=14,key='i6_low_cover')
    warehouse=None;kind='Warehouse' if mode=='i6_warehouses' else 'Branch'
    if kind=='Warehouse' or mode=='i6_transfers':
        master=inv.warehouses();names=master.set_index('warehouse_id').warehouse_label.to_dict()
        warehouse=choice('selectbox',t('i6_warehouse_select',lang),[None,*names],lang,'i6_warehouse',lambda v:v+' · '+names[v] if v else t('i6_all_warehouses',lang))
    data=ctx.get('inventory6',(kind,warehouse if kind=='Warehouse' else None,int(lookback),int(horizon),int(low_cover)))
    if kind=='Warehouse':st.info(t('i6_warehouse_override',lang))
    st.subheader(t('i6_locations' if mode=='i6_overview' else mode,lang))
    if mode=='i6_transfers':
        transfers(ctx,warehouse);return
    if not data['month']:st.info(t('empty',lang));return
    st.caption(t('i6_snapshot',lang,month=ltr(data['month'],lang)))
    keys=('stock_units','stock_value','high_risk_combinations','high_risk_categories') if kind=='Warehouse' else ('stock_units','stock_value','high_risk_combinations','high_risk_categories','low_cover_combinations','estimated_replenishment')
    for start in range(0,len(keys),3):
        for col,key in zip(st.columns(min(3,len(keys)-start)),keys[start:start+3]):
            with col:metric('i6_high_categories' if key=='high_risk_categories' else key,data['summary'][key],lang,'money' if key=='stock_value' else 'number')
    st.caption(t('i6_estimate_note',lang))
    st.caption(t('i6_rules',lang,**data['planning']))
    if kind=='Branch':
        st.caption(t('i6_window',lang,start=ltr(data['window']['start'],lang),end=ltr(data['window']['end'],lang),days=data['window']['days']))
        st.caption(t('i6_formula',lang,**data['planning']))
        if not data['window']['complete']:st.warning(t('i6_uncovered',lang))
    if mode=='i6_overview':
        chart(data['categories'],'category','stock_units',lang,'stock_chart',key='i6_category_stock')
        table(data['categories'][['category','stock_units','stock_value','max_recorded_risk','high_risk_combinations']],lang,'i6_category_overview')
        st.subheader(t('i6_risk_rows',lang))
        table(data['high_risk_rows'][['location','category','stock_units','recorded_risk','risk_label']],lang,'i6_high_risk_overview')
        st.subheader(t('i6_coverage',lang))
        table(data['low_cover_rows'][['location','category','stock_units','daily_units','cover_days','estimated_replenishment']],lang,'i6_low_overview')
        st.caption(t('i6_zero_note',lang))
    elif mode=='i6_locations':
        frame=data['rows'];locations=frame.groupby(['location_id','location','retail_location_type'],as_index=False).agg(stock_units=('stock_units','sum'),stock_value=('stock_value','sum'),max_recorded_risk=('recorded_risk','max'))
        table(locations,lang,'i6_location_totals')
        names=locations.set_index('location_id').location.to_dict()
        selected=choice('selectbox',t('p5_drill',lang),list(names),lang,'i6_location',lambda v:v+' · '+names[v])
        st.caption(t('p5_drill_note',lang))
        local=frame.loc[frame.location_id.eq(selected)]
        st.subheader(selected+' · '+names[selected])
        table(local[['category','stock_units','stock_value','recorded_risk','cover_days','estimated_replenishment']],lang,'i6_location_detail')
        full(local[DETAIL],lang,'i6_location_all')
        pair(ctx)
    elif mode=='i6_warehouses':
        st.caption(t('i6_available',lang,months=ltr(', '.join(data['available_months']),lang)))
        table(data['rows'][['location','category','stock_units','stock_value','recorded_risk']],lang,'i6_warehouse_rows')
        chart(data['categories'],'category','stock_units',lang,'stock_chart',key='i6_wh_category')
        table(data['categories'],lang,'i6_warehouse_categories')
    elif mode=='i6_risk':
        st.subheader(t('i6_risk_categories',lang))
        chart(data['categories'],'category','max_recorded_risk',lang,'risk_chart',key='i6_risk_chart')
        table(data['categories'],lang,'i6_risk_category')
        st.subheader(t('i6_risk_rows',lang));table(data['high_risk_rows'][['location','retail_location_type','category','stock_units','recorded_risk']],lang,'i6_risk_rows')
        st.subheader(t('i6_distribution',lang));st.caption(t('i6_share_note',lang));table(data['distribution'],lang,'i6_distribution')
    elif mode=='i6_coverage':
        st.caption(t('i6_zero_note',lang))
        table(data['rows'][['location','category','stock_units','daily_units','cover_days','estimated_replenishment']],lang,'i6_cover_rows')
        full(data['rows'][DETAIL],lang,'i6_cover_all')
        st.subheader(t('i6_replenish',lang));table(data['rows'].loc[data['rows'].replenishment_attention,['location','category','stock_units','daily_units','cover_days','estimated_replenishment']],lang,'i6_replenish')
        st.subheader(t('i6_slow',lang));table(data['slow_rows'][['location','category','stock_units','daily_units','cover_days','slow_moving_proxy','high_cover_proxy']],lang,'i6_slow')
    else:
        st.caption(t('i6_balance_note',lang));st.info(t('i6_warehouse_override',lang))
        branch=data['history'].copy();branch['stock_kind']='Branch'
        warehouse_data=ctx.get('inventory6',('Warehouse',None,int(lookback),int(horizon),int(low_cover)))
        wh=warehouse_data['history'].copy();wh['stock_kind']='Warehouse'
        history=pd.concat([branch,wh],ignore_index=True);history['stock_kind']=history.stock_kind.map(lambda v:t(v,lang))
        for key,title in (('stock_units','i6_stock_trend'),('stock_value','i6_value_trend'),('mean_recorded_risk','i6_risk_trend')):
            if history.empty:st.info(t('empty',lang));continue
            fig=px.line(history,x='month',y=key,color='stock_kind',markers=True,labels={c:t(c,lang) for c in history if c in TEXT},color_discrete_sequence=['#0c9697','#10263e'])
            style_figure(fig,lang,title);fig.update_xaxes(type='category')
            st.plotly_chart(fig,width='stretch',config={'displayModeBar':False},key='i6_trend_'+key)
        table(history,lang,'i6_history')
        st.subheader(t('i6_network',lang));st.caption(t('i6_network_note',lang))
        table(inv.network_distribution(data,warehouse_data),lang,'i6_network')
        st.subheader(t('i6_changes',lang));table(data['category_changes'],lang,'i6_changes')


def transfers(ctx,warehouse):
    lang=ctx.lang;st.caption(t('i6_transfer_note',lang))
    status=choice('selectbox',t('i6_status',lang),[None,*inv.STATUSES],lang,'i6_status',lambda v:t(v,lang) if v else t('i6_all_statuses',lang))
    data=ctx.get('transfers6',(warehouse,status))
    for col,key in zip(st.columns(3),('transfer_count','transfer_units','transport_cost')):
        with col:metric(key,data['summary'][key],lang,'money' if key=='transport_cost' else 'number')
    if data['monthly'].empty:st.info(t('empty',lang));return
    frame=data['monthly'].copy();frame['transfer_status']=frame.transfer_status.map(lambda v:t(v,lang))
    fig=px.bar(frame,x='month',y='transfer_units',color='transfer_status',labels={c:t(c,lang) for c in frame if c in TEXT},color_discrete_sequence=['#0c9697','#10263e','#6899ad'])
    style_figure(fig,lang,'i6_transfer_trend');fig.update_xaxes(type='category')
    st.plotly_chart(fig,width='stretch',config={'displayModeBar':False},key='i6_transfer_trend')
    for key in ('statuses','sources','destinations','categories'):
        table(data[key],lang,'i6_transfer_'+key)


def pair(ctx):
    lang=ctx.lang
    with st.expander(t('i6_pair_select',lang)):
        st.caption(t('b4_pair_scope',lang))
        master=kpi.branches();names=master.set_index('branch_id').branch_name_ar.to_dict();options=list(names)
        a=choice('selectbox',t('location_a',lang),options,lang,'i6_pair_a',lambda v:v+' · '+names[v])
        b=choice('selectbox',t('location_b',lang),options[1:]+options[:1],lang,'i6_pair_b',lambda v:v+' · '+names[v])
        if a==b:st.info(t('i6_pair_missing',lang));return
        try:report=ctx.get('inventory6_pair',(a,b))
        except ValueError:st.info(t('i6_pair_missing',lang));return
        st.caption(t('i6_snapshot',lang,month=report['meta']['snapshot'] or t('unavailable',lang)))
        for row in report['meta']['location_types']:st.caption(row['branch_id']+' · '+t(row['retail_location_type'],lang))
        table(pd.DataFrame(report['data']),lang,'i6_pair')
