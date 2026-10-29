"""Phase 5 aggregate profitability; financial definitions stay in metrics.py.

No writes, arbitrary SQL, expense allocations or refund adjustments. Contributions
use company GP for the SAME dates, irrespective of the selected filters.
"""
from dataclasses import dataclass, asdict, replace
import math
import pandas as pd
from services import metrics as kpi, sales_branch as sb
from services.filters import filters, previous_period

RANKS = ('gross_profit', 'sales', 'gross_margin_pct', 'units')


def nonnegative(value):
    if isinstance(value, bool):
        raise ValueError('A finite nonnegative number is required')
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError('A finite nonnegative number is required') from None
    if not math.isfinite(value) or value < 0:
        raise ValueError('A finite nonnegative number is required')
    return value


@dataclass(frozen=True)
class ScreeningRules:
    high_revenue: float = 100000
    high_units: float = 500
    low_margin: float = 30
    high_margin: float = 45
    lower_units: float = 100
    high_contribution: float = 10

    def __post_init__(self):
        for key, value in asdict(self).items():
            object.__setattr__(self, key, nonnegative(value))
        if self.low_margin > self.high_margin or self.lower_units > self.high_units:
            raise ValueError('Screening thresholds overlap inconsistently')


def enrich(frame, company_gp, scoped_gp):
    """Weighted ratio of approved aggregate totals; zero denominators unavailable."""
    frame = frame.copy()
    frame['gross_margin_pct'] = kpi.ratio(frame.gross_profit, frame.sales, 100).where(frame.sales.ne(0))
    frame['company_gp_share_pct'] = kpi.ratio(frame.gross_profit, company_gp, 100) if company_gp else None
    frame['scoped_gp_share_pct'] = kpi.ratio(frame.gross_profit, scoped_gp, 100) if scoped_gp else None
    return frame


def rank_products(frame, metric='gross_profit', ascending=False, min_revenue=0, min_units=0):
    if metric not in RANKS or not isinstance(ascending, bool):
        raise ValueError('Unsupported product ranking')
    revenue, units = nonnegative(min_revenue), nonnegative(min_units)
    eligible = frame.loc[frame.sales.ge(revenue) & frame.units.ge(units)]
    return eligible.dropna(subset=[metric]).sort_values([metric, 'product_id'], ascending=[ascending, True]).reset_index(drop=True)


def screen_products(frame, rules=None):
    rules = rules or ScreeningRules()
    active = frame.loc[frame.has_recorded_lines & frame.sales.gt(0)]
    return {
        'p5_high_revenue_low': active.loc[active.sales.ge(rules.high_revenue) & active.gross_margin_pct.lt(rules.low_margin)],
        'p5_high_volume_low': active.loc[active.units.ge(rules.high_units) & active.gross_margin_pct.lt(rules.low_margin)],
        'p5_lower_volume_high': active.loc[active.units.lt(rules.lower_units) & active.gross_margin_pct.ge(rules.high_margin)],
        'p5_high_contributors': frame.loc[frame.has_recorded_lines & frame.gross_profit.gt(0) & frame.company_gp_share_pct.ge(rules.high_contribution)],
    }


def changes(current, previous, key, comparable):
    """Outer merge retains ceased sales; percentage change needs positive prior GP."""
    cols = [key, 'sales', 'gross_profit']
    frame = current[cols].merge(previous[cols].rename(columns={'sales':'previous_sales', 'gross_profit':'previous_gross_profit'}),
                                on=key, how='outer', validate='one_to_one')
    for col in ('sales', 'gross_profit', 'previous_sales', 'previous_gross_profit'):
        frame[col] = pd.to_numeric(frame[col]).fillna(0)
    if not comparable:
        frame[['previous_sales', 'previous_gross_profit']] = float('nan')
    frame['gp_change'] = frame.gross_profit - frame.previous_gross_profit
    frame['gp_growth_pct'] = pd.Series([kpi.growth_percent(c, p, comparable) for c, p in zip(frame.gross_profit, frame.previous_gross_profit)], dtype=float)
    frame['comparable_coverage'] = comparable
    return frame


def products(scope, company_gp=None):
    if company_gp is None:
        company_gp = kpi.overview(scope.start, scope.end)['gross_profit']
    frame = sb.product_roster(scope)
    return enrich(frame, company_gp, frame.gross_profit.sum())


def locations(scope):
    frame = sb.location_roster(scope.start, scope.end, location_type=scope.location_type, category=scope.category)
    if scope.branch:
        frame = frame.loc[frame.branch_id.eq(scope.branch)].copy()
    return frame


def dashboard(start, end, branch=None, *, location_type=None, category=None):
    scope = filters(start, end, branch, location_type, category)
    result = sb.period_summary(scope)
    company_gp = kpi.overview(scope.start, scope.end)['gross_profit']
    scoped_gp = result['current']['gross_profit']
    result['current']['company_gp_share_pct'] = kpi.ratio(scoped_gp, company_gp, 100) if company_gp else None
    result['company_gross_profit'] = company_gp
    result['products'] = products(scope, company_gp)
    result['categories'] = enrich(kpi.category_performance(**sb.args(scope)), company_gp, scoped_gp)
    result['locations'] = enrich(locations(scope), company_gp, scoped_gp)
    monthly = sb.sales_trends(**sb.args(scope), grain='monthly')
    result['monthly'] = enrich(monthly, company_gp, scoped_gp)
    result['category_monthly'] = enrich(sb.category_months(scope), company_gp, scoped_gp)
    ps, pe = previous_period(scope.start, scope.end)
    prior = replace(scope, start=ps, end=pe)
    comparable = result['growth']['comparable_coverage']
    result['category_changes'] = changes(result['categories'], kpi.category_performance(**sb.args(prior)), 'category', comparable)
    # Approved branch KPI GP is line-based; master roster preserves zero-current locations.
    result['location_changes'] = changes(result['locations'], locations(prior), 'branch_id', comparable)
    result['declining_categories'] = result['category_changes'].loc[result['category_changes'].gp_change.lt(0)].copy()
    result['net_profit'] = result['return_adjusted_gross_profit'] = None
    return result


def leaders(frame):
    """Show independently ranked revenue and GP leaders, without causal claims."""
    rows = []
    for metric in ('sales', 'gross_profit'):
        if frame.empty:
            continue
        row = rank_products(frame, metric).iloc[0].to_dict()
        row['rank_basis'] = metric
        rows.append(row)
    return pd.DataFrame(rows)
