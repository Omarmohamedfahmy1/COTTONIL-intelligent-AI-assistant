"""Stable widget keys preserve canonical filter values when labels/language change."""
from dataclasses import asdict
from datetime import date,timedelta
import streamlit as st
from services.filters import filters,complete_month_bounds,LOCATION_TYPES
from ui.i18n import t,category_name,PAGES,ltr
from ui.data import catalog,stamp,Context


def initialize():
    if 'language' not in st.session_state:
        st.session_state.language='English' if st.query_params.get('lang')=='en' else 'العربية'
    if 'page' not in st.session_state:
        candidate=st.query_params.get('page',PAGES[0])
        st.session_state.page=candidate if candidate in PAGES else PAGES[0]
    st.session_state.setdefault('dialog',[])
    st.session_state.setdefault('assistant_open',False)


def choice(kind,label,options,lang,key,format_func,**kwargs):
    """Remount translated option widgets while preserving their canonical values.

    Streamlit may retain an old frontend display value when format_func changes
    under the same widget key. Callbacks keep state independent of localized keys.
    """
    widget_key=key+('_en' if lang=='English' else '_ar')
    if key not in st.session_state or st.session_state.get(key) not in options:
        st.session_state[key]=options[0]
    # None is a valid service scope (all), but Streamlit treats a widget value of
    # None as a cleared selection. A presentation-only sentinel keeps its label visible.
    sentinel='__all__'
    def decode(value):
        return None if value==sentinel else value
    widget_options=[sentinel if value is None else value for value in options]
    st.session_state[widget_key]=sentinel if st.session_state[key] is None else st.session_state[key]
    def save():
        st.session_state[key]=decode(st.session_state[widget_key])
    selected=getattr(st,kind)(label,widget_options,key=widget_key,format_func=lambda value:format_func(decode(value)),on_change=save,**kwargs)
    return decode(selected)


def sidebar():
    initialize()
    with st.sidebar:
        st.markdown('## COTTONIL')
        lang=st.radio(t('language',st.session_state.language),['العربية','English'],key='language',horizontal=True)
        st.caption(t('brand_sub',lang))
        choice('radio',t('navigation',lang),PAGES,lang,'page',lambda page:t(page,lang))
        st.divider()
        st.subheader(t('filters',lang))
        locations,categories,(first,last)=catalog(stamp())
        if first is None or last is None:
            st.warning(t('empty',lang))
            st.stop()
        complete=complete_month_bounds(first,last)
        end=date.fromisoformat(complete[1]) if complete else last
        st.session_state.setdefault('filter_dates',(max(first,end-timedelta(days=364)),end))
        try:
            period=st.date_input(t('dates',lang),min_value=first,max_value=last,format='YYYY-MM-DD',key='filter_dates')
        except (ValueError,TypeError):
            st.error(t('invalid_dates',lang));st.stop()
        location_type=choice('selectbox',t('type_filter',lang),[None,*LOCATION_TYPES],lang,'filter_type',
            lambda value:t(value,lang) if value else t('all_types',lang))
        available=locations if location_type is None else locations[locations.retail_location_type==location_type]
        options=[None,*available.branch_id.tolist()]
        if st.session_state.get('filter_branch') not in options:
            st.session_state.filter_branch=None
            st.caption(t('location_reset',lang))
        names=locations.set_index('branch_id').branch_name_ar.to_dict()
        branch=choice('selectbox',t('branch_filter',lang),options,lang,'filter_branch',
            lambda value:f'{value} · {names[value]}' if value else t('all_locations',lang))
        if st.session_state.get('filter_category') not in [None,*categories]:
            st.session_state.filter_category=None
        category=choice('selectbox',t('category_filter',lang),[None,*categories],lang,'filter_category',
            lambda value:category_name(value,lang) if value else t('all_categories',lang))
        st.divider()
        st.caption(t('coverage',lang,first=ltr(first,lang),last=ltr(last,lang)))
        st.caption(t('source',lang))
    if not isinstance(period,(tuple,list)) or len(period)!=2 or period[0]>period[1]:
        st.warning(t('invalid_dates',lang));st.stop()
    try:
        scope=filters(*period,branch,location_type,category)
    except ValueError:
        st.error(t('invalid_scope',lang));st.stop()
    st.session_state.active_scope=asdict(scope)
    st.query_params['lang']='en' if lang=='English' else 'ar'
    st.query_params['page']=st.session_state.page
    return Context(lang,scope)
