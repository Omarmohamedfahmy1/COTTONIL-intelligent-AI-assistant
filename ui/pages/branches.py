import streamlit as st
from services.sales_branch import rank_locations
from ui.components import chart,table
from ui.i18n import t,ltr
from ui.state import choice
from ui.data import catalog,stamp
from ui.sales_branch_components import sales_body,grouped_chart,pair_table


def render(ctx):
    lang=ctx.lang
    mode=choice('radio',t('b4_mode',lang),['ranking','detail','pair'],lang,'b4_mode',lambda v:t(v,lang),horizontal=True)
    locations,_,_=catalog(stamp())
    names=locations.set_index('branch_id').branch_name_ar.to_dict()
    labels=lambda v:f'{v} · {names[v]}'
    st.caption(t('b4_assistant_scope',lang))
    if mode=='detail':
        options=locations if not ctx.scope.location_type else locations[locations.retail_location_type.eq(ctx.scope.location_type)]
        ids=options.branch_id.tolist()
        if not ids:st.info(t('empty',lang));return
        if 'b4_detail' not in st.session_state:st.session_state.b4_detail=ctx.scope.branch or ids[0]
        branch=choice('selectbox',t('b4_detail_select',lang),ids,lang,'b4_detail',labels)
        st.info(t('b4_detail_scope',lang,branch=labels(branch)))
        sales_body(ctx.get('detail4',branch),lang,'b4_detail',full=False)
        return
    if mode=='pair':
        st.info(t('b4_pair_scope',lang))
        if len(locations)<2:st.warning(t('b4_pair_distinct',lang));return
        if 'b4_a' not in st.session_state:
            matching=locations if not ctx.scope.location_type else locations[locations.retail_location_type.eq(ctx.scope.location_type)]
            st.session_state.b4_a=ctx.scope.branch or (matching.branch_id.iloc[0] if not matching.empty else locations.branch_id.iloc[0])
        a=choice('selectbox',t('location_a',lang),locations.branch_id.tolist(),lang,'b4_a',labels)
        b=choice('selectbox',t('location_b',lang),locations.loc[locations.branch_id.ne(a),'branch_id'].tolist(),lang,'b4_b',labels)
        data=ctx.get('pair4',(a,b))
        types=locations.set_index('branch_id').retail_location_type.to_dict()
        st.caption(t('b4_pair_names',lang,a=labels(a),b=labels(b),type_a=t(types[a],lang),type_b=t(types[b],lang)))
        st.caption(t('b4_pair_coverage',lang));st.caption(t('sales_note',lang))
        pair_table(data['table'],lang)
        grouped_chart(data['monthly'],'period','sales','branch_id',lang,'b4_pair_trends','b4_pair_trends')
        grouped_chart(data['categories'],'category','sales','branch_id',lang,'b4_pair_categories','b4_pair_categories')
        table(data['monthly'],lang,'b4_pair_monthly');table(data['categories'],lang,'b4_pair_categories')
        return
    st.info(t('benchmark_note',lang));st.caption(t('b4_ranking_note',lang));st.caption(t('previous_note',lang))
    by=choice('selectbox',t('rank_by',lang),['sales','gross_profit','growth_pct','aov','orders','units','customers','company_sales_share_pct','orders_per_listed_employee'],lang,'branch_rank',lambda v:t(v,lang))
    ascending=st.toggle(t('ascending',lang),key='branch_ascending')
    roster=ctx.get('locations4');frame=rank_locations(roster,by,ascending)
    st.caption(t('b4_counts',lang,active=int(roster.recorded_orders.sum()),empty=int((~roster.recorded_orders).sum()),total=len(roster)))
    st.caption(t('b4_company_share_note',lang))
    st.caption(t('executive_units_note',lang))
    columns=['branch_id','branch','retail_location_type','sales','gross_profit','growth_pct','orders','units','customers','aov','company_sales_share_pct','recorded_orders','orders_per_listed_employee']
    compact=list(dict.fromkeys(['branch','retail_location_type',by,'sales','gross_profit','growth_pct','aov']))[:6]
    table(frame[compact],lang,'branch_performance')
    with st.expander(t('b4_full_metrics',lang)):
        table(frame[columns],lang,'b4_all_metrics')
    chart(frame.head(12).iloc[::-1],'branch',by,lang,'branch_compare',horizontal=True,key='branch_compare')
    st.caption(t('roster_note',lang))
    st.caption(t('s4_rules',lang))
    declines=roster.loc[roster.significant_decline,['branch_id','branch','retail_location_type','sales','previous_sales','growth_pct','recorded_orders']]
    st.subheader(t('s4_declines',lang));table(declines,lang,'b4_declines')
    active=roster.loc[roster.recorded_orders]
    if not active.empty:
        revenue=active.sort_values(['sales','branch_id'],ascending=[False,True]).iloc[0]
        profit=active.sort_values(['gross_profit','branch_id'],ascending=[False,True]).iloc[0]
        st.info(t('b4_revenue_profit',lang,revenue_name=revenue.branch,profit_name=profit.branch,revenue=ltr(f'{revenue.sales:,.2f}',lang),profit=ltr(f'{profit.gross_profit:,.2f}',lang)))
    st.subheader(t('b4_no_sales',lang));st.caption(t('b4_no_sales_note',lang))
    table(roster.loc[~roster.recorded_orders,['branch_id','branch','retail_location_type','sales','orders','previous_sales','growth_pct']],lang,'b4_no_sales')
    st.caption(t('source_names',lang))
