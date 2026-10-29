"""Parameterized context/coverage regression over catalog-derived entities.

All numbers originate in local approved services or explicit test-only stubs.
No real Groq client may be constructed in these tests.
"""
import copy,itertools,unittest,math
from calendar import monthrange
from datetime import date,timedelta
from unittest.mock import patch
from services import metrics as kpi,assistant_registry as registry,business_assistant as ba
from services.assistant_context import resolve,Clarification
from services.assistant_quality import assess
from services.assistant_request import output_issues
from services.assistant_config import Settings
from services.sales_branch import period_summary
from services.filters import filters
from ui.assistant_answers import assemble

class ContextCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master=kpi.branches();cls.first,cls.last=kpi.metadata()
        cls.catalog=kpi.read('SELECT DISTINCT category_en FROM products_catalog ORDER BY 1')
        groups=[g.branch_id.tolist() for _,g in cls.master.groupby('retail_location_type')]
        cls.pairs=[(g[1],g[-2]) for g in groups]+[(groups[0][2],groups[1][3])]
        cls.windows=[('2024-02-03','2024-02-21'),('2025-07-01','2025-09-30'),('2026-01-01','2026-01-31')]
        cls.scope=dict(start=str(cls.first),end=str(cls.last),branch=None,location_type=None,category=cls.catalog.category_en.iloc[0])
    def setUp(self):
        self.block=patch('services.business_assistant.GroqProvider',side_effect=AssertionError('No paid tests'));self.block.start();self.addCleanup(self.block.stop)
    def commit(self,question,state,scope=None):
        r=resolve(question,scope or self.scope,state)
        state.update(r);state['last_plan']=ba.plan_offline(question,r)
        return r
    def test_parameterized_pairs_dates_metrics_bilingual_references(self):
        metrics={'sales':'sales','gross profit':'gross_profit','gross margin':'gross_margin_pct','orders':'orders','average order value':'aov','units sold':'units','growth':'growth_pct'}
        refs=('same branches','them','نفس الفرعين','قارنهم')
        for pair,window,(label,metric) in itertools.product(self.pairs,self.windows,metrics.items()):
            with self.subTest(pair=pair,window=window,metric=metric):
                state=ba.fresh_state();a,b=pair;start,end=window
                initial=self.commit(f'Compare {label} {a} and {b} from {start} to {end}',state)
                for text in refs:
                    r=self.commit(text,state)
                    self.assertEqual(r['pair'],list(pair));self.assertEqual(r['scope'],initial['scope'])
                    self.assertEqual(r['request']['metrics'],[metric])
                    plan=ba.plan_offline(text,r)
                    self.assertTrue(plan);self.assertNotIn('location_ranking',[n for n,_ in plan])
                    self.assertTrue(all(n in ('two_location_comparison','profit5_pair') for n,_ in plan))
                r=self.commit('الشهر اللي قبله',state)
                previous=date.fromisoformat(start)-timedelta(days=1)
                self.assertEqual(r['scope']['end'],str(previous));self.assertEqual(r['scope']['start'],str(previous.replace(day=1)))
                self.assertEqual(r['request']['metrics'],[metric]);self.assertEqual(r['pair'],list(pair))
    def test_patch_only_explicit_dimensions(self):
        for pair in self.pairs:
            state=ba.fresh_state();a,b=pair
            first=self.commit(f'Compare gross margin {a} and {b} from 2024-02-01 to 2024-02-29',state)
            r=self.commit('from 2025-04-05 to 2025-04-27',state)
            self.assertEqual(r['pair'],list(pair));self.assertEqual(r['request']['metrics'],['gross_margin_pct'])
            self.assertEqual(r['scope']['category'],first['scope']['category'])
            r=self.commit('And orders?',state)
            self.assertEqual(r['scope']['start'],'2025-04-05');self.assertEqual(r['request']['metrics'],['orders'])
            replacement=self.master.branch_id.iloc[-1]
            r=self.commit(f'Sales {replacement}',state)
            self.assertEqual(r['scope']['branch'],replacement);self.assertEqual(r['pair'],[])
            self.assertEqual(r['scope']['start'],'2025-04-05');self.assertEqual(r['scope']['category'],first['scope']['category'])
    def test_metric_change_preserves_product_grain_and_direction(self):
        state=ba.fresh_state()
        self.commit('Lowest sales products from 2024-03-01 to 2024-03-31',state)
        r=self.commit('And gross profit?',state)
        self.assertEqual(r['request']['aggregation'],'product')
        self.assertEqual(ba.plan_offline('And gross profit?',r),[('profit5_products',{'metric':'gross_profit','ascending':True})])
    def test_daily_grain_survives_metric_and_date_changes(self):
        state=ba.fresh_state();self.commit('Daily sales from 2024-03-01 to 2024-03-10',state)
        self.commit('And gross profit?',state)
        r=self.commit('from 2024-04-03 to 2024-04-20',state)
        self.assertEqual(r['request']['metrics'],['gross_profit'])
        self.assertEqual(ba.plan_offline('same period',r),[('sales4_trends',{'grain':'daily'})])
    def test_missing_capability_clarifies_instead_of_ignoring_direction(self):
        r=ba.run('Lowest gross profit categories',self.scope,settings=Settings())
        self.assertEqual(r['code'],'no_compatible_tool');self.assertFalse(r['semantic_complete'])
    def test_entity_reset_does_not_erase_explicit_aggregation(self):
        for phrase,grain in [('company-wide gross profit products','product'),('all locations monthly sales','time'),('highest company-wide sales branches','locations')]:
            with self.subTest(grain=grain):
                r=resolve(phrase,self.scope,ba.fresh_state())
                self.assertEqual(r['request']['aggregation'],grain)
    def test_pair_summary_tool_cannot_satisfy_detailed_grain(self):
        a,b=self.pairs[0]
        for dimension in ('products','daily','categories'):
            with self.subTest(dimension=dimension),patch.object(registry,'execute') as execute:
                r=ba.run(f'Compare gross profit {dimension} {a} and {b}',self.scope,settings=Settings())
                self.assertEqual(r['code'],'no_compatible_tool');execute.assert_not_called()
    def test_wrong_model_tool_can_recover_only_to_compatible_evidence(self):
        from test_phase9 import FakeProvider,completion,call
        a,b=self.pairs[-1]
        provider=FakeProvider(completion([call('location_ranking',id='wrong')]),completion([call('profit5_pair',id='correct')]))
        result=ba.run(f'Compare gross profit {a} and {b} from 2025-01-01 to 2025-12-31',self.scope,
            connected=True,settings=Settings(api_key='fake'),provider=provider)
        self.assertTrue(result['semantic_complete']);self.assertEqual([r['meta']['tool'] for r in result['reports']],['profit5_pair'])
        self.assertEqual(result['resolved']['pair'],[a,b]);self.assertEqual(result['tool_events'][0]['status'],'rejected')
    def test_insufficient_metric_evidence_requires_compatible_tool(self):
        from test_phase9 import FakeProvider,completion,call
        a,b=self.pairs[-1]
        provider=FakeProvider(completion([call('profit5_pair',id='partial')]),completion([call('two_location_comparison',id='covered')]))
        result=ba.run(f'Compare average order value {a} and {b} from 2025-01-01 to 2025-12-31',self.scope,
            connected=True,settings=Settings(api_key='fake'),provider=provider)
        self.assertEqual(len(provider.sent),2);self.assertTrue(result['semantic_complete'])
        self.assertEqual(result['missing_metrics'],[]);self.assertEqual(result['resolved']['pair'],[a,b])
    def test_no_prior_pair_requires_clarification(self):
        for text in ('same branches','them','نفس الفرعين','قارنهم'):
            with self.subTest(text=text),self.assertRaises(Clarification):resolve(text,self.scope,ba.fresh_state())
    def test_explicit_type_is_not_silently_discarded(self):
        for kind,g in self.master.groupby('retail_location_type'):
            scope={**self.scope,'location_type':kind};pair=g.branch_id.iloc[:2].tolist()
            r=resolve('Compare sales '+' and '.join(pair),scope,ba.fresh_state())
            self.assertEqual(r['scope']['location_type'],kind)
            other=self.master.loc[self.master.retail_location_type.ne(kind),'branch_id'].iloc[0]
            with self.assertRaises(ValueError):resolve(f'Compare sales {pair[0]} and {other}',scope,ba.fresh_state())
    def test_dashboard_category_patch_keeps_pair_and_period(self):
        state=ba.fresh_state();pair=self.pairs[0]
        original=self.commit(f'Compare orders {pair[0]} and {pair[1]} from 2024-01-01 to 2024-01-31',state)
        new={**self.scope,'category':self.catalog.category_en.iloc[-1]}
        r=self.commit('same branches',state,new)
        self.assertEqual(r['pair'],list(pair));self.assertEqual(r['scope']['start'],original['scope']['start'])
        self.assertEqual(r['scope']['category'],new['category']);self.assertEqual(r['request']['metrics'],['orders'])
    def test_warehouse_dimension_changes_without_resetting_other_constraints(self):
        warehouses=registry.stock.inv.warehouses().warehouse_id.tolist()
        state=ba.fresh_state();self.commit('Warehouse inventory '+warehouses[0],state)
        original=dict(state['scope']);r=self.commit(warehouses[-1],state)
        self.assertEqual(r['warehouse'],warehouses[-1]);self.assertEqual(r['scope'],original)
        self.assertEqual(ba.plan_offline(warehouses[-1],r)[0][0],'inventory6_warehouse')
        r=self.commit('all warehouses',state)
        self.assertIsNone(r['warehouse']);self.assertEqual(r['scope'],original)
    def test_entity_grain_date_and_metric_mismatches_rejected(self):
        a,b=self.pairs[0];r=resolve(f'Compare gross profit {a} and {b} from 2024-01-01 to 2024-01-31',self.scope,ba.fresh_state())
        correct=registry.execute('profit5_pair',{},r)
        self.assertEqual(output_issues(correct,r),[])
        for dimension,value in [('period','2025-01-01 to 2025-01-31'),('branch_a',self.master.branch_id.iloc[-1]),('category',None)]:
            with self.subTest(dimension=dimension):
                wrong=copy.deepcopy(correct);wrong['meta'][dimension]=value
                with patch.object(registry,'execute',return_value=wrong),self.assertRaises(ValueError):ba.verified_execute('profit5_pair',{},r)
        with self.assertRaises(ValueError):registry.execute('location_ranking',{'metric':'gross_profit'},r)
        with self.assertRaises(ValueError):registry.execute('profit5_pair',{'metric':'sales'},r)
        product=resolve('Lowest gross profit products',self.scope,ba.fresh_state())
        with self.assertRaises(ValueError):registry.execute('profit5_products',{'metric':'sales'},product)
        with self.assertRaises(ValueError):registry.execute('profit5_products',{'metric':'gross_profit','ascending':False},product)
        missing=copy.deepcopy(correct);missing['data']=[row for row in missing['data'] if row['metric']!='gross_profit']
        quality=assess([missing],['profit5_pair'],r)
        self.assertFalse(quality['semantic_complete']);self.assertIn('gross_profit',quality['missing_metrics'])
    def test_unavailable_pair_forecast_never_runs_company_forecast(self):
        for pair in self.pairs:
            with patch.object(registry,'execute') as execute:
                result=ba.run('Compare forecast revenue '+' and '.join(pair),self.scope,settings=Settings())
            self.assertEqual(result['code'],'no_compatible_tool');self.assertFalse(result['semantic_complete']);execute.assert_not_called()
    def test_stock_winner_without_category_discloses_grain_limit(self):
        a,b=self.pairs[0];scope={**self.scope,'category':None}
        r=ba.run(f'Which has higher inventory risk {a} and {b}?',scope,settings=Settings())
        self.assertTrue(r['reports']);self.assertFalse(r['semantic_complete'])
        self.assertIn('unsupported_aggregation',r['coverage_reasons'])
    def test_company_customer_privacy_scope_is_not_pair_evidence(self):
        a,b=self.pairs[0];scope={**self.scope,'category':None}
        r=resolve(f'Compare sales and repeat customers {a} and {b}',scope,ba.fresh_state())
        report=dict(meta=dict(tool='customer8_summary',period=scope['start']+' to '+scope['end'],branch_id='all'),data=[dict(c8_identified=100)])
        quality=assess([report],['customer8_summary'],r)
        self.assertFalse(quality['semantic_complete']);self.assertIn('privacy_scope_override',quality['coverage_reasons'])
    def test_real_pair_metrics_reconcile_across_entities_and_periods(self):
        for pair,window in itertools.product(self.pairs,self.windows[:2]):
            with self.subTest(pair=pair,window=window):
                state=ba.fresh_state();a,b=pair;start,end=window
                first=ba.run(f'Compare sales {a} and {b} from {start} to {end}',self.scope,state,settings=Settings())
                for question,metric in [('And gross profit?','gross_profit'),('نفس الفرعين، هامش الربح؟','gross_margin_pct'),('And orders?','orders')]:
                    result=ba.run(question,self.scope,state,settings=Settings())
                    self.assertTrue(result['reports'])
                    report=result['reports'][0];row=next(v for v in report['data'] if v.get('metric')==metric)
                    unavailable=False
                    for branch,column in zip(pair,('location_a','location_b')):
                        # Approved pair policy deliberately marks empty AOV/margin
                        # unavailable, unlike the low-level overview's zero fallback.
                        expected=period_summary(filters(start,end,branch,category=self.scope['category']))['current'][metric]
                        if expected is None or not math.isfinite(expected):
                            self.assertIsNone(row[column]);unavailable=True
                        else:self.assertAlmostEqual(row[column],expected,places=6)
                    self.assertEqual(result['semantic_complete'],not unavailable,result.get('coverage_reasons'))
                    if unavailable:self.assertIn(metric,result['missing_metrics'])
                    text=assemble(result,'English',question)
                    self.assertNotIn('sales before refunds',text.casefold());self.assertNotIn('المبيعات',text)
                    self.assertEqual(result['resolved']['scope'],first['resolved']['scope'])

if __name__=='__main__':unittest.main()
