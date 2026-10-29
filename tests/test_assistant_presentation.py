"""Presentation-only regression: verified fixtures, real local tools, no paid API."""
import copy,unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from ui.assistant_answers import assemble,answer_language,critical_warnings
from services import business_assistant as ba
from services.assistant_config import Settings

SCOPE=dict(start='2026-07-01',end='2026-09-30',branch=None,location_type=None,category=None)
def fixture(a=299302.15,b=286628.58):
    return dict(status='supported',answer_state='full',reports=[dict(meta=dict(tool='profit5_pair',period='2026-07-01 to 2026-09-30',
        branch_a='BR001',branch_b='BR002',branch_id='pair',classification='recorded'),data=[
        dict(metric='sales',location_a=773606.03,location_b=736682.27),
        dict(metric='gross_profit',location_a=a,location_b=b),
        dict(metric='gross_margin_pct',location_a=38.69,location_b=38.91)],plot=None)],
        resolved=dict(pair=['BR001','BR002'],scope=SCOPE),coverage_reasons=[])

class SummaryTests(unittest.TestCase):
    def test_arabic_exact_profit_fixture_not_sales(self):
        text=assemble(fixture(),'English','مين فيهم حقق مجمل ربح أعلى؟')
        self.assertTrue(text.startswith('موقع BR001 حقق مجمل الربح أعلى بـ12,673.57 جنيه'))
        for value in ('299,302.15','286,628.58','BR002'):self.assertIn(value,text)
        self.assertNotIn('773,606',text);self.assertNotIn('المبيعات',text)
        self.assertNotIn('الطلب المفسّر',text)
    def test_english_question_overrides_arabic_dashboard(self):
        text=assemble(fixture(),'العربية','Which has higher gross profit?')
        self.assertTrue(text.startswith('Location BR001 has higher gross profit'))
        self.assertIn('12,673.57 EGP',text);self.assertNotIn('sales',text)
    def test_values_are_dynamic_and_report_unchanged(self):
        result=fixture(100.25,150.75);before=copy.deepcopy(result)
        text=assemble(result,'English','Compare gross profit')
        self.assertTrue(text.startswith('Location BR002'));self.assertIn('50.50 EGP',text)
        self.assertEqual(result,before);self.assertNotIn('12,673.57',text)
    def test_tie_does_not_invent_winner(self):
        text=assemble(fixture(12,12),'English','Compare gross profit')
        self.assertIn('equal',text);self.assertIn('12.00 EGP each',text);self.assertNotIn('higher',text)
    def test_negative_gross_profit_comparison(self):
        text=assemble(fixture(-100,-250),'English','Compare gross profit')
        self.assertTrue(text.startswith('Location BR001'));self.assertIn('150.00 EGP',text)
    def test_margin_uses_percentage_point_difference(self):
        text=assemble(fixture(),'English','Compare gross margins')
        self.assertTrue(text.startswith('Location BR002'));self.assertIn('0.22 percentage points',text)
        self.assertNotIn('EGP',text)
    def test_requested_metric_missing_no_sales_substitution(self):
        result=fixture();result['reports'][0]['data']=result['reports'][0]['data'][:1]
        text=assemble(result,'English','Compare gross profit')
        self.assertNotIn('773,606',text);self.assertNotIn('sales',text);self.assertIn('not available',text)
    def test_missing_pair_value_never_claims_winner(self):
        for value in (None,True,float('nan'),float('inf'),'299302.15'):
            with self.subTest(value=value):
                text=assemble(fixture(value,12),'English','Compare gross profit')
                self.assertNotIn('higher',text);self.assertNotIn('12.00',text)
    def test_overview_only_requested_metric(self):
        result=dict(answer_state='full',reports=[dict(meta=dict(tool='company_overview'),data=[dict(sales=900,gross_profit=300,orders=4)])])
        text=assemble(result,'English','What is gross profit?')
        self.assertEqual(text,'Gross profit: 300.00 EGP.')
        self.assertEqual(assemble(result,'English','What are sales?'),'Sales before refunds: 900.00 EGP.')
    def test_two_requested_metrics_two_sentences(self):
        text=assemble(fixture(),'English','Compare sales and gross profit')
        self.assertIn('gross profit',text);self.assertIn('sales before refunds',text)
        self.assertEqual(text.count(' for '),2)
    def test_period_cell_is_not_presented_as_company_total(self):
        result=dict(answer_state='full',reports=[dict(meta=dict(tool='sales4_trends'),data=[
            dict(period='2026-07',sales=100),dict(period='2026-08',sales=200)])])
        self.assertEqual(assemble(result,'English','Show monthly sales'),'2026-07 · Sales before refunds: 100.00 EGP.')
    def test_identifier_only_and_arabic_digits_do_not_force_language(self):
        self.assertEqual(answer_language('BR001 ٣','English'),'English')
        self.assertEqual(answer_language('Gross profit BR001','العربية'),'English')
    def test_critical_research_and_privacy_warnings(self):
        result=fixture();result['reports'][0]['meta']['tool']='customer8_churn'
        result['coverage_reasons']=['privacy_scope_override']
        self.assertIn('unreliable',' '.join(critical_warnings(result,'English')))
        self.assertIn('fixed company-wide',' '.join(critical_warnings(result,'English')))

@unittest.skipUnless((Path(__file__).resolve().parents[1]/'data/cottonil.db').exists(),'Local original DB required')
class LocalContextTests(unittest.TestCase):
    def test_real_english_arabic_followups_preserve_pair_and_period(self):
        state=ba.fresh_state()
        with patch('services.business_assistant.GroqProvider',side_effect=AssertionError('No paid calls')):
            first=ba.run('Compare sales BR001 and BR002 last 3 months',SCOPE,state,settings=Settings())
            self.assertEqual(first['resolved']['pair'],['BR001','BR002'])
            for question in ('مين فيهم حقق مجمل ربح أعلى؟','And gross profit?','طب الشهر اللي قبله؟'):
                result=ba.run(question,SCOPE,state,settings=Settings())
                text=assemble(result,'English',question)
                self.assertEqual(result['resolved']['pair'],['BR001','BR002'])
                report=result['reports'][0]
                profit=next(row for row in report['data'] if row.get('metric')=='gross_profit')
                expected=abs(Decimal(str(profit['location_a'])).quantize(Decimal('.01'))-Decimal(str(profit['location_b'])).quantize(Decimal('.01')))
                self.assertIn(f'{expected:,.2f}',text)
                self.assertNotIn('sales',text);self.assertNotIn('المبيعات',text)
            self.assertEqual(result['resolved']['scope']['start'],'2026-06-01')

class PresentationUITests(unittest.TestCase):
    def test_summary_first_details_collapsed_question_language_and_visible_warning(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120).run()
        app.sidebar.radio[1].set_value('AI Business Assistant').run()
        # A pronoun-only question requires a real structured prior request.
        state=ba.fresh_state();seed=ba.resolve('Compare gross profit BR001 and BR002 from 2026-07-01 to 2026-09-30',dict(app.session_state['active_scope']),state)
        state.update(seed);app.session_state['a9_state']=state
        question='مين فيهم حقق مجمل ربح أعلى؟';answer=fixture()
        with patch('ui.assistant_phase9.run',return_value=answer):app.chat_input[0].set_value(question).run()
        self.assertFalse(app.exception)
        message=app.session_state['dialog'][-1]
        self.assertTrue(message['content'].startswith('موقع BR001'))
        self.assertEqual(message['details'],'')
        self.assertFalse(any('الطلب المفسّر' in m.value for m in app.chat_message[-1].markdown))
        evidence=[e for e in app.expander if e.label=='النتائج التفصيلية']
        self.assertEqual(len(evidence),1);self.assertFalse(evidence[0].proto.expanded)
        self.assertNotIn('الطلب المفسّر',app.chat_message[-1].markdown[0].value)
        # Dashboard Arabic, typed English: both the direct answer and details use English.
        question='Which has higher gross profit?';answer=fixture();answer['answer_state']='partial'
        with patch('ui.assistant_phase9.run',return_value=answer):app.chat_input[0].set_value(question).run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state['dialog'][-1]['answer_lang'],'English')
        self.assertTrue(any('Partial answer' in e.value for e in app.chat_message[-1].warning))
        evidence=[e for e in app.chat_message[-1].expander if e.label=='Detailed results']
        self.assertEqual(len(evidence),1);self.assertFalse(evidence[0].proto.expanded)
        research=dict(answer_state='full',status='supported',resolved=dict(scope=SCOPE,pair=[]),reports=[dict(meta=dict(tool='customer8_churn',period='2025-10-01 to 2026-09-30',
            classification='experimental research'),data=[dict(c8_roc_auc=.5)],plot=None)])
        with patch('ui.assistant_phase9.run',return_value=research):app.chat_input[0].set_value('Is customer churn reliable?').run()
        self.assertFalse(app.exception)
        self.assertIn('Customer model research is unreliable and unsuitable for individual decisions.',[e.value for e in app.chat_message[-1].warning])

if __name__=='__main__':unittest.main()
