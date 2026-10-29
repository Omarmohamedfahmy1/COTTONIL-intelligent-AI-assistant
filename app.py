"""Cottonil bilingual application shell. Business definitions live in services/."""
import streamlit as st
from analytics import DB
from ui.i18n import t,PAGES,ltr
from ui.state import sidebar,initialize
from ui.theme import apply_theme
from ui.components import scope_caption
from ui.assistant import quick_access
from ui.data import catalog,stamp
from ui.pages import overview,sales,branches,inventory,forecasting,profitability,customers,assistant

st.set_page_config(page_title='Cottonil | Business Intelligence',page_icon='🧵',layout='wide',initial_sidebar_state='expanded')
initialize()
apply_theme(st.session_state.language)
if not DB.exists():
    st.error(t('missing_db',st.session_state.language))
    st.stop()
try:
    ctx=sidebar()
    apply_theme(ctx.lang)
    heading,action=st.columns([3,1])
    with heading:
        st.caption('COTTONIL · '+t('brand_sub',ctx.lang))
        st.title(t(st.session_state.page,ctx.lang))
    with action:
        quick_access(ctx)
    scope_caption(ctx)
    _,_,(first,last)=catalog(stamp())
    st.caption(t('coverage',ctx.lang,first=ltr(first,ctx.lang),last=ltr(last,ctx.lang))+' · '+t('source',ctx.lang))
    st.divider()
    pages=dict(zip(PAGES,[overview,sales,branches,inventory,forecasting,profitability,customers,assistant]))
    with st.spinner(t('loading',ctx.lang)):
        pages[st.session_state.page].render(ctx)
    with st.expander(t('definitions',ctx.lang)):
        for key in ('sales_note','refund_note','identified_note','growth_definition'):
            st.write(t(key,ctx.lang))
    st.divider()
    st.caption(t('footer',ctx.lang))
except ValueError:
    st.error(t('invalid_scope',st.session_state.language))
except Exception:
    st.error(t('data_error',st.session_state.language))
