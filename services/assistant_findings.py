"""Evidence-bound answer obligations and descriptive comparisons; no analytics math.

Select existing public cells, never infer causes, individual risk or action effects.
Labels and metric definitions remain application-owned; no generated model prose.
"""
import math
import re
import hashlib,json
from services.assistant_capabilities import CAPABILITIES
from services.assistant_language import obligations
from services.assistant_obligations import typed_support

DIMENSIONS=('c8_segment','branch_id','location_id','product_id','category','period','month','calendar_month','c8_cohort','c8_month','forecast_model')
COMPONENTS={
    'description': r'\b(?:explain|interpret|observations?|insights?|meaning|behavior|behaviour)\b|اشرح|فسّر|فسر|تفسير|وضح|سلوك',
    'investigation': r'\b(?:attention|priorities|priority|investigate|investigation|review first)\b|اهتمام|أولوية|اولويه|أولويات|اولويات|يحتاج مراجعة|تستحق المراجعة',
    'cause': r'\b(?:why|cause|causes|caused|causal)\b|لماذا|ليه|سبب|أسباب|اسباب',
    'predictive_conclusion': r'\b(?:will churn|churn probability|who will leave|guarantee|guaranteed)\b|احتمال فقدان|سوف يغادر|سيغادر|اضمن|مضمون',
}

def components(question, previous=None, inherit=False):
    found=[key for key,pattern in COMPONENTS.items() if re.search(pattern,question,re.I)]
    typed=obligations(question)
    if set(typed)&{'noncausal_description','customer_reliability'}:found=[c for c in found if c!='cause']
    if 'inference_limit' in typed:found=[c for c in found if c!='predictive_conclusion']
    if not found and inherit:found=[c for c in (previous or []) if c!='facts']
    return list(dict.fromkeys(['facts']+found+typed))

def numeric(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)

def _freeze(value):
    """Order-independent, hashable public metadata; no inferred scope mappings."""
    if isinstance(value,dict):return tuple(sorted((k,_freeze(v)) for k,v in value.items()))
    if isinstance(value,(tuple,list)):return tuple(_freeze(v) for v in value)
    return value

def _contract(meta,row,metric,field,*,side=None,period_comparison=False):
    """Describe the actual service row, never the requested/desired grain."""
    tool=meta.get('tool');cap=CAPABILITIES.get(tool)
    entity_type=grain=None;stratum={}
    scope={k:meta.get(k) for k in ('branch_id','location_type','category','warehouse_id','product_ids','categories',
        'status','min_revenue','min_units','screen','rules','planning','sales_window','financial_basis','classification','scope_policy')}
    # Scope-policy prose is not identity: equivalent approved adapters can use
    # different wording. All structured constraints remain part of identity.
    scope.pop('scope_policy')
    if scope['branch_id']=='all':scope['branch_id']=None
    scope['evaluation_stage']=row.get('stage',row.get('c8_stage'))
    for key in ('product_ids','categories'):
        if scope[key] is not None:scope[key]=sorted(scope[key])
    if side:
        entity_type='location';grain=('location',)
        scope['branch_id']=None
        scope['comparison_entities']=sorted(str(meta[k]) for k in ('branch_a','branch_b') if meta.get(k) is not None)
        if row.get('category') is not None:
            grain=('location','category');scope['category']=row['category'];stratum['category']=row['category']
    elif period_comparison:
        entity_type='period';grain=('period_total',)
    elif cap and cap.domain=='forecast' and cap.role=='forecast':
        entity_type='forecast_period';grain=('monthly','forecast_target')
    elif 'product_id' in row:
        entity_type='product';grain=('product',)
    elif 'c8_previous_segment' in row:
        entity_type='customer_segment_transition';grain=('previous_segment','current_segment') if 'c8_segment' in row else ('previous_segment',)
    elif 'c8_segment' in row:
        entity_type='customer_segment';grain=('customer_segment',)
    elif 'c8_cohort' in row:
        entity_type='customer_cohort';grain=('cohort','age') if 'c8_age' in row else ('cohort',)
        scope['cohort_age']=row.get('c8_age')
        if 'c8_age' in row:stratum['cohort_age']=row['c8_age']
    elif 'source_warehouse_id' in row or 'destination_branch_id' in row:
        entity_type='transfer_route';grain=tuple(k for k in ('month','source_warehouse_id','destination_branch_id','transfer_status') if k in row)
    elif 'warehouse_id' in row:
        entity_type='warehouse';grain=('warehouse','category') if 'category' in row else ('warehouse',)
        scope['warehouse_id']=None
    elif any(k in row for k in ('branch_id','location_id')):
        entity_type='location';grain=('location','category') if cap and cap.domain=='inventory' and 'category' in row else ('location',)
        scope['branch_id']=None
    elif 'category' in row:
        entity_type='category';grain=('category',)
    elif any(k in row for k in ('period','month','c8_month','calendar_month')):
        entity_type='time';grain=('calendar_month_of_year',) if 'calendar_month' in row else ('time',meta.get('grain') or ('monthly' if cap and (cap.domain in ('forecast','customers') or cap.role=='trend') else tool))
    elif cap and cap.role in ('summary','legacy_snapshot'):
        entity_type='location' if meta.get('branch_id') not in (None,'all') else 'company'
        grain=(entity_type,)
        if entity_type=='location':scope['branch_id']=None
    if cap is None:entity_type=grain=None
    if cap:
        expected={'products':'product','screening':'product','leaders':'product','categories':'category',
            'locations':'location','decline':'location','trend':'time','seasonality':'time',
            'segments':'customer_segment','retention':'customer_cohort','activity':'time',
            'changes':'customer_segment_transition'}.get(cap.role)
        if expected and entity_type!=expected:entity_type=grain=None
        if cap.role=='summary' and entity_type not in ('company','location'):entity_type=grain=None
        if cap.domain=='forecast' and cap.role=='forecast' and 'month' not in row:entity_type=grain=None
    if entity_type in ('product','category','location','warehouse') and not side and any(k in row for k in ('period','month')):
        grain=(*grain,'time',meta.get('grain') or ('monthly' if 'month' in row else 'unpublished'))
    if cap and cap.domain in ('inventory','sales_inventory'):
        scope['inventory_population']='warehouse' if cap.role=='warehouse' else 'sales_location'
    if cap and cap.domain=='forecast':
        scope.update({k:meta.get(k,row.get(k)) for k in ('origin','target','horizon','forecast_start','forecast_end','training_start','training_end')})
        if cap.role in ('growth','category_pair'):grain=('category','horizon_total')
        basis=('forecast',('horizon_total' if cap.role in ('growth','category_pair') else cap.role),scope['origin'],scope['horizon'])
    elif cap and cap.domain in ('inventory','sales_inventory'):
        basis=('legacy_snapshot' if cap.role=='legacy_snapshot' else 'monthly_snapshot',meta.get('snapshot'))
        if cap.role=='transfers':basis=('recorded_transfer_dates',)
        elif cap.domain=='sales_inventory':basis=('aligned_transaction_and_snapshot',meta.get('snapshot'))
    elif cap and cap.domain=='customers':basis=('fixed_customer_window',cap.role)
    elif period_comparison:basis=('approved_period_comparison',meta.get('previous_period'))
    else:basis=('transaction_dates',)
    units=meta.get('units') or {}
    unit=units.get(field) or units.get(metric) or (meta.get('unit') if cap and cap.domain=='forecast' and cap.role=='forecast' else None)
    # A missing published unit is NOT assumed to be EGP/units. Within the same
    # approved operation/column its unit contract is stable; cross-operation
    # comparisons then require an explicit matching published unit.
    if not unit and cap:unit=('approved_column_unit',tool,field)
    return dict(entity_type=entity_type,aggregation_grain=grain,unit=_freeze(unit),scope=_freeze(scope),
        time_basis=_freeze(basis),measure=field,source=tool,stratum=_freeze(stratum),
        time_coordinate=row.get('period',row.get('month',row.get('c8_month',row.get('calendar_month')))))

def _entity(row,meta,contract,fallback):
    kind=contract['entity_type']
    keys={'product':('product_id',),'category':('category',),'customer_segment':('c8_segment',),
        'customer_segment_transition':('c8_previous_segment','c8_segment'),'customer_cohort':('c8_cohort',),
        'location':('branch_id','location_id'),'warehouse':('warehouse_id',),
        'forecast_period':('month',),'time':('period','month','c8_month','calendar_month')}.get(kind,())
    values=[str(row[k]) for k in keys if row.get(k) is not None]
    if not values and kind=='location' and meta.get('branch_id') not in (None,'all','pair'):values=[str(meta['branch_id'])]
    if not values and kind=='warehouse' and meta.get('warehouse_id') is not None:values=[str(meta['warehouse_id'])]
    if kind=='transfer_route':values=[str(row[k]) for k in contract['aggregation_grain']]
    if kind in ('location','warehouse') and 'category' in (contract['aggregation_grain'] or ()) and row.get('category') is not None:values.append(str(row['category']))
    return ' / '.join(values) if values else fallback

def observations(reports, request):
    """Comparable requested cells only. No sums, ratios, scores or KPI creation."""
    metrics=request.get('metrics',[]);result=[];seen=set()
    for report in reports:
        meta=report['meta']
        source_instance=hashlib.sha256(json.dumps(report,sort_keys=True,default=str).encode()).hexdigest()
        if meta.get('state') in ('unavailable','unreliable') or meta.get('tool') in ('customer8_churn','customer8_value'):continue
        for row in report.get('data',[]):
            values=[]
            if row.get('metric') in metrics and meta.get('branch_a'):
                values=[(row['metric'],meta.get('branch_'+s),row.get('location_'+s),row['metric'],s,False) for s in ('a','b')]
            elif meta.get('branch_a'):
                values=[(metric,str(meta.get('branch_'+s))+(' / '+str(row['category']) if row.get('category') is not None else ''),row.get(metric+'_'+s),metric,s,False) for metric in metrics for s in ('a','b')]
            elif row.get('metric') in metrics and 'current' in row:
                values=[(row['metric'],meta.get(key),row.get(column),row['metric'],None,True) for key,column in (('period','current'),('previous_period','previous'))]
            else:
                identity=('c8_previous_segment','warehouse_id',*DIMENSIONS)
                entity=next((str(row[k]) for k in identity if row.get(k) is not None),None)
                for metric in metrics:
                    field='central' if meta.get('tool')=='forecast7_values' and metric in ('sales','units') else metric
                    if field=='recorded_risk' and field not in row:field='max_recorded_risk'
                    values.append((metric,entity,row.get(field),field,None,False))
            for metric,entity,value,field,side,period_comparison in values:
                if not numeric(value):continue
                contract=_contract(meta,row,metric,field,side=side,period_comparison=period_comparison)
                if not side and not period_comparison:entity=_entity(row,meta,contract,entity)
                # Missing temporal metadata cannot authorize cross-report joins.
                cap=CAPABILITIES.get(meta.get('tool'))
                if not all(k in meta for k in ('branch_id','category','location_type')):
                    contract['scope']=(*contract['scope'],('same_report_only',source_instance))
                if cap and ((cap.domain in ('inventory','sales_inventory') and cap.role!='transfers' and not meta.get('snapshot')) or
                            (cap.domain=='forecast' and (not meta.get('origin') or not meta.get('horizon')))):
                    contract['time_basis']=(*contract['time_basis'],('same_report_only',source_instance))
                contract['source_instance']=source_instance
                if side and row.get('category') is not None:contract['time_coordinate']=meta.get('snapshot')
                if period_comparison:contract['time_coordinate']=entity
                signature=(metric,entity,meta.get('period'),value,_freeze(contract))
                if signature in seen:continue
                seen.add(signature)
                result.append(dict(metric=metric,entity=entity,value=value,period=meta.get('period'),
                    estimated=meta.get('tool','').startswith('forecast7_'),**contract))
    return result

def comparison(cells):
    """Compare one population/measure/time basis, never unlike aggregation levels."""
    groups={}
    for cell in cells:
        groups.setdefault((cell['metric'],cell['period']),[]).append(cell)
    group=[]
    keys=('entity_type','aggregation_grain','unit','time_basis','measure','estimated')
    for candidates in groups.values():
        if any(not c.get('entity_type') or not c.get('aggregation_grain') or not c.get('unit') or not c.get('period') or
               any(c.get(k) is None for k in ('scope','time_basis','measure')) for c in candidates):continue
        if len({_freeze({k:c.get(k) for k in keys}) for c in candidates})!=1:continue
        # Only schema-declared matched strata may vary within one family, e.g.
        # compare the same locations separately inside each recorded category.
        base_scopes=[];slices={}
        for c in candidates:
            scope=dict(c.get('scope',()));stratum=dict(c.get('stratum',()))
            if any(scope.get(k)!=v for k,v in stratum.items()):break
            base_scopes.append(_freeze({k:v for k,v in scope.items() if k not in stratum}))
            slices.setdefault(_freeze(c.get('scope')),[]).append(c)
        else:
            if len(set(base_scopes))!=1:continue
            complete=True
            for items in slices.values():
                by_entity={}
                for c in items:by_entity.setdefault(c['entity'],set()).add(c['value'])
                if len({c['entity'] for c in items if c['entity'] is not None})<2 or any(len(v)>1 for v in by_entity.values()):complete=False;break
            if complete:group=next(iter(slices.values()));break
    if not group:return None
    high=max(group,key=lambda c:c['value']);low=min(group,key=lambda c:c['value'])
    return dict(high=high,low=low,tied=high['value']==low['value'])

def coverage(reports, request):
    asked=request.get('answer_components',['facts']);cells=observations(reports,request);pair=comparison(cells)
    # Published research measurements remain reportable facts, but are excluded
    # from comparative managerial priorities and predictive conclusions above.
    measured=any(numeric(row.get(metric)) for r in reports if r['meta'].get('state')!='unavailable'
                 for row in r.get('data',[]) for metric in request.get('metrics',[]))
    supported=['facts'] if cells or measured else []
    if pair:supported.append('description')
    if pair:supported.append('investigation')
    supported=list(set(supported)|typed_support(reports,request,cells,pair))
    incomplete=False
    for report in reports:
        rows=report.get('data',[])
        for metric in request.get('metrics',[]):
            if any(metric in row for row in rows) and any(not numeric(row.get(metric)) for row in rows):incomplete=True
    missing=[c for c in asked if c not in supported and c!='facts']
    if incomplete:missing.append('facts')
    return dict(requested_answer_components=asked,supported_answer_components=[c for c in asked if c in supported],
        missing_answer_components=missing)
