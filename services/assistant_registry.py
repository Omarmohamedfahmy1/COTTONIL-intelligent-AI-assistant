"""Closed typed adapters to approved analytics. No model-authored SQL or formulas."""
from datetime import date,timedelta
import json,math,re,time
from services import metrics as kpi,executive,sales_branch_tools as sales,profitability_tools as profit,inventory_tools as stock,forecast_tools as forecast,customer_tools as customers
from services.filters import filters,complete_month_bounds
from services.assistant_context import shift_months
from services.assistant_request import compatible,output_issues
from services.assistant_capabilities import CAPABILITIES,description

GROUPS={**{n:'sales' for n in sales.ALLOWED},**{n:'profit' for n in profit.ALLOWED},**{n:'stock' for n in stock.ALLOWED},
        **{n:'forecast' for n in forecast.ALLOWED},**{n:'customers' for n in customers.ALLOWED},
        'company_overview':'executive','executive_comparison':'executive','executive_stock':'executive',
        'category_risk_sales':'aligned','sales_seasonality':'seasonality'}
DESCRIPTIONS={
 'company_overview':'Authoritative revenue (EGP before refunds/ex-tax), gross profit (not net), weighted margin, orders/AOV and identified customers.',
 'executive_comparison':'Current versus equal-length previous period; coverage and undefined growth retained.',
 'executive_stock':'Legacy Executive inventory snapshot/risk, DIFFERENT from Inventory Phase 6; never substitute policies.',
 'category_risk_sales':'Aligned category actual sales/growth with completed-month recorded stock risk. Descriptive, not probability or causality.',
 'sales_seasonality':'Approved average sales by calendar month, using complete observed months only; observed sample counts, not causal seasonality.',
 'two_location_comparison':'Compare exactly two locations, actual sales/orders/profit/AOV/growth over common dates.',
 'profit5_pair':'Compare exactly two locations gross profit and weighted margin; NOT net profit.',
 'inventory6_pair':'Compare two locations monthly category stocks, same completed snapshot; not SKU.',
 'customer8_churn':'Company-wide unreliable churn research, ROC near random, never individual scores or actions.',
 'customer8_value':'Company-wide unreliable next-365-day revenue research, WAPE high, not lifetime value or usable financial plan.',
 'forecast7_values':'Next 1/3/6 months after SOURCE complete month. Company/location revenue EGP OR category demand units, experimental states and uncalibrated bands.',
 'forecast7_accuracy':'Chronological model/baseline test scores and reliability for selected forecast target.',
 'forecast7_categories':'Compare exactly two categories future unit demand, not revenue.',
}
BASE={'start':{'type':'string','description':'Inclusive ISO date; omit to use resolved session dates'},'end':{'type':'string'},
 'branch':{'type':['string','null'],'description':'Known BR ID; omit to retain session'},
 'location_type':{'type':['string','null'],'enum':[None,'Retail branch','Point of sale / reseller']},
 'category':{'type':['string','null'],'description':'Exact English category; omit to retain session'},
 'limit':{'type':'integer','minimum':1,'maximum':20},'branch_a':{'type':'string'},'branch_b':{'type':'string'},
 'metric':{'type':'string','enum':['sales','gross_profit','units','gross_margin_pct','growth_pct','aov','orders']},
 'ascending':{'type':'boolean'},'grain':{'type':'string','enum':['daily','weekly','monthly','yearly']},
 'horizon':{'type':'integer','enum':[1,3,6]},'warehouse':{'type':'string'},
 'status':{'type':'string','enum':['Completed','In transit','Partially received']},
 'month':{'type':'string','description':'YYYY-MM completed snapshot cutoff; returned actual month may be earlier'},
 'categories':{'type':'array','items':{'type':'string'},'minItems':2,'maxItems':2,'uniqueItems':True}}
BASE['product_ids']={'type':'array','items':{'type':'string'},'minItems':1,'maxItems':20,'uniqueItems':True,'description':'Known catalog IDs; omit to retain server-resolved product filter.'}
def fields(name):
    result={'start','end','branch','location_type','category','limit'}
    if name in ('two_location_comparison','profit5_pair','inventory6_pair'):result|={'branch_a','branch_b'}
    if name in ('location_ranking','sales4_products','profit5_products','profit5_categories','profit5_locations'):result|={'metric','ascending'}
    if CAPABILITIES[name].role in ('products','screening','leaders'):result.add('product_ids')
    if name=='sales4_trends':result.add('grain')
    if name.startswith('forecast7_'):result.add('horizon')
    if name=='forecast7_categories':result.add('categories')
    if name.startswith('inventory6_'):result.add('month')
    if name in ('inventory6_warehouse','inventory6_transfers'):result.add('warehouse')
    if name=='inventory6_transfers':result.add('status')
    return result
def schemas(operations=None):
    # One compact dispatcher prevents repeating the same scope schema per operation.
    operations=list(operations) if operations else list(GROUPS)
    if any(n not in GROUPS for n in operations):raise ValueError('Unknown advertised operation')
    parameters=set().union(*(fields(n) for n in operations))
    tool_description='Read-only aggregate Cottonil analytics. Choose operation; omit optional parameters to retain server scope. '+ ' '.join(n+': '+DESCRIPTIONS.get(n,'')+' '+description(n) for n in operations)
    return [dict(type='function',function=dict(name='cottonil_query',description=tool_description,
        parameters=dict(type='object',properties={'operation':{'type':'string','enum':operations},
            'parameters':dict(type='object',properties={k:BASE[k] for k in sorted(parameters)},additionalProperties=False)},required=['operation'],additionalProperties=False)))]

def decode_call(name,args):
    if name!='cottonil_query' or not isinstance(args,dict) or set(args)-{'operation','parameters'} or 'operation' not in args:
        raise ValueError('Unknown tool or invalid dispatcher')
    operation=args['operation'];params=args.get('parameters',{})
    validate(operation,params)
    return operation,params

def validate(name,args):
    if not isinstance(name,str) or name not in GROUPS or not isinstance(args,dict) or set(args)-fields(name):raise ValueError('Invalid tool or parameters')
    for key,value in args.items():
        spec=BASE[key];types=spec['type'] if isinstance(spec['type'],list) else [spec['type']]
        valid=any((typ=='null' and value is None) or (typ=='string' and isinstance(value,str) and len(value)<=100) or
            (typ=='integer' and isinstance(value,int) and not isinstance(value,bool)) or
            (typ=='boolean' and isinstance(value,bool)) or (typ=='array' and isinstance(value,list)) for typ in types)
        if not valid or ('enum' in spec and value not in spec['enum']):raise ValueError('Invalid parameter type/value')
        if key=='metric' and value not in CAPABILITIES[name].metrics:raise ValueError('Metric is not supported by this operation')
        if key=='ascending' and value and name in ('profit5_categories','profit5_locations'):raise ValueError('Only descending category/location profitability rankings are exposed')
        if key=='limit' and not 1<=value<=20:raise ValueError('Invalid row limit')
        if key=='categories' and (len(value)!=2 or any(not isinstance(v,str) or len(v)>100 for v in value) or len(set(value))!=2):raise ValueError('Two categories required')
        if key=='product_ids' and (not 1<=len(value)<=20 or any(not isinstance(v,str) or len(v)>100 for v in value) or len(set(value))!=len(value)):raise ValueError('Known distinct product IDs required')
    return args

# Output columns are compile-time, not accepted from the model or raw DB text.
COMMON=set('sales gross_profit gross_margin_pct orders aov customers branches units anonymous_orders registered_customers growth_pct stock_month stock_units stock_value high_risk_categories estimated_30d_replenishment_units period month category product_id branch_id retail_location_type metric current previous absolute_change percentage_change state is_complete_period is_complete_month recorded_orders location_id recorded_risk sold_units daily_units cover_days estimated_replenishment max_recorded_risk sales_a sales_b gross_profit_a gross_profit_b gross_margin_pct_a gross_margin_pct_b value_a value_b stock_units_a stock_units_b stock_value_a stock_value_b recorded_risk_a recorded_risk_b company_gp_share_pct rank_basis central lower upper forecast_model stage cutoff lead target unit actual predicted mae rmse wape_pct smape_pct bias bias_pct model baseline test_wape_pct validation_wape_pct forecast_vs_recent_pct history_units recent_units forecast_units transfer_count transfer_units transport_cost source_warehouse_id destination_branch_id transfer_status previous_sales partial_boundary growth_state'.split())
CUSTOMER_COLUMNS=set('c8_registered c8_identified c8_anonymous_orders c8_identified_orders c8_total_orders c8_identification_pct c8_identified_revenue c8_anonymous_revenue c8_revenue c8_new c8_returning c8_repeat c8_repeat_rate c8_frequency c8_avg_spend c8_segment c8_customers c8_customer_share c8_revenue_share c8_recency c8_recency_band c8_orders c8_cohort c8_age c8_cohort_size c8_active c8_retention_pct c8_month c8_first c8_second c8_median_days c8_model c8_stage c8_cutoff c8_samples c8_prevalence c8_roc_auc c8_average_precision c8_brier c8_ece c8_precision c8_recall c8_tn c8_fp c8_fn c8_tp c8_threshold c8_prediction_start c8_prediction_end c8_eligible c8_prediction c8_state c8_baseline c8_window c8_repeat_customers c8_repeat_pct'.split())
META=set('tool period branch_id branch_a branch_b category location_type source snapshot origin target unit state reason model baseline horizon forecast_start forecast_end test_start test_end training_start training_end test_wape_pct test_band_coverage_pct uncertainty history_policy scope_policy company_wide selected net_profit_available refund_adjustment_available privacy_k individual_predictions_published previous_period comparable_coverage metric grain warehouse_id status total_rows rows_returned limit'.split())

COMMON.update('location_a location_b mean_recorded_risk high_risk_combinations forecast_total recent_actual_total source_start source_end calendar_month avg_sales observed_months'.split())
COMMON.update('selected_model selected_baseline observations horizon'.split())
COMMON.update('recent_actual_units forecast_start forecast_end'.split())
META.update('baseline_test_wape_pct test_observations'.split())
META.add('product_ids')
META.add('categories')
CUSTOMER_COLUMNS.update('c8_average_spend c8_predicted_revenue c8_observed c8_median_second_days c8_followup_days c8_previous_segment c8_previous_frequency c8_current_frequency c8_frequency_change c8_master_segment c8_days c8_outside_window c8_over'.split())

def execute(name,args,resolved):
    if not compatible(name,resolved):raise ValueError('Tool does not cover the resolved aggregation/entities')
    started=time.perf_counter();args=validate(name,args);scope=dict(resolved['scope']);scope.update({k:v for k,v in args.items() if k in ('start','end','branch','location_type','category')})
    if any(args[k]!=resolved['scope'].get(k) for k in ('start','end','branch','location_type','category') if k in args):
        raise ValueError('Use the server-resolved scope; clarify overrides with user')
    params={k:v for k,v in args.items() if k not in scope};limit=args.get('limit',20 if name=='inventory6_pair' else 12)
    ranking=resolved.get('request',{}).get('ranking_metrics',[])
    if ranking and 'metric' in fields(name):
        if args.get('metric') is not None and args['metric'] not in ranking:raise ValueError('Metric is a displayed measure, not a ranking axis')
        if len(ranking)==1:params.setdefault('metric',ranking[0])
    products=resolved.get('product_ids',[])
    if 'product_ids' in args and args['product_ids']!=products:raise ValueError('Use server-resolved products')
    if products and GROUPS[name]!='customers':
        if 'product_ids' not in fields(name):raise ValueError('Operation cannot filter products')
        params['product_ids']=products;limit=max(limit,len(products));params['limit']=limit
    requested=resolved.get('request',{}).get('metrics',[])
    if 'metric' in args and requested and args['metric'] not in requested:raise ValueError('Metric differs from resolved request')
    if len(requested)==1 and 'metric' in fields(name):params.setdefault('metric',requested[0])
    for field,value in resolved.get('request',{}).get('parameters',{}).items():
        if field in fields(name):
            if field in args and args[field]!=value:raise ValueError('Parameter differs from resolved request')
            params.setdefault(field,value)
    if 'limit' in resolved.get('request',{}).get('parameters',{}):
        limit=max(len(products),resolved['request']['parameters']['limit']);params['limit']=limit
    if 'month' in args:
        if not re.fullmatch(r'\d{4}-\d{2}',args['month']):raise ValueError('Invalid snapshot month')
        month=date.fromisoformat(args['month']+'-01');scope['end']=str(shift_months(month,1)-timedelta(days=1));params.pop('month')
    filters(**scope)
    if name.endswith('_pair') or name=='two_location_comparison':
        pair=[params.get('branch_a'),params.get('branch_b')]
        if pair==[None,None]:pair=resolved.get('pair',[])
        if len(pair)!=2 or pair[0]==pair[1] or None in pair:raise ValueError('Two distinct locations required')
        if pair!=resolved.get('pair'):raise ValueError('Use the explicitly resolved pair')
        for identifier in pair:filters(scope['start'],scope['end'],identifier)
        params.update(branch_a=pair[0],branch_b=pair[1])
    if 'warehouse' in params:
        from services.inventory import warehouses
        if params['warehouse'] not in set(warehouses().warehouse_id):raise ValueError('Unknown warehouse')
        if params['warehouse']!=resolved.get('warehouse'):raise ValueError('Use the explicitly resolved warehouse')
    if name in ('inventory6_warehouse','inventory6_transfers') and resolved.get('warehouse'):params.setdefault('warehouse',resolved['warehouse'])
    if name=='forecast7_categories':
        if 'categories' not in params:params['categories']=resolved.get('categories',[])
        if params['categories']!=resolved.get('categories') or len(params['categories'])!=2:raise ValueError('Use two explicitly resolved categories')
    if name.startswith('forecast7_'):
        if 'horizon' in params and params['horizon']!=resolved.get('horizon',3):raise ValueError('Use the server-resolved forecast horizon')
        params.setdefault('horizon',resolved.get('horizon',3))
    group=GROUPS[name]
    snapshot_end=resolved.get('temporal',{}).get('snapshot_as_of')
    if group=='stock' and snapshot_end and name!='inventory6_transfers':
        scope.update(start=min(scope['start'],snapshot_end),end=snapshot_end)
    if group=='customers':
        # Fixed company window across every Phase 9 turn/session: prevents overlapping
        # fine-scope customer queries, not a claim of formal differential privacy.
        first,last=kpi.metadata();bounds=complete_month_bounds(first,last);end=date.fromisoformat(bounds[1])
        scope=dict(start=str(shift_months(end.replace(day=1),-11)),end=str(end),branch=None,location_type=None,category=None)
        result=customers.answer_readonly(name,scope)
        result['meta']['scope_policy']='Phase 9 privacy restriction: fixed latest complete 12 months, company-wide; filters overridden. Research uses its own mature historical schedule.'
    elif group in ('sales','profit','stock','forecast'):
        result={'sales':sales,'profit':profit,'stock':stock,'forecast':forecast}[group].answer_readonly(name,scope,params)
    elif group=='seasonality':
        result=dict(meta=dict(tool=name,period=f"{scope['start']} to {scope['end']}",branch_id=scope['branch'] or 'all',category=scope['category'],location_type=scope['location_type'],source='Approved metrics.seasonality',scope_policy='Only complete observed months; per-calendar-month averages with observed month counts, no causal inference'),data=sales.records(kpi.seasonality(**scope)),plot=None)
    elif group=='executive':
        result=executive.assistant_summary(scope)
        if name=='executive_comparison':result['data']=sales.records(executive.summary(**scope)['comparison'])
        if name=='executive_stock':result['data']=[{k:v for k,v in result['data'][0].items() if k in ('stock_month','stock_units','stock_value','high_risk_categories','estimated_30d_replenishment_units')}]
        result['meta']['tool']=name
        result['meta']['scope_policy']='Executive legacy stock latest recorded <= end; legacy risk/30-day heuristic. Financial definitions remain authoritative.'
    else:
        import pandas as pd
        data=executive.dashboard(**scope)
        stock_scope=dict(scope)
        if snapshot_end:stock_scope.update(start=min(stock_scope['start'],snapshot_end),end=snapshot_end)
        risks=stock.answer_readonly('inventory6_risk',stock_scope,dict(limit=20))
        frame=data['category_changes'].merge(pd.DataFrame(risks['data']),on='category',how='left',validate='one_to_one',suffixes=('','_inventory'))
        if resolved.get('categories'):frame=frame.loc[frame.category.isin(resolved['categories'])]
        result=dict(meta=dict(tool=name,period=f"{scope['start']} to {scope['end']}",branch_id=scope['branch'] or 'all',category=scope['category'],location_type=scope['location_type'],snapshot=risks['meta']['snapshot'],source='Executive approved comparable category changes + Phase 6 completed stock categories',scope_policy='Category grain; transaction window and completed snapshot explicitly distinct; no stockout probability or causal claim'),data=sales.records(frame),plot=None)
    original=result['data'];rows=[]
    for row in original[:limit]:
        clean={k:v for k,v in row.items() if k in COMMON|CUSTOMER_COLUMNS and not isinstance(v,(list,dict))}
        # Bounded data labels cannot execute or become final-model instructions.
        for k,v in clean.items():
            if isinstance(v,str):clean[k]=re.sub(r'[\x00-\x1f]',' ',v)[:120]
            elif isinstance(v,float) and not math.isfinite(v):clean[k]=None
        if isinstance(clean.get('customers'),(int,float)) and 0<clean['customers']<5:clean['customers']=None
        if clean.get('metric')=='customers':
            small=any(isinstance(clean.get(key),(int,float)) and 0<clean[key]<5 for key in ('location_a','location_b','current','previous'))
            for key in ('location_a','location_b','current','previous'):
                if isinstance(clean.get(key),(int,float)) and 0<clean[key]<5:clean[key]=None
            if small:
                for key in ('absolute_change','percentage_change'):
                    if key in clean:clean[key]=None
        rows.append(clean)
    meta={k:v for k,v in result['meta'].items() if k in META}
    # Keep audited assumptions available locally for evidence review. The model
    # receives a smaller projection below the orchestrator, not these definitions.
    if group=='stock':
        meta['planning']=result['meta'].get('planning')
        meta['sales_window']=result['meta'].get('sales_window')
        meta['definitions']={
            'snapshot':'Latest recorded month with calendar month-end <= selected end; never sum balances across months.',
            'risk':'Recorded location/category score >=0.7; category attention means at least one high-risk row, not mean-category risk or stockout probability.',
            'velocity':'Matching sale-line units / lookback calendar days, ending selected snapshot month-end; require complete source lookback.',
            'cover':'Recorded closing units / daily sales when daily sales >0; otherwise unavailable.',
            'replenishment':'max(0, ceil(daily sales * horizon days - recorded stock)), per location/category; deficits sum without netting another location surplus.',
            'warehouse':'No warehouse demand/cover/replenishment inferred from branch sales.'}
    elif name=='executive_stock':
        meta['definitions']={
            'snapshot':'Legacy latest matching recorded month label <= selected end YYYY-MM; capture timestamp unknown.',
            'risk':'Mean recorded location/category score, rounded to3 decimals; High >=0.7; count High category means.',
            'velocity':'Legacy matching sold_90d /90, through selected end rather than Phase6 snapshot-end coverage policy.',
            'replenishment':'Legacy max(0, ceil(daily run-rate *30 - category-aggregated stock)); not Phase6 summed location deficits.'}
    else:
        meta['definitions']={'revenue':'Approved scoped order/line contributions, ex-tax before refunds.',
            'gross_profit':'Approved sale-line margin sum, before returns/OPEX; not net profit.',
            'gross_margin_pct':'100 * aggregate gross profit / aggregate revenue; not average row margins.',
            'orders':'Distinct matching orders; category counts non-additive.',
            'aov':'Scoped revenue / matching orders; category contribution when filtered.'}
    if name=='category_risk_sales' and resolved.get('categories'):
        meta['categories']=list(resolved['categories']);meta['scope_policy']+='; explicit conversational category set retained'
    total_rows=max(len(original),result['meta'].get('total_rows',len(original)))
    meta.update(tool=name,returned_rows=len(rows),total_rows=total_rows,truncated=total_rows>len(rows),
        source_last_order=resolved['source_end'],last_complete_month=resolved['last_complete_month'],
        classification='experimental research' if name in ('customer8_churn','customer8_value') else 'model forecast' if group=='forecast' else 'recorded + heuristic estimates' if group=='stock' else 'recorded',
        units={'sales':'EGP','gross_profit':'EGP','aov':'EGP','stock_value':'EGP','units':'units','stock_units':'units','gross_margin_pct':'percent','growth_pct':'percent','orders':'orders','customers':'identified purchasers'},
        financial_basis='Ex-tax, before refunds. Gross profit before returns/OPEX; net profit/refund adjustment unavailable.',
        inventory_basis='Monthly category/location; Executive legacy and Phase 6 completed snapshot/risk differ; cover/replenishment are heuristics.',
        model_basis='Forecast bands uncalibrated; churn and customer revenue research unreliable; no individual actions.',elapsed_seconds=time.perf_counter()-started)
    requested_limit=resolved.get('request',{}).get('parameters',{}).get('limit')
    if requested_limit and ranking and meta.get('metric') in ranking and CAPABILITIES[name].role in ('products','categories','locations'):
        meta['selection_kind']='requested_top_k'
    meta['units'].update(c8_predicted_revenue='EGP',c8_revenue='EGP',c8_average_spend='EGP',c8_repeat_rate='percent',c8_roc_auc='ratio',c8_brier='ratio',recorded_risk='recorded score, not stockout probability')
    meta['units'].update(avg_sales='EGP',stock_value_a='EGP',stock_value_b='EGP',stock_units_a='units',stock_units_b='units',location_a='unit of row metric',location_b='unit of row metric')
    if group=='forecast':meta['units'].update({k:meta.get('unit','see target') for k in ('central','lower','upper')})
    graph=None
    if rows:
        x=next((c for c in ('period','month','category','branch_id','product_id') if c in rows[0]),None)
        y=next((c for c in ('sales','gross_profit','stock_units','central','c8_customers') if isinstance(rows[0].get(c),(int,float))),None)
        if x and y:graph=dict(x=x,y=y,type='line' if x in ('month','period') else 'bar')
    payload=dict(meta=meta,data=rows,plot=graph)
    if output_issues(payload,resolved):raise ValueError('Returned evidence does not match resolved scope')
    return payload
