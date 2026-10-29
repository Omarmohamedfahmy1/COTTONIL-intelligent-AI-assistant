"""Read-only Phase 0 schema, key, coverage and audit checks. No customer output."""
import argparse
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3

try:
    from .build_db import DEFAULT_DB, identifier
except ImportError:
    from build_db import DEFAULT_DB, identifier

PRIMARY_KEYS = {
    "branches": "branch_id", "customers": "customer_id", "delivery_shipments": "shipment_id",
    "employees": "employee_id", "factories": "factory_id", "import_partners": "import_partner_id",
    "import_shipments": "import_shipment_id", "inventory_transfers": "transfer_id",
    "inventory_transfer_items": "transfer_line_id", "marketing_campaigns": "campaign_id",
    "operating_expenses": "expense_id", "payroll": "payroll_id", "products_catalog": "product_id",
    "purchase_orders": "po_id", "purchase_order_items": "po_line_id", "sales_orders": "sales_order_id",
    "sales_order_items": "sales_line_id", "sales_payments": "payment_id", "sales_returns": "return_id",
    "sku_variants": "sku_id", "suppliers": "supplier_id", "warehouses": "warehouse_id",
    "product_catalog_public_reference": "product_id",
}
RELATIONSHIPS = [
    ("sales_orders", "branch_id", "branches", "branch_id"),
    ("sales_orders", "customer_id", "customers", "customer_id"),
    ("sales_order_items", "sales_order_id", "sales_orders", "sales_order_id"),
    ("sales_order_items", "branch_id", "branches", "branch_id"),
    ("sales_order_items", "sku_id", "sku_variants", "sku_id"),
    ("sales_order_items", "product_id", "products_catalog", "product_id"),
    ("sku_variants", "product_id", "products_catalog", "product_id"),
    ("sales_payments", "sales_order_id", "sales_orders", "sales_order_id"),
    ("delivery_shipments", "sales_order_id", "sales_orders", "sales_order_id"),
    ("sales_returns", "sales_order_id", "sales_orders", "sales_order_id"),
    ("sales_returns", "sales_line_id", "sales_order_items", "sales_line_id"),
    ("sales_returns", "sku_id", "sku_variants", "sku_id"),
    ("employees", "branch_id", "branches", "branch_id"),
    ("payroll", "employee_id", "employees", "employee_id"),
    ("purchase_orders", "supplier_id", "suppliers", "supplier_id"),
    ("purchase_orders", "receiving_warehouse_id", "warehouses", "warehouse_id"),
    ("purchase_order_items", "po_id", "purchase_orders", "po_id"),
    ("purchase_order_items", "sku_id", "sku_variants", "sku_id"),
    ("inventory_transfers", "source_warehouse_id", "warehouses", "warehouse_id"),
    ("inventory_transfers", "destination_branch_id", "branches", "branch_id"),
    ("inventory_transfer_items", "transfer_id", "inventory_transfers", "transfer_id"),
    ("inventory_transfer_items", "sku_id", "sku_variants", "sku_id"),
    ("import_shipments", "import_partner_id", "import_partners", "import_partner_id"),
    ("import_shipments", "destination_warehouse_id", "warehouses", "warehouse_id"),
]


def validate(path):
    result = {"checks": {}, "schema": {}, "counts": {}, "date_coverage": {}}
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        def check(name, actual, expected):
            result["checks"][name] = {"actual": actual, "expected": expected, "passed": actual == expected}

        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '\\_%' ESCAPE '\\' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        check("table_set", tables, sorted([*PRIMARY_KEYS, "monthly_stock", "data_dictionary"]))
        check("sqlite_integrity", conn.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
        # Imported CSV schema has no declared FKs: explicit anti-joins below are authoritative.
        check("pragma_foreign_key_check", conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        for table in tables:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({identifier(table)})")]
            result["schema"][table] = cols
            result["counts"][table] = conn.execute(f"SELECT COUNT(*) FROM {identifier(table)}").fetchone()[0]
            for col in cols:
                if col.endswith("_date") or col in ("year_month", "pay_month"):
                    dates, invalid, formats = [], 0, set()
                    for (value,) in conn.execute(f"SELECT DISTINCT {identifier(col)} FROM {identifier(table)} WHERE {identifier(col)} IS NOT NULL"):
                        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m"):
                            try:
                                parsed = datetime.strptime(value, fmt)
                                dates.append(parsed.strftime("%Y-%m" if fmt == "%Y-%m" else "%Y-%m-%d"))
                                formats.add(fmt)
                                break
                            except ValueError:
                                continue
                        else:
                            invalid += 1
                    name = table + "." + col
                    result["date_coverage"][name] = [min(dates), max(dates)] if dates else [None, None]
                    result.setdefault("date_formats", {})[name] = sorted(formats)
                    check("unparseable_dates:" + name, invalid, 0)
        for table, key in PRIMARY_KEYS.items():
            check(f"key:{table}.{key}", conn.execute(f"SELECT COUNT(*)-COUNT(DISTINCT {identifier(key)}) FROM {identifier(table)}").fetchone()[0], 0)
        for child, key, parent, pk in RELATIONSHIPS:
            check(f"fk:{child}.{key}->{parent}.{pk}", conn.execute(f"SELECT COUNT(*) FROM {identifier(child)} c WHERE c.{identifier(key)} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {identifier(parent)} p WHERE p.{identifier(pk)}=c.{identifier(key)})").fetchone()[0], 0)
        for table, count in {"branches":80, "customers":85000, "sales_orders":540000, "sales_order_items":1138536, "products_catalog":139, "sku_variants":695, "product_catalog_public_reference":238}.items():
            check("audit_count:" + table, result["counts"][table], count)
        check("audit_sales_dates", list(result["date_coverage"]["sales_orders.order_date"]), ["2018-10-19", "2026-10-18"])
        check("audit_anonymous_orders", conn.execute("SELECT COUNT(*) FROM sales_orders WHERE customer_id IS NULL").fetchone()[0], 102961)
        check("stock_composite_key_duplicates", conn.execute("SELECT COUNT(*) FROM (SELECT 1 FROM monthly_stock GROUP BY year_month,stock_location_id,product_category HAVING COUNT(*)>1)").fetchone()[0], 0)
        check("stock_location_orphans", conn.execute("SELECT COUNT(*) FROM monthly_stock s WHERE NOT EXISTS (SELECT 1 FROM branches b WHERE b.branch_id=s.stock_location_id) AND NOT EXISTS (SELECT 1 FROM warehouses w WHERE w.warehouse_id=s.stock_location_id)").fetchone()[0], 0)
        check("line_order_scope_mismatch", conn.execute("SELECT COUNT(*) FROM sales_order_items i JOIN sales_orders o USING(sales_order_id) WHERE i.branch_id IS NOT o.branch_id OR i.order_date IS NOT o.order_date").fetchone()[0], 0)
        check("line_sku_product_mismatch", conn.execute("SELECT COUNT(*) FROM sales_order_items i JOIN sku_variants s USING(sku_id) WHERE i.product_id IS NOT s.product_id").fetchone()[0], 0)
        # Retain the original MVP reconciliations and their rounding tolerances.
        header_net = conn.execute("SELECT SUM(net_before_tax_EGP) FROM sales_orders").fetchone()[0]
        line_net = conn.execute("SELECT SUM(net_line_EGP) FROM sales_order_items").fetchone()[0]
        margin_delta = conn.execute("SELECT SUM(net_line_EGP-quantity*unit_cost_EGP-margin_EGP) FROM sales_order_items").fetchone()[0]
        result["reconciliation"] = {"header_minus_line_net_EGP": header_net-line_net, "margin_residual_EGP": margin_delta}
        check("header_line_net_within_1_EGP", abs(header_net-line_net) < 1, True)
        check("margin_residual_within_200_EGP", abs(margin_delta) < 200, True)
        result["location_types"] = dict(conn.execute("SELECT retail_location_type,COUNT(*) FROM branches GROUP BY retail_location_type"))
        result["stock_location_types"] = dict(conn.execute("SELECT stock_location_type,COUNT(*) FROM monthly_stock GROUP BY stock_location_type"))
        result["dictionary_schema_differences"] = [list(r) for r in conn.execute("SELECT table_name,field_name FROM data_dictionary") if r[0].removesuffix(".csv") not in result["schema"] or r[1] not in result["schema"].get(r[0].removesuffix(".csv"), [])]
        result["source_sha256"] = conn.execute("SELECT sha256 FROM _source_metadata").fetchone()[0]
    result["passed"] = all(c["passed"] for c in result["checks"].values())
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = validate(args.db)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    for name, check in result["checks"].items():
        print(f"{'PASS' if check['passed'] else 'FAIL'} {name}: {check['actual']}")
    print(f"Checks: {sum(c['passed'] for c in result['checks'].values())}/{len(result['checks'])} passed")
    raise SystemExit(0 if result["passed"] else 1)
