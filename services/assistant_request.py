"""Structured analytical intent/coverage, independent of IDs, dates and results.

Canonical fields and tool capabilities describe the existing approved API, not
business answers. Natural-language aliases are shared grammar, never fixtures.
"""
import re,math
from copy import deepcopy
from datetime import date
from calendar import monthrange
from services.assistant_capabilities import compatible_grain,CAPABILITIES
from services.assistant_semantics import signals
from services.assistant_findings import components
from services.assistant_language import requested_grain,obligations,dual_ranking,ranking_syntax,temporal_extrema,normalized

METRIC_ALIASES={
 'gross_margin_pct':('gross profit margin','gross margin','margin','هامش مجمل الربح','هامش الربح','هامش','هوامش'),
 'aov':('average order value','aov','متوسط قيمة الطلب','متوسط الطلب'),
 'gross_profit':('gross profit','profit','مجمل الربح','مجمل ربح','أرباح','ارباح','ربح'),
 'sales':('sales','revenue','مبيعات','إيراد','ايراد','إيرادات','ايرادات'),
 'orders':('orders','order count','طلبات'),
 'units':('units sold','sold units','units','الوحدات المباعة','وحدات'),
 'growth_pct':('sales growth','growth','نمو'),
 'recorded_risk':('inventory risk','stock risk','recorded risk','risk','risky','riskier','مخاطر المخزون','مخاطر','خطر','خطورة','خطورت','stockout probability','probability of stockout','احتمال نفاد المخزون','احتمالية نفاد المخزون'),
 'cover_days':('stock cover','cover','تغطية'),
 'estimated_replenishment':('replenishment','replenish','توريد'),
 'stock_units':('stock units','inventory units','وحدات المخزون','inventory','stock','مخزون','warehouse','مستودع','مخازن'),
 'stock_value':('stock value','inventory value','inventory valuation','قيمة المخزون','تقييم المخزون'),
 'c8_repeat_rate':('repeat customer rate','repeat purchase rate','more than once','أكتر من مرة','أكثر من مرة','اكثر من مرة'),
}
FINANCIAL=frozenset(('sales','gross_profit','gross_margin_pct','orders','aov','units','growth_pct','customers'))
STOCK=frozenset(('stock_units','stock_value','recorded_risk','cover_days','estimated_replenishment'))
PAIR_TOOLS=frozenset(('two_location_comparison','profit5_pair','inventory6_pair'))

def metric_domains(metrics):
    fields=set(metrics);domains=[]
    if fields&{'sales','orders','aov','units','growth_pct'}:domains.append('sales')
    if fields&{'gross_profit','gross_margin_pct'}:domains.append('profitability')
    if fields&STOCK:domains.append('inventory')
    if any(m.startswith('c8_') for m in fields):domains.append('customers')
    return domains

def metrics_in(question):
    q=normalized(question);candidates=[];chosen=[]
    for metric,aliases in METRIC_ALIASES.items():
        for alias in aliases:
            plural='s?' if alias.isascii() and alias[-1].isalpha() and not alias.endswith('s') else ''
            # Match Arabic words as words too: نمو must not match النموذج.
            prefix='' if alias.isascii() else r'(?:وال|بال|فال|كال|لل|ال|[وبفكل])?'
            pattern=r'(?<!\w)'+prefix+re.escape(alias)+plural+r'(?!\w)'
            for match in re.finditer(pattern,q):candidates.append((match.start(),match.end(),metric))
    for start,end,metric in sorted(candidates,key=lambda hit:(-(hit[1]-hit[0]),hit[0])):
        if not any(start<b and end>a for a,b,_ in chosen):chosen.append((start,end,metric))
    found=list(dict.fromkeys(metric for _,_,metric in sorted(chosen)))
    quantity=any(alias in q for alias in ('stock units','inventory units','وحدات المخزون'))
    if set(found)&(STOCK-{'stock_units'}) and not quantity:found=[m for m in found if m!='stock_units']
    return found

def reference(question):
    q=question.casefold()
    return bool(re.search(r'\b(them|those|same|before|previous)\b',q) or
        any(word in q for word in ('نفس','قارنهم','فيهم','بينهم','عندهم','قبله','قبلها','السابق')))

def request_for(question,resolved,previous=None):
    previous=previous or {};q=question.casefold();metrics=metrics_in(question);tags=signals(question);typed=obligations(question,forecast=resolved.get('forecast',False))
    ranking=ranking_syntax(question)
    # Published policy: unqualified best-selling means recorded sold units.
    # Explicit value/quantity measures always take precedence over that default.
    metric_policy=None
    explicit_axis=re.search(r'\b(?:ranked |sorted |measured )?by\b|\bbased on\b|حسب|من حيث|بقيمة',q)
    if ranking['bestselling'] and not explicit_axis:
        metrics=list(dict.fromkeys(['units']+metrics));metric_policy='bestselling_recorded_units'
    if 'inference_limit' in typed and ('segments' in tags or previous.get('aggregation')=='segment'):
        tags=[t for t in tags if t!='churn']
        metrics=[m for m in metrics if m not in STOCK]
        if 'segments' not in tags:tags.append('segments')
    if resolved.get('forecast') and resolved.get('company_wide') and not metrics:metrics=['units' if resolved['scope'].get('category') else 'sales']
    if 'warehouse' in resolved.get('explicit_dimensions',[]) and 'warehouse' not in tags:tags.append('warehouse')
    explicit_dimensions=bool(resolved.get('explicit_dimensions'))
    inherited=not metrics and (reference(question) or explicit_dimensions)
    roles={'segments','retention','activity','changes','churn','value','transfers','seasonality','repeat_summary'}
    if (set(tags)&roles)-set(previous.get('signals',[])):inherited=False
    if inherited:
        metrics=list(previous.get('metrics',[]))
        if not set(tags)-{'warehouse','location','product','category'}:tags=list(dict.fromkeys(previous.get('signals',[])+tags))
    defaults={'seasonality':'avg_sales','decline':'growth_pct','screening':'gross_margin_pct','leaders':'gross_profit','retention':'c8_retention_pct','segments':'c8_customers','activity':'c8_frequency','changes':'c8_frequency_change','churn':'c8_roc_auc','value':'c8_predicted_revenue','transfers':'transfer_units','repeat_summary':'c8_repeat_rate'}
    if 'seasonality' in tags and metrics==['sales']:metrics=['avg_sales']
    if not metrics:metrics=list(dict.fromkeys(defaults[tag] for tag in tags if tag in defaults))
    for tag in tags:
        if tag in {'retention','segments','activity','changes','churn','value','transfers','repeat_summary'} and defaults[tag] not in metrics:metrics.append(defaults[tag])
    if 'value' in tags and not any(w in q for w in ('sales','مبيعات')):metrics=[m for m in metrics if m!='sales']
    if resolved.get('forecast') and 'growth' in tags:metrics=['forecast_vs_recent_pct','forecast_units','recent_actual_units']
    if resolved.get('forecast') and len(resolved.get('categories',[]))==2 and not metrics:metrics=['forecast_units']+(['test_wape_pct'] if resolved.get('forecast_accuracy') else [])
    special=bool(resolved.get('forecast')) or any(w in q for w in ('customer','rfm','churn','retention','cohort','clv','عملاء','عميل','احتفاظ','شرائح','forecast','توقع','متوقع','seasonality','موسمية'))
    grain=previous.get('aggregation');detail_grain=previous.get('detail_grain')
    if resolved.get('pair') and 'entities' in resolved.get('explicit_dimensions',[]) and not reference(question) and not requested_grain(question):
        grain=None;detail_grain=None
    if 'customer_reliability' in typed:grain='company';detail_grain=None
    if 'warehouse' in resolved.get('explicit_dimensions',[]) and not resolved['pair'] and not set(metrics)&FINANCIAL:grain='warehouse';detail_grain=None
    semantic_grains={'screening':'product','leaders':'product','decline':'locations','seasonality':'time','retention':'cohort','segments':'segment','activity':'time','changes':'segment_change','churn':'company','value':'company'}
    for tag in tags:
        if tag in semantic_grains:grain=semantic_grains[tag]
    if set(tags)&{'churn','value'}:detail_grain=None
    if set(metrics)&STOCK and grain=='product' and 'product' not in tags and not reference(question):grain='company';detail_grain=None
    if resolved.get('product_ids'):grain='product'
    elif requested_grain(question):grain=requested_grain(question)
    elif any(w in q for w in ('trend','monthly','daily','weekly','yearly','اتجاه','شهري','يومي','أسبوعي','اسبوعي','سنوي')):grain='time'
    elif any(w in q for w in ('highest','lowest','largest','smallest','ranking','top ','الفروع الأعلى','الفروع الاقل')) and not resolved['pair'] and grain not in ('segment','cohort','segment_change','warehouse','time'):grain='locations'
    if grain in ('product','category','time'):detail_grain=grain
    if any(w in q for w in ('overall','summary','total ','إجمالي','اجمالي','ملخص')):detail_grain=None;grain='company'
    if resolved['pair']:grain='location_pair'
    elif resolved['scope'].get('branch'):grain='location'
    elif grain in ('location_pair','location') or grain is None:grain='company'
    if any(w in q for w in ('company-wide','all locations','الشركة كلها','كل الفروع')) and detail_grain is None and grain!='locations':grain='company'
    parameters=deepcopy(previous.get('parameters',{}))
    if grain!=previous.get('aggregation') and not reference(question):parameters={}
    if previous.get('ranking_metrics') and (grain not in ('product','category','locations') or set(metrics)&STOCK or any(m.startswith('c8_') for m in metrics)) and not reference(question):
        parameters.pop('limit',None);parameters.pop('ascending',None)
    for value,words in {'daily':('daily','يومي'),'weekly':('weekly','أسبوعي','اسبوعي'),
            'monthly':('monthly','شهري'),'yearly':('yearly','سنوي')}.items():
        if any(w in q for w in words):parameters['grain']=value
    if any(w in q for w in ('lowest','smallest','ascending','أقل','اقل','أصغر','اصغر')):parameters['ascending']=True
    elif any(w in q for w in ('highest','descending','أعلى','اعلى')):parameters['ascending']=False
    count=re.search(r'(?:\btop|\bhighest|\blowest|\bbottom|أعلى|اعلى|أقل|اقل|أفضل)\s+(\d+)(?![\d.])',q.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789')))
    if count:parameters['limit']=int(count[1])
    if ranking['count'] is not None:parameters['limit']=ranking['count']
    if ranking['ambiguous_count']:parameters.pop('limit',None)
    series=grain=='time' and not special and bool(set(metrics)&FINANCIAL)
    extremes=temporal_extrema(question) if series else []
    if series:typed+=['series']+['series_'+v for v in extremes]
    unresolved=['numeric_predicate'] if re.search(r'(?:[<>]=?|\bat least|\bat most|\babove|\bbelow|\bgreater than|\bless than|على الأقل|أكثر من|أقل من)\s*\d',q) else []
    if ranking['ambiguous_count']:unresolved.append('ranking_count')
    if inherited:unresolved=list(dict.fromkeys(previous.get('unresolved_constraints',[])+unresolved))
    domains=metric_domains(metrics)
    if set(tags)&{'warehouse','transfers'}:domains.append('inventory')
    if resolved.get('forecast'):domains=['forecast']
    if any(w in q for w in ('customer','rfm','cohort','churn','clv','عملاء','عميل','شرائح')):domains.append('customers')
    if not domains and inherited:domains=list(previous.get('domains',[]))
    axes=list(metrics)
    axis_phrase=explicit_axis
    if axis_phrase and not dual_ranking(question):
        axis_metrics=metrics_in(question[axis_phrase.end():])
        if axis_metrics:axes=[axis_metrics[0]]
    ranks=(axes if dual_ranking(question) else axes[:1]) if (grain in ('product','category','locations') and ('ranking' in tags or 'limit' in parameters or previous.get('ranking_metrics'))) else []
    if 'customer_reliability' in typed:
        metrics=list(dict.fromkeys(metrics+['c8_roc_auc','c8_average_precision','c8_brier','c8_ece','c8_prevalence','c8_samples']))
    return dict(metrics=metrics,aggregation=grain,detail_grain=detail_grain,parameters=parameters,ranking_metrics=ranks,metric_policy=metric_policy,
        series_extrema=extremes,answer_shape=('series' if series else 'ranking' if ranks else 'pair' if resolved['pair'] else 'facts'),
        extreme_direction='smallest' if parameters.get('ascending') else 'largest',
        answer_components=list(dict.fromkeys(components(question,previous.get('answer_components'),inherited)+typed)),
        intent='forecast' if resolved.get('forecast') else 'compare' if 'compare' in tags else 'rank' if 'ranking' in tags else 'analyze',
        domains=sorted(set(domains)),signals=tags,entity_types=['location_pair'] if resolved['pair'] else ['product'] if grain=='product' else ['warehouse'] if resolved.get('warehouse') else ['location'] if resolved['scope'].get('branch') else ['company'],
        date_period={k:resolved['scope'][k] for k in ('start','end')},filters={**{k:resolved['scope'].get(k) for k in ('branch','category','location_type')},'products':list(resolved.get('product_ids',[])),'warehouse':resolved.get('warehouse')},
        context_references=dict(explicit=reference(question),inherited=bool(previous and not resolved.get('explicit_dimensions'))),
        explicit_overrides=list(resolved.get('explicit_dimensions',[])),required_capabilities=[],
        unresolved_constraints=unresolved,
        forecast=bool(resolved.get('forecast')),
        unsupported_risk_metric=bool('recorded_risk' in metrics and any(w in q for w in ('stockout probability','probability of stockout','predicted risk','احتمال نفاد','احتمالية نفاد'))),
        inventory_scope=('warehouse' if resolved.get('warehouse') or any(w in q for w in ('warehouse','مستودع','مخازن')) else 'branch' if set(metrics)&STOCK else previous.get('inventory_scope','branch')),
        scope=deepcopy(resolved['scope']),entities=list(resolved.get('product_ids') or resolved['pair'] or ([resolved['scope']['branch']] if resolved['scope'].get('branch') else [resolved['warehouse']] if resolved.get('warehouse') else [])),
        special=special or (inherited and previous.get('special',False)),inherited=inherited,
        unsupported_aggregation=bool(set(metrics)&STOCK and resolved['pair'] and detail_grain!='category' and not resolved['scope'].get('category') and
            any(w in q for w in ('higher','highest','winner','أعلى','اعلى','اكتر','أكثر'))))

def select_plan(request,legacy_plan):
    """Select by capability and resolved grain; never substitute a location ranking for a pair."""
    metrics=set(request['metrics']);grain=request['aggregation'];params=request['parameters']
    if request['special'] or not metrics:return legacy_plan
    if any(n in ('category_risk_sales','executive_stock','sales_seasonality') for n,a in legacy_plan):return legacy_plan
    # Mixed-domain adapters already have separate approved policies.
    if any(n.startswith(('customer8_','forecast7_')) for n,a in legacy_plan):return legacy_plan
    finance=metrics&FINANCIAL;stock=metrics&STOCK;plan=[]
    if grain=='location_pair':
        if request.get('detail_grain') is not None:finance=set()  # Preserve compatible stock evidence when finance cannot cover this grain.
        for metric in request['metrics']:
            if metric in finance:plan.append(('profit5_pair' if metric in ('gross_profit','gross_margin_pct') else 'two_location_comparison',{}))
        if stock:plan.append(('inventory6_pair',{}))
        # Keep independently requested domains; do not duplicate finance adapters.
        return list(dict((n,(n,a)) for n,a in plan).values())
    if finance:
        for metric in request['metrics']:
            if metric not in finance:continue
            if request.get('ranking_metrics') and metric not in request['ranking_metrics']:continue
            if grain=='product':
                if metric not in ('sales','gross_profit','gross_margin_pct','units'):continue
                tool='profit5_products' if metric in ('gross_profit','gross_margin_pct') or params.get('ascending',False) else 'sales4_products'
                plan.append((tool,dict(metric=metric,ascending=params.get('ascending',False))))
            elif grain=='category':
                if metric in ('sales','gross_profit','gross_margin_pct') and not params.get('ascending',False):plan.append(('profit5_categories',dict(metric=metric)))
            elif grain=='locations':
                from services.sales_branch import RANK_METRICS
                if metric in RANK_METRICS:plan.append(('location_ranking',dict(metric=metric,ascending=params.get('ascending',False))))
                elif metric=='gross_margin_pct' and not params.get('ascending',False):plan.append(('profit5_locations',dict(metric=metric)))
            elif grain=='time':
                if metric in CAPABILITIES['sales4_trends'].metrics:plan.append(('sales4_trends',dict(grain=params.get('grain','monthly'))))
                elif params.get('grain','monthly')=='monthly' and metric in CAPABILITIES['profit5_trends'].metrics:plan.append(('profit5_trends',{}))
            else:plan.append(('location_detail' if grain=='location' else 'company_overview',{}))
    if stock:
        stock_plan=[(n,a) for n,a in legacy_plan if n.startswith('inventory6_') or n=='executive_stock']
        if stock_plan:plan.extend(stock_plan)
        else:
            tool='inventory6_risk' if 'recorded_risk' in stock else 'inventory6_cover' if 'cover_days' in stock else 'inventory6_replenishment' if 'estimated_replenishment' in stock else 'inventory6_stock'
            plan.append((tool,{}))
    return list({(n,tuple(sorted(a.items()))):(n,a) for n,a in plan}.values())

def compatible(name,resolved):
    request=resolved.get('request')
    if not request:return True
    if resolved.get('product_ids') and CAPABILITIES[name].role not in ('products','screening','leaders') and CAPABILITIES[name].domain!='customers':return False
    if not compatible_grain(name,request):return False
    if resolved.get('pair') and name in ('two_location_comparison','profit5_pair') and request.get('detail_grain') is not None:return False
    if resolved.get('pair') and name not in PAIR_TOOLS:
        # Fixed customer privacy exception is disclosed rather than pretending pair coverage.
        return name.startswith('customer8_')
    if not resolved.get('pair') and name in PAIR_TOOLS:return False
    if request['aggregation'] not in ('locations',) and name in ('location_ranking','declining_locations'):return False
    return True

def output_issues(report,resolved):
    """Check evidence's actual entities/dates/columns/grain, not just its tool name."""
    request=resolved.get('request')
    if not request:return []
    meta=report.get('meta',{});rows=report.get('data',[]);scope=resolved['scope'];issues=[]
    name=meta.get('tool','')
    if name.startswith('customer8_'):return []  # Existing fixed-scope privacy disclosure remains authoritative.
    if resolved.get('product_ids'):
        if meta.get('product_ids')!=resolved['product_ids']:issues.append('products')
        if any(row.get('product_id') not in resolved['product_ids'] for row in rows):issues.append('products')
        if rows and CAPABILITIES[name].role=='products' and set(row.get('product_id') for row in rows)!=set(resolved['product_ids']):issues.append('product_coverage')
    if not compatible(name,resolved):issues.append('aggregation')
    expected_start,expected_end=scope['start'],scope['end']
    if name.startswith('inventory6_') and name!='inventory6_transfers' and resolved.get('temporal',{}).get('snapshot_as_of'):
        expected_end=resolved['temporal']['snapshot_as_of'];expected_start=min(expected_start,expected_end)
    if meta.get('period')!=expected_start+' to '+expected_end:issues.append('dates')
    pair=resolved.get('pair',[])
    if pair:
        if [meta.get('branch_a'),meta.get('branch_b')]!=pair:issues.append('entities')
        if any(row.get(k) is not None and row[k] not in pair for row in rows for k in ('branch_id','location_id')):issues.append('entities')
        if name in ('two_location_comparison','profit5_pair') and any(not {'metric','location_a','location_b'}<=set(row) for row in rows):issues.append('aggregation')
        if name=='inventory6_pair' and any(not {'category','stock_units_a','stock_units_b'}<=set(row) for row in rows):issues.append('aggregation')
    elif name not in ('location_ranking','declining_locations','inventory6_warehouse') and meta.get('branch_id')!=(scope.get('branch') or 'all'):issues.append('entities')
    if meta.get('category')!=scope.get('category') and name!='forecast7_categories':issues.append('category')
    if meta.get('location_type')!=scope.get('location_type') and not pair and name!='inventory6_warehouse':issues.append('location_type')
    if name=='sales4_trends' and meta.get('grain')!=request['parameters'].get('grain','monthly'):issues.append('aggregation')
    if request.get('ranking_metrics') and meta.get('metric') is not None and meta['metric'] not in request['ranking_metrics']:issues.append('ranking_axis')
    if (request.get('intent')=='rank' or request.get('ranking_metrics')) and meta.get('metric') in request.get('metrics',[]) and request.get('aggregation') in ('product','category','locations'):
        values=[row.get(meta['metric']) for row in rows]
        if all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in values):
            if values!=sorted(values,reverse=not request['parameters'].get('ascending',False)):issues.append('ranking_order')
    if scope.get('branch') and name!='inventory6_warehouse':
        if any(row.get(k) not in (None,scope['branch']) for row in rows for k in ('branch_id','location_id')):issues.append('entities')
    for row in rows:
        values=[row[k] for k in ('location_a','location_b','current','previous','absolute_change','percentage_change') if k in row] if 'metric' in row else [row[k] for k in request['metrics'] if k in row]
        if name=='inventory6_pair':values.extend(row[k] for metric in request['metrics'] for k in (metric+'_a',metric+'_b') if k in row)
        if any(v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)) for v in values):issues.append('metric_value')
    if (name.startswith('inventory6_') or name=='category_risk_sales') and meta.get('snapshot'):
        month=date.fromisoformat(meta['snapshot']+'-01')
        snapshot_end=resolved.get('temporal',{}).get('snapshot_as_of') or expected_end
        if month.replace(day=monthrange(month.year,month.month)[1])>date.fromisoformat(snapshot_end):issues.append('snapshot')
    if name.startswith('forecast7_') and meta.get('horizon')!=resolved.get('horizon'):issues.append('horizon')
    if name in ('forecast7_values','forecast7_accuracy'):
        target,unit=('units','units') if scope.get('category') else ('revenue','EGP')
        if meta.get('target')!=target or meta.get('unit')!=unit:issues.append('forecast_target')
        if name=='forecast7_values' and rows and resolved.get('forecast_months') and not set(resolved['forecast_months'])<=set(r.get('month') for r in rows):issues.append('forecast_months')
        if meta.get('state')!='unavailable' and name=='forecast7_values':
            if len(rows)!=resolved.get('horizon'):issues.append('forecast_months')
            if any(isinstance(r.get('central'),bool) or not isinstance(r.get('central'),(int,float)) or not math.isfinite(r['central']) or r['central']<0 for r in rows):issues.append('forecast_value')
        if meta.get('state')!='unavailable' and name=='forecast7_accuracy':
            for key in ('test_wape_pct','baseline_test_wape_pct'):
                value=meta.get(key)
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:issues.append('forecast_evaluation')
    if name.startswith('forecast7_') and meta.get('forecast_start') and meta.get('forecast_end'):
        def forecast_date(value):
            text=str(value)[:10]
            return date.fromisoformat(text+'-01' if len(text)==7 else text)
        for row in rows:
            if 'month' in row:
                try:
                    month=forecast_date(row['month'])
                    if not forecast_date(meta['forecast_start'])<=month<=forecast_date(meta['forecast_end']):issues.append('dates')
                except (ValueError,TypeError):issues.append('dates')
    return sorted(set(issues))

def complete_requested_selection(report,resolved):
    request=resolved.get('request',{});meta=report.get('meta',{});rows=report.get('data',[])
    limit=request.get('parameters',{}).get('limit');metric=meta.get('metric');total=meta.get('total_rows')
    if meta.get('selection_kind')!='requested_top_k' or metric not in request.get('ranking_metrics',[]):return False
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=20 or not isinstance(total,int) or isinstance(total,bool):return False
    if not rows or len(rows)!=min(limit,total) or output_issues(report,resolved):return False
    key={'product':'product_id','category':'category','locations':'branch_id'}.get(request.get('aggregation'))
    if not key or any(row.get(key) is None for row in rows) or len({row[key] for row in rows})!=len(rows):return False
    return all(isinstance(row.get(metric),(int,float)) and not isinstance(row[metric],bool) and math.isfinite(row[metric]) for row in rows)

def missing_metrics(reports,resolved):
    request=resolved.get('request',{});covered=set()
    for report in reports:
        if output_issues(report,resolved):continue
        for row in report.get('data',[]):
            if 'metric' in row:
                keys=('location_a','location_b') if 'location_a' in row else ('current','previous')
                if all(isinstance(row.get(k),(int,float)) and not isinstance(row[k],bool) and math.isfinite(row[k]) for k in keys):covered.add(row['metric'])
                if row.get('metric')=='sales' and isinstance(row.get('percentage_change'),(int,float)) and math.isfinite(row['percentage_change']):covered.add('growth_pct')
            else:
                covered.update(k for k,v in row.items() if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v))
                for metric in STOCK:
                    if row.get(metric+'_a') is not None and row.get(metric+'_b') is not None:covered.add(metric)
                if row.get('max_recorded_risk') is not None:covered.add('recorded_risk')
    if len(resolved.get('product_ids',[]))==2 and request.get('intent')=='compare':
        for metric in request.get('metrics',[]):
            by_id={row.get('product_id'):row.get(metric) for report in reports for row in report['data'] if row.get('product_id') in resolved['product_ids']}
            if not all(isinstance(by_id.get(p),(int,float)) and not isinstance(by_id[p],bool) and math.isfinite(by_id[p]) for p in resolved['product_ids']):covered.discard(metric)
    return sorted(set(request.get('metrics',[]))-covered) if not request.get('forecast') else []
