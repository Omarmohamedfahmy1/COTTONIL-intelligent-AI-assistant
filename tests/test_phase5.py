"""Profitability edge cases, authoritative reconciliation and bilingual UI flows."""
from pathlib import Path
import tempfile, unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
import analytics as api
import db.connection as connection
from services import profitability as p, sales_branch as sb
from services.profitability_tools import answer_readonly, dispatch
from services.filters import filters
from test_phase1 import fixture
from ui.i18n import t
from ui.data import Context
from ui.assistant import offline_answer

ROOT=Path(__file__).resolve().parents[1]


class ProfitabilityFixtureTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        path=Path(temp.name)/'test.db';fixture(path)
        change=patch.object(connection,'DB_PATH',path);change.start();self.addCleanup(change.stop)

    def test_mixed_category_order_totals_not_multiplied(self):
        data=p.dashboard('2024-01-01','2024-01-31')
        self.assertEqual(data['current']['sales'],380);self.assertEqual(data['current']['gross_profit'],150)
        for key in ('products','categories','locations','monthly','category_monthly'):
            self.assertEqual(data[key].sales.sum(),380);self.assertEqual(data[key].gross_profit.sum(),150)

    def test_weighted_margin_is_ratio_of_totals(self):
        data=p.dashboard('2024-01-01','2024-01-31')
        self.assertAlmostEqual(data['current']['gross_margin_pct'],150/380*100)
        self.assertNotAlmostEqual(data['products'].gross_margin_pct.mean(),150/380*100)
        self.assertAlmostEqual(data['monthly'].gross_margin_pct.iloc[0],150/380*100)

    def test_category_and_location_filters_and_company_denominator(self):
        data=p.dashboard('2024-01-01','2024-01-31','B1',location_type='Retail branch',category='A')
        self.assertEqual(data['current']['gross_profit'],60)
        self.assertEqual(data['company_gross_profit'],150)
        self.assertEqual(data['current']['company_gp_share_pct'],40)
        self.assertEqual(set(data['locations'].branch_id),{'B1'})
        self.assertEqual(data['categories'].scoped_gp_share_pct.iloc[0],100)
        with self.assertRaises(ValueError):p.dashboard('2024-01-01','2024-01-31','B2',location_type='Retail branch')

    def test_zero_sales_margin_and_empty_period(self):
        data=p.dashboard('2024-02-29','2024-02-29')
        self.assertEqual(data['current']['orders'],1)
        self.assertIsNone(data['current']['gross_margin_pct'])
        self.assertTrue(data['products'].gross_margin_pct.isna().all())
        self.assertTrue(p.rank_products(data['products'],'gross_margin_pct').empty)
        empty=p.dashboard('2010-01-01','2010-01-31')
        self.assertTrue(empty['monthly'].empty);self.assertIsNone(empty['current']['company_gp_share_pct'])
        self.assertTrue(empty['category_changes'].gp_change.isna().all())

    def test_rank_minimums_do_not_mutate_totals_and_reject_bad_input(self):
        frame=p.products(filters('2024-01-01','2024-01-31'));before=frame.copy(deep=True)
        self.assertEqual(len(p.rank_products(frame,'sales',min_revenue=200)),1)
        self.assertEqual(len(p.rank_products(frame,'units',min_units=3)),1)
        self.assertEqual(p.rank_products(frame,'sales',True).iloc[0].product_id,'P3')
        pd.testing.assert_frame_equal(before,frame)
        for value in (-1,float('nan'),float('inf'),True,'bad'):
            with self.assertRaises(ValueError):p.rank_products(frame,min_units=value)
        with self.assertRaises(ValueError):p.rank_products(frame,'DROP TABLE')

    def test_screening_strict_and_inclusive_boundaries(self):
        frame=pd.DataFrame(dict(product_id=['a','b','c','d'],has_recorded_lines=[True]*4,
            sales=[100000,100000,1,0],units=[500,500,99,0],gross_margin_pct=[29.9,30,45,float('nan')],
            gross_profit=[29900,30000,.45,0],company_gp_share_pct=[10,10,.0001,0]))
        groups=p.screen_products(frame)
        self.assertEqual(groups['p5_high_volume_low'].product_id.tolist(),['a'])
        self.assertEqual(groups['p5_high_revenue_low'].product_id.tolist(),['a'])
        self.assertEqual(groups['p5_lower_volume_high'].product_id.tolist(),['c'])
        self.assertEqual(groups['p5_high_contributors'].product_id.tolist(),['a','b'])
        with self.assertRaises(ValueError):p.ScreeningRules(low_margin=60,high_margin=40)
        with self.assertRaises(ValueError):p.ScreeningRules(lower_units=501)

    def test_signed_contribution_and_zero_denominator(self):
        frame=pd.DataFrame({'sales':[100,50],'gross_profit':[120,-20]})
        result=p.enrich(frame,100,100)
        self.assertEqual(result.company_gp_share_pct.tolist(),[120,-20])
        self.assertTrue(p.enrich(frame,0,0).company_gp_share_pct.isna().all())

    def test_complete_partial_and_uncovered_baseline(self):
        full=p.dashboard('2024-01-01','2024-01-31')
        self.assertTrue(full['monthly'].is_complete_period.all())
        partial=p.dashboard('2024-01-02','2024-01-31')
        self.assertFalse(partial['monthly'].is_complete_period.all())
        self.assertTrue(full['category_changes'].previous_gross_profit.isna().all())

    def test_ceased_sales_and_zero_previous_gp(self):
        data=p.dashboard('2024-01-03','2024-01-04')
        change=data['category_changes'].set_index('category')
        self.assertEqual(change.loc['A','gp_growth_pct'],-100)
        self.assertEqual(change.loc['A','gp_change'],-60)
        self.assertEqual(set(data['declining_categories'].category),{'A','B'})
        self.assertTrue(data['location_changes'].loc[data['location_changes'].branch_id.eq('B3'),'gp_growth_pct'].isna().all())

    def test_refunds_return_date_do_not_adjust_gp(self):
        january=p.dashboard('2024-01-01','2024-01-31')
        february=p.dashboard('2024-02-01','2024-02-29')
        self.assertEqual(january['current']['refunds'],10);self.assertEqual(february['current']['refunds'],70)
        self.assertEqual(january['current']['gross_profit'],150)
        self.assertIsNone(january['net_profit']);self.assertIsNone(january['return_adjusted_gross_profit'])
        self.assertIsNone(january['current']['refund_adjusted_sales'])

    def test_anonymous_orders_preserved(self):
        data=p.dashboard('2024-01-01','2024-01-31')
        self.assertEqual(data['current']['anonymous_orders'],1);self.assertEqual(data['current']['customers'],1)
        self.assertEqual(data['current']['orders'],2)

    def test_assistant_uses_identical_service_and_safe_columns(self):
        scope=dict(start='2024-01-01',end='2024-01-31',category='A')
        report=answer_readonly('profit5_products',scope)
        expected=p.rank_products(p.products(filters(**scope))).iloc[0]
        self.assertEqual(report['data'][0]['gross_profit'],expected.gross_profit)
        self.assertEqual(report['data'][0]['company_gp_share_pct'],expected.company_gp_share_pct)
        self.assertNotIn('customer_id',str(report));self.assertNotIn('employee_id',str(report))
        for name in ('profit5_categories','profit5_locations','profit5_trends','profit5_screening','profit5_leaders'):
            self.assertIn('data',answer_readonly(name,scope))
        for limit in (0,21,True):
            with self.assertRaises(ValueError):answer_readonly('profit5_products',scope,{'limit':limit})
        with self.assertRaises(ValueError):answer_readonly('sql',scope)


@unittest.skipUnless(api.DB.exists(),'Build local database')
class ProfitabilityIntegrationTests(unittest.TestCase):
    def test_bilingual_questions_and_clarifications(self):
        ctx=Context('English',filters('2026-01-01','2026-09-30',category='Socks'))
        cases=[('Which products generated the highest gross profit?','profit5_products'),
            ('Which branches have the highest gross margin?','profit5_locations'),
            ('Which products sell a lot but have low margins?','profit5_screening'),
            ('What are the most profitable categories?','profit5_categories'),
            ('ايه أكتر المنتجات اللي بتكسب الشركة؟','profit5_products'),
            ('إيه الفرق بين أعلى المنتجات مبيعًا وأعلى المنتجات ربحية؟','profit5_leaders')]
        for q,expected in cases:
            _,reports=offline_answer(q,ctx);self.assertEqual(reports[0]['meta']['tool'],expected)
        for q in ('Compare gross profit between two branches.','قارن ربحية فرعين خلال نفس الفترة.'):
            self.assertEqual(dispatch(q,ctx.assistant_scope()),{'clarify':'two_ids_required'})
        self.assertIsNone(dispatch('Show company sales',ctx.assistant_scope()))
        self.assertIn('clarify',dispatch('net profit',ctx.assistant_scope()))
        self.assertEqual(dispatch('Product profit next year',ctx.assistant_scope()),{'clarify':'time_scope_request'})

    def test_pair_types_order_and_shared_financial_values(self):
        scope=dict(start='2026-01-01',end='2026-09-30',category='Socks')
        result=dispatch('Compare gross profit BR002 and BR001',scope)
        self.assertEqual(result['meta']['location_types'][0]['branch_id'],'BR002')
        row=next(r for r in result['data'] if r['metric']=='gross_profit')
        self.assertAlmostEqual(row['location_a'],api.overview(**scope,branch='BR002')['gross_profit'])
        self.assertAlmostEqual(row['location_b'],api.overview(**scope,branch='BR001')['gross_profit'])

    def test_ui_modes_both_languages_and_rank_controls(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
        app.sidebar.radio[1].set_value('Profitability Analysis').run()
        for lang,suffix in (('English','_en'),('العربية','_ar')):
            app.sidebar.radio(key='language').set_value(lang).run()
            for mode in ('p5_overview','p5_products','p5_categories','p5_locations','p5_screening'):
                app.selectbox(key='p5_mode'+suffix).set_value(mode).run()
                self.assertFalse(app.exception,[e.message for e in app.exception]);self.assertFalse(app.error)
                self.assertEqual(len(app.metric),6)
            app.selectbox(key='p5_mode'+suffix).set_value('p5_products').run()
            initial=[m.value for m in app.metric]
            for rank in p.RANKS:
                app.selectbox(key='p5_rank'+suffix).set_value(rank).run()
                self.assertFalse(app.exception)
            app.number_input(key='p5_min_revenue').set_value(1000000000.0).run()
            self.assertEqual([m.value for m in app.metric],initial)
            self.assertIn(t('empty',lang),[m.value for m in app.info])

    def test_ui_global_filters_and_partial_month(self):
        from datetime import date
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
        app.sidebar.selectbox(key='filter_type_ar').set_value('Retail branch').run()
        branch=api.branches().query("retail_location_type=='Retail branch'").branch_id.iloc[0]
        app.sidebar.selectbox(key='filter_branch_ar').set_value(branch).run()
        app.sidebar.selectbox(key='filter_category_ar').set_value('Socks').run()
        app.sidebar.date_input(key='filter_dates').set_value((date(2026,10,1),date(2026,10,18))).run()
        app.sidebar.radio[1].set_value('Profitability Analysis').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('2026-10' in w.value for w in app.warning))
        before=dict(app.session_state['active_scope'])
        for mode in ('p5_products','p5_categories','p5_screening'):
            app.selectbox(key='p5_mode_ar').set_value(mode).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('2026-10' in w.value for w in app.warning))
        app.selectbox(key='p5_mode_ar').set_value('p5_locations').run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        self.assertEqual(app.selectbox(key='p5_location_ar').value,branch)
        self.assertEqual(dict(app.session_state['active_scope']),before)
        self.assertEqual(len(app.dataframe[0].value),1)


if __name__=='__main__':unittest.main()
