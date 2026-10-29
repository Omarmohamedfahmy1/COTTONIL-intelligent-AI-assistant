"""Known-answer customer histories, temporal models, privacy and real UI parity."""
from contextlib import closing
from datetime import date
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
import analytics as api
import db.connection as connection
from services import customer_data as cd,customers as cs,customer_models as cm
from services.customer_tools import answer_readonly,dispatch
from services.filters import filters
from ui.data import Context
from ui.assistant import offline_answer
from ui.i18n import t
from test_phase1 import fixture

ROOT=Path(__file__).resolve().parents[1]


def orders(rows):
    frame=pd.DataFrame(rows,columns=['customer_id','order_date','sales','branch_id'])
    frame['order_date']=pd.to_datetime(frame.order_date);frame['sales_order_id']=['T'+str(i) for i in range(len(frame))]
    return frame


def synthetic():
    rng=np.random.default_rng(4);rows=[]
    for month in pd.period_range('2018-01','2026-10',freq='M'):
        for customer in range(250):
            if rng.random()<.20:rows.append((f'FAKE{customer}',str(month)+'-05',float(rng.integers(100,1500)),'Synthetic'))
    return orders(rows)


class CustomerRulesTests(unittest.TestCase):
    def test_feature_exclusive_cutoff_and_lookback(self):
        frame=orders([('a','2024-01-01',10,'A'),('a','2024-12-31',20,'B'),('a','2025-01-01',999,'A'),(None,'2024-12-20',700,'A')])
        got=cd.features(frame,'2025-01-01').iloc[0]
        self.assertEqual(got.frequency,1);self.assertEqual(got.monetary,20);self.assertEqual(got.recency_days,0)

    def test_recency_frequency_monetary_boundaries(self):
        frame=pd.DataFrame(dict(recency_days=[30,31,90,91,180,181,270,271],frequency=[1,2,3,4,5,6,1,2],monetary=[500,501,1500,1501,3000,3001,6000,6001]))
        got=cd.score_rfm(frame)
        self.assertEqual(got.r_score.tolist(),[5,4,4,3,3,2,2,1]);self.assertEqual(got.m_score.tolist(),[1,2,2,3,3,4,4,5]);self.assertEqual(got.f_score.max(),5)
        self.assertEqual(got.c8_segment.iloc[-1],'c8_inactive')

    def test_features_do_not_change_when_future_sales_mutate(self):
        frame=orders([('a','2024-10-01',100,'A'),('a','2025-02-01',200,'B')]);original=cd.features(frame,'2025-01-01')
        frame.loc[1,'sales']=999999;pd.testing.assert_frame_equal(original,cd.features(frame,'2025-01-01'))

    def test_churn_label_boundaries_and_no_anonymous_assignment(self):
        frame=orders([('a','2024-12-31',100,'A'),('a','2025-01-01',20,'A'),('b','2024-12-31',100,'A'),('b','2025-06-30',20,'A'),(None,'2025-01-01',500,'A')])
        got=cm.labeled_cohort(frame,'2025-01-01','2025-12-31').set_index('customer_id')
        self.assertEqual(got.loc['a','churn_label'],0);self.assertEqual(got.loc['b','churn_label'],1);self.assertEqual(got.loc['a','future_revenue'],20);self.assertEqual(len(got),2)

    def test_censored_future_labels_rejected(self):
        frame=orders([('a','2024-12-31',100,'A')])
        with self.assertRaises(ValueError):cm.labeled_cohort(frame,'2025-01-01','2025-06-01')
        with self.assertRaises(ValueError):cm.labeled_cohort(frame,'2025-01-01','2025-12-30')

    def test_privacy_suppresses_additive_family_and_private_fields(self):
        frame=pd.DataFrame({'c8_segment':['a','b'],'c8_customers':[2,100],'c8_revenue':[10,999]})
        self.assertTrue(cd.protected(frame).empty)
        with self.assertRaises(ValueError):cd.protected(pd.DataFrame({'customer_id':['PRIVATE'],'c8_customers':[10]}))

    def test_cohorts_first_recorded_and_incomplete_future(self):
        frame=orders([(f'FAKE{i}',when,100,'A') for i in range(10) for when in ('2024-01-01','2024-02-02')])
        retention,summary=cs.cohorts(frame,'2024-01-01','2024-03-15','2024-01-01','2024-03-15')
        self.assertEqual(set(retention.c8_cohort),{'2024-01'});self.assertEqual(retention.c8_retention_pct.iloc[1],100)
        self.assertTrue(pd.isna(retention.loc[retention.c8_age.eq(2),'c8_retention_pct'].iloc[0]));self.assertEqual(summary.c8_median_second_days.iloc[0],32)

    def test_small_retention_complements_suppressed(self):
        frame=orders([(f'FAKE{i}','2024-01-01',100,'A') for i in range(6)]+[(f'FAKE{i}','2024-02-02',100,'A') for i in range(5)])
        retention,_=cs.cohorts(frame,'2024-01-01','2024-02-29','2024-01-01','2024-02-29');self.assertTrue(retention.empty)

    def test_classification_auc_pr_confusion_brier_calibration(self):
        score,cal=cm.classification_metrics([0,0,1,1],[.1,.2,.8,.9])
        self.assertEqual(score['c8_roc_auc'],1);self.assertEqual(score['c8_average_precision'],1);self.assertEqual(score['c8_tp'],2);self.assertEqual(score['c8_tn'],2)
        self.assertAlmostEqual(score['c8_brier'],.025);self.assertTrue(cal.empty)

    def test_single_class_and_invalid_probabilities(self):
        score,_=cm.classification_metrics([0,0],[.2,.2]);self.assertIsNone(score['c8_roc_auc']);self.assertIsNone(score['c8_average_precision'])
        with self.assertRaises(ValueError):cm.classification_metrics([0,1],[0,2])

    def test_churn_gate_rejects_random_or_uncalibrated(self):
        baseline={'c8_brier':.25};metric=dict(c8_samples=1000,c8_roc_auc=.5,c8_average_precision=.6,c8_prevalence=.6,c8_brier=.24,c8_ece=.02)
        self.assertFalse(cm.churn_gate(metric,baseline));metric.update(c8_roc_auc=.8,c8_average_precision=.8,c8_brier=.20,c8_ece=.2);self.assertFalse(cm.churn_gate(metric,baseline))

    def test_value_selection_falls_back_without_meaningful_improvement(self):
        validation=pd.DataFrame({'c8_model':['c8_mean_value','c8_median_value','c8_ridge_value'],'mae':[10,9,8.9]})
        self.assertEqual(cm.choose_value(validation),('c8_median_value','c8_median_value'));validation.loc[2,'mae']=8;self.assertEqual(cm.choose_value(validation)[0],'c8_ridge_value')

    def test_365_day_revenue_not_profit_or_lifetime(self):
        frame=orders([('a','2024-12-31',100,'A'),('a','2025-12-31',200,'A'),('a','2026-01-01',999,'A')]);got=cm.labeled_cohort(frame,'2025-01-01','2026-01-01')
        self.assertEqual(got.future_revenue.iloc[0],200)


class CustomerTemporalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.orders=synthetic();cls.result=cm.evaluate(cls.orders,'2026-10-18')

    def test_temporal_schedule_and_purging(self):
        result=self.result;self.assertNotEqual(result['state'],'unavailable');schedule=result['schedule']
        self.assertTrue((schedule.c8_feature_end<schedule.c8_cutoff).all())
        train_end=schedule.loc[schedule.c8_stage.eq('train'),'c8_value_end'].max();val_cut=schedule.loc[schedule.c8_stage.eq('validation'),'c8_cutoff'].iloc[0]
        self.assertLess(train_end,val_cut);self.assertLess(schedule.loc[schedule.c8_stage.eq('validation'),'c8_value_end'].iloc[0],schedule.loc[schedule.c8_stage.eq('test'),'c8_cutoff'].min())

    def test_selection_ignores_held_out_future_values(self):
        changed=self.orders.copy();changed.loc[changed.order_date.ge('2024-10-19'),'sales']*=20;got=cm.evaluate(changed,'2026-10-18')
        self.assertEqual(got['selected_churn'],self.result['selected_churn']);self.assertEqual(got['selected_value'],self.result['selected_value'])

    def test_aggregate_research_has_no_individual_outputs(self):
        result=self.result;self.assertFalse(result['individual_predictions_published'])
        for frame in result.values():
            if isinstance(frame,pd.DataFrame):self.assertFalse(set(frame)&{'customer_id','customer_name_ar','churn_probability','future_revenue'})
        self.assertGreater(result['sample']['test_rows'],result['sample']['test_unique'])

    def test_current_revenue_horizon_365_days(self):
        forecast=self.result['value_forecast'];self.assertEqual((pd.Timestamp(forecast['c8_prediction_end'])-pd.Timestamp(forecast['c8_prediction_start'])).days,364)
        self.assertEqual(forecast['c8_prediction_start'],'2026-10-19')


class CustomerFixtureTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);path=Path(tmp.name)/'fixture.db';fixture(path)
        with closing(sqlite3.connect(path)) as db,db:db.execute("ALTER TABLE customers ADD COLUMN customer_segment TEXT DEFAULT 'Retail'")
        change=patch.object(connection,'DB_PATH',path);change.start();self.addCleanup(change.stop)

    def test_small_scope_summary_suppression_and_master_independence(self):
        result=cs.dashboard('2024-01-01','2024-02-29','B1')
        self.assertIsNone(result['summary']['c8_identified']);self.assertEqual(result['summary']['c8_registered'],3)

    def test_category_revenue_per_order_without_join_multiplication(self):
        frame=cd.history(category='A');self.assertEqual(frame.loc[frame.sales_order_id.eq('O1'),'sales'].iloc[0],150);self.assertEqual(frame.sales_order_id.nunique(),len(frame))

    def test_no_data_and_unavailable_research(self):
        result=cs.dashboard('2030-01-01','2030-02-01');self.assertEqual(result['summary']['c8_identified'],0);self.assertTrue(result['activity'].empty)
        self.assertEqual(cm.research()['state'],'unavailable')


@unittest.skipUnless(api.DB.exists(),'Build original local database')
class CustomerDatasetTests(unittest.TestCase):
    def test_audit_registration_identification_and_multiple_locations(self):
        result=cs.audit();self.assertEqual(result['orders'],540000);self.assertEqual(result['identified_purchasers'],74660);self.assertEqual(result['anonymous_orders'],102961)
        self.assertEqual(result['orders_before_registration'],0);self.assertGreater(result['multiple_location_purchasers'],0)

    def test_scope_totals_and_unique_customers_reconcile(self):
        for scope in ({},{'branch':'BR001'},{'category':'Socks'}):
            got=cs.dashboard('2026-01-01','2026-09-30',**scope)['summary'];expected=api.overview('2026-01-01','2026-09-30',**scope)
            self.assertEqual(got['c8_identified'],expected['customers']);self.assertAlmostEqual(got['c8_identified_revenue']+got['c8_anonymous_revenue'],expected['sales'],delta=.02)

    def test_dashboard_assistant_parity_and_bilingual_questions(self):
        ctx=Context('English',filters('2026-01-01','2026-09-30'));report=answer_readonly('customer8_summary',ctx.assistant_scope())
        self.assertEqual(report['data'][0]['c8_identified'],ctx.get('customer8')['summary']['c8_identified'])
        for q,expected in [('How many identified customers purchased this month?','customer8_summary'),('What percentage of customers purchased more than once?','customer8_summary'),('Which customer segments have the highest historical revenue?','customer8_segments'),('Show customer retention by acquisition cohort.','customer8_cohorts'),('How has purchasing frequency changed?','customer8_changes'),("What is the churn model ROC-AUC?",'customer8_churn'),('What is the estimated next-year customer revenue?','customer8_value'),('كام عميل اشترى الشهر ده؟','customer8_summary'),('إيه أكتر شريحة عملاء بتشتري؟','customer8_segments'),('نسبة العملاء اللي بيرجعوا يشتروا تاني كام؟','customer8_summary'),('هل نموذج توقع فقدان العملاء دقيق؟','customer8_churn'),('إيه الشرائح اللي تكرار الشراء عندها قل؟','customer8_changes')]:
            text,reports=offline_answer(q,ctx);self.assertTrue(text);self.assertTrue(reports,q);self.assertEqual(reports[0]['meta']['tool'],expected,q)
        self.assertIn('clarify',dispatch('Show customer names',ctx.assistant_scope()))

    def test_unreliable_churn_suppression_cache_and_copy(self):
        result=cm.research();self.assertEqual(result['state'],'c8_unreliable');self.assertEqual(result['selected_churn'],'c8_prevalence_model');self.assertFalse(result['individual_predictions_published'])
        result['classification'].loc[0,'c8_roc_auc']=999;self.assertNotEqual(cm.research()['classification'].c8_roc_auc.iloc[0],999)

    def test_all_customer_views_both_languages_and_private_column_absence(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run();app.sidebar.radio[1].set_value('Customer Intelligence').run()
        for lang,suffix in [('English','_en'),('العربية','_ar')]:
            app.sidebar.radio(key='language').set_value(lang).run()
            for mode in ('c8_overview','c8_rfm','c8_cohorts','c8_repeat','c8_value','c8_churn','c8_limitations'):
                app.selectbox(key='c8_mode'+suffix).set_value(mode).run();self.assertFalse(app.exception);self.assertFalse(app.error)
                for element in app.dataframe:self.assertFalse(set(element.value.columns)&{'customer_id','customer_name_ar','churn_probability'})
            self.assertEqual(app.button(key='assistant_access').label,t('ask',lang))


if __name__=='__main__':unittest.main()
