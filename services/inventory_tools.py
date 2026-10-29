"""Fixed aggregate local inventory allowlist; no SQL or free-form execution."""
import re
from services import inventory as inv,metrics as kpi,sales_branch as sb
from services.filters import filters
from services.sales_branch_tools import records,resolve_period

ALLOWED=('inventory6_stock','inventory6_risk','inventory6_cover','inventory6_replenishment','inventory6_warehouse','inventory6_transfers','inventory6_pair')
ROW_COLUMNS=['location_id','location','retail_location_type','category','stock_units','recorded_risk','sold_units','daily_units','cover_days','estimated_replenishment']


def answer_readonly(name,context,params=None):
    if name not in ALLOWED:raise ValueError('Unsupported inventory tool')
    params=params or {};scope=filters(**context);limit=params.get('limit',20)
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=20:raise ValueError('Limit must be 1..20')
    planning=inv.Planning(**params.get('planning',{}))
    meta=dict(tool=name,period=f'{scope.start} to {scope.end}',branch_id=scope.branch or 'all',location_type=scope.location_type,
        category=scope.category,source='Verified monthly category balances and recorded transfers; heuristic cover/replenishment, not ML or SKU balances',
        planning=vars(planning),scope_policy='Global filters apply; start date affects transaction/history window, snapshot uses latest completed month <= end date')
    if name=='inventory6_pair':
        a,b=params.get('branch_a'),params.get('branch_b');data=inv.compare_two(scope.start,scope.end,a,b,category=scope.category,planning=planning)
        left=data['rows'].loc[data['rows'].location_id.eq(a),['category','stock_units','stock_value','recorded_risk']]
        right=data['rows'].loc[data['rows'].location_id.eq(b),['category','stock_units','stock_value','recorded_risk']]
        frame=left.merge(right,on='category',how='outer',suffixes=('_a','_b'),validate='one_to_one')
        meta.update(snapshot=data['month'],branch_id='pair',location_type=None,branch_a=a,branch_b=b,
            location_types=records(data['locations'][['branch_id','retail_location_type']]),scope_policy='Explicit pair overrides global branch/type; common dates/category retained, same snapshot required')
    elif name=='inventory6_transfers':
        data=inv.transfer_analysis(**sb.args(scope),warehouse=params.get('warehouse'),status=params.get('status'))
        frame=data['events'].groupby(['month','source_warehouse_id','destination_branch_id','transfer_status'],as_index=False).agg(transfer_count=('transfer_id','count'),transfer_units=('transfer_units','sum'),transport_cost=('transport_cost','sum'))
        meta.update(status=params.get('status'),warehouse_id=params.get('warehouse'),totals=data['summary'],snapshot=None)
    else:
        kind='Warehouse' if name=='inventory6_warehouse' else 'Branch'
        data=inv.dashboard(**sb.args(scope),kind=kind,warehouse=params.get('warehouse'),planning=planning)
        meta.update(snapshot=data['month'],sales_window=data['window'],totals=data['summary'])
        if kind=='Warehouse':meta.update(branch_id='all',location_type=None,warehouse_id=params.get('warehouse'),scope_policy='Explicit warehouse view ignores global branch/type; dates/category retained; no warehouse demand or cover inferred')
        if name=='inventory6_risk':frame=data['categories'].sort_values(['max_recorded_risk','category'],ascending=[False,True])
        elif name=='inventory6_cover':frame=data['low_cover_rows'][ROW_COLUMNS].sort_values(['cover_days','location_id','category'])
        elif name=='inventory6_replenishment':frame=data['rows'].loc[data['rows'].replenishment_attention,ROW_COLUMNS].sort_values(['estimated_replenishment','location_id','category'],ascending=[False,True,True])
        elif scope.branch and kind=='Branch':frame=data['rows'][ROW_COLUMNS]
        else:frame=data['categories']
    meta.update(total_rows=len(frame),rows_returned=min(limit,len(frame)),limit=limit)
    # JSON normalization also turns unavailable numeric estimates into null.
    import json
    meta=json.loads(__import__('pandas').DataFrame([meta]).to_json(orient='records'))[0]
    return dict(meta=meta,data=records(frame.head(limit)),plot=None)


def dispatch(question,context):
    q=question.casefold()
    if not any(w in q for w in ('inventory','stock','warehouse','transfer','replenish','coverage','مخزون','مخازن','مستودع','تحويل','توريد','تغطية')):return None
    try:scope=resolve_period(question,filters(**context))
    except (TypeError,ValueError):return {'clarify':'time_scope_request'}
    ids=[v.upper() for v in re.findall(r'\bBR\d{3}\b',question,re.I)]
    master=kpi.branches()
    if any(v not in set(master.branch_id) for v in ids):return {'clarify':'two_ids_required'}
    for row in master.itertuples():
        name=str(row.branch_name_ar)
        if len(name)>1 and re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',question):
            if master.branch_name_ar.eq(name).sum()!=1:return {'clarify':'two_ids_required'}
            ids.append(row.branch_id)
    ids=list(dict.fromkeys(ids));params={}
    if any(w in q for w in ('compare','قارن','مقارنة بين')):
        if len(ids)!=2:return {'clarify':'two_ids_required'}
        return answer_readonly('inventory6_pair',sb.args(scope),dict(branch_a=ids[0],branch_b=ids[1]))
    if len(ids)>1:return {'clarify':'two_ids_required'}
    if ids:
        try:scope=filters(scope.start,scope.end,ids[0],scope.location_type,scope.category)
        except ValueError:return {'clarify':'invalid_scope'}
    warehouse_ids=re.findall(r'\bWH\d{2}\b',question,re.I)
    if len(warehouse_ids)>1:return {'clarify':'invalid_scope'}
    if warehouse_ids:
        identifier=warehouse_ids[0].upper()
        if identifier not in set(inv.warehouses().warehouse_id):return {'clarify':'invalid_scope'}
        params['warehouse']=identifier
    if any(w in q for w in ('transfer','تحويل','نقل')):
        name='inventory6_transfers'
        for words,status in [(('partially received','مستلم جزئيًا'), 'Partially received'),(('in transit','قيد النقل'),'In transit'),(('completed','مكتمل'),'Completed')]:
            if any(w in q for w in words):params['status']=status;break
    elif any(w in q for w in ('warehouse','مخازن','مستودع')) or warehouse_ids:name='inventory6_warehouse'
    elif any(w in q for w in ('replenish','توريد')):name='inventory6_replenishment'
    elif any(w in q for w in ('cover','low stock','ممكن ميكفيش','قليل','تغطية')):name='inventory6_cover'
    elif any(w in q for w in ('risk','خطر','مخاطر')):name='inventory6_risk'
    else:name='inventory6_stock'
    return answer_readonly(name,sb.args(scope),params)
