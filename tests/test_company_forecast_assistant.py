"""Company/category forecasts: source-origin dates, context reset and grounded metrics."""
import copy,itertools,unittest
from pathlib import Path
from unittest.mock import patch
from services import business_assistant as ba,metrics as kpi,forecasting as fc
from services.assistant_config import Settings
from services.assistant_context import resolve
from services.assistant_forecast import requested_months,month_after,ForecastRequestError
from services.assistant_request import output_issues
from services.filters import complete_month_bounds
from ui.assistant_answers import assemble,critical_warnings
from ui.assistant_evidence import prepare,sections
from test_phase9 import FakeProvider,completion,call

class CompanyForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        first,last=kpi.metadata();cls.origin=complete_month_bounds(first,last)[1]
        cls.scope=dict(start=str(first),end=str(last),branch=None,location_type=None,category=None)
        ids=kpi.branches().branch_id.tolist();cls.pairs=[ids[1:3],ids[9:11],ids[-4:-2]]
        cls.categories=kpi.read('SELECT DISTINCT category_en FROM products_catalog ORDER BY 1').category_en.iloc[:2].tolist()
        cls.questions=('توقع مبيعات الشركة في أكتوبر ونوفمبر وديسمبر 2026، وقولي دقة النموذج.','Forecast company revenue in October, November and December 2026 and report model accuracy')
    def setUp(self):
        blocker=patch('services.business_assistant.GroqProvider',side_effect=AssertionError('No paid calls'));blocker.start();self.addCleanup(blocker.stop)
    def local(self,q,state=None,scope=None):return ba.run(q,scope or self.scope,state,settings=Settings(api_key=''))
    def seed(self,pair,category=None):
        scope={**self.scope,'category':category};state=ba.fresh_state()
        self.local(f'Compare sales {pair[0]} and {pair[1]} Q3 2026',state,scope);return state,scope
    def test_failed_manual_question_and_english_both_tools_in_fresh_and_prior_conversations(self):
        for q,pair,category in itertools.product(self.questions,[None,*self.pairs],(None,self.categories[0])):
            with self.subTest(q=q,pair=pair,category=category):
                state,scope=self.seed(pair,category) if pair else (ba.fresh_state(),{**self.scope,'category':category})
                r=self.local(q,state,scope);self.assertEqual(r['answer_state'],'full')
                self.assertEqual(r['resolved']['pair'],[]);self.assertIsNone(r['resolved']['scope']['branch']);self.assertIsNone(r['resolved']['scope']['category'])
                self.assertEqual(r['resolved']['categories'],[])
                self.assertEqual([x['meta']['tool'] for x in r['reports']],['forecast7_values','forecast7_accuracy'])
                self.assertEqual(r['resolved']['forecast_months'],[month_after(__import__('datetime').date.fromisoformat(self.origin),i) for i in (1,2,3)])
                self.assertTrue(all(x['meta']['unit']=='EGP' and x['meta']['target']=='revenue' for x in r['reports']))
                text=assemble(r,'English',q)
                for row in r['reports'][0]['data']:self.assertIn(row['month'],text);self.assertIn(f"{row['central']:,.2f}",text)
                self.assertIn('WAPE',text);self.assertNotIn('guaranteed accuracy',text)
    def test_company_resets_pair_location_type_warehouse_and_category_but_keeps_history_dates(self):
        pair=self.pairs[0];state,scope=self.seed(pair,self.categories[0]);old_dates=(state['scope']['start'],state['scope']['end'])
        state['warehouse']=kpi.read('SELECT warehouse_id FROM warehouses ORDER BY 1').warehouse_id.iloc[0]
        scope={**scope,'location_type':'Retail branch','branch':pair[0]}
        for q in ('Forecast company-wide revenue next 3 months','توقع إيرادات الشركة للشهور القادمة'):
            r=resolve(q,scope,copy.deepcopy(state))
            self.assertEqual(r['pair'],[])
            for key in ('branch','category','location_type'):self.assertIsNone(r['scope'][key])
            self.assertIsNone(r['warehouse']);self.assertEqual((r['scope']['start'],r['scope']['end']),old_dates)
    def test_horizons_reconcile_to_unmodified_authoritative_service(self):
        for horizon in (1,3,6):
            r=self.local(f'Forecast company sales next {horizon} months and accuracy')
            direct=fc.forecast_report(horizon=horizon)
            values,accuracy=r['reports'];self.assertEqual(len(values['data']),horizon)
            for actual,expected in zip(values['data'],direct['forecasts'].itertuples()):self.assertAlmostEqual(actual['central'],expected.central)
            self.assertAlmostEqual(accuracy['meta']['test_wape_pct'],direct['metrics']['wape_pct'])
            self.assertAlmostEqual(accuracy['meta']['baseline_test_wape_pct'],direct['baseline_metrics']['wape_pct'])
            self.assertEqual(accuracy['meta']['test_observations'],direct['metrics']['observations'])
    def test_named_month_grammar_changes_with_source_origin_not_host_clock(self):
        examples=[('2024-09-30','October, November and December 2024',3),('2025-11-30','December 2025, January and February 2026',3),('2027-03-31','أبريل ومايو ويونيو ٢٠٢٧',3),('2025-12-31','January 2026',1)]
        for origin,phrase,horizon in examples:
            actual,months=requested_months('Forecast '+phrase,origin,6)
            self.assertEqual(actual,horizon);self.assertEqual(months,[month_after(__import__('datetime').date.fromisoformat(origin),i) for i in range(1,horizon+1)])
        with self.assertRaises(ForecastRequestError):requested_months('Forecast October November December 2024','2025-09-30',3)
        horizon,months=requested_months('Forecast November and December 2024','2024-09-30',1)
        self.assertEqual(horizon,3);self.assertEqual(months,['2024-11','2024-12'])
    def test_category_units_then_explicit_company_revenue_and_back(self):
        state=ba.fresh_state()
        for category in self.categories:
            r=self.local(f'Forecast next 3 months {category} and model accuracy',state)
            self.assertTrue(r['reports']);self.assertEqual(r['reports'][0]['meta']['unit'],'units')
            self.assertEqual(r['reports'][0]['meta']['target'],'units');self.assertIn('Unit demand',assemble(r,'English','Forecast'))
            r=self.local('Forecast company revenue next 3 months and accuracy',state)
            self.assertEqual(r['reports'][0]['meta']['unit'],'EGP');self.assertIsNone(r['resolved']['scope']['category'])
        r=self.local('Forecast '+ ' and '.join(self.categories)+' and model accuracy')
        self.assertEqual(r['answer_state'],'partial');self.assertEqual([x['meta']['tool'] for x in r['reports']],['forecast7_categories'])
        self.assertIn('category_evaluation_scope',r['coverage_reasons'])
    def test_unsupported_dates_horizons_and_contradictions_never_execute_tools(self):
        questions=('Forecast company sales in January 2030','توقع مبيعات الشركة في أكتوبر ونوفمبر 2030','Forecast company revenue in October November December 2025','Forecast company revenue next 2 months','Forecast company revenue next 1 month in October November December 2026')
        for q in questions:
            with patch.object(ba.registry,'execute') as tool:r=self.local(q)
            tool.assert_not_called();self.assertFalse(r['reports']);self.assertFalse(r['semantic_complete'])
            text=assemble(r,'English',q);self.assertTrue(text)
    def test_unavailable_and_experimental_results_keep_actual_service_reasons(self):
        original=fc.forecast_report(horizon=3)
        for reason in ('f7_missing','f7_insufficient','f7_zero'):
            unavailable=copy.deepcopy(original);unavailable.update(state='unavailable',reason=reason,metrics=None,baseline_metrics=None)
            unavailable['forecasts']=unavailable['forecasts'].iloc[:0];unavailable['comparison']=unavailable['comparison'].iloc[:0]
            with patch.object(fc,'forecast_report',return_value=unavailable):r=self.local(self.questions[0])
            self.assertEqual(r['answer_state'],'unavailable');self.assertIn(reason,[x['meta']['reason'] for x in r['reports']])
            self.assertNotIn('لا توجد أداة',assemble(r,'English',self.questions[0]))
        experimental=copy.deepcopy(original);experimental.update(state='experimental',reason='f7_experimental')
        with patch.object(fc,'forecast_report',return_value=experimental):r=self.local(self.questions[1])
        self.assertEqual(r['answer_state'],'partial');self.assertTrue(r['reports'][0]['data'])
        self.assertTrue(any('experimental' in w for w in critical_warnings(r,'English')))
    def test_wrong_months_and_revenue_units_fail_closed(self):
        r=self.local(self.questions[1]);resolved=r['resolved']
        for mode in ('unit','month'):
            payload=copy.deepcopy(r['reports'][0])
            if mode=='unit':payload['meta']['unit']='units'
            else:payload['data'][0]['month']='2099-01'
            self.assertTrue(output_issues(payload,resolved))
            bad=copy.deepcopy(r);bad['reports']=[payload]
            self.assertFalse(prepare(bad,self.questions[1],resolved)['reports'])
    def test_mock_connected_calls_values_and_accuracy_without_extra_final_call(self):
        for q,pair in itertools.product(self.questions,self.pairs[:2]):
            state,scope=self.seed(pair,self.categories[0])
            provider=FakeProvider(completion([call('forecast7_values',id='values'),call('forecast7_accuracy',id='accuracy')]))
            r=ba.run(q,scope,state,connected=True,provider=provider,settings=Settings(api_key='fake'))
            self.assertEqual(r['answer_state'],'full');self.assertEqual(len(provider.sent),1)
            self.assertEqual([e['status'] for e in r['tool_events']],['verified','verified'])
    def test_forecast_details_keep_all_months_and_compact_model_baseline_test_rows(self):
        q=self.questions[1];r=self.local(q);views=sections(prepare(r,q,r['resolved']),q)
        self.assertEqual(len(views[0]['data']),3)
        accuracy=next(v for v in views if 'forecast_model' in v['data'][0])
        self.assertLessEqual(len(accuracy['data']),2);self.assertTrue(all(x['stage']=='test' for x in accuracy['data']))
        q='Forecast company revenue January 2027 and model accuracy';r=self.local(q)
        self.assertEqual(r['resolved']['horizon'],6)
        views=sections(prepare(r,q,r['resolved']),q)
        self.assertEqual([x['month'] for x in views[0]['data']],['2027-01'])
        self.assertIn('2027-01',assemble(r,'English',q));self.assertNotIn('2026-10:',assemble(r,'English',q))
    def test_actual_streamlit_bilingual_render_after_pair_context(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120).run()
        app.sidebar.radio[1].set_value('AI Business Assistant').run();pair=self.pairs[0]
        app.chat_input[0].set_value(f'Compare sales {pair[0]} and {pair[1]} Q3 2026').run()
        for q in self.questions:
            app.chat_input[0].set_value(q).run();self.assertFalse(app.exception)
            last=app.chat_message[-1];text=' '.join(x.value for x in last.markdown)
            self.assertIn('WAPE',text)
            for row in app.session_state['dialog'][-1]['reports'][0]['data']:self.assertIn(row['month'],text)
            self.assertFalse(any('Unsupported' in w.value or 'غير مدعوم' in w.value for w in last.warning))
            self.assertTrue(any('WAPE' in w.value for w in last.warning))
            test_start=app.session_state['dialog'][-1]['reports'][1]['meta']['test_start']
            self.assertTrue(any(test_start in c.value for c in last.caption))

if __name__=='__main__':unittest.main()
