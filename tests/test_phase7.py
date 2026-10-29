"""Temporal leakage, model/metric contracts and real bilingual forecasting UI."""
from pathlib import Path
from contextlib import closing
import sqlite3,tempfile,unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
import analytics as api
import db.connection as connection
from services import forecasting as fc,forecast_models as fm
from services.forecast_tools import answer_readonly,dispatch
from services.filters import filters
from ui.assistant import offline_answer
from ui.data import Context
from ui.i18n import t,CATEGORIES
from test_phase1 import fixture

ROOT=Path(__file__).resolve().parents[1]


def series(n=96):
    values=100+np.arange(n)*1.5+10*np.sin(np.arange(n)*2*np.pi/12)
    return pd.DataFrame(dict(month=pd.period_range('2018-01',periods=n,freq='M').astype(str),value=values))


class ForecastModelTests(unittest.TestCase):
    def test_metrics_known_answers_and_zero_denominators(self):
        m=fm.metrics([100,0],[110,10]);self.assertEqual(m['mae'],10);self.assertEqual(m['wape_pct'],20)
        self.assertEqual(m['bias'],10);self.assertEqual(m['bias_pct'],20);self.assertEqual(m['rmse'],10)
        self.assertAlmostEqual(m['smape_pct'],(200*10/210+200)/2)
        m=fm.metrics([0,0],[0,0]);self.assertIsNone(m['wape_pct']);self.assertIsNone(m['bias_pct']);self.assertEqual(m['smape_pct'],0)
        self.assertIsNone(fm.metrics([1e-12],[2e-12])['wape_pct'])
        with self.assertRaises(ValueError):fm.metrics([],[])

    def test_baselines_are_exact_and_horizon_aligned(self):
        data=series(36);y=np.arange(1,37,dtype=float);ps=pd.PeriodIndex(data.month,freq='M')
        np.testing.assert_array_equal(fm.predict('naive',y,ps,6),[36]*6)
        np.testing.assert_array_equal(fm.predict('seasonal_naive',y,ps,6),[25,26,27,28,29,30])
        np.testing.assert_array_equal(fm.predict('moving_average',y,ps,3),[33.5]*3)
        with self.assertRaises(ValueError):fm.predict('naive',y,ps,2)

    def test_lag_rolling_features_never_include_target(self):
        y=np.arange(1,21,dtype=float);months=pd.period_range('2020-01',periods=20,freq='M')
        x,target=fm.supervised(y,months)
        self.assertEqual(x[0,0],12);self.assertEqual(x[0,5],11);self.assertEqual(x[0,7],6.5);self.assertEqual(target[0],13)
        y[12:]=999999;other,_=fm.supervised(y,months);np.testing.assert_array_equal(x[0],other[0])

    def test_recursive_lags_use_previous_prediction(self):
        data=series(36);seen=[];original=fm.lag_features
        def spy(history,month):seen.append(list(history));return original(history,month)
        with patch.object(fm,'lag_features',side_effect=spy):prediction=fm.predict('ridge_lags',data.value,data.month,3)
        self.assertEqual([len(x) for x in seen[-3:]],[36,37,38])
        self.assertAlmostEqual(seen[-2][-1],prediction[0]);self.assertAlmostEqual(seen[-1][-1],prediction[1])

    def test_validation_selection_and_bands_ignore_final_test_values(self):
        data=series();a=fc.evaluate(data,3)
        altered=data.copy();altered.loc[84:,'value']*=100
        b=fc.evaluate(altered,3)
        self.assertEqual(a['selection'],b['selection'])
        pd.testing.assert_frame_equal(a['backtests'].query("stage=='validation'"),b['backtests'].query("stage=='validation'"))
        self.assertNotEqual(a['metrics']['wape_pct'],b['metrics']['wape_pct'])

    def test_chronology_final_test_and_forecast_months(self):
        d=series();result=fc.evaluate(d,6);splits=result['split_schedule']
        self.assertTrue((splits.training_end<splits.target_start).all())
        self.assertTrue(splits.query("stage=='validation'").target_end.lt(result['test_start']).all())
        test=splits.query("stage=='test'")
        self.assertEqual(len(test),2);self.assertLess(test.iloc[0].target_end,test.iloc[1].target_start)
        self.assertEqual(result['forecasts'].month.tolist(),pd.period_range('2026-01',periods=6,freq='M').astype(str).tolist())

    def test_selection_requires_real_validation_improvement(self):
        rows=[]
        for i in range(7):
            for model,error in [('naive',20),('seasonal_naive',30),('moving_average',40),('ridge_lags',5)]:
                rows.append(dict(stage='validation',origin=str(i),lead=1,forecast_model=model,actual=100,predicted=100+error))
        frame=pd.DataFrame(rows);scores=fm.score_rows(frame,'validation',1)
        chosen,baseline,_=fm.choose(scores,frame,1);self.assertEqual(chosen,'ridge_lags');self.assertEqual(baseline,'naive')
        frame.loc[frame.forecast_model.eq('ridge_lags'),'predicted']=150
        chosen,baseline,_=fm.choose(fm.score_rows(frame,'validation',1),frame,1);self.assertEqual(chosen,baseline)

    def test_uncertainty_uses_validation_only_by_lead(self):
        frame=pd.DataFrame([dict(stage='validation',forecast_model='naive',lead=1,actual=10,predicted=p) for p in [10,11,12,13,14]])
        frame=pd.concat([frame,pd.DataFrame([dict(stage='test',forecast_model='naive',lead=1,actual=10,predicted=99999)])],ignore_index=True)
        self.assertAlmostEqual(fm.uncertainty(frame,'naive',1)[0],3.2)
        self.assertIsNone(fm.uncertainty(frame.iloc[:4],'naive',1)[0])

    def test_sparse_fallback_does_not_force_regression(self):
        d=series();d['value']=0.;d.loc[::6,'value']=100
        result=fc.evaluate(d,3)
        self.assertEqual(result['state'],'experimental');self.assertIn(result['model'],fm.BASELINES)
        self.assertTrue(set(result['comparison'].forecast_model)<=set(fm.BASELINES))

    def test_missing_zero_and_insufficient_histories(self):
        d=series();d.loc[10,'value']=np.nan;self.assertEqual(fc.evaluate(d)['reason'],'f7_missing')
        d=series();d['value']=0;self.assertEqual(fc.evaluate(d)['reason'],'f7_zero')
        self.assertEqual(fc.evaluate(series(59))['reason'],'f7_insufficient')
        result=fc.evaluate(series(60));self.assertEqual(result['state'],'experimental');self.assertTrue(all(x is None for x in result['band_widths']))

    def test_invalid_month_order_and_nonnegative_predictions(self):
        with self.assertRaises(ValueError):fc.evaluate(series().iloc[::-1])
        with self.assertRaises(ValueError):fc.evaluate(series().drop(index=10))
        d=series(36)
        for model in fm.MODELS:self.assertTrue((fm.predict(model,d.value,d.month,3)>=0).all())


class ForecastHistoryFixtureTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);path=Path(tmp.name)/'fixture.db';fixture(path)
        with closing(sqlite3.connect(path)) as db,db:
            db.executescript("INSERT INTO sales_orders VALUES ('O5','2024-03-31','B2',NULL,'Store',0); INSERT INTO sales_order_items VALUES ('L7','O5','2024-03-31','B2','P1',0,0,0);")
        change=patch.object(connection,'DB_PATH',path);change.start();self.addCleanup(change.stop)

    def test_complete_month_exclusion_and_asof_boundaries(self):
        frame,bounds=fc.monthly_history(as_of='2024-03-18')
        self.assertEqual(bounds,('2024-01-01','2024-02-29'));self.assertEqual(frame.month.tolist(),['2024-01','2024-02'])
        self.assertEqual(fc.monthly_history(as_of='2024-02-28')[0].month.tolist(),['2024-01'])

    def test_absence_is_missing_but_recorded_zero_stays_zero(self):
        frame,_=fc.monthly_history('B2')
        self.assertTrue(pd.isna(frame.iloc[0].value));self.assertFalse(frame.iloc[0].recorded_month)
        self.assertEqual(frame.iloc[-1].value,0);self.assertTrue(frame.iloc[-1].recorded_month)

    def test_revenue_and_category_units_use_approved_aggregates(self):
        company,_=fc.monthly_history();a,_=fc.monthly_history(category='A')
        self.assertEqual(company.value.iloc[0],380);self.assertEqual(a.value.iloc[0],2)
        retail,_=fc.monthly_history(location_type='Retail branch');self.assertEqual(retail.value.iloc[0],380)
        report=fc.forecast_report(category='A');self.assertEqual(report['target'],'units');self.assertEqual(report['state'],'unavailable')


@unittest.skipUnless(api.DB.exists(),'Build local database')
class ForecastIntegrationTests(unittest.TestCase):
    def test_actual_source_boundary_and_target_reconciliation(self):
        history,bounds=fc.monthly_history();self.assertEqual(bounds,('2018-11-01','2026-09-30'));self.assertEqual(len(history),95)
        self.assertNotIn('2026-10',history.month.tolist())
        expected=api.overview(*bounds)['sales'];self.assertAlmostEqual(history.value.sum(),expected,delta=.02)
        category,_=fc.monthly_history(category='Socks');self.assertAlmostEqual(category.value.sum(),api.overview(*bounds,category='Socks')['units'])

    def test_data_version_cache_and_copy_isolation(self):
        fc._cached.cache_clear();a=fc.forecast_report(horizon=1);hits=fc._cached.cache_info().hits
        a['forecasts'].loc[0,'central']=-999
        b=fc.forecast_report(horizon=1);self.assertGreater(fc._cached.cache_info().hits,hits);self.assertGreaterEqual(b['forecasts'].central.iloc[0],0)
        for invalid in (True,1.0,2,'3',None):
            with self.assertRaises(ValueError):fc.forecast_report(horizon=invalid)

    def test_bounded_bilingual_tools_and_clarification(self):
        scope=Context('English',filters('2026-01-01','2026-09-30'))
        for question,tool in [('Forecast company sales for next month.','forecast7_values'),('What are expected sales for next 3 months?','forecast7_values'),('What is the forecast accuracy?','forecast7_accuracy'),('What model performed best against the baseline?','forecast7_accuracy'),('توقع مبيعات الشهر الجاي.','forecast7_values'),('إيه المبيعات المتوقعة لفرع BR001؟','forecast7_values'),('النموذج دقته قد إيه؟','forecast7_accuracy')]:
            _,reports=offline_answer(question,scope);self.assertEqual(reports[0]['meta']['tool'],tool)
        self.assertEqual(dispatch('توقع الطلب على فئة معينة خلال 3 شهور.',scope.assistant_scope(),CATEGORIES),{'clarify':'f7_category_request'})
        self.assertEqual(dispatch('Forecast sales next 12 months',scope.assistant_scope()),{'clarify':'f7_horizon_request'})
        self.assertIn('clarify',dispatch('Compare expected demand across two categories',scope.assistant_scope()))
        self.assertIsNone(dispatch('Which categories may require replenishment?',scope.assistant_scope()))
        self.assertIn('clarify',dispatch('Forecast SKU sales',scope.assistant_scope()))

    def test_service_dashboard_assistant_parity_and_category_pair(self):
        scope=dict(start='2026-01-01',end='2026-09-30',category='Socks')
        direct=fc.forecast_report(category='Socks',horizon=3);tool=answer_readonly('forecast7_values',scope,{'horizon':3})
        self.assertEqual(tool['meta']['target'],'units');self.assertEqual(tool['meta']['origin'],direct['origin'])
        self.assertAlmostEqual(tool['data'][0]['central'],direct['forecasts'].central.iloc[0],places=7)
        pair=answer_readonly('forecast7_categories',scope,{'categories':['Socks','Men underwear'],'horizon':1})
        self.assertEqual(len(pair['data']),2);self.assertNotIn('customer_id',str(pair))
        with self.assertRaises(ValueError):answer_readonly('sql',scope)

    def test_ui_modes_and_horizons_both_languages(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run();app.sidebar.radio[1].set_value('Demand Forecasting').run()
        for lang,suffix in [('English','_en'),('العربية','_ar')]:
            app.sidebar.radio(key='language').set_value(lang).run()
            for horizon in (1,3,6):
                app.selectbox(key='f7_horizon'+suffix).set_value(horizon).run()
                self.assertFalse(app.exception,[e.message for e in app.exception]);self.assertFalse(app.error)
            for mode in ('f7_overview','f7_models','f7_backtests','f7_uncertainty'):
                app.selectbox(key='f7_mode'+suffix).set_value(mode).run();self.assertFalse(app.exception);self.assertFalse(app.error)
            self.assertEqual(app.button(key='assistant_access').label,t('ask',lang))

    def test_ui_location_category_filters_and_display_dates_do_not_retrain(self):
        from datetime import date
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run();app.sidebar.radio[1].set_value('Demand Forecasting').run()
        origin=app.metric[2].value
        app.sidebar.date_input(key='filter_dates').set_value((date(2020,1,1),date(2020,12,31))).run()
        self.assertEqual(app.metric[2].value,origin)
        app.sidebar.selectbox(key='filter_branch_ar').set_value('BR001').run()
        app.sidebar.selectbox(key='filter_category_ar').set_value('Socks').run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        self.assertIn('Socks',app.session_state['active_scope']['category'])


if __name__=='__main__':unittest.main()
