"""Narrow Phase 4 local assistant allowlist. No SQL or free-form execution."""
from dataclasses import replace
from datetime import date,timedelta
import json,re
import pandas as pd
from services import sales_branch as sb
from services import metrics as kpi
from services.filters import filters,complete_month_bounds

ALLOWED=('sales4_trends','sales4_products','location_ranking','declining_locations','two_location_comparison','location_detail')


def records(frame):
    return json.loads(frame.to_json(orient='records',force_ascii=False,double_precision=15))


def answer_readonly(name,context,params=None):
    if name not in ALLOWED:raise ValueError('Unsupported Phase 4 read-only tool')
    params=params or {}
    scope=filters(**context)
    limit=params.get('limit',8)
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=20:raise ValueError('Limit must be 1..20')
    meta={'tool':name,'period':f'{scope.start} to {scope.end}','branch_id':scope.branch or 'all',
          'category':scope.category,'location_type':scope.location_type,'source':'Verified Phase 4 services over original historical task dataset'}
    if name=='sales4_trends':
        grain=params.get('grain','monthly')
        frame=sb.sales_trends(**sb.args(scope),grain=grain)
        meta.update(grain=grain,rows_returned=len(frame),scope_policy='Global filters; incomplete periods explicitly flagged')
        return dict(meta=meta,data=records(frame),plot={'x':'period','y':'sales','type':'line'})
    if name=='location_detail':
        if not scope.branch:raise ValueError('A location ID is required')
        frame=pd.DataFrame([sb.period_summary(scope)['current']])
        return dict(meta=meta,data=records(frame),plot=None)
    if name=='sales4_products':
        metric=params.get('metric','units')
        if metric not in ('units','sales','gross_profit','gross_margin_pct'):raise ValueError('Unsupported product rank')
        frame=sb.product_roster(scope)
        if params.get('product_ids'):frame=frame.loc[frame.product_id.isin(params['product_ids'])]
        meta['total_rows']=len(frame)
        frame=frame.sort_values([metric,'product_id'],ascending=[params.get('ascending',False),True]).head(limit)
        meta.update(metric=metric,ascending=params.get('ascending',False))
        if params.get('product_ids'):meta['product_ids']=params['product_ids']
        meta.update(metric=metric,limit=limit)
    elif name in ('location_ranking','declining_locations'):
        metric=params.get('metric','sales')
        frame=sb.location_roster(scope.start,scope.end,location_type=scope.location_type,category=scope.category)
        if name=='declining_locations':
            metric='growth_pct'
            frame=frame[frame.growth_pct.lt(0)].sort_values(['growth_pct','branch_id'])
        else:frame=sb.rank_locations(frame,metric,params.get('ascending',False))
        meta['total_rows']=len(frame);frame=frame.head(limit)
        frame=frame[['branch_id','branch','retail_location_type','sales','gross_profit','orders','units','customers','aov','growth_pct','recorded_orders']]
        meta.update(metric=metric,limit=limit,branch_id='all',scope_policy='All eligible locations; selected global location ignored; date/type/category retained')
    else:
        result=sb.compare_two(scope.start,scope.end,params.get('branch_a'),params.get('branch_b'),category=scope.category)
        frame=result['table'];meta.update(branch_a=params['branch_a'],branch_b=params['branch_b'],location_type=None,branch_id='pair',
            location_types=records(result['locations'][['branch_id','retail_location_type']]),scope_policy='Explicit local pair overrides global location/type, retains date/category')
    return dict(meta=meta,data=records(frame),plot=None)


def quarter_bounds(question):
    """Explicit calendar quarter grammar shared by initial and follow-up requests."""
    q=question.casefold().translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'));dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',q)
    quarters=re.findall(r'\bq([1-4])\s*[,/-]?\s*(\d{4})\b|الربع\s+(الأول|الاول|الثاني|الثالث|الرابع|[1-4])\s+(?:من\s+|لعام\s+|عام\s+)?(\d{4})(?!\d)',q)
    if quarters:
        if len(quarters)!=1 or dates:raise ValueError('Specify one unambiguous calendar quarter')
        number,year,ordinal,arabic_year=quarters[0]
        quarter=int(number) if number else int(ordinal) if ordinal.isdigit() else {'الأول':1,'الاول':1,'الثاني':2,'الثالث':3,'الرابع':4}[ordinal]
        year=int(year or arabic_year);month=(quarter-1)*3+1
        start=date(year,month,1);end=date(year+1,1,1)-timedelta(days=1) if quarter==4 else date(year,month+3,1)-timedelta(days=1)
        return str(start),str(end)
    return None

def resolve_period(question,scope):
    """Closed grammar anchored to dataset dates, never the host's current date."""
    q=question.casefold().translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'));dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',q)
    quarter=quarter_bounds(question)
    if quarter:return replace(scope,start=quarter[0],end=quarter[1])
    if dates:
        if len(dates)!=2:raise ValueError('Specify two ISO dates')
        return filters(dates[0],dates[1],scope.branch,scope.location_type,scope.category)
    first,last=kpi.metadata()
    if any(w in q for w in ('last month','الشهر الماضي','الشهر اللي فات')):
        end=last.replace(day=1)-timedelta(days=1)
        return replace(scope,start=str(end.replace(day=1)),end=str(end))
    words={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'ثلاثة':3,'ثلاث':3,'ستة':6,'ست':6,'اثنين':2,'شهرين':2}
    duration=re.search(r'(?:last|آخر|اخر)\s+(\d+|'+ '|'.join(words)+r')\s+(?:(?:completed?|full|calendar)\s+)*(?:months?|شهور|أشهر|اشهر)',q)
    if duration:
        token=duration[1];count=int(token) if token.isdigit() else words[token]
        if not 1<=count<=120:raise ValueError('Unsupported historical month count')
        bounds=complete_month_bounds(first,last)
        end=date.fromisoformat(bounds[1]);index=end.year*12+end.month-count
        start=date(index//12,index%12+1,1)
        return replace(scope,start=str(start),end=str(end))
    if re.search(r'\b\d{4}\b',q) or any(w in q for w in ('last ','next ','this month','yesterday','today','الماضي','أمس','امبارح','السنة','last year','august','september','أغسطس','سبتمبر')):
        raise ValueError('Unsupported temporal phrase')
    return scope


def dispatch(question,context):
    """Return None for legacy intents, or a structured report/clarification code."""
    q=question.casefold()
    if any(w in q for w in ('inventory','stock','مخزون','forecast','predict','توقع','customer','عملاء','عميل')):return None
    pair=any(w in q for w in ('compare','قارن','مقارنة بين'))
    branch=any(w in q for w in ('branch','location','فرع','فروع','مواقع'))
    product=any(w in q for w in ('product','منتج','منتجات','الأكثر مبيع','sold the most'))
    trend=any(w in q for w in ('monthly','daily','weekly','yearly','sales trend','trends','اتجاه','شهري','الشهرية','يومي','أسبوعي','اسبوعي','سنوي'))
    if not (pair or branch or product or trend):return None
    try:scope=resolve_period(question,filters(**context))
    except (ValueError,TypeError):return {'clarify':'time_scope_request'}
    master=kpi.branches()
    ids=[v.upper() for v in re.findall(r'\bBR\d{3}\b',question,re.I)]
    if any(v not in set(master.branch_id) for v in ids):return {'clarify':'two_ids_required'}
    for row in master.itertuples():
        name=str(row.branch_name_ar)
        if len(name)>1 and re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',question):
            if master.branch_name_ar.eq(name).sum()>1:return {'clarify':'two_ids_required'}
            ids.append(row.branch_id)
    ids=list(dict.fromkeys(ids))
    if pair:
        if len(ids)!=2:return {'clarify':'two_ids_required'}
        return answer_readonly('two_location_comparison',sb.args(scope),dict(branch_a=ids[0],branch_b=ids[1]))
    if len(ids)>1:return {'clarify':'two_ids_required'}
    if ids:
        # A named single location must remain compatible with global type.
        try:scope=filters(scope.start,scope.end,ids[0],scope.location_type,scope.category)
        except ValueError:return {'clarify':'invalid_scope'}
    if trend and not product:
        grain='daily' if any(v in q for v in ('daily','يومي')) else 'weekly' if any(v in q for v in ('weekly','أسبوعي','اسبوعي')) else 'yearly' if any(v in q for v in ('yearly','سنوي')) else 'monthly'
        return answer_readonly('sales4_trends',sb.args(scope),{'grain':grain})
    if product:
        metric='gross_margin_pct' if any(w in q for w in ('margin','هامش')) else 'gross_profit' if any(w in q for w in ('profit','ربح')) else 'sales' if any(w in q for w in ('revenue','إيراد','ايراد','sales')) else 'units'
        return answer_readonly('sales4_products',sb.args(scope),dict(metric=metric))
    if ids and not any(w in q for w in ('highest','lowest','rank','أفضل','أعلى','أقل','اقل','growth','نمو','declin','انخفاض')):
        return answer_readonly('location_detail',sb.args(scope))
    if branch:
        if any(w in q for w in ('declin','انخفاض','تراجع','سالب','انخفض')):
            return answer_readonly('declining_locations',sb.args(scope))
        metric='growth_pct' if any(w in q for w in ('growth','نمو')) else 'gross_profit' if any(w in q for w in ('profit','ربح')) else 'aov' if any(w in q for w in ('aov','متوسط الطلب','average order')) else 'sales'
        ascending=any(w in q for w in ('lowest','worst','أقل','اقل','اضعف','أضعف'))
        return answer_readonly('location_ranking',sb.args(scope),dict(metric=metric,ascending=ascending))
    return answer_readonly('sales4_trends',sb.args(scope))
