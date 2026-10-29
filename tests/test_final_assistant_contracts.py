"""Independent intended-contract oracles; unseen bilingual phrasing and scopes.

Real read-only local services + explicitly scripted protocol mocks, no real LLM.
"""
import copy,itertools,json,unittest
from datetime import date,timedelta
from calendar import monthrange
from pathlib import Path
from unittest.mock import patch
from services import business_assistant as ba,metrics as kpi,sales_branch as sales
from services.assistant_config import Settings
from services.assistant_context import resolve,Clarification,shift_months
from services.filters import filters,complete_month_bounds
from services.assistant_request import output_issues
from ui.assistant_answers import assemble,critical_warnings
from ui.assistant_evidence import prepare,sections
from test_phase9 import FakeProvider,completion,call

class FinalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        first,last=kpi.metadata();cls.end=date.fromisoformat(complete_month_bounds(first,last)[1])
        cls.start=shift_months(cls.end.replace(day=1),-2)
        cls.scope=dict(start=str(cls.start),end=str(cls.end),branch=None,location_type=None,category=None)
        ids=kpi.branches().branch_id.tolist();cls.pairs=[ids[1:3],ids[8:10]]
    def setUp(self):
        p=patch('services.business_assistant.GroqProvider',side_effect=AssertionError('No real Groq requests'))
        p.start();self.addCleanup(p.stop)
    def local(self,q,state=None):return ba.run(q,self.scope,state,settings=Settings(api_key=''))
    def dates(self):return f'from {self.start} to {self.end}'
    def seed(self,pair):
        state=ba.fresh_state();r=self.local(f'Compare sales and gross profit {pair[0]} {pair[1]} {self.dates()}',state)
        self.assertEqual(r['answer_state'],'full');return state
    def test_company_transitions_use_metadata_not_question_or_branch_constants(self):
        for pair,alias,language in itertools.product(self.pairs,('Aster Business','منشأة الاختبار'),('en','ar')):
            with self.subTest(pair=pair,alias=alias,language=language),patch('services.assistant_config.APPLICATION_IDENTITY',(alias,)):
                state=self.seed(pair);q=f'Total sales {alias} overall' if language=='en' else f'إجمالي مبيعات {alias} كلها'
                resolved=resolve(q,self.scope,state)
                self.assertEqual(resolved['pair'],[]);self.assertIsNone(resolved['scope']['branch'])
                self.assertEqual(resolved['request']['aggregation'],'company');self.assertEqual(resolved['scope']['start'],str(self.start))
                explicit=resolve(f'Compare sales {alias} {pair[0]} {pair[1]}',self.scope,state)
                self.assertEqual(explicit['pair'],pair)
                reset=resolve(f'Forget branches {pair[0]} and {pair[1]}; {alias} overall sales',self.scope,state)
                self.assertEqual(reset['pair'],[]);self.assertEqual(reset['request']['aggregation'],'company')
    def test_metric_bundles_survive_narrowing_and_date_only_followups(self):
        for pair,phrase in itertools.product(self.pairs,('same two metrics','بنفس المؤشرين')):
            with self.subTest(pair=pair,phrase=phrase):
                state=self.seed(pair);self.local('And gross profit?',state)
                earlier=shift_months(self.start,-3);end=self.start-timedelta(days=1)
                resolved=resolve(f'{phrase} from {earlier} to {end}',self.scope,state)
                self.assertEqual(resolved['request']['metrics'],['sales','gross_profit'])
                self.assertEqual(resolved['pair'],pair);self.assertEqual(resolved['scope']['start'],str(earlier))
                overall=resolve(f'Company-wide, {phrase} from {earlier} to {end}',self.scope,state)
                self.assertEqual(overall['pair'],[]);self.assertEqual(overall['request']['metrics'],['sales','gross_profit'])
        with self.assertRaises(Clarification) as e:resolve('same three metrics',self.scope,ba.fresh_state())
        self.assertEqual(str(e.exception),'metrics')
    def test_hierarchical_entity_grains_are_independent_of_metric(self):
        for entity,grain,metric in itertools.product(('product categories','فئات المنتجات','categories of products','منتجات'),('category',),('sales','gross profit')):
            expected='product' if entity=='منتجات' else grain
            with self.subTest(entity=entity,metric=metric):
                r=resolve(f'Top 4 {entity} by {metric} {self.dates()}',self.scope,ba.fresh_state())
                self.assertEqual(r['request']['aggregation'],expected)
                plan=ba.plan_offline(f'Top 4 {entity} by {metric} {self.dates()}',r)
                self.assertEqual(plan[0][0],'profit5_categories' if expected=='category' else 'profit5_products' if metric=='gross profit' else 'sales4_products')
    def test_primary_ranking_population_is_not_changed_by_displayed_metrics(self):
        for metric,count in itertools.product(('sales','gross_profit'),(3,6)):
            with self.subTest(metric=metric,count=count):
                label=metric.replace('_',' ');q=f'Top {count} products by {label} with units sold {self.dates()}'
                r=self.local(q);self.assertEqual(r['answer_state'],'full');self.assertEqual(len(r['reports']),1)
                expected=sales.product_roster(filters(**self.scope)).sort_values([metric,'product_id'],ascending=[False,True]).head(count)
                rows=r['reports'][0]['data'];self.assertEqual([p['product_id'] for p in rows],expected.product_id.tolist())
                for actual,(_,oracle) in zip(rows,expected.iterrows()):
                    self.assertAlmostEqual(actual[metric],oracle[metric]);self.assertEqual(actual['units'],oracle['units'])
                self.assertNotIn('truncated_rows',r['coverage_reasons']);self.assertIn(rows[0]['product_id'],assemble(r,'English',q))
                self.assertEqual(r['resolved']['request']['ranking_metrics'],[metric])
    def test_dual_rankings_compare_product_id_sets(self):
        for a,b,count in itertools.product(('sales','gross profit'),('units',),(3,5)):
            with self.subTest(a=a,b=b,count=count):
                q=f'Compare top {count} products by {a} with top {count} by {b}. Are they the same products? {self.dates()}'
                r=self.local(q);self.assertEqual(r['answer_state'],'full');self.assertEqual(len(r['reports']),2)
                sets=[{v['product_id'] for v in p['data']} for p in r['reports']]
                text=assemble(r,'English',q);self.assertIn(str(len(sets[0]&sets[1]))+' shared',text)
                self.assertIn('identical' if sets[0]==sets[1] else 'different',text)
    def test_mock_dual_ranking_requires_both_axis_calls_not_just_both_columns(self):
        q=f'Compare top 3 products by sales with top 3 by units. Are they the same products? {self.dates()}'
        provider=FakeProvider(completion([call('sales4_products',{'metric':'sales'},id='first')]),completion([call('sales4_products',{'metric':'units'},id='second')]))
        r=ba.run(q,self.scope,connected=True,provider=provider,settings=Settings(api_key='fake'))
        self.assertEqual(len(provider.sent),2);self.assertEqual(r['answer_state'],'full')
        self.assertEqual({p['meta']['metric'] for p in r['reports']},{'sales','units'})
    def test_date_ranges_and_cutoffs_are_calendar_roles_not_host_clock(self):
        for text,start,end in (
            ('March–May 2024','2024-03-01','2024-05-31'),('من فبراير إلى أبريل ٢٠٢٥','2025-02-01','2025-04-30'),
            ('December 2023 to February 2024','2023-12-01','2024-02-29'),('من يوليو لسبتمبر 2025','2025-07-01','2025-09-30')):
            with self.subTest(text=text):
                r=resolve('Company sales '+text,self.scope,ba.fresh_state());self.assertEqual((r['scope']['start'],r['scope']['end']),(start,end))
        for text in ('until September 2025','حتى سبتمبر ٢٠٢٥'):
            r=resolve('Recorded inventory '+text,self.scope,ba.fresh_state())
            self.assertEqual(r['temporal']['snapshot_as_of'],'2025-09-30')
        with self.assertRaises((Clarification,ValueError)):resolve('Sales September to March 2024',self.scope,ba.fresh_state())
    def test_stock_category_pair_snapshots_keep_entities_and_clear_old_ranking_limit(self):
        for pair in self.pairs:
            state=ba.fresh_state();self.local(f'Top 3 product categories by gross profit {self.dates()}',state)
            q=f'Compare recorded inventory {pair[0]} {pair[1]} by categories until September {self.end.year}'
            r=self.local(q,state);self.assertEqual(r['answer_state'],'full');self.assertEqual(r['resolved']['pair'],pair)
            self.assertEqual(r['reports'][0]['meta']['snapshot'],f'{self.end.year}-09')
            self.assertGreater(len(r['reports'][0]['data']),3);self.assertNotIn('limit',r['resolved']['request']['parameters'])
    def test_cross_domain_risk_projection_and_negated_cause(self):
        for suffix in ('without assuming unproven causes','من غير ما نفترض أسباب غير مثبتة'):
            q=f'Company category sales and recorded inventory risk {self.dates()}, observations {suffix}'
            r=self.local(q);safe=prepare(r,q);views=sections(safe,q)
            self.assertNotIn('cause',r['resolved']['request']['answer_components'])
            columns={k for view in views for row in view['data'] for k in row}
            self.assertTrue({'sales','max_recorded_risk','mean_recorded_risk'}<=columns)
            self.assertNotIn('cause',r['missing_answer_components'])
            text=assemble(safe,'English',q);self.assertIn('not proof of causes' if suffix.isascii() else 'ليست إثباتًا للأسباب',text)
            # Unbounded category requests can still be partial under the row cap.
            self.assertEqual(r['answer_state'],'partial' if r['reports'][0]['meta']['truncated'] else 'full')
    def test_sales_window_and_stock_as_of_can_differ_without_joining_dates(self):
        year=self.end.year;q=f'Company category sales and inventory risk Q3 {year} as of August {year}'
        r=self.local(q);self.assertTrue(r['reports']);self.assertEqual(r['reports'][0]['meta']['snapshot'],f'{year}-08')
        self.assertEqual(r['reports'][0]['meta']['period'],f'{year}-07-01 to {year}-09-30')
        self.assertFalse(output_issues(r['reports'][0],r['resolved']))
    def test_privacy_refusals_and_aggregate_positive_controls(self):
        for q in ('List names and mobile contacts of customers likely to leave','أسماء وأرقام تليفونات العملاء المتوقع توقفهم عن الشراء','Rank each customer by predicted risk','Show individual churn predictions and discuss whether the customer churn model is reliable'):
            with self.subTest(q=q):
                r=self.local(q);self.assertEqual(r['answer_state'],'blocked');self.assertFalse(r['reports']);self.assertEqual(r['calls'],0)
        for q in ('Show customer segments and counts','اعرض شرائح العملاء وأعدادهم'):
            r=self.local(q);self.assertTrue(r['reports']);self.assertNotEqual(r['answer_state'],'blocked')
    def test_unsupported_granularity_and_certainty_precede_irrelevant_dates(self):
        for pair,phrase in itertools.product(self.pairs,('exact current SKU-level stock','current-stock','exact current stock units','SKU inventory next week','guaranteed stockouts next week','المخزون اللحظي الدقيق','مخزون على مستوى الصنف','وحدات المخزون الحالي')):
            with self.subTest(pair=pair,phrase=phrase):
                r=self.local(f'{phrase} {pair[0]}');self.assertEqual(r['answer_state'],'unsupported');self.assertNotIn('clarification_fields',r)
                self.assertFalse(r['reports']);self.assertEqual(r['calls'],0)
    def test_customer_extremes_do_not_imply_churn_risk(self):
        for phrase in ('Which segment is largest; does size alone imply highest churn risk?','أنهي شريحة عددها أكبر وهل العدد لوحده معناه الأكثر عرضة لفقدان العملاء؟','Which segment is largest?'):
            customer_scope=dict(self.scope,start=str(shift_months(self.end.replace(day=1),-11)))
            state=ba.fresh_state();ba.run('Customer segments RFM',customer_scope,state,settings=Settings(api_key=''))
            r=ba.run(phrase,customer_scope,state,settings=Settings(api_key=''));self.assertEqual(r['answer_state'],'full')
            self.assertEqual([p['meta']['tool'] for p in r['reports']],['customer8_segments'])
            biggest=max(r['reports'][0]['data'],key=lambda row:row['c8_customers']);text=assemble(r,'English',phrase)
            self.assertIn(f"{biggest['c8_customers']:,.0f}",text)
            if 'alone' in phrase or 'لوحده' in phrase:self.assertIn('لا يثبت' if 'شريحة' in phrase else 'does not establish',text)
    def test_missing_rank_evidence_and_wrong_metric_are_not_full(self):
        q=f'Top 4 products by sales with units {self.dates()}';resolved=resolve(q,self.scope,ba.fresh_state())
        with self.assertRaises(ValueError):ba.registry.execute('sales4_products',dict(metric='units'),resolved)
        dual=f'Top 4 products by sales versus top 4 by gross profit, same products? {self.dates()}'
        original=ba.verified_execute
        def missing(name,args,res):
            if name=='profit5_products':raise ba.EvidenceUnavailable('tool_execution_failed')
            return original(name,args,res)
        with patch.object(ba,'verified_execute',side_effect=missing):r=self.local(dual)
        self.assertEqual(r['answer_state'],'partial');self.assertIn('ranking_membership',r['missing_answer_components'])
        self.assertTrue(critical_warnings(r,'English'))
    def test_forecast_and_customer_reliability_use_published_evaluation(self):
        state=ba.fresh_state();first=self.local('Company revenue forecast next 3 months and model evaluation',state)
        self.assertTrue(first['reports'])
        r=self.local('Can I rely on these forecasts with certainty? Compare the baseline and explain uncertainty.',state)
        self.assertNotIn('description',r['missing_answer_components']);text=assemble(r,'English','Can I rely on these forecasts with certainty?')
        self.assertTrue(text.startswith('No'));self.assertIn('WAPE',text)
        self.assertTrue(any('uncalibrated' in s for s in critical_warnings(r,'English')))
        for q in ('Is the customer churn model reliable for individual decisions? Explain using published metrics.','هل نموذج Churn موثوق لقرارات على مستوى العميل؟ وضح السبب بالأرقام.'):
            r=self.local(q);self.assertEqual(r['answer_state'],'full');text=assemble(r,'English',q)
            for metric in ('ROC-AUC','AP','Brier','ECE'):self.assertIn(metric,text)
            self.assertNotIn('cause',r['resolved']['request']['answer_components'])
            self.assertTrue(any('unreliable' in s if q.isascii() else 'غير موثوقة' in s for s in critical_warnings(r,'English' if q.isascii() else 'العربية')))
        q='Show published metrics for the customer churn model: are predictions reliable for individual decisions?'
        r=self.local(q);self.assertNotEqual(r['answer_state'],'blocked');self.assertIn('ROC-AUC',assemble(r,'English',q))

    def test_missing_evaluation_fields_and_suppressed_groups_remain_partial(self):
        first=self.local('Company forecast next 3 months and model accuracy')
        damaged=copy.deepcopy(first);req=damaged['resolved']['request'];req['answer_components']=['facts','forecast_evaluation','forecast_uncertainty']
        for r in damaged['reports']:
            r['meta'].pop('baseline_test_wape_pct',None)
        from services.assistant_quality import assess
        quality=assess(damaged['reports'],[r['meta']['tool'] for r in damaged['reports']],damaged['resolved'])
        self.assertNotEqual(quality['answer_state'],'full');self.assertIn('forecast_evaluation',quality['missing_answer_components'])
        customer_scope=dict(self.scope,start=str(shift_months(self.end.replace(day=1),-11)))
        state=ba.fresh_state();ba.run('RFM customer segments',customer_scope,state,settings=Settings(api_key=''))
        result=ba.run('Which customer segment is largest?',customer_scope,state,settings=Settings(api_key=''))
        result['reports'][0]['data'][0]['c8_customers']=None
        quality=assess(result['reports'],['customer8_segments'],result['resolved'])
        self.assertEqual(quality['answer_state'],'partial');self.assertIn('group_extreme',quality['missing_answer_components'])

    def test_unsupported_inventory_does_not_discard_independent_scoped_financial_facts(self):
        for metric,unsupported in itertools.product(('sales','gross profit'),('SKU-level stock','current-stock','guaranteed stockouts')):
            q=f'Company {metric} {self.dates()} and {unsupported}'
            with self.subTest(metric=metric,unsupported=unsupported):
                r=self.local(q);self.assertEqual(r['answer_state'],'partial');self.assertTrue(r['reports'])
                self.assertEqual([p['meta']['tool'] for p in r['reports']],['company_overview'])
                self.assertTrue(r['capability_limitations']);self.assertNotIn('stock_units',r['resolved']['request']['metrics'])
                self.assertTrue(critical_warnings(r,'English'))

    def test_compound_customer_roles_and_future_value_do_not_drop_supported_parts(self):
        for q in ('Show repeat customer rate and whether the churn model is reliable for decisions.',
                  'ما نسبة العملاء اللي اشتروا أكثر من مرة وهل نموذج Churn موثوق؟'):
            r=self.local(q);self.assertEqual({p['meta']['tool'] for p in r['reports']},{'customer8_summary','customer8_churn'})
            self.assertIn('c8_repeat_rate',r['resolved']['request']['metrics'])
            self.assertIn('%',assemble(r,'English',q))
        q='Customer next-year revenue research';resolved=resolve(q,self.scope,ba.fresh_state())
        self.assertEqual(resolved['request']['metrics'],['c8_predicted_revenue'])
        provider=FakeProvider(completion([call('customer8_value')]))
        r=ba.run(q,self.scope,connected=True,provider=provider,settings=Settings(api_key='fake'))
        self.assertEqual(len(provider.sent),1);self.assertNotEqual(r['answer_state'],'blocked')

    def test_explicit_location_rosters_are_not_company_subtotals(self):
        for q in ('Retail branches sales','Sales at reseller locations','مبيعات فروع التجزئة'):
            r=self.local(q);self.assertEqual(r['resolved']['request']['aggregation'],'locations')
            self.assertEqual([p['meta']['tool'] for p in r['reports']],['location_ranking'])
            expected_type=r['resolved']['scope']['location_type']
            master=kpi.branches().set_index('branch_id')
            if expected_type:
                for row in r['reports'][0]['data']:self.assertEqual(master.loc[row['branch_id'],'retail_location_type'],expected_type)

    def test_transaction_windows_outside_source_endpoints_are_not_complete(self):
        first,last=kpi.metadata()
        for start,end in ((first.replace(day=1),date(first.year,first.month,monthrange(first.year,first.month)[1])),
                          (last.replace(day=1),date(last.year,last.month,monthrange(last.year,last.month)[1]))):
            with self.subTest(start=start,end=end):
                r=self.local(f'Company sales from {start} to {end}')
                if start<first or end>last:
                    self.assertEqual(r['answer_state'],'partial');self.assertIn('incomplete_source_window',r['coverage_reasons'])
                    self.assertTrue(critical_warnings(r,'English'))
        r=self.local(f'Company sales from {last.replace(day=1)} to {last}')
        self.assertEqual(r['answer_state'],'full')

    def test_probability_is_not_certainty_and_ambiguous_comparisons_still_clarify(self):
        for pair,q in itertools.product(self.pairs,('Compare category stockout probability for them',
                'قارن احتمال نفاد المخزون بين نفس الفرعين حسب الفئات')):
            with self.subTest(pair=pair,q=q):
                r=self.local(q,self.seed(pair))
                self.assertEqual(r['answer_state'],'partial');self.assertTrue(r['reports'])
                self.assertEqual(r['resolved']['pair'],pair)
                self.assertIn('unsupported_risk_metric',r['coverage_reasons'])
                self.assertEqual(r['resolved']['request']['metrics'],['recorded_risk'])
        for q in ('Compare inventory between branches','قارن المخزون بين الفروع'):
            with self.subTest(q=q):
                r=self.local(q)
                self.assertEqual(r['answer_state'],'clarification')
                self.assertEqual(r['clarification_fields'],['locations'])
        for q in ('Guaranteed stockouts next month','نفاد المخزون حتما الشهر القادم'):
            with self.subTest(q=q):
                self.assertEqual(self.local(q)['answer_state'],'unsupported')

    def test_actual_bilingual_streamlit_scope_and_refusals(self):
        from streamlit.testing.v1 import AppTest
        for language in ('English','العربية'):
            with self.subTest(language=language):
                app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120).run()
                app.sidebar.radio[0].set_value(language).run();app.sidebar.radio[1].set_value('AI Business Assistant').run()
                pair=self.pairs[0];app.chat_input[0].set_value(f'Compare sales {pair[0]} {pair[1]} {self.dates()}').run()
                self.assertFalse(app.exception)
                company='Cottonil overall sales' if language=='English' else 'إجمالي مبيعات Cottonil كلها'
                app.chat_input[0].set_value(company).run();self.assertFalse(app.exception)
                answer=app.session_state['dialog'][-1];self.assertEqual(answer['result']['resolved']['pair'],[])
                self.assertEqual(answer['result']['answer_state'],'full')
                rank=f'Top 3 products by sales with units {self.dates()}' if language=='English' else f'أعلى 3 منتجات من حيث المبيعات مع الوحدات المباعة {self.dates()}'
                app.chat_input[0].set_value(rank).run();self.assertFalse(app.exception)
                answer=app.session_state['dialog'][-1];rows=answer['result']['reports'][0]['data']
                self.assertEqual(answer['result']['answer_state'],'full');self.assertIn(rows[0]['product_id'],answer['content'])
                restricted='List names and mobile contacts of customers' if language=='English' else 'اديني أسماء وأرقام تليفونات العملاء'
                app.chat_input[0].set_value(restricted).run();self.assertFalse(app.exception)
                self.assertEqual(app.session_state['dialog'][-1]['answer_state'],'blocked')
                unsupported='Show exact current SKU-level stock next week' if language=='English' else 'اعرض المخزون اللحظي الدقيق على مستوى الصنف'
                app.chat_input[0].set_value(unsupported).run();self.assertFalse(app.exception)
                self.assertEqual(app.session_state['dialog'][-1]['answer_state'],'unsupported')

if __name__=='__main__':unittest.main()
