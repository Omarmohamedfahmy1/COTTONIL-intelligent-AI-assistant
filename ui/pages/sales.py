import streamlit as st
from ui.i18n import t
from ui.state import choice
from ui.sales_branch_components import sales_body


def render(ctx):
    lang=ctx.lang
    grain=choice('selectbox',t('s4_periods',lang),['monthly','weekly','daily','yearly'],lang,'s4_grain',lambda v:t(v,lang))
    sales_body(ctx.get('sales4',grain),lang,'s4')
