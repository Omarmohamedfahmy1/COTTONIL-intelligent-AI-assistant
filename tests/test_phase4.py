"""Phase 4 fixture, reconciliation, parser, and actual UI interaction contracts."""
from datetime import date
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
import analytics as api
import db.connection as connection
from services import sales_branch as sb
from services.sales_branch_tools import answer_readonly,dispatch,resolve_period
from services.filters import filters
from test_phase1 import fixture
from ui.i18n import t
from ui.assistant import offline_answer
from ui.data import Context

ROOT=Path(__file__).resolve().parents[1]

class SalesBranchFixtureTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        p=Path(tmp.name)/'fixture.db';fixture(p)
        change=patch.object(connection,'DB_PATH',p);change.start();self.addCleanup(change.stop)

    def test_all_grains_reconcile_mixed_category_orders(self):
        for category in (None,'A','B','C'):
            expected=api.overview('2024-01-01','2024-02-29',category=category)
            for grain in sb.GRAINS:
                rows=sb.sales_trends('2024-01-01','2024-02-29',category=category,grain=grain)
                for metric in ('sales','gross_profit','orders','units'):
                    self.assertAlmostEqual(rows[metric].sum(),expected[metric],places=6)
            if category=='A':self.assertEqual(expected['orders'],3)
        a=sb.sales_trends('2024-01-01','2024-01-31',category='A')
        b=sb.sales_trends('2024-01-01','2024-01-31',category='B')
        self.assertEqual(a.sales.sum()+b.sales.sum(),380)
        self.assertEqual(a.orders.sum()+b.orders.sum(),3)  # Not additive across categories.

    def test_zero_order_master_locations_and_ceased_selling_growth(self):
        roster=sb.location_roster('2024-01-03','2024-01-04').set_index('branch_id')
        self.assertEqual(set(roster.index),{'B1','B2','B3'})
        self.assertFalse(roster.loc['B1','recorded_orders'])
        self.assertEqual(roster.loc['B1','growth_pct'],-100)
        self.assertTrue(roster.loc['B1','significant_decline'])
        self.assertFalse(roster.loc['B3','recorded_orders'])
        self.assertTrue(pd.isna(roster.loc['B3','growth_pct']))
        self.assertTrue(pd.isna(roster.loc['B3','aov']))
        # B2 has a zero-valued recorded order; it remains a recorded-order location.
        day=sb.location_roster('2024-02-29','2024-02-29').set_index('branch_id')
        self.assertTrue(day.loc['B2','recorded_orders']);self.assertEqual(day.loc['B2','sales'],0)

    def test_rank_policy_defined_growth_includes_no_current_orders(self):
        frame=sb.location_roster('2024-01-03','2024-01-04')
        self.assertEqual(sb.rank_locations(frame,'sales').branch_id.tolist(),[])
        self.assertIn('B1',sb.rank_locations(frame,'growth_pct',True).branch_id.tolist())
        self.assertNotIn('B3',sb.rank_locations(frame,'growth_pct').branch_id.tolist())
        with self.assertRaises(ValueError):sb.rank_locations(frame,'DROP TABLE')

    def test_product_roster_includes_operational_zero_sale_products(self):
        scope=filters('2024-01-01','2024-01-31')
        products=sb.product_roster(scope).set_index('product_id')
        self.assertEqual(products.sales.sum(),380)
        self.assertFalse(products.loc['P3','has_recorded_lines'])
        self.assertEqual(products.loc['P3','units'],0)
        self.assertTrue(pd.isna(products.loc['P3','gross_margin_pct']))

    def test_pair_uses_common_dates_category_and_explicit_type_order(self):
        pair=sb.compare_two('2024-01-01','2024-02-29','B2','B1',category='A')
        self.assertEqual(pair['locations'].branch_id.tolist(),['B2','B1'])
        self.assertEqual(pair['locations'].retail_location_type.tolist(),['Point of sale / reseller','Retail branch'])
        self.assertEqual(pair['left']['current']['sales'],200)
        self.assertEqual(pair['right']['current']['sales'],150)
        self.assertEqual(pair['monthly'].sales.sum(),350)
        with self.assertRaises(ValueError):sb.compare_two('2024-01-01','2024-01-31','B1','B1')
        with self.assertRaises(ValueError):sb.compare_two('2024-01-01','2024-01-31','B1','UNKNOWN')

    def test_partial_bounds_zero_baselines_and_coverage(self):
        partial=sb.sales_analysis('2024-01-15','2024-02-15')
        self.assertFalse(partial['trends'].is_complete_period.any())
        self.assertFalse(partial['yoy'].yoy_comparable.any())
        self.assertTrue(partial['yoy'].yoy_growth_pct.isna().all())
        full=sb.sales_analysis('2023-12-31','2024-01-31')
        self.assertFalse(full['growth']['comparable_coverage'])
        self.assertTrue(full['comparison'].previous.isna().all())
        empty=sb.branch_detail('2024-01-01','2024-01-31','B3')
        self.assertIsNone(empty['current']['aov'])
        self.assertEqual(empty['current']['orders'],0)

    def test_type_category_intersections_and_contributions(self):
        data=sb.sales_analysis('2024-01-01','2024-01-31','B1',location_type='Retail branch',category='A')
        self.assertEqual(data['current']['sales'],150)
        self.assertAlmostEqual(data['categories'].scoped_sales_share_pct.sum(),100)
        self.assertAlmostEqual(data['categories'].company_sales_share_pct.sum(),100*150/380)
        self.assertEqual(sb.location_roster('2024-01-01','2024-01-31',location_type='Retail branch').branch_id.tolist(),['B1','B3'])
        with self.assertRaises(ValueError):sb.sales_analysis('2024-01-01','2024-01-31','B1',location_type='Point of sale / reseller')
        with self.assertRaises(ValueError):sb.sales_trends('2024-01-01','2024-01-31',grain='arbitrary')

    def test_readonly_tools_and_ambiguous_requests(self):
        context=dict(start='2024-01-01',end='2024-02-29')
        with self.assertRaises(ValueError):answer_readonly('execute_sql',context)
        with self.assertRaises(ValueError):answer_readonly('sales4_products',context,{'limit':True})
        self.assertEqual(dispatch('قارنلي أداء فرعين خلال آخر 3 شهور',context)['clarify'],'two_ids_required')
        self.assertEqual(dispatch('Compare One and Two',context)['meta']['tool'],'two_location_comparison')
        self.assertEqual(dispatch('Which products sold the most yesterday?',context)['clarify'],'time_scope_request')


@unittest.skipUnless(api.DB.exists(),'Build the original local database')
class SalesBranchDatasetTests(unittest.TestCase):
    def test_company_and_retail_pos_scope_reconciliation(self):
        master=api.branches()
        for branch,kind in [(None,None),*[(r.branch_id,r.retail_location_type) for r in master.groupby('retail_location_type').first().reset_index().itertuples()]]:
            scope=dict(start='2026-01-01',end='2026-09-30',branch=branch,location_type=kind,category='Socks')
            result=sb.sales_analysis(**scope)
            expected=api.overview(**scope)
            for key in ('sales','gross_profit','orders','units','customers'):self.assertEqual(result['current'][key],expected[key])
            for frame in ('products','categories','trends','channels'):
                self.assertAlmostEqual(result[frame].sales.sum(),expected['sales'],delta=.02)
            self.assertAlmostEqual(result['category_monthly'].gross_profit.sum(),expected['gross_profit'],delta=.02)

    def test_full_calendar_yoy_and_mom_against_authoritative_periods(self):
        scope=filters('2026-01-01','2026-09-30',category='Socks')
        rows=sb.yearly_comparison(scope)
        self.assertTrue(rows.yoy_comparable.all())
        first=rows.iloc[0]
        expected=api.overview('2025-01-01','2025-01-31',category='Socks')['sales']
        before=api.overview('2025-12-01','2025-12-31',category='Socks')['sales']
        self.assertAlmostEqual(first.previous_year_sales,expected,delta=.02)
        self.assertAlmostEqual(first.previous_month_sales,before,delta=.02)
        partial=sb.yearly_comparison(filters('2026-10-01','2026-10-18'))
        self.assertFalse(partial.yoy_comparable.any());self.assertTrue(partial.mom_growth_pct.isna().all())

    def test_dataset_anchored_relative_dates_and_pair_tools(self):
        scope=filters('2026-01-01','2026-09-30')
        month=resolve_period('Which products sold the most last month?',scope)
        self.assertEqual((month.start,month.end),('2026-09-01','2026-09-30'))
        three=resolve_period('قارن خلال آخر ٣ شهور',scope)
        self.assertEqual((three.start,three.end),('2026-07-01','2026-09-30'))
        report=dispatch('Compare BR002 and BR001 last 3 months',sb.args(scope))
        self.assertEqual(report['meta']['period'],'2026-07-01 to 2026-09-30')
        self.assertEqual(report['meta']['location_types'][0]['branch_id'],'BR002')

    def test_assistant_values_match_service_and_preserve_executive(self):
        context=Context('English',filters('2026-01-01','2026-09-30',category='Socks'))
        for q,name in [('What were the monthly sales trends?','sales4_trends'),('Which branches generated the highest revenue?','location_ranking'),('ايه أقل الفروع مبيعات؟','location_ranking'),('Which locations experienced declining sales?','declining_locations')]:
            text,reports=offline_answer(q,context)
            self.assertEqual(reports[0]['meta']['tool'],name)
            self.assertIn('2026-01-01',text)
        _,reports=offline_answer('Show company sales',context)
        self.assertEqual(reports[0]['meta']['tool'],'company_overview')
        self.assertEqual(reports[1]['meta']['tool'],'executive_summary')
        _,pair=offline_answer('Compare BR001 and BR002',context)
        expected=sb.compare_two('2026-01-01','2026-09-30','BR001','BR002',category='Socks')['table']
        self.assertAlmostEqual(pair[0]['data'][0]['location_a'],expected.iloc[0].location_a,delta=.000001)

    def test_daily_weekly_yearly_totals_and_no_customer_record_columns(self):
        expected=api.overview('2026-09-01','2026-10-18')
        for grain in sb.GRAINS:
            frame=sb.sales_trends('2026-09-01','2026-10-18',grain=grain)
            self.assertAlmostEqual(frame.sales.sum(),expected['sales'],delta=.02)
            self.assertEqual(frame.units.sum(),expected['units'])
            self.assertNotIn('customer_id',frame)
            self.assertFalse(frame.is_complete_period.all()) if grain!='daily' else None


@unittest.skipUnless(api.DB.exists(),'Build the local database for UI tests')
class SalesBranchUITests(unittest.TestCase):
    def app(self):return AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
    def clean(self,p):
        self.assertFalse(p.exception,[e.message for e in p.exception]);self.assertFalse(p.error,[e.value for e in p.error])

    def test_sales_all_grains_and_localization(self):
        p=self.app();p.sidebar.radio[1].set_value('Sales Analytics').run()
        for language in ('English','العربية'):
            p.sidebar.radio(key='language').set_value(language).run()
            suffix='_en' if language=='English' else '_ar'
            for grain in sb.GRAINS:
                p.selectbox(key='s4_grain'+suffix).set_value(grain).run();self.clean(p)
                self.assertIn(t('units',language),[m.label for m in p.metric])
            self.assertIn(t('s4_season_note',language),[c.value for c in p.caption])

    def test_detail_and_cross_type_pair_keep_global_filters(self):
        p=self.app();p.sidebar.selectbox(key='filter_type_ar').set_value('Retail branch').run()
        p.sidebar.selectbox(key='filter_category_ar').set_value('Socks').run()
        p.sidebar.radio[1].set_value('Branch Performance').run()
        before=dict(p.session_state['active_scope'])
        p.radio(key='b4_mode_ar').set_value('detail').run();self.clean(p)
        self.assertIn('b4_detail',p.session_state)
        p.radio(key='b4_mode_ar').set_value('pair').run();self.clean(p)
        master=api.branches();pos=master.query("retail_location_type=='Point of sale / reseller'").branch_id.iloc[0]
        retail=master.query("retail_location_type=='Retail branch'").branch_id.iloc[0]
        p.selectbox(key='b4_a_ar').set_value(retail).run();self.clean(p)
        p.selectbox(key='b4_b_ar').set_value(pos).run();self.clean(p)
        self.assertEqual(dict(p.session_state['active_scope']),before)
        self.assertIn(t('b4_pair_scope','العربية'),[i.value for i in p.info])
        self.assertEqual(len(p.dataframe[0].value),8)
        self.assertEqual(p.button(key='assistant_access').label,t('ask','العربية'))
        p.sidebar.radio(key='language').set_value('English').run();self.clean(p)
        self.assertEqual(p.selectbox(key='b4_b_en').value,pos)

    def test_no_orders_and_partial_dates_preserve_honest_states(self):
        p=self.app();first,_=api.metadata()
        p.sidebar.date_input(key='filter_dates').set_value((first,first)).run()
        p.sidebar.radio[1].set_value('Branch Performance').run();self.clean(p)
        self.assertIn(t('b4_no_sales_note','العربية'),[c.value for c in p.caption])
        p.sidebar.radio[1].set_value('Sales Analytics').run();self.clean(p)
        self.assertIn(t('coverage_unavailable','العربية'),[w.value for w in p.warning])

    def test_primary_ranking_keeps_names_and_selected_metric_visible(self):
        p=self.app();p.sidebar.radio[1].set_value('Branch Performance').run()
        for key in ('sales','units','customers','aov','gross_profit','growth_pct'):
            p.selectbox(key='branch_rank_ar').set_value(key).run();self.clean(p)
            first=p.dataframe[0].value
            self.assertLessEqual(len(first.columns),6)
            self.assertIn(t('branch','العربية'),first)
            self.assertIn(t(key,'العربية'),first)
            self.assertEqual(len(first),80)

if __name__=='__main__':unittest.main()
