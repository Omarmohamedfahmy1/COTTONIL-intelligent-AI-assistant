"""Fail-closed, question-scoped evidence projections. No SQL or model prose."""
from copy import deepcopy
import json,re
from services.assistant_request import output_issues,request_for,missing_metrics
from services.assistant_quality import assess
from services.assistant_registry import GROUPS,COMMON,CUSTOMER_COLUMNS
from services.assistant_findings import components
from ui.assistant_answers import requested_metrics,_number,comparison_delta

DIMENSIONS=('branch_id','location_id','product_id','category','period','month','calendar_month','forecast_model','stage','model','c8_model','c8_segment','c8_cohort','c8_month','c8_age','c8_stage')
FORECAST_VALUES=('central','lower','upper')

def prepare(result,question,expected=None):
    """Never trust a complete label or an old cached narrative over actual evidence."""
    safe=deepcopy(result);resolved=deepcopy(expected) if expected is not None else safe.get('resolved',{});valid=[];rejected=[]
    if safe.get('answer_state')=='clarification' and not set(safe.get('clarification_fields',[]))&{'dates','locations','categories','horizon','products','warehouses','forecast_category','metrics'}:
        safe['answer_state']='unsupported' if safe.get('code')=='no_compatible_tool' else 'unavailable'
    if resolved.get('scope') and not resolved.get('request'):
        resolved.setdefault('pair',[])
        resolved['request']=request_for(question,resolved)
    if resolved.get('request'):resolved['request'].setdefault('answer_components',components(question))
    for report in safe.get('reports',[]):
        if not isinstance(report,dict) or not isinstance(report.get('meta'),dict) or not isinstance(report.get('data'),list) or any(not isinstance(row,dict) for row in report['data']):
            rejected.append('invalid_evidence');continue
        meta=report.get('meta',{});issues=[]
        if not resolved.get('scope') or not resolved.get('request'):issues=['missing_request_snapshot']
        elif meta.get('tool') not in GROUPS:issues=['unknown_source']
        else:
            try:issues=output_issues(report,resolved)
            except (ValueError,TypeError,KeyError):issues=['invalid_evidence']
        if issues:rejected.extend(issues);continue
        # Even a forged cached payload cannot expose private/unapproved columns.
        report['data']=[{k:v for k,v in row.items() if k in COMMON|CUSTOMER_COLUMNS} for row in report.get('data',[])]
        valid.append(report)
    cells={};conflict=False
    for report in valid:
        meta=report['meta']
        if not meta.get('branch_a'):continue
        for row in report['data']:
            if 'metric' not in row:continue
            signature=(meta.get('period'),meta.get('branch_a'),meta.get('branch_b'),row['metric'])
            values=tuple(_number(row.get(k)) for k in ('location_a','location_b'))
            if signature in cells and any(a is not None and b is not None and a!=b for a,b in zip(cells[signature],values)):conflict=True
            cells[signature]=values
    if conflict:valid=[];rejected.append('conflicting_evidence')
    safe['reports']=valid;safe['resolved']=resolved;safe['rejected_evidence']=sorted(set(rejected))
    if valid and resolved.get('request'):
        quality=assess(valid,[r['meta']['tool'] for r in valid],resolved)
        if safe.get('answer_state')=='full':safe.update(quality)
        else:
            safe['missing_metrics']=quality['missing_metrics']
            safe['shape_issues']=quality['shape_issues']
            safe['coverage_reasons']=sorted(set(safe.get('coverage_reasons',[])+quality['coverage_reasons']))
            for key in ('requested_answer_components','supported_answer_components','missing_answer_components'):safe[key]=quality[key]
            if safe.get('answer_state')=='unavailable' and 'facts' in quality['supported_answer_components'] and 'outside_source' not in quality['coverage_reasons']:
                safe.update(answer_state='partial',semantic_complete=False)
    if rejected:
        safe.update(answer_state='partial' if valid else 'unavailable',semantic_complete=False,code='evidence_scope_mismatch')
        safe['facts']=[]
    return safe

def _measures(report,request,question):
    rows=report['data'];meta=report['meta']
    columns=list(dict.fromkeys(k for row in rows for k in row))
    wanted=request.get('metrics') or requested_metrics(question,[report])
    if 'central' in columns:return [k for k in FORECAST_VALUES if k in columns]
    selected=[k for k in wanted if k in columns]
    if 'recorded_risk' in wanted:selected+= [k for k in ('max_recorded_risk','mean_recorded_risk') if k in columns and k not in selected]
    if selected:return selected
    # API field names/localized labels are vocabulary, not canned question routes.
    from ui.i18n import TEXT
    q=question.casefold()
    numeric=[k for k in columns if k not in DIMENSIONS and any(_number(row.get(k)) is not None for row in rows)]
    mentioned=[k for k in numeric if any(label.casefold() in q for label in (k,k.replace('_',' '),*TEXT.get(k,())) if label)]
    if mentioned:return mentioned[:3]
    if meta.get('tool','').startswith('forecast7_'):return [k for k in ('wape_pct','mae','rmse') if k in numeric][:2]
    if meta.get('tool','').startswith('customer8_'):return numeric[:2]
    return []

def sections(result,question):
    """Deduplicate overlapping tools and retain only requested dimensions/measures."""
    resolved=result.get('resolved',{});request=resolved.get('request',{});views=[];pairs={}
    for report in result.get('reports',[]):
        rows=report.get('data',[]);meta=report['meta']
        if meta['tool']=='forecast7_values' and resolved.get('forecast_months'):rows=[row for row in rows if row.get('month') in resolved['forecast_months']]
        if meta['tool']=='forecast7_accuracy':rows=[row for row in rows if row.get('stage')=='test' and row.get('forecast_model') in (meta.get('model'),meta.get('baseline'))]
        if not rows:continue
        wanted=request.get('metrics') or requested_metrics(question,[report])
        if meta['tool']=='executive_comparison':
            keep={'sales' if metric=='growth_pct' else metric for metric in wanted}
            data=[{k:row.get(k) for k in ('metric','current','previous','absolute_change','percentage_change')} for row in rows if row.get('metric') in keep]
            if data:views.append(dict(data=data,measures=['current','previous','absolute_change','percentage_change'],period=meta['period'],snapshot=None,sources=[meta],chart=None,differences={}))
            continue
        if all({'metric','location_a','location_b'}<=set(row) for row in rows):
            key=(meta['period'],meta.get('branch_a'),meta.get('branch_b'))
            view=pairs.setdefault(key,dict(data=[{'branch_id':key[1]},{'branch_id':key[2]}],measures=[],period=key[0],snapshot=None,sources=[],chart=None,differences={}))
            for row in rows:
                metric=row['metric']
                if metric not in wanted or metric in view['measures']:continue
                view['measures'].append(metric)
                view['data'][0][metric]=row['location_a'];view['data'][1][metric]=row['location_b']
                view['differences'][metric]=comparison_delta(row['location_a'],row['location_b'])
            if meta not in view['sources']:view['sources'].append(meta)
            continue
        if meta.get('branch_a') and meta.get('branch_b'):
            measures=[k for metric in wanted for k in (metric+'_a',metric+'_b') if any(k in row for row in rows)]
            columns=['category',*measures]
            labels={k:(metric,meta['branch_a'] if k.endswith('_a') else meta['branch_b']) for metric in wanted for k in (metric+'_a',metric+'_b') if k in measures}
        else:
            measures=_measures(report,request,question)
            dimensions=[k for k in DIMENSIONS if any(k in row for row in rows)]
            columns=[*dimensions[:2],*measures];labels={}
        if not measures:continue
        data=[{k:row.get(k) for k in columns if k in row} for row in rows]
        if meta.get('product_ids'):data.sort(key=lambda row:meta['product_ids'].index(row['product_id']))
        dimension=next((k for k in columns if k not in measures),None)
        chart=None
        if dimension and len(data)>2 and not meta.get('branch_a'):
            temporal=dimension in ('month','period','c8_month')
            ranking=request.get('aggregation') in ('locations','product','category')
            if temporal or ranking:chart=dict(x=dimension,y=measures[0],kind='line' if temporal else 'bar')
        views.append(dict(data=data,measures=measures,period=meta.get('period'),snapshot=meta.get('snapshot'),sources=[meta],chart=chart,labels=labels,differences={}))
    views=list(pairs.values())+views
    dedup={}
    for view in views:
        if not view['measures']:continue
        signature=json.dumps(dict(data=view['data'],period=view['period'],snapshot=view['snapshot']),sort_keys=True,default=str)
        if signature in dedup:dedup[signature]['sources'].extend(m for m in view['sources'] if m not in dedup[signature]['sources'])
        else:dedup[signature]=view
    return list(dedup.values())

def isolate(text,lang):
    if lang=='English':return text
    return re.sub(r'(?<![A-Za-z0-9\u2066])[A-Za-z0-9][A-Za-z0-9_.,:/%+\-]*',lambda m:'\u2066'+m.group()+'\u2069',text)

def period_label(period,lang):
    parts=re.fullmatch(r'(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})',str(period))
    if parts and lang!='English':return 'من '+isolate(parts[1],lang)+' إلى '+isolate(parts[2],lang)
    return isolate(str(period),lang)

def render_details(views,lang,key):
    import pandas as pd
    import streamlit as st
    from ui.i18n import t,TEXT,ltr,category_name,data_value
    from ui.assistant_answers import _value
    from ui.data import catalog,stamp
    master=catalog(stamp())[0];names=dict(zip(master.branch_id,master.branch_name_ar))
    periods=[]
    for index,view in enumerate(views):
        meta=view['sources'][0]
        period=(str(meta['forecast_start'])+' → '+str(meta['forecast_end'])) if meta.get('forecast_start') and meta.get('forecast_end') else view['period']
        if meta.get('tool')=='forecast7_accuracy' and meta.get('test_start') and meta.get('test_end'):period=meta['test_start']+' → '+meta['test_end']
        if meta.get('tool')=='forecast7_values' and view['data']:period=view['data'][0]['month']+' → '+view['data'][-1]['month']
        if period not in periods:st.caption(period_label(period,lang));periods.append(period)
        if view.get('snapshot'):st.caption(('Recorded snapshot: ' if lang=='English' else 'لقطة المخزون المسجّلة: ')+ltr(view['snapshot'],lang))
        frame=pd.DataFrame(view['data']);labels=view.get('labels',{})
        columns={}
        for column in frame:
            metric,branch=labels.get(column,(column,None))
            label=t(metric,lang) if metric in TEXT else metric.replace('_',' ')
            if branch:label+=' · '+ltr(branch,lang)
            columns[column]=label
        display=frame.copy()
        if 'branch_id' in display:display['branch_id']=display.branch_id.map(lambda value:ltr(value,lang)+' · '+names[value] if value in names else ltr(value,lang))
        for col in display:
            if display[col].dtype=='object' and col!='branch_id':display[col]=display[col].map(lambda v:data_value(v,lang))
            if col in view['measures']:
                precision=3 if 'risk' in col else 2
                display[col]=display[col].map(lambda v:f'{v:,.{precision}f}' if _number(v) is not None else '—')
        display=display.rename(columns=columns)
        if lang!='English':display=display.iloc[:,::-1]
        expanded=False
        if len(frame)>8:expanded=st.checkbox('Show all relevant rows' if lang=='English' else 'عرض كل الصفوف ذات الصلة',key=f'{key}_{index}_rows')
        shown=display if expanded else display.head(8)
        st.dataframe(shown,hide_index=True,width='stretch',height=min(40+35*len(shown),320))
        if len(shown)<len(frame):st.caption((f'Showing {len(shown)} of {len(frame)} returned rows.' if lang=='English' else f'المعروض {len(shown)} من {len(frame)} صفًا مسترجعًا.'))
        for metric,difference in view['differences'].items():
            if difference is not None:st.caption(('Difference · ' if lang=='English' else 'الفرق · ')+(t(metric,lang) if metric in TEXT else metric)+': '+_value(difference,metric,lang,True))
        graph=view.get('chart')
        if graph and st.checkbox('Show chart' if lang=='English' else 'عرض الرسم البياني',key=f'{key}_{index}_chart'):
            data=frame.rename(columns=columns)
            (st.line_chart if graph['kind']=='line' else st.bar_chart)(data,x=columns[graph['x']],y=columns[graph['y']],height=220,color='#0c9697')

def render_sources(views,lang,key):
    import streamlit as st
    from services.business_assistant import safe_csv
    seen=set()
    for i,view in enumerate(views):
        for meta in view['sources']:
            curated={k:meta[k] for k in ('tool','source','period','branch_a','branch_b','branch_id','category','location_type','snapshot','origin','target','unit','scope_policy','state','reason','model','baseline','test_start','test_end','test_observations','uncertainty','test_band_coverage_pct','total_rows','returned_rows','selection_kind') if k in meta}
            relevant=set(view['measures'])|{value[0] for value in view.get('labels',{}).values()}
            units={k:v for k,v in meta.get('units',{}).items() if k in relevant}
            definitions={k:v for k,v in meta.get('definitions',{}).items() if k in relevant}
            if units:curated['units']=units
            if definitions:curated['definitions']=definitions
            signature=json.dumps(curated,sort_keys=True,default=str)
            if signature in seen:continue
            seen.add(signature)
            st.json(curated,expanded=False)
        if view['data']:st.download_button('Download relevant evidence' if lang=='English' else 'تنزيل الأدلة ذات الصلة',safe_csv(dict(data=view['data'])),file_name='cottonil_verified_evidence.csv',mime='text/csv',key=f'{key}_{i}_export')
