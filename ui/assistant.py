"""Localized presentation of the existing offline tools and optional provider.

Legacy engine plus a narrow Phase 4 read-only service allowlist. No free-form
planner or financial formulas; numerical statements come from verified reports.
"""
import os
import pandas as pd
import streamlit as st
from assistant_engine import offline_reply
from ui.i18n import t,category_name,ltr
from ui.components import money,table,chart,scope_caption
from ui.state import choice


def offline_answer(question,ctx):
    from services.customer_tools import dispatch as customer_dispatch
    from services.forecast_tools import dispatch as forecast_dispatch
    from ui.i18n import CATEGORIES
    from services.inventory_tools import dispatch as inventory_dispatch
    from services.profitability_tools import dispatch as profit_dispatch
    from services.sales_branch_tools import dispatch
    local=customer_dispatch(question,ctx.assistant_scope())
    if local is None:local=forecast_dispatch(question,ctx.assistant_scope(),CATEGORIES)
    if local is None:local=inventory_dispatch(question,ctx.assistant_scope())
    if local is None:local=profit_dispatch(question,ctx.assistant_scope())
    if local is None:local=dispatch(question,ctx.assistant_scope())
    if local is not None:
        if 'clarify' in local:return t(local['clarify'],ctx.lang),[]
        meta=local['meta'];start,end=meta['period'].split(' to ')
        text=t('c8_assistant_verified' if meta['tool'].startswith('customer8_') else 'f7_assistant_verified' if meta['tool'].startswith('forecast7_') else 'i6_assistant_verified' if meta['tool'].startswith('inventory6_') else 'p5_assistant_verified' if meta['tool'].startswith('profit5_') else 's4_assistant_verified',ctx.lang,tool=t(meta['tool'],ctx.lang),
            start=ltr(start,ctx.lang),end=ltr(end,ctx.lang),
            branch=t('all_locations',ctx.lang) if meta['branch_id']=='all' else t('pair',ctx.lang) if meta['branch_id']=='pair' else ltr(meta['branch_id'],ctx.lang),
            kind=t(meta['location_type'],ctx.lang) if meta.get('location_type') else t('all_types',ctx.lang),
            category=category_name(meta['category'],ctx.lang) if meta.get('category') else t('all_categories',ctx.lang))
        if meta['tool'].startswith('customer8_'):
            text+='\n\n'+t('c8_privacy_note',ctx.lang)
            if meta.get('company_wide'):
                text+='\n\n'+t('c8_model_note',ctx.lang,origin=meta.get('origin') or t('unavailable',ctx.lang))
                text+='\n\n'+t(meta['state'],ctx.lang)
            else:text+='\n\n'+t('c8_scope_note',ctx.lang)
        if meta['tool'].startswith('forecast7_'):
            text+='\n\n'+t('f7_assistant_note',ctx.lang,origin=ltr(meta.get('origin') or t('f7_multiple_origins',ctx.lang),ctx.lang),target=t(meta.get('target','units'),ctx.lang),unit=t('units' if meta.get('unit')=='units' else 'egp',ctx.lang))
            if meta.get('state'):text+='\n\n'+t(meta['state'],ctx.lang)
            if meta.get('reason'):text+='\n\n'+t(meta['reason'],ctx.lang)
        if not local['data']:text+='\n\n'+t('empty',ctx.lang)
        return text,[local]
    _,reports=offline_reply(question,ctx.assistant_scope())
    if not reports:
        return t('unsupported',ctx.lang),[]
    report=reports[0]
    if not report.get('data'):
        return t('empty',ctx.lang),reports
    row,meta=report['data'][0],report['meta']
    tool=meta['tool']
    if tool=='company_overview':
        text=t('answer_sales',ctx.lang,sales=money(row['sales'],ctx.lang,False),profit=money(row['gross_profit'],ctx.lang,False),orders=f"{row['orders']:,}")
        from services.executive import assistant_summary
        reports.append(assistant_summary(ctx.assistant_scope()))
    elif tool=='demand_forecast':
        value=f"{row['value']:,.2f} {t('units',ctx.lang)}" if meta.get('category') else money(row['value'],ctx.lang,False)
        text=t('answer_forecast',ctx.lang,month=row['month'],value=value,error=meta['validation_WAPE_pct'])
    elif tool=='inventory':
        text=t('answer_inventory',ctx.lang,month=meta['snapshot'])
    else:
        text=t('report_ready',ctx.lang)
    start,end=meta['period'].split(' to ')
    text+='\n\n'+t('answer_scope',ctx.lang,start=start,end=end,
        branch=t('all_locations',ctx.lang) if meta['branch_id']=='all' else meta['branch_id'],
        category=category_name(meta.get('category'),ctx.lang) if meta.get('category') else t('all_categories',ctx.lang))
    return text,reports


def report_view(report,ctx,key):
    data=report.get('data',[])
    if not data:
        st.info(t('empty',ctx.lang));return
    tool=report['meta']['tool']
    if tool.startswith('customer8_'):
        st.caption(t('c8_privacy_note',ctx.lang));st.caption(t('c8_scope_note',ctx.lang))
        if report['meta'].get('company_wide'):
            st.info(t('c8_model_note',ctx.lang,origin=report['meta'].get('origin')))
            st.warning(t(report['meta']['state'],ctx.lang))
            st.caption(t('c8_churn_note' if tool=='customer8_churn' else 'c8_value_note',ctx.lang))
    if tool.startswith('forecast7_'):
        st.caption(t('f7_dates',ctx.lang));st.caption(t('f7_band_note',ctx.lang));st.caption(t('f7_boundary',ctx.lang))
    if tool.startswith('inventory6_'):
        st.caption(t('i6_snapshot_policy',ctx.lang));st.caption(t('i6_estimate_note',ctx.lang))
        meta=report['meta']
        st.caption(t('i6_rules',ctx.lang,**meta['planning']));st.caption(t('i6_formula',ctx.lang,**meta['planning']))
        if meta.get('snapshot'):st.caption(t('i6_snapshot',ctx.lang,month=meta['snapshot']))
        if tool=='inventory6_warehouse':st.info(t('i6_warehouse_override',ctx.lang))
        if tool=='inventory6_transfers':st.caption(t('i6_transfer_note',ctx.lang))
        if tool=='inventory6_pair':
            st.caption(t('b4_pair_scope',ctx.lang))
            for row in meta['location_types']:st.caption(row['branch_id']+' · '+t(row['retail_location_type'],ctx.lang))
        if meta.get('sales_window') and tool!='inventory6_warehouse':
            st.caption(t('i6_window',ctx.lang,start=ltr(meta['sales_window']['start'],ctx.lang),end=ltr(meta['sales_window']['end'],ctx.lang),days=meta['sales_window']['days']))
            if not meta['sales_window']['complete']:st.warning(t('i6_uncovered',ctx.lang))
    if tool.startswith('profit5_'):
        st.caption(t('sales_note',ctx.lang));st.caption(t('p5_unavailable_financials',ctx.lang))
        st.caption(t('p5_tool_policy',ctx.lang))
        if tool=='profit5_screening':st.caption(t('p5_rules',ctx.lang,**report['meta']['rules']))
        if tool=='profit5_pair':
            st.caption(t('b4_pair_scope',ctx.lang))
            for row in report['meta']['location_types']:
                st.caption(row['branch_id']+' · '+t(row['retail_location_type'],ctx.lang))
    from services.sales_branch_tools import ALLOWED as PHASE4_TOOLS
    if tool in PHASE4_TOOLS:
        st.caption(t('sales_note',ctx.lang))
        if tool in ('location_ranking','declining_locations'):st.caption(t('b4_ranking_note',ctx.lang))
        if tool=='two_location_comparison':
            st.caption(t('b4_pair_scope',ctx.lang))
            meta=report['meta']
            st.caption(t('b4_pair_names',ctx.lang,a=meta['branch_a'],b=meta['branch_b'],
                type_a=t(meta['location_types'][0]['retail_location_type'],ctx.lang),
                type_b=t(meta['location_types'][1]['retail_location_type'],ctx.lang)))
    if tool=='executive_summary':
        st.subheader(t('executive_scorecards',ctx.lang))
        st.caption(t('executive_assistant_note',ctx.lang))
        st.caption(t('stock_note',ctx.lang,month=ltr(report['data'][0]['stock_month'] or t('unavailable',ctx.lang),ctx.lang)))
        st.caption(t('registered_scope',ctx.lang))
    if tool in ('company_overview','profitability'):
        st.caption(t('sales_note',ctx.lang))
        if tool=='company_overview':st.caption(t('refund_note',ctx.lang))
    if tool=='compare_branches':st.caption(t('benchmark_note',ctx.lang))
    if tool=='inventory':st.caption(t('stock_note',ctx.lang,month=ltr(report['meta']['snapshot'],ctx.lang)))
    if tool=='demand_forecast':st.caption(t('forecast_note',ctx.lang))
    if tool=='customer_intelligence':
        st.warning(t('churn_warning',ctx.lang,auc=report['meta']['model_validation_roc_auc']))
        st.caption(t('value_note',ctx.lang))
    frame=pd.DataFrame(data)
    table(frame,ctx.lang,key,False)
    graph=report.get('plot')
    if graph and graph['x'] in frame and graph['y'] in frame:
        title={'sales4_trends':'monthly_sales','sales_trends':'monthly_sales','compare_branches':'branch_compare','top_products':'top_products',
               'profitability':'profit_category','inventory':'stock_chart','demand_forecast':'forecast_chart'}.get(tool,'table')
        chart(frame,graph['x'],graph['y'],ctx.lang,title,graph['type'],key=key+'_chart')


def render(ctx,prefix='full'):
    from ui.assistant_phase9 import render as phase9_render
    return phase9_render(ctx,prefix)


def quick_access(ctx):
    def open_panel():
        st.session_state.assistant_open=True
    def dismiss_panel():
        st.session_state.assistant_open=False
    st.button(t('ask',ctx.lang),key='assistant_access',type='primary',width='stretch',on_click=open_panel)
    if st.session_state.assistant_open:
        @st.dialog(t('AI Business Assistant',ctx.lang),width='large',on_dismiss=dismiss_panel)
        def panel():
            render(ctx,'quick')
            if st.button(t('close',ctx.lang),key='assistant_close'):
                dismiss_panel()
                st.rerun()
        panel()


def run_llm(question,context,api_key=None,history=None,model=None,*,state=None,retry=False):
    """Compatibility symbol for UI tests; inference is exclusively official Groq SDK."""
    from dataclasses import replace
    from ui.assistant_phase9 import settings
    from services.business_assistant import run
    config=settings()
    if api_key:config=replace(config,api_key=api_key)
    generation=st.session_state.get('a9_generation',0)
    return run(question,context,state,connected=True,settings=config,retry=retry,
        cancelled=lambda:st.session_state.get('a9_generation',0)!=generation)
