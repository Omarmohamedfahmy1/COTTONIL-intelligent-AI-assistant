"""Evidence/interpretation boundaries: synthetic aggregates + real offline/mock tools."""
import copy,itertools,unittest
from services.assistant_findings import components,observations,comparison
from services.assistant_quality import assess
from ui.assistant_answers import assemble,critical_warnings
from ui.assistant_evidence import prepare,sections,isolate

def fixture(values=(13,29),metric='c8_customers',question='Show customer segments'):
    scope=dict(start='2025-01-01',end='2025-12-31',branch=None,category=None,location_type=None)
    request=dict(metrics=[metric],aggregation='segment',parameters={},domains=['customers'],
        intent='analyze',answer_components=components(question),forecast=False)
    resolved=dict(scope=scope,pair=[],request=request)
    report=dict(meta=dict(tool='customer8_segments',period=scope['start']+' to '+scope['end'],branch_id='all'),
        data=[dict(c8_segment=name,**{metric:v}) for name,v in zip(('Group-K','Group-T'),values)])
    result=dict(reports=[report],resolved=resolved,status='supported')
    result.update(assess(result['reports'],['customer8_segments'],resolved))
    return result

class ManagerialAnswers(unittest.TestCase):
    def test_counts_and_labels_are_dynamic_in_both_languages(self):
        for values,ar in itertools.product(((13,29),(87,12),(0,43)),(False,True)):
            with self.subTest(values=values,ar=ar):
                q='اعرض شرائح العملاء وأعدادهم' if ar else 'Show customer segments and counts'
                r=fixture(values,question=q);before=copy.deepcopy(r);text=assemble(r,'English',q)
                self.assertEqual(r['answer_state'],'full');self.assertEqual(r,before)
                for value in values:self.assertIn(f'{value:,}',text)
                for label in ('Group-K','Group-T'):self.assertIn(label,text)
                self.assertNotIn('not available',text);self.assertIn('حقائق موثقة' if ar else 'Verified facts',text)
                self.assertNotIn('c8_customers',text)

    def test_description_and_review_are_predicates_not_business_claims(self):
        for metric,values,ar in itertools.product(('c8_customers','c8_orders','c8_revenue'),((12,40),(64,16)),(False,True)):
            with self.subTest(metric=metric,values=values,ar=ar):
                q='اشرح الشرائح وأيها يستحق اهتمام الإدارة' if ar else 'Explain segments and review priorities'
                r=fixture(values,metric,q);text=assemble(r,'English',q)
                self.assertEqual(r['answer_state'],'full');self.assertFalse(r['missing_answer_components'])
                winner='Group-K' if values[0]>values[1] else 'Group-T'
                note=text.split('\n\n')[-1];self.assertIn(winner,note)
                self.assertIn('ملاحظة وصفية' if ar else 'Descriptive observation',note)
                self.assertIn('محتملة' if ar else 'possible',note)
                self.assertNotIn('will churn',text);self.assertNotIn('probability',text)
                r['resolved']['request']['parameters']['ascending']=True
                low_note=assemble(r,'English',q).split('\n\n')[-1]
                self.assertIn('Group-T' if values[0]>values[1] else 'Group-K',low_note)
                self.assertIn('أقل' if ar else 'lowest',low_note)

    def test_ties_missing_suppressed_and_invalid_cells(self):
        tied=fixture((18,18),question='Explain review priorities');text=assemble(tied,'English','Explain review priorities')
        self.assertIn('no unique review priority',text)
        for invalid in (None,True,float('nan'),float('inf'),'20'):
            with self.subTest(invalid=invalid):
                r=fixture((36,invalid),question='Explain review priorities')
                self.assertEqual(r['answer_state'],'partial');self.assertIn('facts',r['missing_answer_components'])
                self.assertIn('36',assemble(r,'English','Explain review priorities'))
                self.assertNotIn('highest shown',assemble(r,'English','Explain review priorities'))
                self.assertTrue(critical_warnings(r,'English'))

    def test_causes_and_predictions_never_complete_from_counts(self):
        for q in ('Show segments and why customers stopped buying','اعرض الشرائح وأسباب توقف الشراء',
                  'Show segments and their churn probability','اعرض الشرائح واحتمال فقدان العملاء'):
            with self.subTest(q=q):
                r=fixture(question=q);self.assertEqual(r['answer_state'],'partial')
                self.assertFalse(r['semantic_complete']);self.assertIn('13',assemble(r,'English',q))
                warnings=' '.join(critical_warnings(r,'English'));self.assertIn('Unsupported conclusion',warnings)

    def test_partial_state_does_not_erase_facts_and_scope_rejection_is_kept(self):
        r=fixture();r.update(answer_state='unavailable',semantic_complete=False)
        safe=prepare(r,'Show segments',r['resolved'])
        self.assertEqual(safe['answer_state'],'partial');self.assertIn('29',assemble(safe,'English','Show segments'))
        r['reports'][0]['meta']['period']='2023-01-01 to 2023-12-31'
        safe=prepare(r,'Show segments',r['resolved'])
        # Fixed customer privacy scope is disclosed, never passed off as requested scope.
        self.assertNotEqual(safe['answer_state'],'full');self.assertIn('privacy_scope_override',safe['coverage_reasons'])

    def test_unreliable_model_does_not_swallow_other_verified_data(self):
        r=fixture(question='Show segments and review priorities')
        r['reports'].append(dict(meta=dict(tool='customer8_churn',state='unavailable'),data=[]))
        r.update(assess(r['reports'],['customer8_segments','customer8_churn'],r['resolved']))
        self.assertEqual(r['answer_state'],'partial');self.assertIn('29',assemble(r,'English','Show segments and review priorities'))
        self.assertIn('unreliable',' '.join(critical_warnings(r,'English')))
        research=dict(answer_state='partial',reports=[dict(meta=dict(tool='customer8_value',state='unreliable'),data=[dict(c8_predicted_revenue=19)])])
        self.assertIn('unreliable',assemble(research,'English','Customer revenue research'))
        self.assertFalse(observations(research['reports'],dict(metrics=['c8_predicted_revenue'])))
        from services.assistant_findings import coverage
        measured=coverage(research['reports'],dict(metrics=['c8_predicted_revenue'],answer_components=['facts','investigation','predictive_conclusion']))
        self.assertEqual(measured['supported_answer_components'],['facts'])
        self.assertEqual(measured['missing_answer_components'],['investigation','predictive_conclusion'])

    def test_cross_domain_facts_survive_missing_forecast(self):
        r=dict(answer_state='partial',resolved=dict(request=dict(metrics=['sales'],answer_components=['facts'])),reports=[
            dict(meta=dict(tool='forecast7_values',state='unavailable',reason='f7_missing'),data=[]),
            dict(meta=dict(tool='company_overview'),data=[dict(sales=321)])])
        text=assemble(r,'English','Company sales and forecast')
        self.assertIn('321.00 EGP',text);self.assertNotIn('Forecast unavailable',text)

    def test_generic_comparisons_stay_in_metric_period_and_domain(self):
        for tool,metric,dimension in (('location_ranking','sales','branch_id'),('profit5_products','gross_profit','product_id'),
                                      ('inventory6_stock','stock_units','category'),('forecast7_values','sales','month')):
            with self.subTest(tool=tool):
                field='central' if tool=='forecast7_values' else metric
                report=dict(meta=dict(tool=tool,period='fixture-window'),data=[{dimension:'Entity-X',field:42},{dimension:'Entity-Y',field:91}])
                cells=observations([report],dict(metrics=[metric]));pair=comparison(cells)
                self.assertEqual(pair['high']['entity'],'Entity-Y');self.assertEqual(pair['high']['value'],91)
                self.assertEqual(pair['high']['estimated'],tool.startswith('forecast7_'))
                other=copy.deepcopy(cells[0]);other.update(entity='Other',period='different-window',value=999)
                self.assertEqual(comparison(cells+[other])['high']['value'],91)

    def test_relevant_details_and_rtl_remain_available(self):
        r=fixture();r['reports'][0]['data'][0]['c8_revenue']=700
        safe=prepare(r,'Show segments',r['resolved']);views=sections(safe,'Show segments')
        self.assertTrue(views);self.assertNotIn('c8_revenue',views[0]['data'][0])
        self.assertIn('\u2066',isolate(assemble(safe,'Arabic','اعرض شرائح العملاء'),'Arabic'))

    def test_real_offline_mock_and_bilingual_followups(self):
        from scripts.audit_assistant import trace,fixture_context
        from services.business_assistant import fresh_state
        for mode,ar in itertools.product(('offline','mock'),(False,True)):
            with self.subTest(mode=mode,ar=ar):
                state=fresh_state();q='اعرض شرائح RFM وأعداد العملاء' if ar else 'Show RFM customer segments and counts'
                r,_=trace(q,fixture_context(),state,mode=mode)
                self.assertTrue(r['reports']);self.assertIn('موثقة' if ar else 'Verified',assemble(r,'English',q))
                follow='مين فيهم يستحق اهتمام الإدارة؟' if ar else 'Which of them deserves management attention?'
                r,_=trace(follow,fixture_context(),state,mode=mode)
                self.assertEqual(r['resolved']['request']['metrics'],['c8_customers'])
                self.assertIn('investigation',r['resolved']['request']['answer_components'])
                self.assertIn('ملاحظة وصفية' if ar else 'Descriptive observation',assemble(r,'English',follow))

if __name__=='__main__':unittest.main()
