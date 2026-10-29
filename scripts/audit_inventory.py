"""Read-only inventory schema, grain, mapping and coverage audit. No private rows."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from db.connection import read

TABLES=('monthly_stock','warehouses','branches','inventory_transfers','inventory_transfer_items','sku_variants','products_catalog','sales_orders','sales_order_items')


def audit():
    tables={name:dict(columns=read('PRAGMA table_info('+name+')')[['name','type']].to_dict('records'),rows=int(read('SELECT COUNT(*) n FROM '+name).iloc[0,0])) for name in TABLES}
    queries={
      'stock_grain_duplicates':'SELECT COUNT(*) FROM (SELECT year_month,stock_location_type,stock_location_id,product_category,COUNT(*) n FROM monthly_stock GROUP BY 1,2,3,4 HAVING COUNT(*)>1)',
      'transfer_id_duplicates':'SELECT COUNT(*)-COUNT(DISTINCT transfer_id) FROM inventory_transfers',
      'line_id_duplicates':'SELECT COUNT(*)-COUNT(DISTINCT transfer_line_id) FROM inventory_transfer_items',
      'sku_id_duplicates':'SELECT COUNT(*)-COUNT(DISTINCT sku_id) FROM sku_variants',
      'product_id_duplicates':'SELECT COUNT(*)-COUNT(DISTINCT product_id) FROM products_catalog',
      'branch_id_duplicates':'SELECT COUNT(*)-COUNT(DISTINCT branch_id) FROM branches',
      'warehouse_id_duplicates':'SELECT COUNT(*)-COUNT(DISTINCT warehouse_id) FROM warehouses',
      'orphan_transfer_lines':'SELECT COUNT(*) FROM inventory_transfer_items l LEFT JOIN inventory_transfers t ON t.transfer_id=l.transfer_id WHERE t.transfer_id IS NULL',
      'unmapped_transfer_skus':'SELECT COUNT(*) FROM inventory_transfer_items l LEFT JOIN sku_variants v ON v.sku_id=l.sku_id LEFT JOIN products_catalog p ON p.product_id=v.product_id WHERE v.sku_id IS NULL OR p.product_id IS NULL',
      'unknown_sources':'SELECT COUNT(*) FROM inventory_transfers t LEFT JOIN warehouses w ON w.warehouse_id=t.source_warehouse_id WHERE w.warehouse_id IS NULL',
      'unknown_destinations':'SELECT COUNT(*) FROM inventory_transfers t LEFT JOIN branches b ON b.branch_id=t.destination_branch_id WHERE b.branch_id IS NULL',
      'stock_unknown_locations':"SELECT COUNT(*) FROM monthly_stock s WHERE (stock_location_type='Branch' AND NOT EXISTS (SELECT 1 FROM branches b WHERE b.branch_id=s.stock_location_id)) OR (stock_location_type='Warehouse' AND NOT EXISTS (SELECT 1 FROM warehouses w WHERE w.warehouse_id=s.stock_location_id)) OR stock_location_type NOT IN ('Branch','Warehouse')",
      'stock_unknown_categories':'SELECT COUNT(*) FROM monthly_stock s WHERE NOT EXISTS (SELECT 1 FROM products_catalog p WHERE p.category_en=s.product_category)',
      'invalid_stock_risk':'SELECT COUNT(*) FROM monthly_stock WHERE stockout_risk_score IS NULL OR stockout_risk_score<0 OR stockout_risk_score>1',
      'negative_stock':'SELECT COUNT(*) FROM monthly_stock WHERE closing_units<0 OR closing_stock_value_EGP<0',
      'invalid_transfer_quantity':'SELECT COUNT(*) FROM inventory_transfer_items WHERE quantity_units IS NULL OR quantity_units<0',
      'headers_without_lines':'SELECT COUNT(*) FROM inventory_transfers t WHERE NOT EXISTS (SELECT 1 FROM inventory_transfer_items l WHERE l.transfer_id=t.transfer_id)'}
    checks={key:int(read(sql).iloc[0,0]) for key,sql in queries.items()}
    return dict(tables=tables,checks=checks,passed=all(v==0 for v in checks.values()),
       stock_coverage=read('SELECT MIN(year_month) first,MAX(year_month) last,COUNT(DISTINCT year_month) months FROM monthly_stock').to_dict('records'),
       stock_locations=read('SELECT stock_location_type,COUNT(*) rows,COUNT(DISTINCT stock_location_id) locations FROM monthly_stock GROUP BY 1').to_dict('records'),
       monthly_rows=read('SELECT year_month,COUNT(*) rows,COUNT(DISTINCT stock_location_id) locations FROM monthly_stock GROUP BY 1 ORDER BY 1').to_dict('records'),
       transfer_statuses=read('SELECT transfer_status,COUNT(*) transfers,SUM(transport_cost_EGP) transport_cost FROM inventory_transfers GROUP BY 1').to_dict('records'),
       transfer_coverage=read('SELECT MIN(transfer_date) first,MAX(transfer_date) last FROM inventory_transfers').to_dict('records'))


if __name__=='__main__':
    result=audit();(ROOT/'reports/phase_6_inventory_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('Inventory audit:',len(result['checks']),'checks, passed:',result['passed'])
    raise SystemExit(0 if result['passed'] else 1)
