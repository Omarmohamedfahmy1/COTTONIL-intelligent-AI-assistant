"""Inventory-risk follow-up scope, evidence, failure taxonomy and UI regressions."""
import copy,itertools,unittest
from pathlib import Path
from unittest.mock import patch
from services import business_assistant as ba,metrics as kpi
from services.assistant_config import Settings
from services.groq_provider import ProviderError
from ui.assistant_answers import assemble,critical_warnings
from ui.assistant_evidence import prepare,sections
from test_phase9 import FakeProvider,completion,call

class RiskFollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ids=kpi.branches().branch_id.tolist();cls.pairs=[ids[2:4],ids[10:12],ids[-6:-4]]
        first,last=kpi.metadata();cls.scope=dict(start=str(first),end=str(last),branch=None,location_type=None,category=None)
        cls.questions=('Which of them has categories with higher inventory risk? Explain using available numbers.','مين فيهم عنده فئات بمخاطر مخزون أعلى؟ وضح بالأرقام المتاحة.')
    def setUp(self):
        self.block=patch('services.business_assistant.GroqProvider',side_effect=AssertionError('No paid calls'))
        self.block.start();self.addCleanup(self.block.stop)
    def seed(self,pair,period='Q3 2026'):
        state=ba.fresh_state();r=self.local(f'Compare sales {pair[0]} and {pair[1]} {period}',state)
        self.assertTrue(r['reports']);return state
    def local(self,q,state=None):return ba.run(q,self.scope,state,settings=Settings(api_key=''))
    def test_parameterized_risk_category_followups_reconcile_direct_service_scores(self):
        from services import inventory
        for pair,period,q in itertools.product(self.pairs,('Q2 2025','Q3 2026'),self.questions):
            with self.subTest(pair=pair,period=period,q=q):
                state=self.seed(pair,period);scope=copy.deepcopy(state['scope']);r=self.local(q,state)
                self.assertEqual(r['resolved']['pair'],pair);self.assertEqual(r['resolved']['scope'],scope)
                self.assertEqual(r['answer_state'],'full');self.assertEqual(r['tool_events'],[dict(operation='inventory6_pair',status='verified')])
                self.assertEqual(r['resolved']['request']['metrics'],['recorded_risk'])
                report=r['reports'][0];actual=inventory.compare_two(scope['start'],scope['end'],*pair)['rows']
                for row in report['data']:
                    for suffix,identifier in zip(('a','b'),pair):
                        original=actual.loc[actual.category.eq(row['category'])&actual.location_id.eq(identifier),'recorded_risk'].iloc[0]
                        self.assertAlmostEqual(row['recorded_risk_'+suffix],original)
                text=assemble(r,'English',q)
                self.assertIn(pair[0],text);self.assertIn(pair[1],text)
                self.assertIn('مثال' if q==self.questions[1] else 'For example',text)
                for branch in pair:self.assertEqual(r['resolved']['pair'].count(branch),1)
                view=sections(prepare(r,q,r['resolved']),q)[0]
                self.assertEqual(set(view['data'][0]),{'category','recorded_risk_a','recorded_risk_b'})
                self.assertTrue(any('احتمالات' in w if q==self.questions[1] else 'probabilities' in w for w in critical_warnings(r,'العربية' if q==self.questions[1] else 'English')))
    def test_category_and_previous_month_context_are_retained(self):
        category=kpi.read('SELECT DISTINCT category_en FROM products_catalog ORDER BY 1').category_en.iloc[0]
        for pair in self.pairs:
            state=self.seed(pair);r=self.local(self.questions[0]+' '+category,state)
            self.assertEqual(r['resolved']['scope']['category'],category)
            r=self.local('طب الشهر اللي قبله؟',state)
            self.assertEqual(r['resolved']['pair'],pair);self.assertEqual(r['resolved']['scope']['category'],category)
            self.assertEqual(r['resolved']['request']['metrics'],['recorded_risk']);self.assertEqual(r['answer_state'],'full')
        for q in self.questions:
            r=self.local(q+(' والمبيعات' if q==self.questions[1] else ' and sales'),self.seed(self.pairs[0]))
            self.assertEqual(r['answer_state'],'partial');self.assertEqual(r['missing_metrics'],['sales'])
            self.assertEqual([x['meta']['tool'] for x in r['reports']],['inventory6_pair'])
    def test_display_comparison_preserves_three_decimal_risk_precision_and_ties(self):
        state=self.seed(self.pairs[0]);r=self.local(self.questions[0],state);r=copy.deepcopy(r)
        rows=r['reports'][0]['data'];rows[:]=[dict(category=rows[0]['category'],recorded_risk_a=.404,recorded_risk_b=.401),dict(category=rows[1]['category'],recorded_risk_a=.2,recorded_risk_b=.2)]
        text=assemble(r,'English',self.questions[0]);self.assertIn('.404',text);self.assertIn('.401',text)
        self.assertIn('1 are tied',text)
    def test_explicit_warehouse_attribution_is_not_inferred(self):
        for pair,q in itertools.product(self.pairs,self.questions):
            state=self.seed(pair);q+=' warehouse' if q==self.questions[0] else ' مخزون المستودع'
            r=self.local(q,state);self.assertEqual(r['reports'],[]);self.assertEqual(r['answer_state'],'unsupported')
            self.assertEqual(r['tool_failures'][0]['reason'],'inventory_warehouse_mapping')
            text=assemble(r,'English',q);self.assertIn('مستودع' if 'المستودع' in q else 'warehouse',text)
            self.assertNotIn('?',text);self.assertNotIn('؟',text)
    def test_missing_snapshot_stock_scores_and_execution_failure_are_not_user_parameters(self):
        for pair,q,reason in itertools.product(self.pairs[:2],self.questions,('inventory_snapshot_unavailable','inventory_pair_coverage','inventory_risk_metric_unavailable','tool_execution_failed')):
            state=self.seed(pair)
            error=RuntimeError('PRIVATE INTERNAL DETAIL') if reason=='tool_execution_failed' else ba.EvidenceUnavailable(reason)
            with patch.object(ba,'verified_execute',side_effect=error):r=self.local(q,state)
            self.assertEqual(r['answer_state'],'unavailable');self.assertFalse(r.get('clarification_fields'))
            self.assertEqual(r['tool_failures'][0]['reason'],reason)
            text=assemble(r,'English',q);self.assertNotIn('PRIVATE',str(r));self.assertNotIn('?',text);self.assertNotIn('؟',text)
            self.assertNotIn('غير مدعوم' if q==self.questions[1] else 'Unsupported question',text)
    def test_actual_missing_score_and_wrong_scope_outputs_are_withheld(self):
        real=ba.registry.execute
        for fault in ('score','scope','nonfinite'):
            state=self.seed(self.pairs[0])
            def execute(name,args,resolved):
                payload=real(name,args,resolved)
                if name=='inventory6_pair':
                    if fault=='score':payload['data'][0]['recorded_risk_b']=None
                    elif fault=='scope':payload['meta']['branch_b']=self.pairs[-1][-1]
                    else:payload['data'][0]['recorded_risk_a']=float('nan')
                return payload
            with patch.object(ba.registry,'execute',side_effect=execute):r=self.local(self.questions[0],state)
            self.assertFalse(r['semantic_complete'])
            if fault=='score':
                self.assertEqual(r['answer_state'],'partial');self.assertTrue(r['reports'])
                self.assertIn('incomplete_category_coverage',r['coverage_reasons'])
                self.assertNotIn(None,[row['recorded_risk_b'] for row in r['reports'][0]['data']])
            else:
                self.assertFalse(r['reports']);self.assertEqual(r['tool_failures'][0]['reason'],'scope_mismatch')
    def test_unsupported_probability_is_partial_recorded_evidence_only(self):
        for pair,q in itertools.product(self.pairs,('Compare category stockout probability for them','قارن احتمال نفاد المخزون بين نفس الفرعين حسب الفئات')):
            r=self.local(q,self.seed(pair));self.assertEqual(r['answer_state'],'partial');self.assertTrue(r['reports'])
            self.assertIn('unsupported_risk_metric',r['coverage_reasons'])
            self.assertTrue(any('احتمالي' in w if 'قارن' in q else 'unsupported' in w for w in critical_warnings(r,'العربية' if 'قارن' in q else 'English')))
    def test_missing_pair_asks_exactly_one_question(self):
        for q in self.questions:
            r=self.local(q);self.assertEqual(r['answer_state'],'clarification');self.assertEqual(r['clarification_fields'],['locations'])
            text=assemble(r,'English',q);self.assertEqual(text.count('?')+text.count('؟'),1)
            self.assertNotIn('period',text);self.assertNotIn('الفترة',text)
        cached=dict(status='clarify',code='no_evidence',answer_state='clarification',reports=[])
        self.assertEqual(prepare(cached,self.questions[0])['answer_state'],'unavailable')
    def test_mock_wrong_tool_no_tool_and_provider_failure_are_separate(self):
        for q in self.questions:
            for case in ('valid','wrong','none','provider'):
                state=self.seed(self.pairs[1])
                provider=FakeProvider(completion([call('inventory6_pair')])) if case=='valid' else FakeProvider(completion([call('location_ranking')]),completion(content='{}')) if case=='wrong' else FakeProvider(completion(content='{}')) if case=='none' else FakeProvider(ProviderError('network'))
                r=ba.run(q,self.scope,state,connected=True,provider=provider,settings=Settings(api_key='fake'))
                if case=='valid':self.assertEqual(r['answer_state'],'full');self.assertEqual(len(provider.sent),1)
                else:
                    self.assertNotEqual(r['answer_state'],'clarification');text=assemble(r,'English',q)
                    self.assertNotIn('?',text);self.assertNotIn('؟',text)
                    if case=='wrong':self.assertEqual(r['tool_failures'][0]['reason'],'wrong_tool')
                    if case=='none':
                        # A resolved approved contract now survives benign model
                        # omission; invalid tools and provider failures still do not.
                        self.assertIsNone(r['code']);self.assertEqual(r['answer_state'],'full')
                        self.assertEqual(r['diagnostic']['evidence_origin'],'server_plan_fallback')
                        self.assertEqual(r['resolved']['pair'],self.pairs[1]);self.assertTrue(r['reports'])
                        self.assertEqual(len(provider.sent),1)
                    if case=='provider':self.assertEqual(r['answer_state'],'provider_error');self.assertIn('Groq',text)
    def test_ui_shows_scores_warning_and_no_questionless_clarification_badge(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120).run()
        app.sidebar.radio[1].set_value('AI Business Assistant').run();pair=self.pairs[0]
        app.chat_input[0].set_value(f'Compare sales {pair[0]} and {pair[1]} Q3 2026').run()
        app.chat_input[0].set_value(self.questions[1]).run();self.assertFalse(app.exception)
        last=app.chat_message[-1];text=' '.join(x.value for x in last.markdown)
        self.assertIn('مثال',text);self.assertEqual(last.dataframe[0].value.shape[1],3)
        self.assertTrue(any('احتمالات' in w.value for w in last.warning))
        self.assertFalse(any('يلزم توضيح' in w.value for w in last.warning))

if __name__=='__main__':unittest.main()
