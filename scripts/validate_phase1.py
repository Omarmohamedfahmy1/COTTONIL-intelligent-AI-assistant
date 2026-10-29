"""Phase 1 aggregate reconciliation and normalized-date checks; no customer exports."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.connection import DB_PATH
from db.schema import DATE_VIEWS, INDEXES
from services.filters import normalize_source_date
from analytics import overview, branch_performance, category_performance, registered_customers


def validate(source_zip=None):
    result = {'checks': {}, 'observations': {}}
    def check(name, actual, expected=0):
        result['checks'][name] = {'actual':actual, 'expected':expected, 'passed':actual == expected}
    with closing(sqlite3.connect(DB_PATH.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
        order = conn.execute('''SELECT COUNT(*),COALESCE(MAX(ABS(o.net_before_tax_EGP-i.net)),0),
            COALESCE(MAX(ABS(o.gross_EGP-i.gross)),0),COALESCE(MAX(ABS(o.discount_EGP-i.discount)),0)
            FROM sales_orders o JOIN (SELECT sales_order_id,SUM(net_line_EGP) net,
                SUM(gross_line_EGP) gross,SUM(discount_line_EGP) discount FROM sales_order_items
                GROUP BY sales_order_id) i USING(sales_order_id)
            WHERE ABS(o.net_before_tax_EGP-i.net)>.02 OR ABS(o.gross_EGP-i.gross)>.02 OR ABS(o.discount_EGP-i.discount)>.02''').fetchone()
        check('order_header_line_reconciliations_over_0_02_EGP',order[0])
        result['observations']['mismatched_order_max_differences_EGP'] = list(order[1:])
        check('line_margin_mismatches_over_0_06_EGP',conn.execute('''SELECT COUNT(*) FROM sales_order_items
            WHERE ABS(net_line_EGP-quantity*unit_cost_EGP-margin_EGP)>.06''').fetchone()[0])
        check('return_line_order_sku_mismatches',conn.execute('''SELECT COUNT(*) FROM sales_returns r
            JOIN sales_order_items i USING(sales_line_id) WHERE r.sales_order_id!=i.sales_order_id OR r.sku_id!=i.sku_id''').fetchone()[0])
        check('return_before_original_sale',conn.execute('''SELECT COUNT(*) FROM sales_returns r
            JOIN sales_orders o USING(sales_order_id) WHERE r.return_date<o.order_date''').fetchone()[0])
        diagnostic = conn.execute('''SELECT COUNT(*),SUM(CASE WHEN ABS(r.refund_amount_EGP-r.return_quantity*i.net_line_EGP/i.quantity)>.02 THEN 1 ELSE 0 END),
            SUM(ABS(r.refund_amount_EGP-r.return_quantity*i.net_line_EGP/i.quantity))
            FROM sales_returns r JOIN sales_order_items i USING(sales_line_id)''').fetchone()
        result['observations']['refund_basis'] = {'rows':diagnostic[0], 'different_from_prorated_net_over_0_02':diagnostic[1],
            'absolute_difference_sum_EGP':diagnostic[2], 'conclusion':'Compatible ex-tax refund basis not established; refund-adjusted sales unavailable'}
        for table, columns in DATE_VIEWS.items():
            for col in columns:
                bad = 0
                for raw, normalized, count in conn.execute(f'SELECT {col},{col}_iso,COUNT(*) FROM v_{table}_normalized GROUP BY 1,2'):
                    try:
                        expected = normalize_source_date(raw)
                    except ValueError:
                        bad += count
                    else:
                        bad += count if normalized != expected else 0
                check('normalized_dates:'+table+'.'+col,bad)
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        check('missing_phase1_indexes',len(set(INDEXES)-existing))
        if source_zip:
            with Path(source_zip).open('rb') as stream:
                digest=hashlib.file_digest(stream,'sha256').hexdigest()
            original=conn.execute('SELECT sha256 FROM _source_metadata').fetchone()[0]
            check('source_zip_hash_matches',digest,original)
    for start,end in [('2018-10-19','2026-10-18'),('2026-01-01','2026-09-30')]:
        x=overview(start,end)
        by_branch=branch_performance(start,end)
        by_category=category_performance(start,end)
        result['observations'][start+':'+end] = x
        for key in ('sales','gross_profit'):
            for name, rows in [('branch',by_branch),('category',by_category)]:
                residual=float(rows[key].sum()-x[key])
                result['observations'][name+':'+key+':'+start] = residual
                check(name+':'+key+':'+start+':within_0_02_EGP',abs(residual)<.02,True)
    check('registered_customers_as_of_last_sale',registered_customers('2026-10-18'),85000)
    result['passed']=all(item['passed'] for item in result['checks'].values())
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip',type=Path)
    parser.add_argument('--report',type=Path,default=ROOT/'reports'/'phase_1_reconciliation.json')
    args=parser.parse_args()
    result=validate(args.zip)
    args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    for name,item in result['checks'].items():
        print(f"{'PASS' if item['passed'] else 'FAIL'} {name}: {item['actual']}")
    print(f"Checks: {sum(x['passed'] for x in result['checks'].values())}/{len(result['checks'])}")
    raise SystemExit(0 if result['passed'] else 1)
