"""Localized shared display components; no KPI definitions or financial queries."""
import pandas as pd
import plotly.express as px
import streamlit as st
from ui.i18n import t,data_value,category_name,TEXT,ltr

PRIVATE_COLUMNS={'customer_id','customer_name_ar','employee_id','employee_name_ar','churn_probability','risk_band'}


def money(value,lang,compact=True):
    if value is None or pd.isna(value):
        return t('unavailable',lang)
    if compact and abs(value)>=1e9:
        return f'{ltr(f"{value/1e9:,.2f}",lang)} {t("billion",lang)} {t("egp",lang)}'
    if compact and abs(value)>=1e6:
        return f'{ltr(f"{value/1e6:,.2f}",lang)} {t("million",lang)} {t("egp",lang)}'
    return f'{ltr(f"{value:,.2f}",lang)} {t("egp",lang)}'


def metric(key,value,lang,kind='number'):
    if value is None or pd.isna(value):
        display=t('unavailable',lang)
    elif kind=='money':
        display=money(value,lang)
    elif kind=='pct':
        display=ltr(f'{value:.1f}%' if key=='gross_margin_pct' else f'{value:+.1f}%',lang)
    else:
        display=f'{int(value):,}'
    help_text=t('sales_note',lang) if key in ('sales','gross_profit','aov','gross_margin_pct') else None
    if kind=='money':
        help_text=(help_text+' · ' if help_text else '')+money(value,lang,False)
    st.metric(t(key,lang),display,help=help_text)


def public_frame(frame):
    return frame.drop(columns=[c for c in frame.columns if c in PRIVATE_COLUMNS],errors='ignore').copy()


def translated_frame(frame,lang,reverse=False):
    frame=public_frame(frame)
    for col in frame:
        if frame[col].dtype=='object' or frame[col].dtype=='bool':
            frame[col]=frame[col].map(lambda value:data_value(value,lang))
    frame=frame.rename(columns={c:t(c,lang) for c in frame if c in TEXT})
    return frame.iloc[:,::-1] if reverse and lang!='English' else frame


def table(frame,lang,key,export=True):
    if frame is None or frame.empty:
        st.info(t('empty',lang));return
    display=translated_frame(frame,lang,reverse=True)
    numeric={t(c,lang) if c in TEXT else c:st.column_config.NumberColumn(format='%.3f' if c=='risk_score' else ('%d' if pd.api.types.is_integer_dtype(frame[c]) else '%.2f'))
             for c in public_frame(frame) if pd.api.types.is_numeric_dtype(frame[c]) and frame[c].dtype!='bool'}
    st.dataframe(display,hide_index=True,width='stretch',column_config=numeric)
    if export:
        st.download_button(t('export',lang),translated_frame(frame,lang).to_csv(index=False).encode('utf-8-sig'),
            file_name=f'cottonil_{key}.csv',mime='text/csv',key=f'export_{key}')


def chart(frame,x,y,lang,title,kind='bar',horizontal=False,key=None):
    if frame is None or frame.empty:
        st.info(t('empty',lang));return
    frame=public_frame(frame)
    if x in frame:
        frame[x]=frame[x].map(lambda v:data_value(v,lang))
    labels={c:t(c,lang) for c in frame if c in TEXT}
    if kind=='line':
        fig=px.line(frame,x=x,y=y,markers=True,labels=labels)
        fig.update_traces(line_color='#0c9697')
    else:
        fig=px.bar(frame,y=x,x=y,orientation='h',labels=labels) if horizontal else px.bar(frame,x=x,y=y,labels=labels)
        fig.update_traces(marker_color='#0c9697')
    style_figure(fig,lang,title)
    if x in ('month','period'):
        values=frame[x].drop_duplicates().tolist()
        ticks=values[::max(1,len(values)//6)]
        fig.update_xaxes(type='category',tickmode='array',tickvals=ticks,ticktext=ticks)
    st.plotly_chart(fig,width='stretch',config={'displayModeBar':False},key=key)


def style_figure(fig,lang,title):
    fig.update_layout(height=360,title={'text':t(title,lang),'x':0 if lang=='English' else 1,'xanchor':'left' if lang=='English' else 'right'},
        font={'family':'Segoe UI, Tahoma, Arial','color':'#244258','size':13},
        paper_bgcolor='white',plot_bgcolor='white',margin={'l':15,'r':15,'t':55,'b':25},
        xaxis={'gridcolor':'#edf2f6','tickformat':',.2~f','automargin':True},
        yaxis={'gridcolor':'#edf2f6','tickformat':',.2~f','automargin':True},legend={'orientation':'h'})


def scope_caption(ctx):
    s=ctx.scope
    st.caption(t('scope',ctx.lang,start=ltr(s.start,ctx.lang),end=ltr(s.end,ctx.lang),branch=ltr(s.branch,ctx.lang) if s.branch else t('all_locations',ctx.lang),
        kind=t(s.location_type,ctx.lang) if s.location_type else t('all_types',ctx.lang),
        category=category_name(s.category,ctx.lang) if s.category else t('all_categories',ctx.lang)))


def financial_notes(ctx):
    st.caption(t('sales_note',ctx.lang))
    if ctx.scope.category:
        st.info(t('category_note',ctx.lang))
