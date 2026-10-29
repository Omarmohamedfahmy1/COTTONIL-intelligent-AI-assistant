"""One validated scope and date policy for all analytics queries."""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from db.connection import read

LOCATION_TYPES = ('Retail branch', 'Point of sale / reseller')


def iso_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Dates must be ISO YYYY-MM-DD or date objects')
    return date.fromisoformat(value).isoformat()


def normalize_source_date(value):
    """Normalize verified source date formats; reject ambiguous/unrecognized formats."""
    for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except (ValueError, TypeError):
            continue
    raise ValueError('Unsupported source date')


@dataclass(frozen=True)
class Filters:
    start: str
    end: str
    branch: str | None = None
    location_type: str | None = None
    category: str | None = None


def filters(start, end, branch=None, location_type=None, category=None):
    start, end = iso_date(start), iso_date(end)
    if start > end:
        raise ValueError('Start date must not be after end date')
    if location_type is not None and location_type not in LOCATION_TYPES:
        raise ValueError('Unknown sales location type')
    if branch is not None:
        if not isinstance(branch, str):
            raise ValueError('Invalid branch ID')
        found = read('SELECT retail_location_type FROM branches WHERE branch_id=?', (branch,))
        if found.empty:
            raise ValueError('Unknown branch ID')
        if location_type and found.iloc[0, 0] != location_type:
            raise ValueError('Branch does not belong to selected location type')
    if category is not None:
        if not isinstance(category, str) or read('SELECT 1 FROM products_catalog WHERE category_en=? LIMIT 1', (category,)).empty:
            raise ValueError('Unknown product category')
    return Filters(start, end, branch, location_type, category)


def predicate(scope, alias='o', date_column='order_date', include_category=False):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', alias) or date_column not in ('order_date', 'return_date'):
        raise ValueError('Invalid internal SQL alias/date column')
    parts, params = [f'{alias}.{date_column} BETWEEN ? AND ?'], [scope.start, scope.end]
    if scope.branch:
        parts.append(f'{alias}.branch_id=?')
        params.append(scope.branch)
    if scope.location_type:
        parts.append(f'{alias}.branch_id IN (SELECT branch_id FROM branches WHERE retail_location_type=?)')
        params.append(scope.location_type)
    if include_category and scope.category:
        parts.append(f'{alias}.product_id IN (SELECT product_id FROM products_catalog WHERE category_en=?)')
        params.append(scope.category)
    return ' AND '.join(parts), tuple(params)


def previous_period(start, end):
    start, end = date.fromisoformat(iso_date(start)), date.fromisoformat(iso_date(end))
    if start > end:
        raise ValueError('Start date must not be after end date')
    previous_end = start - timedelta(days=1)
    return (previous_end - (end-start)).isoformat(), previous_end.isoformat()


def complete_month_bounds(start, end):
    start, end = date.fromisoformat(iso_date(start)), date.fromisoformat(iso_date(end))
    if start > end:
        return None
    first = start if start.day == 1 else (start.replace(day=28)+timedelta(days=4)).replace(day=1)
    last_day = end.replace(day=monthrange(end.year, end.month)[1])
    last = end if end == last_day else end.replace(day=1)-timedelta(days=1)
    return (first.isoformat(), last.isoformat()) if first <= last else None
