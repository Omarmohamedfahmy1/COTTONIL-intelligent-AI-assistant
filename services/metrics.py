"""Authoritative KPIs. Public signatures retain the MVP's analytics API.

Orders contribute once. Category revenue is matching LINE revenue; order/customer
counts describe orders containing that category and are not additive by category.
See docs/KPI_DICTIONARY.md for dates, scope and deliberately unavailable metrics.
"""
from datetime import date, timedelta
import numpy as np
import pandas as pd
from db.connection import read
from services.filters import filters, predicate, previous_period, complete_month_bounds, iso_date

REFUND_LIMITATION = ('Recorded refunds have unverified tax/discount basis; refund-adjusted '
                     'revenue and return-adjusted gross profit are unavailable.')


def metadata():
    row = read('SELECT MIN(order_date) lo, MAX(order_date) hi FROM sales_orders').iloc[0]
    return tuple(date.fromisoformat(v) if v else None for v in (row.lo, row.hi))


def branches():
    return read('SELECT branch_id,branch_name_ar,governorate_ar,retail_location_type FROM branches ORDER BY branch_id')


def where(start, end, branch=None, alias=''):
    """Compatibility helper; all new query scopes use the same validated Filters."""
    sql, params = predicate(filters(start, end, branch), alias or 'o')
    return (sql.replace('o.', '') if not alias else sql), params


def ratio(numerator, denominator, scale=1):
    if isinstance(denominator, pd.Series):
        return (scale * pd.to_numeric(numerator) / pd.to_numeric(denominator).replace(0, np.nan)).fillna(0)
    return scale * numerator / denominator if denominator else 0.0


def growth_percent(current, previous, comparable=True):
    return 100 * (current-previous) / previous if comparable and previous > 0 else None


def _orders(scope):
    """Return one row per matching order with its scoped revenue contribution."""
    condition, params = predicate(scope, 'o')
    columns = 'o.sales_order_id,o.order_date,o.branch_id,o.customer_id,o.sales_channel'
    if scope.category is None:
        return f'SELECT {columns},o.net_before_tax_EGP sales FROM sales_orders o WHERE {condition}', params
    line_where, line_params = predicate(scope, 'i', include_category=True)
    # Aggregate BEFORE joining the header; mixed-category orders contribute only
    # their selected category's line sales, while counts remain one per order.
    sql = f'''SELECT {columns},matched.sales FROM sales_orders o JOIN (
        SELECT i.sales_order_id,SUM(i.net_line_EGP) sales FROM sales_order_items i
        WHERE {line_where} GROUP BY i.sales_order_id
        ) matched ON matched.sales_order_id=o.sales_order_id WHERE {condition}'''
    return sql, line_params + params


def _order_stats(scope):
    source, params = _orders(scope)
    return read(f'''WITH scoped AS ({source}) SELECT COUNT(*) orders,
        COUNT(DISTINCT customer_id) customers,COUNT(DISTINCT branch_id) branches,
        COALESCE(SUM(sales),0) sales,COUNT(*)-COUNT(customer_id) anonymous_orders
        FROM scoped''', params).iloc[0].to_dict()


def _refunds(scope):
    conditions, params = ['r.return_date BETWEEN ? AND ?'], [scope.start, scope.end]
    if scope.branch:
        conditions.append('o.branch_id=?')
        params.append(scope.branch)
    if scope.location_type:
        conditions.append('EXISTS (SELECT 1 FROM branches b WHERE b.branch_id=o.branch_id AND b.retail_location_type=?)')
        params.append(scope.location_type)
    join = ''
    if scope.category:
        join = ' JOIN sales_order_items i ON i.sales_line_id=r.sales_line_id'
        conditions.append('EXISTS (SELECT 1 FROM products_catalog p WHERE p.product_id=i.product_id AND p.category_en=?)')
        params.append(scope.category)
    return float(read(f'''SELECT COALESCE(SUM(r.refund_amount_EGP),0) amount
        FROM sales_returns r JOIN sales_orders o ON o.sales_order_id=r.sales_order_id
        {join} WHERE {' AND '.join(conditions)}''', params).iloc[0, 0])


def overview(start, end, branch=None, *, location_type=None, category=None):
    scope = filters(start, end, branch, location_type, category)
    result = _order_stats(scope)
    condition, params = predicate(scope, 'i', include_category=True)
    line = read(f'''SELECT COALESCE(SUM(margin_EGP),0) gross_profit,
        COALESCE(SUM(quantity),0) units FROM sales_order_items i WHERE {condition}''', params).iloc[0]
    result.update(line.to_dict())
    for key in ('orders', 'customers', 'branches', 'anonymous_orders', 'units'):
        result[key] = int(result[key])
    result['refunds'] = _refunds(scope)
    result['refund_adjusted_sales'] = None  # No verified compatible refund tax/discount basis.
    result['aov'] = ratio(result['sales'], result['orders'])
    result['gross_margin_pct'] = ratio(result['gross_profit'], result['sales'], 100)
    return result


def registered_customers(as_of):
    """Company-wide registered master customers as of date, independent of purchases."""
    return int(read('SELECT COUNT(*) FROM v_customers_normalized WHERE joined_date_iso<=?', (iso_date(as_of),)).iloc[0, 0])


def _period_covered(start, end):
    first, last = metadata()
    return bool(first and last and first.isoformat() <= start <= end <= last.isoformat())


def sales_growth(start, end, branch=None, *, location_type=None, category=None):
    scope = filters(start, end, branch, location_type, category)
    previous_start, previous_end = previous_period(scope.start, scope.end)
    previous = filters(previous_start, previous_end, branch, location_type, category)
    current_sales, previous_sales = _order_stats(scope)['sales'], _order_stats(previous)['sales']
    covered = _period_covered(scope.start, scope.end) and _period_covered(previous_start, previous_end)
    return {'sales': current_sales, 'previous_sales': previous_sales,
            'previous_start': previous_start, 'previous_end': previous_end,
            'comparable_coverage': covered,
            'growth_pct': growth_percent(current_sales, previous_sales, covered)}


def sales_monthly(start, end, branch=None, *, location_type=None, category=None):
    scope = filters(start, end, branch, location_type, category)
    source, params = _orders(scope)
    frame = read(f'''WITH scoped AS ({source}) SELECT substr(order_date,1,7) month,
        ROUND(SUM(sales),2) sales,COUNT(*) orders,COUNT(DISTINCT customer_id) customers
        FROM scoped GROUP BY 1 ORDER BY 1''', params)
    first, last = metadata()
    bounds = complete_month_bounds(max(scope.start, first.isoformat()), min(scope.end, last.isoformat())) if first else None
    frame['is_complete_month'] = frame.month.map(lambda m: bool(bounds and bounds[0][:7] <= m <= bounds[1][:7])).astype(bool)
    return frame


def sales_channel(start, end, branch=None, *, location_type=None, category=None):
    source, params = _orders(filters(start, end, branch, location_type, category))
    return read(f'''WITH scoped AS ({source}) SELECT sales_channel channel,COUNT(*) orders,
        ROUND(SUM(sales),2) sales FROM scoped GROUP BY 1 ORDER BY sales DESC''', params)


def seasonality(start, end, branch=None, *, location_type=None, category=None):
    frame = sales_monthly(start, end, branch, location_type=location_type, category=category)
    frame = frame[frame.is_complete_month].copy()
    if frame.empty:
        return pd.DataFrame(columns=['calendar_month', 'avg_sales', 'observed_months'])
    frame['calendar_month'] = frame.month.str[-2:].astype(int)
    return frame.groupby('calendar_month', as_index=False).agg(avg_sales=('sales', 'mean'), observed_months=('month', 'count'))


def _profitability(scope, by_product):
    condition, params = predicate(scope, 'i', include_category=True)
    columns = 'i.product_id,p.product_name_ar product,p.category_en category,' if by_product else 'p.category_en category,'
    group = 'i.product_id,p.product_name_ar,p.category_en' if by_product else 'p.category_en'
    frame = read(f'''SELECT {columns} SUM(i.quantity) units,ROUND(SUM(i.net_line_EGP),2) sales,
        ROUND(SUM(i.margin_EGP),2) gross_profit FROM sales_order_items i
        JOIN products_catalog p ON p.product_id=i.product_id WHERE {condition}
        GROUP BY {group} ORDER BY gross_profit DESC''', params)
    frame['gross_margin_pct'] = ratio(frame.gross_profit, frame.sales, 100).round(2)
    return frame


def product_performance(start, end, branch=None, sort='gross_profit', limit=100, *, location_type=None, category=None):
    if sort not in {'gross_profit', 'sales', 'units', 'gross_margin_pct'}:
        raise ValueError('Unsupported product ranking metric')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10000:
        raise ValueError('Product limit must be between 1 and 10000')
    frame = _profitability(filters(start, end, branch, location_type, category), True)
    return frame.sort_values(sort, ascending=False).head(limit).reset_index(drop=True)


def category_performance(start, end, branch=None, *, location_type=None, category=None):
    return _profitability(filters(start, end, branch, location_type, category), False)


def branch_performance(start, end, selected=None, *, branch=None, location_type=None, category=None):
    # Legacy selected is a UI highlight, not a filter. The explicit branch keyword
    # is available to filtered callers; the existing benchmark page keeps all locations.
    if selected is not None:
        filters(start, end, selected)
    scope = filters(start, end, branch, location_type, category)
    source, params = _orders(scope)
    frame = read(f'''WITH scoped AS ({source}) SELECT branch_id,COUNT(*) orders,
        SUM(sales) sales,COUNT(DISTINCT customer_id) customers FROM scoped GROUP BY branch_id''', params)
    condition, params = predicate(scope, 'i', include_category=True)
    profits = read(f'SELECT branch_id,SUM(margin_EGP) gross_profit FROM sales_order_items i WHERE {condition} GROUP BY branch_id', params)
    ps, pe = previous_period(scope.start, scope.end)
    source, params = _orders(filters(ps, pe, branch, location_type, category))
    previous = read(f'WITH scoped AS ({source}) SELECT branch_id,SUM(sales) previous_sales FROM scoped GROUP BY branch_id', params)
    names = branches().rename(columns={'branch_name_ar':'branch','governorate_ar':'governorate'})
    staff = read('SELECT branch_id,COUNT(*) listed_employees FROM employees GROUP BY branch_id')
    frame = frame.merge(profits, on='branch_id', how='left', validate='one_to_one').merge(previous, on='branch_id', how='left', validate='one_to_one')
    frame = frame.merge(names, on='branch_id', how='left', validate='one_to_one').merge(staff, on='branch_id', how='left', validate='one_to_one')
    for column in ('gross_profit', 'previous_sales', 'listed_employees'):
        frame[column] = pd.to_numeric(frame[column]).fillna(0)
    for column in ('orders','sales'):
        frame[column] = pd.to_numeric(frame[column])
    frame['aov'] = ratio(frame.sales, frame.orders)
    frame['gross_margin_pct'] = ratio(frame.gross_profit, frame.sales, 100)
    covered = _period_covered(scope.start, scope.end) and _period_covered(ps, pe)
    frame['growth_pct'] = pd.Series([growth_percent(c, p, covered) for c, p in zip(frame.sales, frame.previous_sales)], index=frame.index, dtype=float)
    frame['orders_per_listed_employee'] = frame.orders / frame.listed_employees.replace(0, np.nan)
    return frame.sort_values('sales', ascending=False).reset_index(drop=True)


def inventory_snapshot(end, branch=None, *, location_type=None, category=None):
    end = iso_date(end)
    start = (date.fromisoformat(end)-timedelta(days=89)).isoformat()
    scope = filters(start, end, branch, location_type, category)
    conditions, params = ["s.stock_location_type='Branch'", 's.year_month<=?'], [end[:7]]
    if branch:
        conditions.append('s.stock_location_id=?')
        params.append(branch)
    if location_type:
        conditions.append('EXISTS (SELECT 1 FROM branches b WHERE b.branch_id=s.stock_location_id AND b.retail_location_type=?)')
        params.append(location_type)
    if category:
        conditions.append('s.product_category=?')
        params.append(category)
    condition = ' AND '.join(conditions)
    month = read(f'SELECT MAX(year_month) FROM monthly_stock s WHERE {condition}', params).iloc[0, 0]
    columns = ['category','stock_units','stock_value','risk_score','sold_90d','daily_run_rate','approx_cover_days','suggested_30d_replenishment','risk_label']
    if month is None:
        return None, pd.DataFrame(columns=columns)
    inv = read(f'''SELECT product_category category,SUM(closing_units) stock_units,
        ROUND(SUM(closing_stock_value_EGP),2) stock_value,ROUND(AVG(stockout_risk_score),3) risk_score
        FROM monthly_stock s WHERE {condition} AND s.year_month=? GROUP BY product_category''', tuple(params)+(month,))
    line_where, params = predicate(scope, 'i', include_category=True)
    sold = read(f'''SELECT p.category_en category,SUM(quantity) sold_90d FROM sales_order_items i
        JOIN products_catalog p ON p.product_id=i.product_id WHERE {line_where} GROUP BY p.category_en''', params)
    inv = inv.merge(sold, on='category', how='left', validate='one_to_one')
    inv['sold_90d'] = pd.to_numeric(inv.sold_90d).fillna(0)
    inv['daily_run_rate'] = inv.sold_90d/90
    inv['approx_cover_days'] = inv.stock_units / inv.daily_run_rate.replace(0, np.nan)
    inv['suggested_30d_replenishment'] = np.maximum(0, np.ceil(inv.daily_run_rate*30-inv.stock_units)).astype(int)
    inv['risk_label'] = np.select([inv.risk_score>=.7, inv.risk_score>=.4], ['High','Medium'], default='Low')
    return month, inv.sort_values(['risk_score','approx_cover_days'], ascending=[False,True]).reset_index(drop=True)


def inventory_summary(frame):
    """Totals of an already scoped single-snapshot category frame; never months/SKUs."""
    return {'stock_units': int(frame.stock_units.sum()),
            'stock_value': float(frame.stock_value.sum()),
            'high_risk_categories': int(frame.risk_label.eq('High').sum()),
            'estimated_30d_replenishment_units': int(frame.suggested_30d_replenishment.sum())}


def company_sales_fully_observed_months(branch=None, category=None, *, location_type=None):
    first, last = metadata()
    if first is None:
        return pd.DataFrame(columns=['month','value'])
    bounds = complete_month_bounds(first, last)
    if not bounds:
        return pd.DataFrame(columns=['month','value'])
    scope = filters(*bounds, branch, location_type, category)
    if category:
        condition, params = predicate(scope, 'i', include_category=True)
        frame = read(f'''SELECT substr(order_date,1,7) month,SUM(quantity) value
            FROM sales_order_items i WHERE {condition} GROUP BY 1 ORDER BY 1''', params)
    else:
        source, params = _orders(scope)
        frame = read(f'WITH scoped AS ({source}) SELECT substr(order_date,1,7) month,SUM(sales) value FROM scoped GROUP BY 1 ORDER BY 1', params)
    months = pd.period_range(bounds[0][:7], bounds[1][:7], freq='M').astype(str)
    return pd.DataFrame({'month':months}).merge(frame, on='month', how='left', validate='one_to_one').fillna({'value':0})


def customer_activity(start, end, branch=None, *, location_type=None, category=None):
    values = _order_stats(filters(start, end, branch, location_type, category))
    return {k: int(values[k]) for k in ('customers','anonymous_orders','orders')}
