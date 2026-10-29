"""Independent service oracles for answer cardinality, periods and all measures.

All connected providers below are scripted; no real Groq requests.
"""
import copy,itertools,unittest
from pathlib import Path
from unittest.mock import patch
from services import business_assistant as ba,metrics as kpi,sales_branch as sales
from services.assistant_config import Settings
from services.filters import filters
from services.assistant_quality import assess
from services.assistant_calendar import named_period
from ui.assistant_answers import assemble,critical_warnings
from ui.assistant_evidence import prepare,sections
from test_phase9 import FakeProvider,completion,call

class CriticalAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        first,last=kpi.metadata();cls.year=last.year;ids=kpi.branches().branch_id.tolist()
        cls.pairs=[ids[4:6],ids[15:17]]
        cls.scope=dict(start=f'{last.year}-01-01',end=f'{last.year}-09-30',branch=None,category=None,location_type=None)
    def setUp(self):
        p=patch.object(ba,'GroqProvider',side_effect=AssertionError('No live calls'));p.start();self.addCleanup(p.stop)
    def run_local(self,q,state=None,mode='offline',operations=None,**kw):
        provider=FakeProvider(completion([call(n,a,id='t'+str(i)) for i,(n,a) in enumerate(operations)])) if operations else FakeProvider(completion(content='fabricated net profit 999999'))
        r=ba.run(q,self.scope,state,connected=mode!='offline',provider=provider if mode!='offline' else None,settings=kw.pop('settings',Settings(api_key='fake')),**kw)
        if mode!='offline':self.assertEqual(len(provider.sent),0 if kw.get('cancelled') and kw['cancelled']() else 1)
        self.assertNotIn('fabricated',str(r))
        return r
    def test_rank_cardinality_word_order_and_scripts_matches_location_oracle(self):
        for year,k,template in itertools.product((self.year-1,self.year),(3,5),(
            'Which {k} branches have the highest sales Q2 {year}?',
            'أنهي {k} فروع حققوا أعلى مبيعات في الربع الثاني من {year}؟',
            'اعرض أعلى {k} فروع بالمبيعات الربع الثاني من {year}.')):
            q=template.format(k=k,year=year)
            for mode in ('offline','empty'):
                with self.subTest(q=q,mode=mode):
                    r=self.run_local(q,mode=mode);self.assertEqual(r['answer_state'],'full')
                    actual=r['reports'][0]['data'];self.assertEqual(len(actual),k)
                    expected=sales.rank_locations(sales.location_roster(f'{year}-04-01',f'{year}-06-30'),'sales').head(k)
                    self.assertEqual([row['branch_id'] for row in actual],expected.branch_id.tolist())
                    text=assemble(r,'English',q)
                    for row,oracle in zip(actual,expected.itertuples()):
                        self.assertAlmostEqual(row['sales'],oracle.sales);self.assertIn(row['branch_id'],text);self.assertIn(f'{oracle.sales:,.2f}',text)
        r=self.run_local(f'أنهي ٥ فروع حققوا أعلى مبيعات الربع الثالث من {self.year}؟')
        self.assertEqual(len(r['reports'][0]['data']),5)
        r=self.run_local(f'Which five branches have highest sales Q3 {self.year}?');self.assertEqual(len(r['reports'][0]['data']),5)
    def test_bestselling_policy_explicit_quantity_value_and_metric_order(self):
        variants=[('إيه أكتر 4 منتجات مبيعاً خلال {year} من يناير لسبتمبر؟','units'),
                  ('Top 4 best-selling products January to September {year}','units'),
                  ('Top 4 best-selling products with gross profit January to September {year}','units'),
                  ('Best-selling 4 products by sales value January to September {year}','sales'),
                  ('Top 4 products with units ranked by sales January to September {year}','sales'),
                  ('أعلى 4 منتجات حسب الوحدات المباعة من يناير لسبتمبر {year}؟','units')]
        for (template,metric),year in itertools.product(variants,(self.year-1,self.year)):
            with self.subTest(template=template,year=year):
                q=template.format(year=year);r=self.run_local(q,mode='empty');self.assertEqual(r['answer_state'],'full')
                self.assertEqual(r['resolved']['request']['ranking_metrics'],[metric])
                self.assertEqual(r['resolved']['scope']['end'],f'{year}-09-30')
                oracle=sales.product_roster(filters(f'{year}-01-01',f'{year}-09-30')).sort_values([metric,'product_id'],ascending=[False,True]).head(4)
                actual=r['reports'][0]['data'];self.assertEqual([x['product_id'] for x in actual],oracle.product_id.tolist())
                text=assemble(r,'English',q)
                for row,expected in zip(actual,oracle.to_dict('records')):
                    self.assertAlmostEqual(row[metric],expected[metric]);self.assertIn(row['product_id'],text);self.assertIn(f'{expected[metric]:,.2f}',text)
    def test_monthly_series_and_both_extrema_match_independent_service(self):
        for year,q,mode in itertools.product((self.year-1,self.year),(
            'Monthly sales January to September {year}, show highest and lowest month.',
            'حللي اتجاه المبيعات الشهرية من يناير لسبتمبر {year}، وحدد أعلى وأقل شهر.'),('offline','empty')):
            with self.subTest(year=year,q=q,mode=mode):
                q=q.format(year=year);r=self.run_local(q,mode=mode);self.assertEqual(r['answer_state'],'full')
                oracle=sales.sales_trends(f'{year}-01-01',f'{year}-09-30',grain='monthly')
                actual=r['reports'][0]['data'];self.assertEqual(len(actual),9)
                text=assemble(r,'English',q)
                for row,expected in zip(actual,oracle.to_dict('records')):
                    self.assertEqual(row['period'],expected['period']);self.assertAlmostEqual(row['sales'],expected['sales'])
                    self.assertIn(row['period'],text);self.assertIn(f'{row["sales"]:,.2f}',text)
                for value in (oracle.sales.max(),oracle.sales.min()):
                    self.assertIn(f'{value:,.2f}',text)
                for word in (('أعلى','أقل') if not q.isascii() else ('Highest','Lowest')):self.assertIn(word,text)
    def test_single_extrema_ties_holes_nulls_and_caps_never_overclaim(self):
        for direction in ('highest','lowest','highest and lowest'):
            q=f'Monthly sales January to March {self.year}, {direction} month'
            r=self.run_local(q);r=copy.deepcopy(r);rows=r['reports'][0]['data']
            rows[0]['sales']=rows[1]['sales']=max(row['sales'] for row in rows)+1
            r['reports'][0]['meta']['truncated']=False
            text=assemble(r,'English',q)
            if 'highest' in direction:
                self.assertIn(rows[0]['period'],text.split('\n\n')[0]);self.assertIn(rows[1]['period'],text.split('\n\n')[0])
            for fault in ('hole','null','cap','duplicate'):
                damaged=copy.deepcopy(r);data=damaged['reports'][0]['data']
                if fault=='hole':data.pop(1)
                if fault=='null':data[0]['sales']=None
                if fault=='cap':damaged['reports'][0]['meta']['truncated']=True
                if fault=='duplicate':data[1]['period']=data[0]['period']
                quality=assess(damaged['reports'],['sales4_trends'],damaged['resolved']);self.assertNotEqual(quality['answer_state'],'full')
                if fault!='cap':self.assertTrue(quality['shape_issues'])
    def test_pair_all_three_metrics_fresh_and_after_unrelated_grains(self):
        for pair,year,seed in itertools.product(self.pairs,(self.year-1,self.year),('','Top 4 products by sales','Monthly company sales')):
            state=ba.fresh_state()
            if seed:self.run_local(f'{seed} Q2 {year}',state)
            for q in (f'Compare {pair[0]} and {pair[1]} sales, gross profit and average order value Q3 {year}',
                      f'قارن بين {pair[0]} و{pair[1]} من حيث المبيعات ومجمل الأرباح ومتوسط قيمة الطلب الربع الثالث من {year}'):
                with self.subTest(pair=pair,year=year,seed=seed,q=q):
                    r=self.run_local(q,state,mode='empty');self.assertEqual(r['answer_state'],'full')
                    self.assertEqual(set(r['resolved']['request']['metrics']),{'sales','gross_profit','aov'})
                    self.assertIsNone(r['resolved']['request']['detail_grain']);self.assertEqual(r['resolved']['pair'],pair)
                    oracle=sales.compare_two(f'{year}-07-01',f'{year}-09-30',*pair)['table']
                    rows={row['metric']:row for report in r['reports'] for row in report['data']}
                    text=assemble(r,'English',q)
                    for metric in ('sales','gross_profit','aov'):
                        expected=next(row for row in oracle.to_dict('records') if row['metric']==metric)
                        for col in ('location_a','location_b'):
                            self.assertAlmostEqual(rows[metric][col],expected[col]);self.assertIn(f'{expected[col]:,.2f}',text)
                    view=sections(prepare(r,q),q)[0];self.assertEqual(set(view['measures']),{'sales','gross_profit','aov'})
    def test_correct_selection_no_extra_model_call_and_sanitized_diagnostic(self):
        pair=self.pairs[0];q=f'Compare sales gross profit AOV {pair[0]} {pair[1]} Q3 {self.year}'
        r=self.run_local(q,mode='scripted',operations=[('two_location_comparison',{})])
        self.assertEqual(r['answer_state'],'full');d=r['diagnostic']
        self.assertEqual(d['selected'],[dict(operation='two_location_comparison')]);self.assertTrue(d['verified']);self.assertFalse(d['rejected'])
        self.assertIn('two_location_comparison',d['advertised']);self.assertNotIn('api_key',str(d))
    def test_wrong_selection_and_failures_do_not_trigger_speculative_fallback(self):
        pair=self.pairs[0];q=f'Compare sales {pair[0]} {pair[1]} Q3 {self.year}'
        provider=FakeProvider(completion([call('location_ranking')]),completion(content='{}'))
        r=ba.run(q,self.scope,connected=True,provider=provider,settings=Settings(api_key='fake'))
        self.assertNotEqual(r['answer_state'],'full');self.assertFalse(r['reports']);self.assertTrue(r['diagnostic']['rejected'])
        with patch.object(ba,'verified_execute',side_effect=RuntimeError('PRIVATE SQL KEY')):
            r=self.run_local(q,mode='empty');self.assertFalse(r['reports']);self.assertNotIn('PRIVATE',str(r));self.assertTrue(r['tool_failures'])
    def test_partial_compatible_selection_recovers_but_changed_source_or_time_does_not(self):
        pair=self.pairs[0];q=f'Compare sales gross profit AOV {pair[0]} {pair[1]} Q3 {self.year}'
        provider=FakeProvider(completion([call('profit5_pair')]),completion(content='{}'))
        r=ba.run(q,self.scope,connected=True,provider=provider,settings=Settings(api_key='fake'))
        self.assertEqual(r['answer_state'],'full');self.assertEqual(len(provider.sent),2)
        self.assertEqual(r['diagnostic']['evidence_origin'],'server_plan_fallback')
        self.assertEqual({row['metric'] for report in r['reports'] for row in report['data']} & {'sales','gross_profit','aov'},{'sales','gross_profit','aov'})
        with patch.object(ba,'source_token',side_effect=['before','after']):
            r=self.run_local(q,mode='empty');self.assertFalse(r['reports'])
            self.assertIn(dict(operation='server_plan',reason='source_changed'),r['tool_failures'])
        clock=[0];provider=FakeProvider(completion(content='{}'));complete=provider.complete
        def delayed(*args):
            result=complete(*args);clock[0]=101;return result
        provider.complete=delayed
        with patch.object(ba.time,'perf_counter',side_effect=lambda:clock[0]),patch.object(ba,'verified_execute') as execute:
            r=ba.run(q,self.scope,connected=True,provider=provider,settings=Settings(api_key='fake'))
            execute.assert_not_called();self.assertFalse(r['reports'])
    def test_fallback_preserves_security_cancellation_time_and_tool_budgets(self):
        for q in ('Customer phone numbers','Exact SKU-level stock','Net profit after OPEX'):
            p=FakeProvider();r=ba.run(q,self.scope,connected=True,provider=p,settings=Settings(api_key='fake'))
            self.assertFalse(p.sent);self.assertFalse(r['reports'])
        q=f'Compare sales {self.pairs[0][0]} {self.pairs[0][1]} Q3 {self.year}'
        with patch.object(ba,'verified_execute') as execute:
            r=self.run_local(q,mode='empty',cancelled=lambda:True);execute.assert_not_called();self.assertNotEqual(r['answer_state'],'full')
        state=ba.fresh_state();state['calls']=40;p=FakeProvider()
        with patch.object(ba,'verified_execute') as execute:
            ba.run(q,self.scope,state,connected=True,provider=p,settings=Settings(api_key='fake'));execute.assert_not_called();self.assertFalse(p.sent)
        # Two domains need two tool slots. No hidden extra execution past one.
        q=f'Company sales and inventory risk Q3 {self.year}'
        with patch.object(ba,'verified_execute',wraps=ba.verified_execute) as execute:
            r=self.run_local(q,mode='empty',settings=Settings(api_key='fake',max_tools=1));self.assertLessEqual(execute.call_count,1);self.assertNotEqual(r['answer_state'],'full')
    def test_missing_rank_or_pair_cells_stay_partial_and_retain_valid_facts(self):
        for q in (f'Top 5 branches by sales Q3 {self.year}',f'Compare sales gross profit AOV {self.pairs[0][0]} {self.pairs[0][1]} Q3 {self.year}'):
            r=self.run_local(q);r=copy.deepcopy(r)
            for report in r['reports']:
                if report['meta']['tool']=='location_ranking':report['data']=report['data'][:2]
                else:report['data']=[row for row in report['data'] if row.get('metric')!='aov']
            quality=assess(r['reports'],r['resolved']['request']['required_operations'],r['resolved'])
            self.assertEqual(quality['answer_state'],'partial');self.assertTrue(quality['shape_issues'])
            r.update(quality);self.assertTrue(critical_warnings(r,'English'))
            if r['resolved']['request']['aggregation']=='locations':
                text=assemble(r,'English',q)
                for row in r['reports'][0]['data']:self.assertIn(row['branch_id'],text)
    def test_month_punctuation_boundaries_and_ambiguous_ranges(self):
        for ending in ('؟','،','!','.'):
            result=named_period(f'من يناير لسبتمبر {self.year}'+ending,self.year)
            self.assertEqual(result['end'],f'{self.year}-09-30')
            result=named_period(f'خلال {self.year} من يناير لسبتمبر'+ending,self.year)
            self.assertEqual(result['end'],f'{self.year}-09-30')
        with self.assertRaises(ValueError):named_period(f'January or September {self.year}',self.year)
    def test_real_streamlit_chat_answers_include_every_essential_row(self):
        from streamlit.testing.v1 import AppTest
        for lang in ('English','العربية'):
            with self.subTest(lang=lang):
                app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120).run()
                app.sidebar.radio[0].set_value(lang).run();app.sidebar.radio[1].set_value('AI Business Assistant').run()
                pair=self.pairs[1]
                questions=([f'Which 5 branches have highest sales Q3 {self.year}?',f'Top 5 best-selling products January to September {self.year}',
                    f'Monthly sales January to September {self.year}, highest and lowest month',f'Compare sales gross profit AOV {pair[0]} {pair[1]} Q3 {self.year}'] if lang=='English' else
                    [f'أنهي 5 فروع حققوا أعلى مبيعات الربع الثالث من {self.year}؟',f'إيه أكتر 5 منتجات مبيعاً خلال {self.year} من يناير لسبتمبر؟',
                     f'المبيعات الشهرية من يناير لسبتمبر {self.year}، أعلى وأقل شهر',f'قارن {pair[0]} و{pair[1]} المبيعات ومجمل الأرباح ومتوسط قيمة الطلب الربع الثالث من {self.year}'])
                for index,q in enumerate(questions):
                    app.chat_input[0].set_value(q).run();self.assertFalse(app.exception)
                    answer=app.session_state['dialog'][-1];self.assertEqual(answer['result']['answer_state'],'full')
                    report=answer['result']['reports'][0];text=answer['content']
                    if index<2:
                        key='branch_id' if index==0 else 'product_id';self.assertEqual(len(report['data']),5)
                        for row in report['data']:self.assertIn(row[key],text)
                    if index==2:
                        self.assertEqual(len(report['data']),9)
                        for row in report['data']:self.assertIn(row['period'],text)
                    if index==3:
                        row=next(row for row in report['data'] if row.get('metric')=='aov');self.assertIn(f'{row["location_a"]:,.2f}',text)

if __name__=='__main__':unittest.main()
