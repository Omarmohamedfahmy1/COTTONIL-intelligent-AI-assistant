"""Groq-only chat presentation; no financial formulas or raw model rendering."""
from dataclasses import replace
from copy import deepcopy
import pandas as pd
import streamlit as st
from services.assistant_config import load_settings
from services.business_assistant import run,fresh_state,safe_csv
from services.assistant_context import resolve,guard
from ui.components import scope_caption,table,chart,money
from ui.i18n import t,ltr
from ui.state import choice
from ui.assistant_answers import assemble,label,answer_language,detailed_results,critical_warnings
from ui.assistant_evidence import prepare,sections,render_details,render_sources,isolate

def settings():
    secret_values={}
    try:
        for name in ('GROQ_API_KEY','GROQ_MODEL'):
            if name in st.secrets:secret_values[name]=st.secrets[name]
    except (FileNotFoundError,KeyError):pass
    return load_settings(secret_values)

def message(result,lang,question=''):
    if 'answer_state' in result:return assemble(result,lang,question)
    status=result['status'];code=result.get('code')
    if status=='blocked':return t('a9_unavailable' if code=='unavailable' else 'a9_blocked',lang)
    if status=='clarify':return t('a9_clarify',lang)
    if status=='unsupported':return t('unsupported',lang)
    if status=='error':return t('a9_error',lang,code=code)+(('\n\n'+' · '.join(result['alternatives'])) if result.get('alternatives') else '')
    if status=='limited':return t('a9_limit',lang)
    text=t('a9_verified',lang)
    overview=next((r for r in result['reports'] if r['meta']['tool']=='company_overview' and r['data']),None)
    if overview:
        row=overview['data'][0]
        text=t('answer_sales',lang,sales=money(row['sales'],lang,False),profit=money(row['gross_profit'],lang,False),orders=f"{row['orders']:,}")+'\n\n'+text
    if result.get('resolved',{}).get('overrides'):text+='\n\n'+t('a9_scope',lang)
    return text

def report_view(report,ctx,key):
    lang=ctx.lang;meta=report['meta'];frame=pd.DataFrame(report['data'])
    st.caption(ltr(meta['tool'],lang)+' · '+ltr(meta['period'],lang)+' · '+str(meta.get('branch_id','all')))
    if meta.get('snapshot'):st.caption(('Recorded completed snapshot: ' if lang=='English' else 'اللقطة الشهرية المكتملة المسجّلة: ')+ltr(meta['snapshot'],lang))
    if meta.get('branch_a') and meta.get('branch_b'):
        st.caption(ltr(meta['branch_a'],lang)+' (A) ↔ '+ltr(meta['branch_b'],lang)+' (B)')
    st.caption(t('a9_basis',lang))
    if meta['tool'].startswith('inventory6_') or meta['tool'] in ('executive_stock','category_risk_sales'):st.caption(t('a9_inventory',lang))
    if meta['tool'].startswith(('forecast7_','customer8_')):st.caption(t('a9_models',lang))
    if meta['tool'].startswith('customer8_'):st.info(t('a9_privacy',lang))
    if meta.get('truncated'):st.warning(t('a9_truncated',lang,shown=meta['returned_rows'],total=meta['total_rows']))
    if meta['tool']=='company_overview' and not frame.empty:
        for col,name in zip(st.columns(2),('sales','gross_profit')):
            if name in frame:col.metric(t(name,lang),money(frame.iloc[0][name],lang,False))
    table(frame,lang,key,False)
    graph=report.get('plot')
    if graph:chart(frame,graph['x'],graph['y'],lang,'table',graph['type'],key=key+'_chart')
    if not frame.empty:
        st.download_button(t('export',lang),safe_csv(report),file_name='cottonil_aggregate_evidence.csv',mime='text/csv',key=key+'_export')
    with st.expander(t('a9_evidence',lang)):st.json(meta)

def render(ctx,prefix='full'):
    import ui.assistant as bridge
    lang=ctx.lang;config=settings()
    state=st.session_state.setdefault('a9_state',fresh_state())
    st.session_state.setdefault('a9_generation',0)
    mode=choice('radio',t('mode',lang),['offline','connected'],lang,prefix+'_mode',lambda v:t(v,lang),horizontal=True)
    entered='';enabled=False
    if mode=='connected':
        st.info(t('a9_status',lang,model=config.model))
        st.caption(t('a9_config' if config.api_key else 'a9_missing',lang))
        enabled=st.checkbox(t('a9_enable',lang),key=prefix+'_groq_enable')
        with st.expander(t('ai_settings',lang)):
            # Legacy widget key retained for the original tests; value is Groq-only.
            entered=st.text_input(t('a9_override',lang),type='password',key=prefix+'_api_key')
            st.caption(t('a9_model_fixed',lang));st.code(config.model,language=None)
    else:st.info(t('a9_offline',lang))
    controls=st.columns(2)
    if controls[0].button(t('clear_chat',lang),key=prefix+'_clear'):
        st.session_state.dialog=[]
        counters={k:state.get(k,0) for k in ('calls','tokens','input_tokens','output_tokens')}
        from services.business_assistant import reset_conversation
        reset_conversation(state);st.session_state.a9_state=state;st.session_state.a9_generation+=1
    if controls[1].button(t('a9_stop',lang),key=prefix+'_stop',help=t('a9_stop_note',lang)):st.session_state.a9_generation+=1
    st.caption(t('suggestions',lang));question=None
    for col,suggestion in zip(st.columns(3)*2,['q_sales','q_branch','q_products','q_inventory','q_forecast','q_customers']):
        if col.button(t(suggestion,lang),key=f'{prefix}_{suggestion}',width='stretch'):question=t(suggestion,lang)
    typed=st.chat_input(t('question',lang),key=prefix+'_question')
    if typed:question=typed
    retry=False
    if mode=='connected' and state.get('pending'):
        if st.button('Retry failed turn (reuse evidence)' if lang=='English' else 'إعادة الطلب المتعثر (مع حفظ الأدلة)',key=prefix+'_retry'):
            question=state['pending']['question'];retry=True
    if question:
        result=None;reply_lang=answer_language(question,lang)
        expected=None
        if not guard(question):
            try:expected=deepcopy(state['pending'].get('resolved',{})) if retry and state.get('pending') else resolve(question,ctx.assistant_scope(),deepcopy(state))
            except (ValueError,TypeError):pass
        with st.spinner(t('checking',lang)):
            try:
                if mode=='connected' and not (enabled or entered):text,reports=t('no_key',reply_lang),[]
                else:
                    if mode=='connected':
                        result=bridge.run_llm(question,ctx.assistant_scope(),entered or None,state=state,retry=retry)
                    else:result=run(question,ctx.assistant_scope(),state,settings=config)
                    result=prepare(result,question,expected)
                    text,reports=message(result,reply_lang,question),result['reports']
            except Exception:text,reports=t('provider_error' if mode=='connected' else 'data_error',reply_lang),[]
        # Rejected prompts are not retained or redisplayed; no raw prompt telemetry.
        display_question=t('a9_blocked',lang) if result and result['status']=='blocked' else question
        answer=dict(role='assistant',content=text,reports=reports,phase9=True,status=result['status'] if result else 'error',
            answer_state=result.get('answer_state') if result else 'provider_error',provider=result.get('provider') if result else None,
            answer_lang=reply_lang,details='',question=display_question,result=deepcopy(result) if result else None,request_snapshot=deepcopy(expected),
            warnings=critical_warnings(result,reply_lang) if result else [])
        if retry and st.session_state.dialog and st.session_state.dialog[-1]['role']=='assistant':st.session_state.dialog[-1]=answer
        else:st.session_state.dialog.extend([dict(role='user',content=display_question),answer])
        st.session_state.dialog=st.session_state.dialog[-16:]
    for i,item in enumerate(st.session_state.dialog):
        with st.chat_message(item['role']):
            item_lang=item.get('answer_lang',lang)
            if item['role']!='assistant':st.markdown(item['content']);continue
            current=prepare(item['result'],item.get('question',''),item['request_snapshot']) if item.get('result') and 'request_snapshot' in item else None
            legacy_evidence=not current and bool(item.get('reports'))
            content=message(current,item_lang,item.get('question','')) if current else item['content']
            if legacy_evidence:content='Ask again to verify the scope of this earlier evidence.' if item_lang=='English' else 'أعد السؤال للتحقق من نطاق هذه الأدلة السابقة.'
            with st.container(key=f'assistant_{"en" if item_lang=="English" else "ar"}_{prefix}_{i}'):
                st.markdown(isolate(content,item_lang))
                outcome=current.get('answer_state') if current else 'unavailable' if legacy_evidence else item.get('answer_state','partial')
                if outcome!='full':st.warning(label(outcome,item_lang))
                warnings=critical_warnings(current,item_lang) if current else item.get('warnings',[])
                for warning in dict.fromkeys(warnings):st.warning(warning)
                views=sections(current,item.get('question','')) if current else []
                if views:
                    with st.expander(t('table',item_lang),expanded=False):render_details(views,item_lang,f'{prefix}_{i}_details')
                    with st.expander('Methodology & Sources' if item_lang=='English' else 'المنهجية والمصادر',expanded=False):render_sources(views,item_lang,f'{prefix}_{i}_sources')
