"""Closed, aggregate-only Phase 5 local tools. Not a free-form planner."""
from dataclasses import asdict
import re
from services import profitability as profit, sales_branch as sb, metrics as kpi
from services.filters import filters
from services.sales_branch_tools import records, resolve_period

ALLOWED = ('profit5_products', 'profit5_categories', 'profit5_locations',
           'profit5_screening', 'profit5_leaders', 'profit5_pair', 'profit5_trends')
PUBLIC_PRODUCT = ['product_id','product','category','sales','units','gross_profit','gross_margin_pct','company_gp_share_pct']


def answer_readonly(name, context, params=None):
    if name not in ALLOWED:
        raise ValueError('Unsupported profitability tool')
    params = params or {}
    limit = params.get('limit', 8)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError('Limit must be 1..20')
    scope = filters(**context)
    meta = dict(tool=name, period=f'{scope.start} to {scope.end}', branch_id=scope.branch or 'all',
                location_type=scope.location_type, category=scope.category,
                source='Approved KPI foundation; sales before refunds excluding tax; gross profit before returns/OPEX',
                scope_policy='All global filters retained; company GP contribution denominator uses same dates and all company locations/types/categories',
                net_profit_available=False, refund_adjustment_available=False)
    if name == 'profit5_pair':
        result = sb.compare_two(scope.start, scope.end, params.get('branch_a'), params.get('branch_b'), category=scope.category)
        frame = result['table'].loc[result['table'].metric.isin(['sales','gross_profit','gross_margin_pct','units','orders'])]
        meta.update(branch_id='pair', branch_a=params['branch_a'], branch_b=params['branch_b'], location_type=None,
                    location_types=records(result['locations'][['branch_id','retail_location_type']]),
                    scope_policy='Explicit pair overrides global location/type; common dates/category retained')
    elif name in ('profit5_products', 'profit5_screening', 'profit5_leaders'):
        frame = profit.products(scope)
        if params.get('product_ids'):frame=frame.loc[frame.product_id.isin(params['product_ids'])];meta['product_ids']=params['product_ids']
        if name == 'profit5_products':
            metric = params.get('metric', 'gross_profit')
            minimum_sales = profit.nonnegative(params.get('min_revenue', 0))
            minimum_units = profit.nonnegative(params.get('min_units', 0))
            frame = profit.rank_products(frame, metric, params.get('ascending', False), minimum_sales, minimum_units)
            meta['total_rows']=len(frame);frame=frame.head(limit)
            meta.update(metric=metric, min_revenue=minimum_sales, min_units=minimum_units)
        elif name == 'profit5_leaders':
            frame = profit.leaders(frame)
        else:
            rules = profit.ScreeningRules(**params.get('rules', {}))
            frame = profit.screen_products(frame, rules)['p5_high_volume_low'].sort_values(['gross_profit','product_id'], ascending=[False,True])
            meta['total_rows']=len(frame);frame=frame.head(limit)
            meta.update(screen='p5_high_volume_low', rules=asdict(rules))
        frame = frame[[*(['rank_basis'] if 'rank_basis' in frame else []), *PUBLIC_PRODUCT]] if not frame.empty else frame.reindex(columns=PUBLIC_PRODUCT)
    else:
        company = kpi.overview(scope.start, scope.end)['gross_profit']
        if name == 'profit5_categories':
            frame = kpi.category_performance(**sb.args(scope)); key = 'category'
        elif name == 'profit5_locations':
            frame = profit.locations(scope); key = 'branch_id'
        else:
            frame = sb.sales_trends(**sb.args(scope), grain='monthly'); key = 'period'
        frame = profit.enrich(frame, company, frame.gross_profit.sum())
        if name != 'profit5_trends':
            metric = params.get('metric', 'gross_profit')
            if metric not in ('gross_profit','gross_margin_pct','sales'):
                raise ValueError('Unsupported profitability ranking')
            frame = frame.dropna(subset=[metric]).sort_values([metric,key], ascending=[False,True])
            meta['total_rows']=len(frame);frame=frame.head(limit)
            meta['metric'] = metric
        cols = [key, *(['branch','retail_location_type'] if key == 'branch_id' else []),
                'sales','units','gross_profit','gross_margin_pct','company_gp_share_pct']
        if name == 'profit5_trends': cols += ['is_complete_period']
        frame = frame[cols]
    meta['rows_returned'] = len(frame)
    return dict(meta=meta, data=records(frame), plot=None)


def dispatch(question, context):
    q = question.casefold()
    if any(w in q for w in ('net profit','صافي الربح','refund-adjusted','return-adjusted')):
        return {'clarify':'p5_unavailable_financials'}
    if any(w in q for w in ('inventory','stock','مخزون','forecast','predict','توقع','customer','عملاء','عميل')):
        return None
    if not any(w in q for w in ('profit','margin','ربح','ربحي','ربحية','هامش','هوامش','بتكسب')):
        return None
    try:
        scope = resolve_period(question, filters(**context))
    except (ValueError, TypeError):
        return {'clarify':'time_scope_request'}
    master = kpi.branches()
    ids = [v.upper() for v in re.findall(r'\bBR\d{3}\b', question, re.I)]
    if any(v not in set(master.branch_id) for v in ids):
        return {'clarify':'two_ids_required'}
    for row in master.itertuples():
        name = str(row.branch_name_ar)
        if len(name)>1 and re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)', question):
            if master.branch_name_ar.eq(name).sum() != 1:
                return {'clarify':'two_ids_required'}
            ids.append(row.branch_id)
    ids = list(dict.fromkeys(ids))
    product = any(w in q for w in ('product','منتج','منتجات'))
    pair = any(w in q for w in ('compare','قارن','مقارنة بين'))
    if pair and not product:
        if len(ids) != 2: return {'clarify':'two_ids_required'}
        return answer_readonly('profit5_pair', sb.args(scope), dict(branch_a=ids[0], branch_b=ids[1]))
    if len(ids)>1: return {'clarify':'two_ids_required'}
    if ids:
        try: scope = filters(scope.start, scope.end, ids[0], scope.location_type, scope.category)
        except ValueError: return {'clarify':'invalid_scope'}
    metric = 'gross_margin_pct' if any(w in q for w in ('margin','هامش','هوامش')) else 'gross_profit'
    if product:
        if any(w in q for w in ('difference','الفرق','compare')):
            name = 'profit5_leaders'
        elif any(w in q for w in ('low margin','low margins','هامش منخفض','هوامش منخفض','هامش قليل')):
            name = 'profit5_screening'
        else: name = 'profit5_products'
    elif any(w in q for w in ('categor','فئة','فئات')): name = 'profit5_categories'
    elif any(w in q for w in ('branch','location','فرع','فروع','مواقع')) or ids: name = 'profit5_locations'
    elif any(w in q for w in ('trend','monthly','شهري','اتجاه')): name = 'profit5_trends'
    else: return {'clarify':'p5_question_scope'}
    return answer_readonly(name, sb.args(scope), {'metric':metric})
