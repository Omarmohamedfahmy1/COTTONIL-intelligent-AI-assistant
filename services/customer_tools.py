"""Bounded aggregate-only customer tools; no identifiers or individual scoring."""
import re
import pandas as pd
from services import customers,customer_models,metrics as kpi
from services.filters import filters
from services.sales_branch_tools import records

ALLOWED=('customer8_summary','customer8_segments','customer8_cohorts','customer8_repeat','customer8_changes','customer8_churn','customer8_value')


def answer_readonly(name,context):
    if name not in ALLOWED:raise ValueError('Unsupported customer tool')
    scope=filters(**context)
    meta=dict(tool=name,period=f'{scope.start} to {scope.end}',branch_id=scope.branch or 'all',location_type=scope.location_type,category=scope.category,
        source='Verified aggregate Phase 8 services',privacy_k=5,individual_predictions_published=False)
    if name in ('customer8_churn','customer8_value'):
        result=customer_models.research();meta.update(company_wide=True,state=result['state'],scope_policy='Company-wide evaluated research; global filters do not redefine training or origin.',origin=result.get('origin'),branch_id='all',location_type=None,category=None)
        if result['state']=='unavailable':frame=pd.DataFrame()
        else:
            meta['period']=result['schedule'].c8_feature_start.min()+' to '+result['schedule'].c8_value_end.max()
            if name=='customer8_churn':frame=result['classification'].loc[result['classification'].c8_stage.eq('test_pooled')];meta.update(selected=result['selected_churn'])
            else:frame=pd.DataFrame([result['value_forecast']]);meta.update(state=result['value_state'],selected=result['selected_value'])
        return dict(meta=meta,data=records(frame),plot=None)
    result=customers.dashboard(scope.start,scope.end,scope.branch,location_type=scope.location_type,category=scope.category)
    frame={'customer8_summary':pd.DataFrame([result['summary']]),'customer8_segments':result['rfm'],'customer8_cohorts':result['retention'],
        'customer8_repeat':result['activity'],'customer8_changes':result['segment_change']}[name]
    if name=='customer8_segments' and not frame.empty:frame=frame.sort_values('c8_revenue',ascending=False)
    meta.update(result['meta']);meta.update(company_wide=False)
    return dict(meta=meta,data=records(frame),plot=None)


def dispatch(question,context):
    q=question.casefold()
    if not any(w in q for w in ('customer','purchaser','purchasing frequency','purchase frequency','repeat purchase','churn','clv','rfm','retention','عميل','عملاء','العملاء','شريحة','شرائح','تكرار الشراء','بيرجعوا')):return None
    if any(w in q for w in ('customer id','customer name','phone','email','individual','رقم العميل','اسم العميل','هاتف','بريد','احتمال العميل')):return {'clarify':'c8_private_request'}
    scope=filters(**context)
    ids=re.findall(r'\bBR\d{3}\b',question,re.I)
    if ids:
        if len(set(v.upper() for v in ids))!=1:return {'clarify':'invalid_scope'}
        try:scope=filters(scope.start,scope.end,ids[0].upper(),scope.location_type,scope.category)
        except ValueError:return {'clarify':'invalid_scope'}
    if 'this month' in q or 'الشهر ده' in q:
        end=min(scope.end,kpi.metadata()[1].isoformat());scope=filters(end[:7]+'-01',end,scope.branch,scope.location_type,scope.category)
    if any(w in q for w in ('churn','roc','baseline','فقدان','دقيق')):name='customer8_churn'
    elif any(w in q for w in ('next-year','next year','next-365','estimated','clv','قيمة العميل','السنة الجاية','السنة القادمة')):name='customer8_value'
    elif any(w in q for w in ('cohort','retention','احتفاظ','دفعات','أفواج')):name='customer8_cohorts'
    elif any(w in q for w in ('changed','declin','قل','تغير')):name='customer8_changes'
    elif any(w in q for w in ('segment','rfm','شريحة','شرائح')):name='customer8_segments'
    elif any(w in q for w in ('frequency','trend','تكرار')):name='customer8_repeat'
    else:name='customer8_summary'
    return answer_readonly(name,vars(scope))
