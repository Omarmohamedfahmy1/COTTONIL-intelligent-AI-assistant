"""Capability prerequisites precede parameters; local/mocked tools only."""
import copy,itertools,unittest
from datetime import date
from unittest.mock import patch
from services import business_assistant as ba,metrics as kpi
from services.assistant_config import Settings
from services.assistant_context import resolve
from services.assistant_quality import assess
from services.assistant_limits import preflight
from ui.assistant_answers import assemble,critical_warnings
from ui.assistant_evidence import prepare

class CapabilityClarificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first,cls.last=kpi.metadata()
        cls.scope=dict(start=str(cls.first),end=str(cls.last),branch=None,category=None,location_type=None)
    def setUp(self):
        blocker=patch('services.business_assistant.GroqProvider',side_effect=AssertionError('Live API forbidden'))
        blocker.start();self.addCleanup(blocker.stop)
    def local(self,q,state=None,**kwargs):return ba.run(q,self.scope,state,settings=Settings(api_key=''),**kwargs)
    def test_impossible_financial_basis_precedes_dates_and_entities(self):
        for term,period in itertools.product(('net profit','net income','صافي ربح','صافي الربح','الربح الصافي','الأرباح الصافية','وصافي الربح'),
                ('',str(self.last.year),'٢٠٢٦','2030-01-01','in an unclear period')):
            with self.subTest(term=term,period=period),patch.object(ba,'resolve') as resolver:
                q=f'{term} {period}';r=self.local(q,connected=True)
                resolver.assert_not_called();self.assertEqual(r['answer_state'],'unsupported')
                self.assertEqual(r['failure_kind'],'incomplete_financial_data');self.assertEqual(r['calls'],0)
                self.assertNotIn('clarification_fields',r);self.assertFalse(r['semantic_complete'])
                text=assemble(r,'English',q)
                self.assertIn('مجمل الربح' if not term.isascii() else 'gross profit',text)
                self.assertFalse('?' in text or '؟' in text)
    def test_contracts_generalize_beyond_finance(self):
        for phrase in ('operating expenses','مصاريف التشغيل','refund-adjusted revenue','صافي المبيعات','SKU stock','مخزون الصنف'):
            with self.subTest(phrase=phrase),patch.object(ba,'resolve') as resolver:
                r=self.local(phrase+' 2030-01-01')
                resolver.assert_not_called();self.assertEqual(r['answer_state'],'unsupported')
                self.assertTrue(r['capability_limitations']);self.assertFalse(r['reports'])
        # Existing risk contract retains recorded-score fallback, not a probability.
        issues,text=preflight('stockout probability');self.assertFalse(issues);self.assertEqual(text,'stockout probability')
    def test_year_only_coverage_and_bilingual_digits(self):
        for year,ar in itertools.product((self.first.year,self.last.year,self.last.year+2),(False,True)):
            q=f'المبيعات في {year}' if ar else f'Company sales in {year}'
            if ar:q=q.translate(str.maketrans('0123456789','٠١٢٣٤٥٦٧٨٩'))
            with self.subTest(year=year,ar=ar):
                r=resolve(q,self.scope,ba.fresh_state());s=r['scope'];c=r['calendar_coverage']
                self.assertEqual((s['start'],s['end']),(f'{year}-01-01',f'{year}-12-31'))
                self.assertEqual(c['complete'],date(year,1,1)>=self.first and date(year,12,31)<=self.last)
                if not c['complete']:
                    warnings=critical_warnings(dict(resolved=r),'العربية' if ar else 'English')
                    self.assertTrue(warnings)
    def test_year_to_date_is_not_full_calendar_year(self):
        for phrase in ('Sales year-to-date','Sales YTD','المبيعات من بداية السنة'):
            r=resolve(phrase+f' {self.last.year}',self.scope,ba.fresh_state())
            self.assertEqual(r['scope']['start'],f'{self.last.year}-01-01')
            self.assertEqual(r['scope']['end'],str(self.last))
    def test_mixed_requests_keep_supported_facts_and_limitations(self):
        for metric,missing,ar in itertools.product(('sales','gross_profit'),('net_profit','refund_adjusted'),(False,True)):
            names={'sales':('sales','المبيعات'),'gross_profit':('gross profit','مجمل الربح'),
                'net_profit':('net income','صافي ربح'),'refund_adjusted':('refund-adjusted revenue','صافي المبيعات')}
            q=f'{names[metric][ar]} {"و" if ar else "and"} {names[missing][ar]} {self.last.year}'
            with self.subTest(q=q):
                r=self.local(q);safe=prepare(r,q);self.assertEqual(safe['answer_state'],'partial')
                self.assertTrue(safe['reports']);self.assertEqual(r['resolved']['request']['metrics'],[metric])
                self.assertIn('unsupported_basis',r['coverage_reasons']);self.assertFalse(safe['semantic_complete'])
                self.assertTrue(critical_warnings(safe,'العربية' if ar else 'English'))
    def test_real_missing_parameters_still_ask_one_question(self):
        for q,field in (('Compare sales','locations'),('قارن مجمل الربح','locations'),
                ('Sales 2030-01-01','dates'),('المبيعات في فترة غير محددة 2030-01-01','dates'),('Sales October or December 2030','dates'),
                ('Sales 2024 or 2025','dates'),('Sales Q5 2030','dates')):
            with self.subTest(q=q):
                r=self.local(q);self.assertEqual(r['answer_state'],'clarification')
                self.assertEqual(r['clarification_fields'],[field]);text=assemble(r,'English',q)
                self.assertEqual(text.count('?')+text.count('؟'),1)
    def test_missing_evidence_is_not_a_user_parameter(self):
        for q in ('Company sales','مبيعات الشركة'):
            with self.subTest(q=q),patch.object(ba,'verified_execute',side_effect=ba.EvidenceUnavailable('tool_execution_failed')):
                r=self.local(q);self.assertEqual(r['answer_state'],'unavailable')
                self.assertNotIn('clarification_fields',r);self.assertEqual(r['tool_failures'][0]['reason'],'tool_execution_failed')
    def test_followup_retains_scope_but_not_unsupported_metric(self):
        for year,ar in itertools.product((self.first.year,self.last.year),(False,True)):
            state=ba.fresh_state();self.local(f'Company sales {year}',state);before=copy.deepcopy(state['scope'])
            r=self.local('طب صافي ربح؟' if ar else 'And net income?',state)
            self.assertEqual(r['answer_state'],'unsupported');self.assertEqual(state['scope'],before)
            next_result=self.local('مجمل الربح' if ar else 'Gross profit',state)
            self.assertEqual(next_result['resolved']['scope'],before)
            if before['end']>str(self.last):
                self.assertIn('incomplete_calendar_year',next_result['coverage_reasons'])
    def test_privacy_guard_remains_first(self):
        for q in ('net profit and customer names','صافي ربح وأسماء العملاء'):
            with patch.object(ba,'resolve') as resolver:
                r=self.local(q);resolver.assert_not_called();self.assertEqual(r['answer_state'],'blocked')
    def test_mixed_missing_parameter_does_not_hide_capability_warning(self):
        for q in ('Gross profit and net income 2030-01-01','مجمل الربح وصافي الربح 2030-01-01'):
            r=self.local(q);self.assertEqual(r['answer_state'],'clarification')
            self.assertEqual(r['clarification_fields'],['dates']);self.assertTrue(r['capability_limitations'])
            text=assemble(r,'English',q);self.assertEqual(text.count('?')+text.count('؟'),1)
            self.assertTrue(critical_warnings(r,'English'))
    def test_actual_ui_keeps_partial_facts_when_pre_resolution_is_skipped(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120).run()
        app.sidebar.radio[1].set_value('AI Business Assistant').run()
        for q in (f'Gross profit and net income in {self.last.year}',f'مجمل الربح وصافي الربح في {self.last.year}'):
            with self.subTest(q=q):
                app.chat_input[0].set_value(q).run();self.assertFalse(app.exception)
                answer=app.session_state['dialog'][-1];result=answer['result']
                self.assertEqual(result['answer_state'],'partial');self.assertTrue(result['reports'])
                self.assertFalse(result.get('rejected_evidence'));self.assertTrue(answer['warnings'])
                self.assertIn('مجمل الربح' if 'مجمل' in q else 'Gross profit',answer['content'])

if __name__=='__main__':unittest.main()
