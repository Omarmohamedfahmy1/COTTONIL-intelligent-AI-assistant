"""Bounded session scope resolution; historical dates, no host-clock semantics."""
from calendar import monthrange
from datetime import date,timedelta
import re
from services import metrics as kpi
from services.filters import filters,complete_month_bounds
from services.sales_branch_tools import resolve_period,quarter_bounds
from services.assistant_request import request_for,reference,metrics_in,metric_domains,STOCK
from services.assistant_forecast import forecast_intent,company_wide,requested_months,wants_accuracy
from services.assistant_semantics import signals,mentions,entity_ids
from services.assistant_limits import preflight
from services.assistant_language import private_intent,metric_reference_size,requested_grain,explicit_global_reset
from services.assistant_calendar import named_period

class Clarification(ValueError):
    def __init__(self,field,context=None):self.context=context;super().__init__(field)
class UnsupportedScope(ValueError):pass

def guard(question):
    if not isinstance(question,str):return 'unsafe'
    q=question.casefold()
    blocked=('customer id','customer names','customer name','phone','email','raw feature',
      'marketing list','اسم العميل','أسماء العملاء','اسماء العملاء','رقم العميل','أرقام العملاء','ايميل','بريد','هاتف','بيانات العملاء','احتمال العميل',
      'sql','select *','drop table','delete from','api_key','api key','secret','password','كلمة السر','مفتاح','ignore previous','ignore instructions',
      'تجاهل التعليمات','system prompt','execute','shell','python code','http://','https://','file://')
    if private_intent(question) or any(w in q for w in blocked) or re.search(r'\b(?:gsk_|sk-)[A-Za-z0-9_-]{15,}',question):return 'unsafe'
    if preflight(question)[0]:return 'unavailable'
    return None

def shift_months(day,delta):
    index=day.year*12+day.month-1+delta
    return date(index//12,index%12+1,1)

def resolve(question,global_scope,state):
    if not isinstance(question,str) or not 1<=len(question)<=3000:raise Clarification('question_length')
    pending=state.get('clarification_context')
    if pending:state={**state,**pending}
    q=question.casefold().translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'));scope=dict(global_scope);previous=state.get('global_scope')
    tags=set(signals(question))
    customer=any(w in q for w in ('customer','rfm','churn','clv','عملاء','عميل'))
    forecast=(forecast_intent(question,state.get('request')) or bool(pending and state.get('request',{}).get('forecast') and not metrics_in(question))) and not customer;company=company_wide(question)
    # Patch dimensions, not the entire conversational scope, when dashboard filters change.
    if previous is not None:
        scope.update(state.get('scope',{}))
        scope.update({k:v for k,v in global_scope.items() if previous.get(k)!=v})
    entity_reset=previous is not None and previous.get('branch')!=global_scope.get('branch')
    pair=list(state.get('pair',[])) if previous is not None and not entity_reset else []
    explicit_dimensions=[];initial_scope=dict(scope)
    product_ids=[];state_categories=[];warehouse=state.get('warehouse');horizon=state.get('horizon',3)
    def clarification(field):
        first,last=kpi.metadata()
        context=dict(scope=dict(scope),pair=list(pair),product_ids=list(product_ids),categories=list(state_categories),warehouse=warehouse,horizon=horizon,
            global_scope=dict(global_scope),explicit_dimensions=list(explicit_dimensions),forecast=forecast,company_wide=company,
            forecast_accuracy=forecast and (wants_accuracy(question) or bool(pending and state.get('forecast_accuracy'))),source_start=str(first),source_end=str(last))
        context['request']=request_for(question,context,state.get('request'))
        context['_clarification_field']=field
        return Clarification(field,context)
    master=kpi.branches();known=set(master.branch_id)
    explicit_ids,invalid=entity_ids(question,known)
    if len(explicit_ids)>2 or invalid:raise clarification('locations')
    # Exact names only. A city is not silently expanded into its locations.
    for row in master.itertuples():
        name=str(row.branch_name_ar)
        if len(name)>2 and name in question:
            if master.branch_name_ar.eq(name).sum()!=1:raise clarification('locations')
            explicit_ids.append(row.branch_id)
    explicit_ids=list(dict.fromkeys(explicit_ids))
    # Explicit catalog locations take precedence over a brand mention (e.g.
    # "our company's branches X/Y"); branding is not a branch replacement.
    if explicit_ids and not explicit_global_reset(question):company=False
    catalog_ids=kpi.read('SELECT product_id FROM products_catalog ORDER BY product_id').product_id.astype(str).tolist()
    product_ids,invalid=entity_ids(question,catalog_ids)
    if invalid or len(product_ids)>20:raise clarification('products')
    if product_ids:tags.add('product');explicit_dimensions.append('products')
    if not product_ids and previous is not None and not company and not explicit_ids and not forecast and not tags&{'warehouse','transfers','location'}:
        if reference(question) or (state.get('request',{}).get('aggregation')=='product' and set(metrics_in(question))&{'sales','gross_profit','gross_margin_pct','units','orders','aov'}):
            product_ids=list(state.get('product_ids',[]))
    if len(explicit_ids)>2:raise clarification('locations')
    if any(w in q for w in ('alexandria','القاهرة','cairo','اسكندرية','الإسكندرية','الاسكندرية')) and not explicit_ids:
        raise clarification('locations')
    if explicit_ids:
        pair=explicit_ids if len(explicit_ids)==2 else []
        scope['branch']=None if pair else explicit_ids[0];explicit_dimensions.append('entities')
    elif not company and reference(question) and any(w in q for w in ('them','same branches','نفس الفرعين','قارنهم','فيهم','بينهم')) and not pair and (
        any(w in q for w in ('same branches','نفس الفرعين')) or
        state.get('request',{}).get('aggregation') not in ('product','category','segment','cohort','segment_change','time','locations','warehouse')):
        raise clarification('locations')
    if company or any(w in q for w in ('company-wide','all locations','الشركة كلها','كل الفروع')):
        pair=[];scope['branch']=None;scope['location_type']=None;explicit_dimensions.append('entities')
    if company:scope['category']=None;explicit_dimensions.append('category')
    if tags&{'product','warehouse','transfers'} and pair and not explicit_ids and not reference(question):
        pair=[];scope['branch']=None;explicit_dimensions.append('entities')
    if requested_grain(question)=='locations' and not explicit_ids and not reference(question):
        pair=[];scope['branch']=None;explicit_dimensions.append('entities')
    retail=any(w in q for w in ('retail only','retail branches','فروع التجزئة','التجزئة فقط'))
    reseller=any(w in q for w in ('reseller','pos locations','point of sale','نقاط البيع','الموزعين')) or bool(re.search(r'\bpos\b',q))
    if retail or reseller:
        scope['location_type']=None if retail and reseller else 'Retail branch' if retail else 'Point of sale / reseller'
        if pair and scope['location_type'] and any(master.set_index('branch_id').loc[v,'retail_location_type']!=scope['location_type'] for v in pair):raise Clarification('locations')
    from services.inventory import warehouses as warehouse_master
    warehouses,invalid=entity_ids(question,warehouse_master().warehouse_id)
    if invalid:raise clarification('warehouses')
    warehouse=state.get('warehouse') if previous is not None and not company else None
    if warehouses:
        if any(v not in set(warehouse_master().warehouse_id) for v in warehouses):raise clarification('warehouses')
        if len(warehouses)!=1:raise UnsupportedScope('warehouse_pair')
        warehouse=warehouses[0];explicit_dimensions.append('warehouse')
        if not explicit_ids and not reference(question):pair=[];scope['branch']=None;explicit_dimensions.append('entities')
    if any(w in q for w in ('all warehouses','كل المخازن','كل المستودعات')):
        warehouse=None;explicit_dimensions.append('warehouse')
    from ui.i18n import CATEGORIES
    categories=kpi.read('SELECT DISTINCT category_en FROM products_catalog ORDER BY 1').category_en.tolist()
    found=[c for c in categories if mentions(question,c) or mentions(question,CATEGORIES.get(c,''))]
    if len(found)>1:
        state_categories=found
        if not any(w in q for w in ('forecast','توقع')):raise clarification('categories')
    else:state_categories=state.get('categories',[]) if previous is not None and not company else []
    if previous is not None and previous.get('category')!=global_scope.get('category'):
        state_categories=[scope['category']] if scope.get('category') else []
    if len(found)==1:scope['category']=found[0];state_categories=found;explicit_dimensions.append('category')
    if len(found)>1:scope['category']=None;explicit_dimensions.append('category')
    if any(w in q for w in ('all categories','كل الفئات')):scope['category']=None;state_categories=[];explicit_dimensions.append('category')
    first,last=kpi.metadata();bounds=complete_month_bounds(first,last);complete_end=date.fromisoformat(bounds[1])
    horizon=state.get('horizon',3) if previous is not None else 3
    if forecast:
        desired=set(metrics_in(question))
        if not desired and not company and (pending or state.get('request',{}).get('forecast')):desired=set(state.get('request',{}).get('metrics',[]))
        if desired-{'sales','units','growth_pct'}:raise UnsupportedScope('forecast_metric')
        if 'growth_pct' in desired and not tags&{'category','growth'}:raise UnsupportedScope('forecast_metric')
        if 'units' in desired and not scope.get('category'):raise clarification('forecast_category')
        if pending and state.get('_clarification_field')=='horizon' and q.strip().isdigit():horizon=int(q.strip());explicit_dimensions.append('horizon')
        requested=re.findall(r'(?<![\d٠-٩])([\d٠-٩]+)\s*(?:months?|شهور|أشهر|شهر)',q)
        if requested:
            if len(requested)!=1:raise clarification('horizon')
            horizon=int(requested[0].translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789')))
            if horizon not in (1,3,6):raise clarification('horizon')
        elif any(w in q for w in ('next month','الشهر الجاي','الشهر القادم')):horizon=1
        elif any(w in q for w in ('next quarter','الربع القادم','الربع الجاي')):horizon=3
        if horizon not in (1,3,6):raise clarification('horizon')
    months=re.findall(r'(?<!\d)(\d{4}-\d{2})(?!-\d|\d)',q)
    iso_dates=re.findall(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)',q)
    forecast_months=[]
    if forecast:horizon,forecast_months=requested_months(question,complete_end,horizon)
    quarter=quarter_bounds(question) if not forecast else None
    named=None if forecast or iso_dates else named_period(question,date.fromisoformat(scope['end']).year)
    years=re.findall(r'(?<![\d-])([12]\d{3})(?![\d-])',q)
    # A named month/season is not a year-only request. Leave unsupported phrases
    # to the existing explicit temporal validation rather than broadening them.
    month_words=('january','february','march','april','may','june','july','august','september','october','november','december',
        'يناير','فبراير','مارس','أبريل','ابريل','مايو','يونيو','يوليو','أغسطس','اغسطس','سبتمبر','أكتوبر','اكتوبر','نوفمبر','ديسمبر',
        'quarter','الربع','month','شهر','summer','winter','الصيف','الشتاء')
    year_only=len(years)==1 and not months and not iso_dates and not re.search(r'\bq\d+\b',q) and not any(mentions(q,w) for w in month_words)
    year_to_date=any(mentions(q,w) for w in ('year to date','year-to-date','ytd','من بداية السنة','منذ بداية العام','حتى تاريخه','حتى الآن'))
    if forecast:
        # Requested future months are a target contract, never transaction filters.
        pass
    elif quarter:
        scope.update(start=quarter[0],end=quarter[1]);explicit_dimensions.append('dates')
    elif iso_dates:
        if len(iso_dates)!=2:raise clarification('dates')
        scope.update(start=iso_dates[0],end=iso_dates[1]);explicit_dimensions.append('dates')
    elif named:
        scope.update(start=named['start'],end=named['end']);explicit_dimensions.append('dates')
    elif year_only:
        year=int(years[0]);end=f'{year:04}-12-31'
        if year_to_date and str(last)>=f'{year:04}-01-01':end=min(end,str(last))
        scope.update(start=f'{year:04}-01-01',end=end);explicit_dimensions.append('dates')
    elif months and (any(w in q for w in ('inventory','stock','warehouse','مخزون','مخازن')) or
        (not metrics_in(question) and set(state.get('request',{}).get('metrics',[]))&STOCK)):
        if len(months)!=1:raise clarification('dates')
        month=date.fromisoformat(months[0]+'-01');scope.update(start=str(month),end=str(shift_months(month,1)-timedelta(days=1)))
    elif any(w in q for w in ('month before','previous month','الشهر اللي قبله','الشهر السابق له')):
        start=date.fromisoformat(scope['start']);end=start-timedelta(days=1)
        scope.update(start=str(end.replace(day=1)),end=str(end))
    elif any(w in q for w in ('last quarter','الربع الماضي','الربع اللي فات')):
        this_quarter=date(last.year,((last.month-1)//3)*3+1,1);end=this_quarter-timedelta(days=1)
        scope.update(start=str(shift_months(this_quarter,-3)),end=str(end))
    elif any(w in q for w in ('this month','الشهر ده','الشهر الحالي')):
        scope.update(start=str(last.replace(day=1)),end=str(last))
    elif any(w in q for w in ('last year','السنة الماضية','السنة اللي فاتت')):
        scope.update(start=f'{last.year-1}-01-01',end=f'{last.year-1}-12-31')
    elif any(w in q for w in ('next quarter','next month','القادم','الجاي','الجاية','forecast','توقع','متوقع')):
        # Forecast origin is enforced by Phase 7, not these display dates.
        pass
    elif customer and tags&{'churn','value'} and not re.search(r'\d{4}',q):
        # Approved customer research owns its mature cutoffs; no host-clock label.
        pass
    else:
        try:scope=vars(resolve_period(question,filters(**scope)))
        except (ValueError,TypeError):raise clarification('dates') from None
    filters(**scope)
    if pair:
        for identifier in pair:filters(scope['start'],scope['end'],identifier,scope.get('location_type'),scope.get('category'))
    explicit_dimensions+= [k for k,v in scope.items() if initial_scope.get(k)!=v]
    resolved=dict(scope=scope,pair=pair,categories=state_categories,global_scope=dict(global_scope),
        source_start=str(first),source_end=str(last),last_complete_month=str(complete_end),overrides=scope!=global_scope or bool(pair),
        last_operations=state.get('last_operations',[]) if previous is not None else [],warehouse=warehouse,horizon=horizon,
        explicit_dimensions=explicit_dimensions,forecast=forecast,company_wide=company,forecast_months=forecast_months,
        forecast_accuracy=forecast and (wants_accuracy(question) or bool(pending and state.get('forecast_accuracy'))),product_ids=product_ids)
    snapshot_as_of=named.get('snapshot_as_of') if named else None
    resolved['temporal']=dict(transaction_window={k:scope[k] for k in ('start','end')},snapshot_as_of=snapshot_as_of,forecast_target_months=forecast_months)
    resolved['metric_bundles']=state.get('metric_bundles',[])
    if not forecast and scope['start'][5:]=='01-01' and scope['end']==scope['start'][:4]+'-12-31':
        available_start=max(scope['start'],str(first));available_end=min(scope['end'],str(last))
        resolved['calendar_coverage']=dict(requested_start=scope['start'],requested_end=scope['end'],
            available_start=available_start if available_start<=available_end else None,
            available_end=available_end if available_start<=available_end else None,
            complete=scope['start']>=str(first) and scope['end']<=str(last),
            basis='historical source coverage, not current calendar date')
    previous_request=dict(state.get('request',{})) if previous is not None else None
    if company and previous_request:previous_request.update(aggregation=None,detail_grain=None,parameters={})
    resolved['request']=request_for(question,resolved,previous_request)
    request=resolved['request']
    bundle_count=metric_reference_size(question)
    if bundle_count is not None and not metrics_in(question):
        entities=request['entities']
        scope_override=bool(set(resolved.get('explicit_dimensions',[]))&{'entities','products','warehouse','category'} or requested_grain(question))
        candidates=[b['metrics'] for b in reversed(state.get('metric_bundles',[])) if (not bundle_count or len(b['metrics'])==bundle_count)
            and (scope_override or (sorted(b.get('entities',[]))==sorted(entities) and b.get('aggregation')==request['aggregation']))
            and (not b.get('domains') or set(b['domains'])&set(request['domains']))]
        if not candidates and (not bundle_count or len(request['metrics'])==bundle_count):candidates=[request['metrics']]
        if not candidates:raise clarification('metrics')
        request['metrics']=list(candidates[0]);request['metric_bundle_size']=len(candidates[0])
        request['domains']=sorted(set(request['domains'])|set(metric_domains(request['metrics'])))
        request['answer_components']=list(dict.fromkeys(request['answer_components']+['metric_bundle']))
    if request['intent']=='compare' and not pair and not found and not company and not forecast and request['aggregation'] in ('company','location','locations') and not tags&{'period_comparison','model','seasonality'}:
        raise clarification('locations')
    resolved['last_plan']=state.get('last_plan',[]) if previous is not None else []
    return resolved
