"""Phase 3 service contracts and actual executive UI integration."""
from datetime import date
from pathlib import Path
import unittest
import pandas as pd
from streamlit.testing.v1 import AppTest
import analytics as api
from services import executive as ex
from ui.data import Context
from ui.assistant import offline_answer
from ui.i18n import t,ltr
from services.filters import filters

ROOT=Path(__file__).resolve().parents[1]

class ExecutiveUnitTests(unittest.TestCase):
    def test_arabic_percentage_sign_direction_is_isolated(self):
        from unittest.mock import patch
        from ui.components import metric
        with patch('ui.components.st.metric') as render:
            metric('growth_pct',-10,'العربية','pct')
            self.assertEqual(render.call_args.args[1],'\u2066-10.0%\u2069')
            metric('gross_margin_pct',38.34,'العربية','pct')
            self.assertEqual(render.call_args.args[1],'\u206638.3%\u2069')

    def values(self,**updates):
        return dict(sales=100.,gross_profit=40.,orders=2,aov=50.,customers=1,branches=1,gross_margin_pct=40.,**updates)

    def test_comparison_coverage_suppresses_previous_and_changes(self):
        result=ex.comparison(self.values(),self.values(),False)
        self.assertTrue(result.previous.isna().all())
        self.assertTrue(result.absolute_change.isna().all())
        self.assertTrue(result.percentage_change.isna().all())
        self.assertTrue(result.state.eq('unavailable').all())

    def test_comparison_zero_previous_and_empty_ratios(self):
        previous=self.values();previous.update(sales=0,orders=0,aov=0,gross_margin_pct=0)
        result=ex.comparison(self.values(),previous,True).set_index('metric')
        self.assertEqual(result.loc['sales','absolute_change'],100)
        self.assertTrue(pd.isna(result.loc['sales','percentage_change']))
        self.assertTrue(pd.isna(result.loc['aov','previous']))
        self.assertTrue(pd.isna(result.loc['gross_margin_pct','previous']))

    def test_margin_delta_is_percentage_points_and_direction_is_explicit(self):
        previous=self.values();previous.update(gross_margin_pct=30,sales=200)
        result=ex.comparison(self.values(),previous,True).set_index('metric')
        self.assertEqual(result.loc['gross_margin_pct','absolute_change'],10)
        self.assertAlmostEqual(result.loc['gross_margin_pct','percentage_change'],100/3)
        self.assertEqual(result.loc['sales','state'],'negative')
        self.assertEqual(result.loc['customers','state'],'unchanged')

    def test_disappeared_category_and_uncovered_categories(self):
        current=pd.DataFrame({'category':['A'],'sales':[20000.]})
        previous=pd.DataFrame({'category':['A','B'],'sales':[10000.,10000.]})
        result=ex.category_changes(current,previous,True).set_index('category')
        self.assertEqual(result.loc['B','growth_pct'],-100)
        self.assertTrue(ex.category_changes(current,previous,False).growth_pct.isna().all())

    def test_alert_threshold_boundaries_and_no_causal_prose(self):
        growth={'comparable_coverage':True,'growth_pct':-10}
        branches=pd.DataFrame({'growth_pct':[-.1,0,None]})
        stock=pd.DataFrame({'risk_score':[.699,.7]})
        changes=pd.DataFrame({'category':['A','B','C'],'sales':[12500,12499,7500],
            'previous_sales':[10000,9999,10000],'growth_pct':[25,25,-25]})
        alerts=ex.insight_rules(growth,branches,stock,changes,1)
        codes=[a['code'] for a in alerts]
        for code in ('revenue_decline','negative_locations','inventory_attention','partial_months'):self.assertIn(code,codes)
        self.assertEqual(codes.count('category_change'),2)
        self.assertEqual(next(a['count'] for a in alerts if a['code']=='inventory_attention'),1)

    def test_zero_and_uncovered_alerts_not_false_growth(self):
        branches=pd.DataFrame({'growth_pct':pd.Series([],dtype=float)})
        stock=pd.DataFrame({'risk_score':pd.Series([],dtype=float)})
        changes=pd.DataFrame(columns=['category','sales','previous_sales','growth_pct']).astype({'previous_sales':float,'growth_pct':float})
        for covered,code in [(False,'coverage_unavailable'),(True,'zero_baseline')]:
            codes=[a['code'] for a in ex.insight_rules({'comparable_coverage':covered,'growth_pct':None},branches,stock,changes,0)]
            self.assertIn(code,codes);self.assertNotIn('revenue_decline',codes)


@unittest.skipUnless(api.DB.exists(),'Build the original local database')
class ExecutiveDataTests(unittest.TestCase):
    def reconcile(self,scope):
        data=ex.dashboard(**scope)
        expected=api.overview(**scope)
        for key,value in expected.items():
            self.assertEqual(data['current'][key],value,key)
        for frame in (data['monthly'],data['branches'],data['categories'],data['channels']):
            self.assertAlmostEqual(float(frame.sales.sum()),expected['sales'],delta=.02)
        for frame in (data['monthly'],data['branches'],data['categories']):
            self.assertAlmostEqual(float(frame.gross_profit.sum()),expected['gross_profit'],delta=.02)
        self.assertEqual(int(data['monthly'].orders.sum()),expected['orders'])
        self.assertEqual(data['current']['growth_pct'],api.sales_growth(**scope)['growth_pct'])
        return data

    def test_company_reconciles_all_aggregate_views(self):
        data=self.reconcile(dict(start='2026-01-01',end='2026-09-30'))
        self.assertEqual(data['network']['Retail branch'],52)
        self.assertEqual(data['network']['Point of sale / reseller'],28)
        self.assertFalse(data['partial_months'])
        self.assertTrue(data['growth']['comparable_coverage'])

    def test_location_category_type_intersections_and_stock(self):
        for kind in ('Retail branch','Point of sale / reseller'):
            branch=api.branches().query('retail_location_type==@kind').branch_id.iloc[0]
            scope=dict(start='2026-08-01',end='2026-09-30',branch=branch,location_type=kind,category='Socks')
            data=self.reconcile(scope)
            self.assertEqual(set(data['branches'].branch_id),{branch})
            month,stock=api.inventory_snapshot(scope['end'],branch,location_type=kind,category='Socks')
            self.assertEqual(data['stock_month'],month)
            self.assertEqual(data['current']['stock_units'],api.inventory_summary(stock)['stock_units'])
            self.assertEqual(set(data['stock'].category),{'Socks'})

    def test_full_coverage_boundary_comparison_is_unavailable(self):
        first,last=api.metadata()
        data=ex.summary(str(first),str(last))
        self.assertFalse(data['growth']['comparable_coverage'])
        self.assertIsNone(data['current']['growth_pct'])
        self.assertTrue(data['comparison'].previous.isna().all())

    def test_empty_scope_and_missing_stock_use_unavailable_not_invented_values(self):
        data=ex.dashboard('2010-01-01','2010-01-31')
        self.assertEqual(data['current']['sales'],0)
        self.assertEqual(data['current']['orders'],0)
        self.assertIsNone(data['current']['stock_units'])
        self.assertIsNone(data['stock_month'])
        self.assertTrue(data['monthly'].empty)
        self.assertTrue(data['branches'].empty)

    def test_partial_months_and_same_day_previous_period(self):
        data=self.reconcile(dict(start='2026-09-15',end='2026-10-18',category='Socks'))
        self.assertEqual(data['partial_months'],2)
        self.assertTrue(data['partial_boundary'])
        self.assertFalse(data['monthly'].is_complete_month.any())
        g=data['growth']
        self.assertEqual((date.fromisoformat(g['previous_end'])-date.fromisoformat(g['previous_start'])).days,33)
        self.assertTrue(g['comparable_coverage'])

    def test_local_assistant_executive_summary_matches_service(self):
        for branch in (None,api.branches().branch_id.iloc[0]):
            scope=filters('2026-01-01','2026-09-30',branch,category='Socks')
            ctx=Context('English',scope)
            _,reports=offline_answer('Show company sales',ctx)
            self.assertEqual(reports[0]['meta']['tool'],'company_overview')
            extra=next(r for r in reports if r['meta']['tool']=='executive_summary')
            expected=ex.summary(**ctx.assistant_scope())['current']
            for key in ('sales','gross_profit','gross_margin_pct','orders','aov','customers','branches','growth_pct','stock_units','stock_value','high_risk_categories'):
                self.assertEqual(extra['data'][0][key],expected[key],key)
            for key in ('sales','gross_profit','orders','customers'):
                self.assertAlmostEqual(reports[0]['data'][0][key],expected[key],delta=.02)


@unittest.skipUnless(api.DB.exists(),'Build the local database for UI execution')
class ExecutiveUITests(unittest.TestCase):
    def test_scorecards_comparison_and_navigation_preserve_scope(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
        for language in ('English','العربية'):
            app.sidebar.radio(key='language').set_value(language).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            labels={m.label for m in app.metric}
            for key in ('sales','gross_profit','gross_margin_pct','orders','aov','customers','branches','growth_pct','stock_units','stock_value','high_risk_categories'):
                self.assertIn(t(key,language),labels)
            self.assertEqual(len(app.dataframe[0].value),7)
            month=ex.summary(**dict(app.session_state['active_scope']))['stock_month']
            self.assertIn(t('stock_note',language,month=ltr(month,language)),[c.value for c in app.caption])
        before=dict(app.session_state['active_scope'])
        app.button(key='executive_open_branches').click().run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        self.assertEqual(app.session_state['page'],'Branch Performance')
        self.assertEqual(dict(app.session_state['active_scope']),before)

    def test_partial_dates_render_explicit_warning_and_unavailable_growth(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
        first,_=api.metadata()
        app.sidebar.date_input(key='filter_dates').set_value((first,first)).run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        self.assertIn(t('coverage_unavailable','العربية'),[w.value for w in app.warning])
        self.assertEqual(next(m.value for m in app.metric if m.label==t('growth_pct','العربية')),t('unavailable','العربية'))

if __name__=='__main__':unittest.main()
