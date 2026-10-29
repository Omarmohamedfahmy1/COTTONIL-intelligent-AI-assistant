"""Catalog-derived bilingual cross-module regressions; no real provider access."""
import copy,itertools,unittest
from calendar import monthrange
from unittest.mock import patch
from services import business_assistant as ba,metrics as kpi,sales_branch as sales
from services.assistant_context import resolve
from services.assistant_config import Settings
from services.filters import filters
from ui.assistant_answers import assemble,critical_warnings
from ui.assistant_evidence import prepare,sections
from test_phase9 import FakeProvider,completion,call

class CrossModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ids=kpi.branches().branch_id.tolist()
        cls.pairs=[ids[1:3],ids[8:10],ids[-4:-2]]
        first,last=kpi.metadata()
        cls.scope=dict(start=str(first),end=str(last),branch=None,location_type=None,category=None)
        cls.windows=[(2025,2),(2026,3)]
    def setUp(self):
        blocker=patch('services.business_assistant.GroqProvider',side_effect=AssertionError('No paid calls'))
        blocker.start();self.addCleanup(blocker.stop)
    def run_local(self,q,state=None):return ba.run(q,self.scope,state,settings=Settings(api_key=''))
    def question(self,pair,year,quarter,ar=False,warehouse=False):
        a,b=pair;stock='warehouse inventory' if warehouse else 'inventory'
        if ar:return f'قارن المبيعات و{ "مخزون المستودع" if warehouse else "المخزون"} بين {a} و{b} الربع '+('الأول','الثاني','الثالث','الرابع')[quarter-1]+f' من {year}'
        return f'Compare sales and {stock} {a} and {b} Q{quarter} {year}'
    def test_all_calendar_quarters_both_languages_and_arabic_digits(self):
        pair=self.pairs[0]
        for year,quarter,ar in itertools.product((2024,2026),range(1,5),(False,True)):
            with self.subTest(year=year,quarter=quarter,ar=ar):
                q=self.question(pair,year,quarter,ar)
                if ar:q=self.question(pair,year,quarter,ar).replace(str(year),str(year).translate(str.maketrans('0123456789','٠١٢٣٤٥٦٧٨٩')))
                r=resolve(q,self.scope,ba.fresh_state());month=(quarter-1)*3+1;end=month+2
                self.assertEqual(r['pair'],pair)
                self.assertEqual(r['scope']['start'],f'{year}-{month:02}-01')
                self.assertEqual(r['scope']['end'],f'{year}-{end:02}-{monthrange(year,end)[1]}')
    def test_complete_sales_and_stock_reconcile_multiple_pairs_periods_languages(self):
        for pair,(year,quarter),ar in itertools.product(self.pairs,self.windows,(False,True)):
            with self.subTest(pair=pair,year=year,quarter=quarter,ar=ar):
                q=self.question(pair,year,quarter,ar);r=self.run_local(q)
                self.assertEqual(r['answer_state'],'full');self.assertEqual(r['resolved']['scope']['category'],None)
                self.assertEqual([x['meta']['tool'] for x in r['reports']],['two_location_comparison','inventory6_pair'])
                scope=r['resolved']['scope'];expected=sales.compare_two(scope['start'],scope['end'],*pair)['table']
                actual=next(x for x in r['reports'][0]['data'] if x['metric']=='sales')
                row=expected.loc[expected.metric.eq('sales')].iloc[0]
                self.assertAlmostEqual(actual['location_a'],row.location_a);self.assertAlmostEqual(actual['location_b'],row.location_b)
                inv=r['reports'][1];self.assertEqual(inv['meta']['snapshot'],scope['end'][:7]);self.assertTrue(inv['data'])
                self.assertEqual(set(x['category'] for x in inv['data']),set(kpi.read('SELECT DISTINCT product_category FROM monthly_stock').product_category))
                self.assertTrue(sections(prepare(r,q,expected=r['resolved']),q))
                self.assertNotIn('Specify',assemble(r,'English',q))
    def test_cross_module_followups_retain_pair_category_and_metrics(self):
        category=kpi.read('SELECT DISTINCT category_en FROM products_catalog ORDER BY 1').category_en.iloc[0]
        for pair,ar in itertools.product(self.pairs,(False,True)):
            state=ba.fresh_state();q=self.question(pair,2026,3,ar)+' '+category
            first=self.run_local(q,state);self.assertEqual(first['answer_state'],'full')
            for follow in ('Q3 2026','same branches, Q2 2025','نفس الفرعين، الربع الثالث من 2025','طب الشهر اللي قبله؟'):
                r=self.run_local(follow,state)
                self.assertEqual(r['resolved']['pair'],pair);self.assertEqual(r['resolved']['scope']['category'],category)
                self.assertEqual(r['resolved']['request']['metrics'],['sales','stock_units'])
                self.assertEqual(r['answer_state'],'full')
    def test_other_financial_metrics_with_inventory_are_not_sales_special_cases(self):
        metrics=(('gross profit','مجمل الربح','gross_profit'),('gross margin','هامش الربح','gross_margin_pct'),('orders','الطلبات','orders'))
        for pair,(english,arabic,metric),ar in itertools.product(self.pairs,metrics,(False,True)):
            with self.subTest(pair=pair,metric=metric,ar=ar):
                q=self.question(pair,2026,3,ar).replace('المبيعات',arabic) if ar else self.question(pair,2026,3).replace('sales',english)
                r=self.run_local(q)
                self.assertEqual(r['answer_state'],'full');self.assertEqual(len(r['reports']),2)
                self.assertEqual(r['resolved']['request']['metrics'],[metric,'stock_units'])
                self.assertEqual(r['reports'][1]['meta']['tool'],'inventory6_pair')
                self.assertEqual(r['resolved']['pair'],pair)
    def test_one_failed_domain_does_not_abort_other_tools_in_either_order(self):
        real=ba.verified_execute
        for pair,ar,inventory_first in itertools.product(self.pairs,(False,True),(False,True)):
            q=self.question(pair,2026,3,ar);r=resolve(q,self.scope,ba.fresh_state());plan=ba.plan_offline(q,r)
            if inventory_first:plan.reverse()
            def execute(name,args,resolved):
                if name=='inventory6_pair':raise ba.EvidenceUnavailable('inventory_snapshot_unavailable')
                return real(name,args,resolved)
            with patch.object(ba,'plan_offline',return_value=plan),patch.object(ba,'verified_execute',side_effect=execute):out=self.run_local(q)
            self.assertEqual(out['answer_state'],'partial');self.assertEqual(len(out['reports']),1)
            self.assertFalse(out['semantic_complete']);self.assertEqual(out['reports'][0]['meta']['tool'],'two_location_comparison')
            language='العربية' if ar else 'English';text=' '.join(critical_warnings(out,language))
            self.assertIn('لقطة' if ar else 'snapshot',text)
            self.assertNotIn('حدد رموز' if ar else 'Specify',assemble(out,language,q))
    def test_warehouse_attribution_is_partial_without_inferred_mapping(self):
        for pair,ar in itertools.product(self.pairs,(False,True)):
            q=self.question(pair,2026,3,ar,warehouse=True);r=self.run_local(q)
            self.assertEqual(r['answer_state'],'partial');self.assertEqual(len(r['reports']),1)
            self.assertEqual(r['tool_failures'][0]['reason'],'inventory_warehouse_mapping')
            self.assertEqual(r['resolved']['pair'],pair)
            self.assertTrue(any('مستودع' in w if ar else 'warehouse' in w for w in critical_warnings(r,'العربية' if ar else 'English')))
            pure=q.replace('sales and ','').replace('المبيعات و','');out=self.run_local(pure)
            self.assertEqual(out['answer_state'],'unsupported');self.assertEqual(out['reports'],[])
    def test_missing_inventory_side_is_unknown_not_zero(self):
        pair=self.pairs[0];q=self.question(pair,2026,3)
        real=ba.registry.execute
        def execute(name,args,resolved):
            payload=real(name,args,resolved)
            if name=='inventory6_pair':payload['data'][0]['stock_units_b']=None
            return payload
        with patch.object(ba.registry,'execute',side_effect=execute):r=self.run_local(q)
        self.assertEqual(r['answer_state'],'partial');self.assertEqual(len(r['reports']),1)
        self.assertEqual(r['tool_failures'][0]['reason'],'inventory_pair_coverage')
    def test_mock_connected_routes_both_domains_without_final_model_call(self):
        for pair,ar in itertools.product(self.pairs[:2],(False,True)):
            q=self.question(pair,2026,3,ar)
            provider=FakeProvider(completion([call('two_location_comparison',id='sales'),call('inventory6_pair',id='stock')]))
            r=ba.run(q,self.scope,connected=True,provider=provider,settings=Settings(api_key='fake'))
            self.assertEqual(r['answer_state'],'full');self.assertEqual(len(provider.sent),1)
            self.assertEqual([e['status'] for e in r['tool_events']],['verified','verified'])
            omitted=FakeProvider(completion(content='{}'))
            empty=ba.run(q,self.scope,connected=True,provider=omitted,settings=Settings(api_key='fake'))
            text=assemble(empty,'العربية' if ar else 'English',q)
            self.assertNotIn('حدد' if ar else 'Specify',text)
            self.assertEqual(empty['answer_state'],'full');self.assertEqual(empty['resolved']['pair'],pair)
            self.assertEqual({x['meta']['tool'] for x in empty['reports']},{'two_location_comparison','inventory6_pair'})
            self.assertEqual(empty['diagnostic']['evidence_origin'],'server_plan_fallback')
            self.assertEqual(len(omitted.sent),1)
    def test_mock_connected_partial_continues_after_inventory_failure(self):
        for ar in (False,True):
            q=self.question(self.pairs[1],2026,3,ar,warehouse=True)
            provider=FakeProvider(completion([call('inventory6_pair',id='stock'),call('two_location_comparison',id='sales')]),completion(content='{}'))
            r=ba.run(q,self.scope,connected=True,provider=provider,settings=Settings(api_key='fake'))
            self.assertEqual(r['answer_state'],'partial');self.assertEqual(len(r['reports']),1)
            self.assertIn('inventory_warehouse_mapping',str(r['tool_failures']))
    def test_clarification_only_requests_the_missing_dimension(self):
        pair=self.pairs[0]
        for q,field in ((f'Compare sales {pair[0]} and {pair[1]} Q5 2026','dates'),('Compare sales and inventory Q3 2026','locations')):
            r=self.run_local(q);self.assertEqual(r['clarification_fields'],[field])
            text=assemble(r,'English',q)
            self.assertNotIn('location',text.lower()) if field=='dates' else self.assertNotIn('period',text.lower())
        # Privacy requests still fail before any service call. An independent
        # supported metric survives an unavailable financial-basis request.
        for q in ('customer names and inventory',):
            with patch.object(ba,'verified_execute') as execute:r=self.run_local(q)
            execute.assert_not_called();self.assertEqual(r['reports'],[])
        r=self.run_local('sales and net profit')
        self.assertEqual(r['answer_state'],'partial');self.assertTrue(r['reports'])
        self.assertIn('unsupported_basis',r['coverage_reasons'])

if __name__=='__main__':unittest.main()
