"""Idempotent, additive Phase 1 views/indexes; raw imported values are untouched."""
INDEXES = {
    'uq_orders_id': 'CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_id ON sales_orders(sales_order_id)',
    'uq_lines_id': 'CREATE UNIQUE INDEX IF NOT EXISTS uq_lines_id ON sales_order_items(sales_line_id)',
    'uq_products_id': 'CREATE UNIQUE INDEX IF NOT EXISTS uq_products_id ON products_catalog(product_id)',
    'uq_branches_id': 'CREATE UNIQUE INDEX IF NOT EXISTS uq_branches_id ON branches(branch_id)',
    'uq_customers_id': 'CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_id ON customers(customer_id)',
    'p1_orders_branch_date': 'CREATE INDEX IF NOT EXISTS p1_orders_branch_date ON sales_orders(branch_id,order_date)',
    'p1_lines_branch_date': 'CREATE INDEX IF NOT EXISTS p1_lines_branch_date ON sales_order_items(branch_id,order_date)',
    'p1_lines_product_date': 'CREATE INDEX IF NOT EXISTS p1_lines_product_date ON sales_order_items(product_id,order_date)',
    'p1_products_category': 'CREATE INDEX IF NOT EXISTS p1_products_category ON products_catalog(category_en,product_id)',
    'p1_returns_date': 'CREATE INDEX IF NOT EXISTS p1_returns_date ON sales_returns(return_date,sales_order_id)',
    'p1_stock_scope': 'CREATE INDEX IF NOT EXISTS p1_stock_scope ON monthly_stock(stock_location_type,stock_location_id,year_month,product_category)',
}
DATE_VIEWS = {
    'customers': ('joined_date',), 'branches': ('opening_date',),
    'employees': ('hire_date',), 'import_shipments': ('shipment_date',),
}


def normalized_date_sql(column):
    # All identifiers here are fixed developer-owned schema constants.
    rest = f'substr({column},instr({column},\'/\')+1)'
    return (f"CASE WHEN instr({column},'/')>0 THEN printf('%04d-%02d-%02d', "
            f"CAST(substr({rest},instr({rest},'/')+1) AS INTEGER), "
            f"CAST(substr({column},1,instr({column},'/')-1) AS INTEGER), "
            f"CAST(substr({rest},1,instr({rest},'/')-1) AS INTEGER)) "
            f"ELSE date({column}) END")


def prepare_connection(conn):
    for sql in INDEXES.values():
        conn.execute(sql)
    for table, columns in DATE_VIEWS.items():
        expressions = ','.join(normalized_date_sql(c) + ' AS ' + c + '_iso' for c in columns)
        conn.execute(f'CREATE VIEW IF NOT EXISTS v_{table}_normalized AS SELECT *,{expressions} FROM {table}')

