"""Known-answer stock/transfer fixtures and actual inventory UI/assistant parity."""
from pathlib import Path
from contextlib import closing
from dataclasses import replace
import sqlite3,tempfile,unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
import analytics as api
import db.connection as connection
from services import inventory as inv
from services.inventory_tools import answer_readonly,dispatch
from services.filters import filters
from ui.assistant import offline_answer
from ui.data import Context
from ui.i18n import t
from test_phase1 import fixture

ROOT=Path(__file__).resolve().parents[1]


def inventory_fixture(path):
    fixture(path)
    with closing(sqlite3.connect(path)) as db,db:
        db.executescript('''
        CREATE TABLE warehouses(warehouse_id TEXT,warehouse_label TEXT,warehouse_kind TEXT);
        INSERT INTO warehouses VALUES ('W1','Warehouse One','DC');
        CREATE TABLE sku_variants(sku_id TEXT,product_id TEXT);
        INSERT INTO sku_variants VALUES ('S1','P1'),('S2','P2');
        CREATE TABLE inventory_transfers(transfer_id TEXT,transfer_date TEXT,source_warehouse_id TEXT,destination_branch_id TEXT,transfer_status TEXT,transport_cost_EGP REAL);
        INSERT INTO inventory_transfers VALUES ('T1','2024-01-02','W1','B1','Completed',100),('T2','2024-01-03','W1','B2','In transit',200),('T3','2024-01-04','W1','B1','Partially received',300);
        CREATE TABLE inventory_transfer_items(transfer_line_id TEXT,transfer_id TEXT,sku_id TEXT,quantity_units INTEGER);
        INSERT INTO inventory_transfer_items VALUES ('TI1','T1','S1',5),('TI2','T1','S1',7),('TI3','T1','S2',3),('TI4','T2','S1',20),('TI5','T3','S2',30);
        INSERT INTO monthly_stock VALUES ('2023-12','B1','Branch','A',5,50,.7),('2024-02','B1','Branch','A',0,0,.4);
        ''')


class InventoryFixtureTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'fixture.db';inventory_fixture(self.path)
        change=patch.object(connection,'DB_PATH',self.path);change.start();self.addCleanup(change.stop)

    def test_snapshot_cutoff_midmonth_month_end_and_leap_year(self):
        self.assertEqual(inv.month_cutoff('2024-02-29'),'2024-02')
        self.assertEqual(inv.month_cutoff('2024-02-28'),'2024-01')
        self.assertEqual(inv.dashboard('2024-01-15','2024-01-20')['month'],'2023-12')
        self.assertEqual(inv.dashboard('2024-01-15','2024-01-31')['month'],'2024-01')
        self.assertEqual(inv.dashboard('2024-01-31','2024-01-31')['month'],'2024-01')

    def test_no_month_summing_and_missing_rows_not_zero(self):
        d=inv.dashboard('2023-12-01','2024-01-31')
        self.assertEqual(d['summary']['stock_units'],33)
        self.assertEqual(d['summary']['stock_value'],330)
        self.assertEqual(d['history'].stock_units.tolist(),[5,33])
        feb=inv.dashboard('2024-02-01','2024-02-29')
        self.assertEqual(set(feb['rows'].location_id),{'B1'})
        self.assertEqual(feb['summary']['stock_units'],0)

    def test_branch_warehouse_and_source_types_stay_separate(self):
        scope=dict(start='2024-01-01',end='2024-01-31')
        self.assertEqual(inv.dashboard(**scope,location_type='Retail branch')['summary']['stock_units'],13)
        self.assertEqual(inv.dashboard(**scope,location_type='Point of sale / reseller')['summary']['stock_units'],20)
        wh=inv.dashboard(**scope,branch='B1',location_type='Retail branch',kind='Warehouse',warehouse='W1')
        self.assertEqual(wh['summary']['stock_units'],1000)
        self.assertTrue(wh['rows'].daily_units.isna().all());self.assertTrue(wh['rows'].cover_days.isna().all())
        self.assertIsNone(wh['summary']['low_cover_combinations'])
        self.assertTrue(pd.isna(wh['summary']['estimated_replenishment']))

    def test_category_and_location_intersection(self):
        d=inv.dashboard('2024-01-01','2024-01-31','B1',category='A')
        self.assertEqual(d['summary']['stock_units'],10);self.assertEqual(d['rows'].category.tolist(),['A'])
        with self.assertRaises(ValueError):inv.dashboard('2024-01-01','2024-01-31','B1',location_type='Point of sale / reseller')
        with self.assertRaises(ValueError):inv.dashboard('2024-01-01','2024-01-31',kind='SKU')
        with self.assertRaises(ValueError):inv.dashboard('2024-01-01','2024-01-31',kind='Warehouse',warehouse='missing')

    def test_network_distribution_same_month_and_missing_not_zero(self):
        branch=inv.dashboard('2024-01-01','2024-01-31');wh=inv.dashboard('2024-01-01','2024-01-31',kind='Warehouse')
        frame=inv.network_distribution(branch,wh).set_index('category')
        self.assertAlmostEqual(frame.loc['A','displayed_warehouse_share_pct'],1000/1030*100)
        self.assertTrue(pd.isna(frame.loc['B','displayed_warehouse_share_pct']))
        wh['month']='2023-12'
        self.assertTrue(inv.network_distribution(branch,wh).displayed_warehouse_share_pct.isna().all())

    def test_risk_mean_never_hides_high_location(self):
        d=inv.dashboard('2024-01-01','2024-01-31');a=d['categories'].set_index('category').loc['A']
        self.assertAlmostEqual(a.mean_recorded_risk,.7)
        self.assertEqual(a.max_recorded_risk,.8);self.assertEqual(a.high_risk_combinations,1)
        self.assertEqual(d['high_risk_rows'].location_id.tolist(),['B1'])
        self.assertEqual(d['summary']['high_risk_categories'],1)

    def test_velocity_uses_matching_branch_category_and_snapshot_window(self):
        d=inv.dashboard('2024-01-20','2024-01-31','B1',planning=inv.Planning(lookback_days=31))
        rows=d['rows'].set_index('category')
        self.assertEqual(d['window']['start'],'2024-01-01')
        self.assertEqual(rows.loc['A','sold_units'],2);self.assertEqual(rows.loc['B','sold_units'],3)
        self.assertAlmostEqual(rows.loc['A','daily_units'],2/31)
        self.assertAlmostEqual(rows.loc['A','cover_days'],155)
        self.assertAlmostEqual(rows.loc['B','cover_days'],31)

    def test_zero_sales_cover_unavailable_and_zero_estimate(self):
        d=inv.dashboard('2024-01-01','2024-01-31','B2',planning=inv.Planning(lookback_days=31))
        row=d['rows'].iloc[0]
        self.assertEqual(row.sold_units,0);self.assertEqual(row.daily_units,0)
        self.assertTrue(pd.isna(row.cover_days));self.assertEqual(row.estimated_replenishment,0)

    def test_zero_stock_positive_velocity_and_horizon_estimate(self):
        d=inv.dashboard('2024-02-01','2024-02-29','B1',planning=inv.Planning(lookback_days=60,horizon_days=31))
        row=d['rows'].iloc[0]
        self.assertAlmostEqual(row.daily_units,2/60)
        self.assertEqual(row.cover_days,0);self.assertTrue(row.low_cover)
        self.assertEqual(row.estimated_replenishment,2)

    def test_insufficient_sales_coverage_not_invented(self):
        d=inv.dashboard('2024-01-01','2024-01-31')
        self.assertFalse(d['window']['complete'])
        self.assertTrue(d['rows'].daily_units.isna().all())
        self.assertTrue(d['rows'].estimated_replenishment.isna().all())
        self.assertIsNone(d['summary']['low_cover_combinations'])

    def test_slow_proxy_and_risk_are_independent(self):
        d=inv.dashboard('2024-01-01','2024-01-31','B2',planning=inv.Planning(lookback_days=31,high_stock_units=20))
        self.assertTrue(d['rows'].slow_moving_proxy.iloc[0]);self.assertEqual(d['rows'].risk_label.iloc[0],'Medium')

    def test_planning_validation(self):
        for values in ({'lookback_days':0},{'lookback_days':True},{'horizon_days':181},{'low_cover_days':121,'high_cover_days':120},{'slow_daily_units':float('nan')},{'high_stock_units':-1}):
            with self.assertRaises(ValueError):inv.Planning(**values)

    def test_stock_changes_missing_baseline_and_real_zero(self):
        d=inv.dashboard('2024-01-01','2024-01-31')
        c=d['category_changes'].set_index('category')
        self.assertEqual(c.loc['A','stock_change_pct'],500)
        self.assertTrue(pd.isna(c.loc['B','previous_stock_units']))
        feb=inv.dashboard('2024-01-01','2024-02-29')['category_changes'].set_index('category')
        self.assertEqual(feb.loc['A','stock_change_pct'],-100)

    def test_transfer_cost_not_multiplied_by_lines_or_categories(self):
        d=inv.transfer_analysis('2024-01-01','2024-01-31')
        self.assertEqual(d['summary'],dict(transfer_count=3,transfer_units=65,transport_cost=600))
        a=inv.transfer_analysis('2024-01-01','2024-01-31',category='A')
        self.assertEqual(a['summary'],dict(transfer_count=2,transfer_units=32,transport_cost=300))
        self.assertEqual(a['categories'].transfer_units.sum(),32)
        self.assertEqual(d['events'].loc[d['events'].transfer_id.eq('T1'),'transport_cost'].iloc[0],100)

    def test_transfer_status_and_source_destination_filters(self):
        for status,units in [('Completed',15),('In transit',20),('Partially received',30)]:
            d=inv.transfer_analysis('2024-01-01','2024-01-31',status=status,warehouse='W1')
            self.assertEqual(d['summary']['transfer_count'],1);self.assertEqual(d['summary']['transfer_units'],units)
        d=inv.transfer_analysis('2024-01-01','2024-01-31',location_type='Retail branch')
        self.assertEqual(d['summary']['transfer_units'],45)
        with self.assertRaises(ValueError):inv.transfer_analysis('2024-01-01','2024-01-31',status='Delivered')

    def test_pair_shared_snapshot_types_and_missing_snapshot(self):
        d=inv.compare_two('2024-01-01','2024-01-31','B1','B2')
        self.assertEqual(d['month'],'2024-01');self.assertEqual(d['rows'].stock_units.sum(),33)
        self.assertEqual(d['locations'].branch_id.tolist(),['B1','B2'])
        with self.assertRaises(ValueError):inv.compare_two('2024-02-01','2024-02-29','B1','B2')

    def test_empty_snapshot_and_transfer_ranges(self):
        d=inv.dashboard('2010-01-01','2010-01-31')
        self.assertIsNone(d['month']);self.assertIsNone(d['summary']['stock_units']);self.assertTrue(d['rows'].empty)
        self.assertEqual(inv.transfer_analysis('2010-01-01','2010-01-31')['summary']['transfer_count'],0)

    def test_assistant_service_parity_and_allowlist(self):
        scope=dict(start='2024-01-01',end='2024-01-31',branch='B1')
        report=answer_readonly('inventory6_stock',scope,{'planning':{'lookback_days':31}})
        self.assertEqual(report['meta']['snapshot'],'2024-01')
        self.assertEqual(sum(r['stock_units'] for r in report['data']),13)
        self.assertAlmostEqual(report['data'][0]['daily_units'],2/31)
        self.assertNotIn('customer_id',str(report));self.assertNotIn('sku_id',str(report))
        for name in ('inventory6_risk','inventory6_cover','inventory6_replenishment','inventory6_warehouse','inventory6_transfers'):
            self.assertIn('data',answer_readonly(name,scope))
        for limit in (True,0,21):
            with self.assertRaises(ValueError):answer_readonly('inventory6_stock',scope,{'limit':limit})
        with self.assertRaises(ValueError):answer_readonly('sql',scope)


@unittest.skipUnless(api.DB.exists(),'Build local database')
class InventoryIntegrationTests(unittest.TestCase):
    def test_bilingual_questions_and_pair_clarification(self):
        scope=filters('2026-01-01','2026-09-30')
        for question,name in [('Which categories have the highest inventory risk?','inventory6_risk'),('Show stock levels in BR001.','inventory6_stock'),('Which locations have low inventory coverage?','inventory6_cover'),('Which categories may require replenishment?','inventory6_replenishment'),('Show warehouse stock by category.','inventory6_warehouse'),('Which warehouse-to-branch transfers were recorded last month?','inventory6_transfers'),('ايه الفئات اللي مخزونها ممكن ميكفيش؟','inventory6_cover'),('أنهي الفروع عندها مخزون قليل؟','inventory6_cover'),('إيه الكميات المقترحة لإعادة التوريد؟','inventory6_replenishment')]:
            _,reports=offline_answer(question,Context('English',scope));self.assertEqual(reports[0]['meta']['tool'],name)
        self.assertEqual(dispatch('قارن المخزون بين فرعين.',vars(scope)),{'clarify':'two_ids_required'})
        report=dispatch('Compare inventory BR001 and BR002',vars(scope));self.assertEqual(report['meta']['branch_id'],'pair')
        self.assertIsNone(dispatch('Which products generated the highest gross profit?',vars(scope)))

    def test_all_inventory_modes_both_languages(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
        app.sidebar.radio[1].set_value('Inventory Intelligence').run()
        for language,suffix in [('English','_en'),('العربية','_ar')]:
            app.sidebar.radio(key='language').set_value(language).run()
            for mode in ('i6_overview','i6_locations','i6_warehouses','i6_risk','i6_coverage','i6_transfers','i6_trends'):
                app.selectbox(key='i6_mode'+suffix).set_value(mode).run()
                self.assertFalse(app.exception,[e.message for e in app.exception]);self.assertFalse(app.error)
                self.assertEqual(app.button(key='assistant_access').label,t('ask',language))
            app.selectbox(key='i6_mode'+suffix).set_value('i6_transfers').run()
            app.selectbox(key='i6_status'+suffix).set_value('In transit').run()
            self.assertFalse(app.exception)

    def test_global_filters_and_warehouse_override(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
        branch=api.branches().query("retail_location_type=='Retail branch'").branch_id.iloc[0]
        app.sidebar.selectbox(key='filter_type_ar').set_value('Retail branch').run()
        app.sidebar.selectbox(key='filter_branch_ar').set_value(branch).run()
        app.sidebar.selectbox(key='filter_category_ar').set_value('Socks').run()
        app.sidebar.radio[1].set_value('Inventory Intelligence').run()
        before=dict(app.session_state['active_scope']);self.assertFalse(app.exception)
        expected=inv.dashboard(**before)['summary']['stock_units']
        self.assertEqual(app.metric[0].value,f'{expected:,}')
        app.selectbox(key='i6_mode_ar').set_value('i6_warehouses').run()
        self.assertFalse(app.exception);self.assertIn(t('i6_warehouse_override','العربية'),[v.value for v in app.info])
        self.assertEqual(dict(app.session_state['active_scope']),before)
        app.selectbox(key='i6_mode_ar').set_value('i6_coverage').run()
        app.number_input(key='i6_horizon').set_value(60).run()
        self.assertFalse(app.exception);self.assertEqual(dict(app.session_state['active_scope']),before)


if __name__=='__main__':unittest.main()
