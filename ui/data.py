"""Cached presentation adapters. Queries/formulas remain in the approved services."""
from dataclasses import dataclass
import streamlit as st
import analytics as api
from predictive import forecast, customer_results


def stamp():
    return api.DB.stat().st_mtime_ns


@st.cache_data(show_spinner=False)
def catalog(version):
    return api.branches(), api.read('SELECT DISTINCT category_en FROM products_catalog ORDER BY category_en').category_en.tolist(), api.metadata()


@st.cache_data(ttl=1200,show_spinner=False)
def query(tag, scope, version, extra=None):
    if tag=='customer8':
        from services.customers import dashboard
        return dashboard(scope.start,scope.end,scope.branch,location_type=scope.location_type,category=scope.category)
    if tag=='customer8_models':
        from services.customer_models import research as customer_research
        return customer_research()
    if tag=='forecast7':
        from services.forecasting import forecast_report
        return forecast_report(scope.branch,location_type=scope.location_type,category=scope.category,horizon=extra or 3)
    if tag=='inventory6':
        from services import inventory as inv
        kind,warehouse,lookback,horizon,low_cover=extra or ('Branch',None,90,30,14)
        return inv.dashboard(scope.start,scope.end,scope.branch,location_type=scope.location_type,category=scope.category,
            kind=kind,warehouse=warehouse,planning=inv.Planning(lookback_days=lookback,horizon_days=horizon,low_cover_days=low_cover))
    if tag=='transfers6':
        from services.inventory import transfer_analysis
        warehouse,status=extra or (None,None)
        return transfer_analysis(scope.start,scope.end,scope.branch,location_type=scope.location_type,category=scope.category,warehouse=warehouse,status=status)
    if tag=='inventory6_pair':
        from services.inventory_tools import answer_readonly
        return answer_readonly('inventory6_pair',dict(start=scope.start,end=scope.end,branch=scope.branch,location_type=scope.location_type,category=scope.category),dict(branch_a=extra[0],branch_b=extra[1]))
    if tag=='profit5':
        from services.profitability import dashboard
        return dashboard(scope.start,scope.end,scope.branch,location_type=scope.location_type,category=scope.category)
    if tag in ('sales4','locations4','detail4','pair4'):
        from services import sales_branch as sb
        if tag=='sales4':return sb.sales_analysis(**sb.args(scope),grain=extra or 'monthly')
        if tag=='locations4':return sb.location_roster(scope.start,scope.end,location_type=scope.location_type,category=scope.category)
        if tag=='detail4':return sb.branch_detail(scope.start,scope.end,extra,location_type=scope.location_type,category=scope.category)
        return sb.compare_two(scope.start,scope.end,*extra,category=scope.category)
    if tag=='executive':
        from services.executive import dashboard
        return dashboard(scope.start,scope.end,scope.branch,location_type=scope.location_type,category=scope.category)
    args=(scope.start,scope.end,scope.branch)
    shared={'location_type':scope.location_type,'category':scope.category}
    functions={'overview':api.overview,'monthly':api.sales_monthly,'channels':api.sales_channel,
               'seasonality':api.seasonality,'categories':api.category_performance,
               'customers':api.customer_activity,'growth':api.sales_growth}
    if tag in functions:
        return functions[tag](*args,**shared)
    if tag=='branches':
        return api.branch_performance(scope.start,scope.end,**shared)
    if tag=='products':
        return api.product_performance(*args,sort=extra or 'gross_profit',limit=1000,**shared)
    if tag=='inventory':
        return api.inventory_snapshot(scope.end,scope.branch,**shared)
    if tag=='forecast':
        return forecast(api.company_sales_fully_observed_months(scope.branch,scope.category,location_type=scope.location_type),6)
    raise ValueError('Unsupported presentation query')


@st.cache_data(ttl=1200,show_spinner=False)
def research(version, artifacts_version):
    scores,meta=customer_results()
    if scores is None:
        return None
    # Existing recency bands, unchanged. Only aggregate research leaves this adapter;
    # customer identifiers, raw predictions and names never reach UI/exports.
    bands=[int(scores.recency_days.between(a,b).sum()) for a,b in [(0,30),(31,90),(91,180),(181,365)]]
    return {'meta':meta,'count':len(scores),'recency_counts':bands}


@dataclass(frozen=True)
class Context:
    lang: str
    scope: object

    def get(self,tag,extra=None):
        return query(tag,self.scope,stamp(),extra)

    def assistant_scope(self):
        return {'start':self.scope.start,'end':self.scope.end,'branch':self.scope.branch,
                'location_type':self.scope.location_type,'category':self.scope.category}
