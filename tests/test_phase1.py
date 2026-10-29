"""Known-answer mixed-order fixtures plus real-dataset reconciliations."""
from contextlib import closing
import csv
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import analytics as api
import db.connection as connection
from db.schema import prepare_connection
from services.filters import filters, iso_date, normalize_source_date, complete_month_bounds
from services import metrics
from assistant_engine import answer_tool
from scripts.build_db import build_database


def fixture(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript('''
        CREATE TABLE branches(branch_id TEXT,branch_name_ar TEXT,governorate_ar TEXT,retail_location_type TEXT,opening_date TEXT);
        INSERT INTO branches VALUES ('B1','One','G','Retail branch','1/1/2020'),('B2','Two','G','Point of sale / reseller','1/2/2020'),('B3','Empty','G','Retail branch','1/1/2020');
        CREATE TABLE customers(customer_id TEXT,joined_date TEXT);
        INSERT INTO customers VALUES ('C1','1/1/2020'),('C2','2/1/2020'),('C3','2/15/2024');
        CREATE TABLE employees(employee_id TEXT,branch_id TEXT,hire_date TEXT);
        INSERT INTO employees VALUES ('E1','B1','1/1/2020');
        CREATE TABLE import_shipments(import_shipment_id TEXT,shipment_date TEXT);
        INSERT INTO import_shipments VALUES ('I1','2/9/2024');
        CREATE TABLE products_catalog(product_id TEXT,product_name_ar TEXT,category_en TEXT);
        INSERT INTO products_catalog VALUES ('P1','A1','A'),('P2','B1','B'),('P3','No sales','C');
        CREATE TABLE sales_orders(sales_order_id TEXT,order_date TEXT,branch_id TEXT,customer_id TEXT,sales_channel TEXT,net_before_tax_EGP REAL);
        INSERT INTO sales_orders VALUES
        ('O0','2023-12-31','B1','C1','Store',100),('O1','2024-01-01','B1','C1','Store',300),
        ('O2','2024-01-02','B1',NULL,'Online',80),('O3','2024-02-01','B2','C2','Store',200),
        ('O4','2024-02-29','B2','C1','Store',0);
        CREATE TABLE sales_order_items(sales_line_id TEXT,sales_order_id TEXT,order_date TEXT,branch_id TEXT,product_id TEXT,quantity INTEGER,net_line_EGP REAL,margin_EGP REAL);
        INSERT INTO sales_order_items VALUES
        ('L0','O0','2023-12-31','B1','P1',1,100,50),('L1','O1','2024-01-01','B1','P1',1,100,40),
        ('L2','O1','2024-01-01','B1','P1',1,50,20),('L3','O1','2024-01-01','B1','P2',1,150,60),
        ('L4','O2','2024-01-02','B1','P2',2,80,30),('L5','O3','2024-02-01','B2','P1',2,200,80),
        ('L6','O4','2024-02-29','B2','P1',1,0,0);
        CREATE TABLE sales_returns(return_id TEXT,sales_order_id TEXT,sales_line_id TEXT,return_date TEXT,refund_amount_EGP REAL);
        INSERT INTO sales_returns VALUES ('R1','O1','L1','2024-02-01',70),('R2','O0','L0','2024-01-05',10);
        CREATE TABLE monthly_stock(year_month TEXT,stock_location_id TEXT,stock_location_type TEXT,product_category TEXT,closing_units INTEGER,closing_stock_value_EGP REAL,stockout_risk_score REAL);
        INSERT INTO monthly_stock VALUES ('2024-01','B1','Branch','A',10,100,.8),('2024-01','B1','Branch','B',3,30,.2),('2024-01','B2','Branch','A',20,200,.6),('2024-01','W1','Warehouse','A',1000,10000,.1);
        ''')
        prepare_connection(conn)


class FixtureKPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/'fixture.db'
        fixture(self.db)
        self.patcher = patch.object(connection, 'DB_PATH', self.db)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_company_known_answers_and_anonymous(self):
        x = api.overview('2024-01-01','2024-01-31')
        self.assertEqual((x['sales'],x['gross_profit'],x['orders'],x['customers'],x['anonymous_orders'],x['branches']), (380,150,2,1,1,1))
        self.assertEqual(x['aov'],190)
        self.assertAlmostEqual(x['gross_margin_pct'],100*150/380)
        self.assertEqual(api.customer_activity('2024-01-01','2024-01-31'), {'orders':2,'customers':1,'anonymous_orders':1})

    def test_mixed_category_revenue_never_repeats_header(self):
        a = api.overview('2024-01-01','2024-01-31',category='A')
        b = api.overview('2024-01-01','2024-01-31',category='B')
        self.assertEqual((a['sales'],a['orders'],a['gross_profit']),(150,1,60))
        self.assertEqual((b['sales'],b['orders'],b['anonymous_orders']),(230,2,1))
        self.assertEqual(a['sales']+b['sales'],380)
        self.assertEqual(a['orders']+b['orders'],3)  # Category order counts are non-additive.

    def test_branch_location_and_category_intersection(self):
        x = api.overview('2024-01-01','2024-02-29','B2',location_type='Point of sale / reseller',category='A')
        self.assertEqual((x['sales'],x['orders'],x['customers']),(200,2,2))
        rows = api.branch_performance('2024-01-01','2024-02-29',branch='B2',category='A')
        self.assertEqual(rows.branch_id.tolist(),['B2'])
        self.assertEqual(rows.sales.sum(),x['sales'])

    def test_product_category_month_channel_reconcile(self):
        for category in (None,'A','B','C'):
            options = {'category':category}
            x=api.overview('2024-01-01','2024-02-29',**options)
            for f in (api.product_performance,api.category_performance):
                data=f('2024-01-01','2024-02-29',**options)
                self.assertEqual(data.sales.sum(),x['sales'])
                self.assertEqual(data.gross_profit.sum(),x['gross_profit'])
            for f in (api.sales_monthly,api.sales_channel):
                self.assertEqual(f('2024-01-01','2024-02-29',**options).sales.sum(),x['sales'])

    def test_registered_customers_use_registration_not_purchase(self):
        self.assertEqual(api.registered_customers('2024-01-01'),2)
        self.assertEqual(api.registered_customers('2024-02-29'),3)
        self.assertEqual(connection.read("SELECT joined_date FROM customers WHERE customer_id='C2'").iloc[0,0],'2/1/2020')
        self.assertEqual(connection.read("SELECT joined_date_iso FROM v_customers_normalized WHERE customer_id='C2'").iloc[0,0],'2020-02-01')

    def test_return_event_date_and_unverified_adjustment(self):
        self.assertEqual(api.overview('2024-01-01','2024-01-31')['refunds'],10)
        x=api.overview('2024-02-01','2024-02-01',category='A')
        self.assertEqual(x['refunds'],70)  # Refund on prior month's sale, attributed by return date.
        self.assertIsNone(x['refund_adjusted_sales'])
        self.assertEqual(x['gross_profit'],80)  # No invented reversal of COGS/profit.

    def test_empty_ranges_and_valid_empty_categories(self):
        for options in ({},{'category':'C'},{'branch':'B3'}):
            x=api.overview('2030-01-01','2030-01-31',**options)
            for key in ('sales','gross_profit','orders','customers','anonymous_orders','units','refunds','aov','gross_margin_pct','branches'):
                self.assertEqual(x[key],0)
            for f in (api.product_performance,api.category_performance,api.sales_monthly,api.sales_channel,api.seasonality):
                self.assertTrue(f('2030-01-01','2030-01-31',**options).empty)
        self.assertTrue(api.branch_performance('2030-01-01','2030-01-31').empty)

    def test_partial_months_respect_selection_and_source_coverage(self):
        monthly=api.sales_monthly('2023-12-01','2024-02-29')
        self.assertEqual(monthly.is_complete_month.tolist(),[False,True,True])
        self.assertFalse(api.sales_monthly('2024-01-02','2024-02-15').is_complete_month.any())
        self.assertTrue(api.seasonality('2024-01-02','2024-02-15').empty)
        self.assertEqual(api.company_sales_fully_observed_months().month.tolist(),['2024-01','2024-02'])
        self.assertEqual(complete_month_bounds('2024-01-01','2024-02-29'),('2024-01-01','2024-02-29'))

    def test_growth_requires_positive_baseline_and_equal_coverage(self):
        self.assertEqual(api.sales_growth('2024-01-01','2024-01-01')['growth_pct'],200)
        self.assertIsNone(api.sales_growth('2024-01-01','2024-01-02')['growth_pct'])
        self.assertIsNone(api.sales_growth('2024-02-01','2024-02-01')['growth_pct'])

    def test_inventory_grain_filters_and_no_velocity(self):
        month, df=api.inventory_snapshot('2024-01-31',location_type='Retail branch',category='A')
        self.assertEqual(month,'2024-01')
        self.assertEqual(df.stock_units.sum(),10)  # Warehouse and reseller excluded.
        summary=api.inventory_summary(df)
        self.assertEqual((summary['stock_units'],summary['stock_value'],summary['high_risk_categories']),(10,100,1))
        response=answer_tool('inventory',{'start':'2024-01-01','end':'2024-01-31','branch':'B1','category':'A'})
        self.assertEqual(response['meta']['summary'],summary)
        _, future=api.inventory_snapshot('2030-01-31')
        self.assertTrue(future.approx_cover_days.isna().all())
        self.assertTrue((future.suggested_30d_replenishment==0).all())
        self.assertTrue(api.inventory_snapshot('2019-01-01')[1].empty)

    def test_scope_rejects_invalid_dates_filters_and_injection(self):
        for start,end in [('2024-02-30','2024-03-01'),('01/02/2024','2024-02-01'),('2024-02-01','2024-01-01')]:
            with self.assertRaises(ValueError):
                api.overview(start,end)
        for kwargs in ({'branch':"B1' OR 1=1 --"},{'location_type':'Warehouse'},{'category':'missing'},{'branch':'B1','location_type':'Point of sale / reseller'}):
            with self.assertRaises(ValueError):
                api.overview('2024-01-01','2024-02-01',**kwargs)
        self.assertEqual(normalize_source_date('2/9/2024'),'2024-02-09')
        with self.assertRaises(ValueError):
            normalize_source_date('garbage')

    def test_read_only_layer_rejects_database_writes(self):
        with self.assertRaises(__import__('pandas').errors.DatabaseError):
            connection.read('DELETE FROM sales_orders')
        self.assertEqual(len(connection.read('SELECT * FROM sales_orders')),5)

    def test_assistant_uses_exact_shared_scope(self):
        context={'start':'2024-01-01','end':'2024-02-29','branch':'B1','category':'A','location_type':'Retail branch'}
        expected=api.overview(context['start'],context['end'],'B1',category='A',location_type='Retail branch')
        actual=answer_tool('company_overview',context)['data'][0]
        for key in expected:
            self.assertEqual(actual[key],expected[key])
        self.assertIs(api.overview,metrics.overview)
        with self.assertRaises(ValueError):
            answer_tool('company_overview',context,{'category':'bad'})

    def test_additive_schema_is_idempotent(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            prepare_connection(conn)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM sales_orders').fetchone()[0],5)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO products_catalog VALUES ('P1','duplicate','A')")

    def test_fresh_import_installs_the_same_views_and_indexes(self):
        source=Path(self.temp.name)/'fixture.zip'
        with closing(sqlite3.connect(self.db)) as conn, zipfile.ZipFile(source,'w') as archive:
            tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                cursor=conn.execute(f'SELECT * FROM {table}')
                output=io.StringIO(newline='')
                writer=csv.writer(output)
                writer.writerow([c[0] for c in cursor.description])
                writer.writerows(cursor.fetchall())
                archive.writestr('02_TABLES/'+table+'.csv',output.getvalue())
        target=Path(self.temp.name)/'rebuilt.db'
        build_database(source,target)
        with closing(sqlite3.connect(target)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM v_customers_normalized').fetchone()[0],3)
            self.assertIsNotNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='p1_orders_branch_date'").fetchone())


@unittest.skipUnless(api.DB.exists(),'Build Cottonil database first')
class RealDatasetKPITests(unittest.TestCase):
    def test_full_history_matches_approved_audit(self):
        x=api.overview('2018-10-19','2026-10-18')
        for key,expected in {'sales':841274176.32,'gross_profit':322558299.50,'orders':540000,'customers':74660,'anonymous_orders':102961,'units':3398655,'branches':80}.items():
            self.assertAlmostEqual(x[key],expected,delta=.02)
        self.assertEqual(api.registered_customers('2026-10-18'),85000)

    def test_date_branch_location_and_category_totals(self):
        branch=api.branches().branch_id.iloc[0]
        for start,end in [('2018-10-19','2018-10-31'),('2024-02-01','2024-02-29'),('2026-01-01','2026-09-30'),('2026-10-01','2026-10-18')]:
            for selected in (None,branch):
                x=api.overview(start,end,selected)
                rows=api.product_performance(start,end,selected,limit=1000)
                self.assertAlmostEqual(x['sales'],rows.sales.sum(),delta=.02)
                self.assertAlmostEqual(x['gross_profit'],rows.gross_profit.sum(),delta=.02)
            all_sales=api.overview(start,end)['sales']
            self.assertAlmostEqual(sum(api.overview(start,end,location_type=t)['sales'] for t in ('Retail branch','Point of sale / reseller')),all_sales,delta=.02)

    def test_category_contributions_and_distinct_order_counts(self):
        categories=api.category_performance('2026-01-01','2026-09-30')
        for row in categories.itertuples():
            x=api.overview('2026-01-01','2026-09-30',category=row.category)
            self.assertAlmostEqual(x['sales'],row.sales,delta=.02)
            self.assertAlmostEqual(x['gross_profit'],row.gross_profit,delta=.02)
            independent=connection.read('''SELECT COUNT(DISTINCT o.sales_order_id) FROM sales_orders o
                JOIN sales_order_items i USING(sales_order_id) JOIN products_catalog p USING(product_id)
                WHERE o.order_date BETWEEN ? AND ? AND p.category_en=?''',('2026-01-01','2026-09-30',row.category)).iloc[0,0]
            self.assertEqual(x['orders'],independent)

    def test_full_history_complete_months_and_no_future_claims(self):
        monthly=api.sales_monthly('2018-10-01','2026-10-31')
        self.assertFalse(monthly.is_complete_month.iloc[0])
        self.assertFalse(monthly.is_complete_month.iloc[-1])
        forecast_input=api.company_sales_fully_observed_months()
        self.assertEqual((forecast_input.month.iloc[0],forecast_input.month.iloc[-1]),('2018-11','2026-09'))
        self.assertIsNone(api.overview('2026-01-01','2026-09-30')['refund_adjusted_sales'])
