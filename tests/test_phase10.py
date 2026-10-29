"""Final quality gates: simulated SDK responses, never paid inference."""
import copy,json,unittest
from dataclasses import replace
from unittest.mock import patch
import httpx
from services import business_assistant as ba,assistant_registry as ar
from services.assistant_config import Settings
from services.assistant_quality import assess,facts
from services.groq_provider import ProviderError,groq_only
from test_phase9 import FakeProvider,completion,call,SCOPE,FAKE_REPORT

class FinalAnswerTests(unittest.TestCase):
    def execute(self,provider,question='sales',state=None,**kwargs):
        def report(name,args,resolved):
            value=copy.deepcopy(FAKE_REPORT);scope=resolved['scope']
            value['meta'].update(tool=name,period=f"{scope['start']} to {scope['end']}",branch_id=scope.get('branch') or 'all',category=scope.get('category'),location_type=scope.get('location_type'))
            return value
        with patch.object(ar,'execute',side_effect=report) as local:
            result=ba.run(question,SCOPE,state,connected=True,provider=provider,settings=Settings(api_key='fake'),**kwargs)
        return result,local
    def test_known_complete_stops_before_unused_400_or_429(self):
        for error in ('invalid_request','rate_limit'):
            p=FakeProvider(completion([call()]),ProviderError(error))
            r,local=self.execute(p)
            self.assertEqual(r['answer_state'],'full');self.assertEqual(len(p.sent),1);self.assertEqual(local.call_count,1)
    def test_missing_customer_domain_is_not_full(self):
        p=FakeProvider(completion([call()]),completion(content='complete'))
        # Model omission now permits approved recovery. Preserve this negative
        # test's missing-evidence premise by making that recovery unavailable.
        verified=ba.verified_execute
        def missing_customer(name,args,resolved):
            if name=='customer8_summary':raise ba.EvidenceUnavailable('customer_summary_unavailable')
            return verified(name,args,resolved)
        with patch.object(ba,'verified_execute',side_effect=missing_customer):
            r,_=self.execute(p,'sales and repeat customers')
        self.assertFalse(r['semantic_complete']);self.assertIn('customer8_summary',r['missing_operations'])
        self.assertIn(dict(operation='customer8_summary',reason='customer_summary_unavailable'),r['tool_failures'])
    def test_open_question_with_verified_cell_remains_partial(self):
        r,_=self.execute(FakeProvider(completion([call()]),completion(content='invented cause')),'Explain business health')
        self.assertEqual(r['answer_state'],'partial');self.assertNotIn('invented',json.dumps(r))
    def test_provider_error_preserves_evidence_and_pending(self):
        state=ba.fresh_state()
        r,_=self.execute(FakeProvider(completion([call()]),ProviderError('invalid_request')),'sales and repeat customers',state)
        self.assertEqual(r['answer_state'],'partial');self.assertTrue(r['can_retry']);self.assertEqual(len(r['reports']),1)
        self.assertEqual(state['pending']['rounds'],2)
    def test_retry_reuses_evidence_and_matching_tool_ids(self):
        state=ba.fresh_state();q='sales and repeat customers'
        self.execute(FakeProvider(completion([call()]),ProviderError('invalid_request')),q,state)
        p=FakeProvider(completion([call('customer8_summary',id='b')]))
        r,local=self.execute(p,q,state,retry=True)
        self.assertEqual(local.call_count,1);self.assertEqual(r['answer_state'],'full')
        self.assertEqual([m['tool_call_id'] for m in p.sent[0] if m['role']=='tool'],['call_1'])
        self.assertEqual(len(state['history']),2);self.assertNotIn('pending',state)
    def test_retry_cooldown_has_no_network(self):
        state=ba.fresh_state();q='sales and repeat customers'
        self.execute(FakeProvider(ProviderError('rate_limit',60)),q,state)
        p=FakeProvider();r,_=self.execute(p,q,state,retry=True)
        self.assertEqual(r['code'],'retry_after');self.assertFalse(p.sent)
    def test_retry_changed_question_invalidates(self):
        state=ba.fresh_state()
        self.execute(FakeProvider(ProviderError('network')),'sales',state)
        r,_=self.execute(FakeProvider(),'gross profit',state,retry=True)
        self.assertEqual(r['code'],'retry_context_changed');self.assertNotIn('pending',state)
    def test_source_changed_invalidates_retry(self):
        state=ba.fresh_state();self.execute(FakeProvider(ProviderError('network')),'sales',state)
        with patch.object(ba,'source_token',return_value=('different',0,0)):
            r,_=self.execute(FakeProvider(),'sales',state,retry=True)
        self.assertEqual(r['code'],'retry_context_changed')
    def test_retry_does_not_shift_previous_month_again(self):
        state=ba.fresh_state();state.update(ba.resolve('sales last 3 months',SCOPE,state));state['last_operations']=['company_overview']
        self.execute(FakeProvider(ProviderError('network')),'The month before?',state)
        frozen=copy.deepcopy(state['pending']['resolved'])
        r,_=self.execute(FakeProvider(completion([call()])),'The month before?',state,retry=True)
        self.assertEqual(r['resolved']['scope'],frozen['scope'])
    def test_reset_clears_retry_but_retains_usage_caps(self):
        state=ba.fresh_state();state.update(calls=7,tokens=500,input_tokens=20,pending={'private':'not retained'})
        ba.reset_conversation(state)
        self.assertEqual(state['calls'],7);self.assertEqual(state['tokens'],500);self.assertNotIn('pending',state)
    def test_empty_choices_is_sanitized_retryable_failure(self):
        from types import SimpleNamespace
        r,_=self.execute(FakeProvider(SimpleNamespace(choices=[],usage=None)))
        self.assertEqual(r['code'],'empty_response');self.assertEqual(r['answer_state'],'provider_error')
    def test_invalid_origin_port_and_userinfo(self):
        for url in ('https://api.groq.com:444/v1','https://user:pass@api.groq.com/v1'):
            with self.assertRaises(ProviderError):groq_only(httpx.Request('GET',url))
    def test_facts_are_exact_cells(self):
        report=copy.deepcopy(FAKE_REPORT)
        f=facts([report])[0];self.assertEqual(f['value'],report['data'][f['row']][f['key']])
    def test_empty_and_outside_data_unavailable(self):
        resolved={'scope':SCOPE,'source_start':'2020-01-01','source_end':'2026-10-18'}
        report=copy.deepcopy(FAKE_REPORT);report['data']=[]
        self.assertEqual(assess([report],['company_overview'],resolved)['answer_state'],'unavailable')
        resolved['scope']={**SCOPE,'start':'2010-01-01','end':'2010-01-02'}
        self.assertEqual(assess([FAKE_REPORT],['company_overview'],resolved)['answer_state'],'unavailable')
    def test_truncated_and_unknown_intent_not_complete(self):
        report=copy.deepcopy(FAKE_REPORT);report['meta']['truncated']=True
        self.assertFalse(assess([report],['company_overview'],{})['semantic_complete'])
        self.assertFalse(assess([FAKE_REPORT],[],{})['semantic_complete'])
    def test_mixed_sales_repeat_plan_has_both_domains(self):
        resolved=ba.resolve('sales and repeat customers',SCOPE,ba.fresh_state())
        self.assertEqual({n for n,a in ba.plan_offline('sales and repeat customers',resolved)}, {'customer8_summary','company_overview'})
    def test_budget_state_separate_from_provider_error(self):
        self.assertEqual(assess([],['company_overview'],{},'limited')['answer_state'],'budget_exhausted')
        self.assertEqual(assess([],['company_overview'],{},'error')['answer_state'],'provider_error')
    def test_combined_tool_declares_all_covered_domains(self):
        report=copy.deepcopy(FAKE_REPORT);report['meta']['tool']='category_risk_sales'
        self.assertEqual(assess([report],['category_risk_sales'],{})['returned_domains'],['inventory','sales'])
    def test_live_gate_fails_before_provider_without_approval(self):
        from scripts.evaluate_phase10 import authorize
        with self.assertRaises(ValueError):authorize({'approved':False,'max_usd':1})
        with self.assertRaises(ValueError):authorize({'approved':True,'max_usd':0})
    def test_global_cost_reservation_stops_before_request(self):
        from scripts.evaluate_phase10 import Budget
        budget=Budget(dict(input_usd_per_million=1,output_usd_per_million=1,max_http_attempts=3,wall_seconds=30,max_usd=.3))
        budget.reserve()
        with self.assertRaises(ProviderError):budget.reserve()
        self.assertEqual(budget.attempts,1)
    def test_approval_requires_exact_cost_acknowledgement(self):
        from scripts.evaluate_phase10 import authorize
        config=dict(approved=True,max_usd=1,approval_reference='future-explicit-user-approval',max_http_attempts=30,wall_seconds=300,input_usd_per_million=.15,output_usd_per_million=.6,model='openai/gpt-oss-120b')
        with self.assertRaises(ValueError):authorize(config,2)
        self.assertEqual(authorize(config,1),config)

class FinalInterfaceTests(unittest.TestCase):
    def test_bilingual_mock_partial_and_retry_control(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        from ui.assistant_answers import label
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120).run()
        app.sidebar.radio[1].set_value('AI Business Assistant').run()
        for language,suffix in [('English','en'),('العربية','ar')]:
            app.sidebar.radio(key='language').set_value(language).run()
            app.radio(key=f'full_mode_{suffix}').set_value('connected').run()
            app.text_input(key='full_api_key').set_value('fake-not-a-secret').run()
            fake=ba.response('error',code='invalid_request',answer_state='partial',provider='Groq')
            question='sales and repeat customers' if language=='English' else 'المبيعات وتكرار شراء العملاء'
            with patch('ui.assistant.run_llm',return_value=fake):app.chat_input[0].set_value(question).run()
            self.assertFalse(app.exception)
            self.assertIn(label('partial',language),[e.value for e in app.warning])
        state=app.session_state['a9_state'];state['pending']={'question':'sales and repeat customers'}
        app.run();self.assertTrue(any(b.key=='full_retry' for b in app.button))
        with patch('ui.assistant.run_llm',return_value=ba.response('limited',answer_state='budget_exhausted')) as bridge:
            app.button(key='full_retry').click().run()
        self.assertTrue(bridge.call_args.kwargs['retry']);self.assertFalse(app.exception)

if __name__=='__main__':unittest.main()
