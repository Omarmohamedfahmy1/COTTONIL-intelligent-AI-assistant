"""Managerial evidence projection and fail-closed history rendering; no live SDK."""
import copy,unittest
from pathlib import Path
from unittest.mock import patch
from services import metrics as kpi,business_assistant as ba
from services.assistant_config import Settings
from ui.assistant_evidence import prepare,sections,isolate
from ui.assistant_answers import assemble

class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ids=kpi.branches().branch_id.tolist();cls.category=kpi.read('SELECT DISTINCT category_en FROM products_catalog ORDER BY 1').iloc[0,0]
        cls.scope=dict(start='2025-01-01',end='2025-12-31',branch=None,location_type=None,category=None)
    def get(self,question,state=None,scope=None):
        with patch('services.business_assistant.GroqProvider',side_effect=AssertionError('No live calls')):
            return ba.run(question,scope or self.scope,state,settings=Settings())
    def test_multiple_pairs_metrics_only_relevant_columns_and_no_chart(self):
        for a,b in [(self.ids[3],self.ids[17]),(self.ids[28],self.ids[61])]:
            for label,metric in [('sales','sales'),('gross profit','gross_profit'),('gross margin','gross_margin_pct')]:
                with self.subTest(pair=(a,b),metric=metric):
                    q=f'Compare {label} {a} and {b}';raw=self.get(q);before=copy.deepcopy(raw)
                    safe=prepare(raw,q);views=sections(safe,q)
                    self.assertEqual(len(views),1);self.assertEqual(len(views[0]['data']),2)
                    self.assertEqual(set(views[0]['data'][0]),{'branch_id',metric})
                    self.assertEqual([r['branch_id'] for r in views[0]['data']],[a,b]);self.assertIsNone(views[0]['chart'])
                    self.assertEqual(raw,before)
    def test_wrong_pair_header_and_wrong_row_ids_are_rejected(self):
        a,b,c,d=self.ids[4:8];q=f'Compare gross profit {a} and {b}';raw=self.get(q)
        for mode in ('header','row','dates','grain'):
            with self.subTest(mode=mode):
                bad=copy.deepcopy(raw);r=bad['reports'][0]
                if mode=='header':r['meta'].update(branch_a=c,branch_b=d)
                elif mode=='row':r['data'][0]['branch_id']=c
                elif mode=='dates':r['meta']['period']='2000-01-01 to 2000-12-31'
                else:r['meta']['tool']='location_ranking'
                safe=prepare(bad,q)
                self.assertFalse(safe['semantic_complete']);self.assertEqual(safe['reports'],[])
                self.assertEqual(sections(safe,q),[]);self.assertNotIn(c,assemble(safe,'English',q))
        # Even a consistently wrong returned context must lose to the pre-call request.
        wrong=self.get(f'Compare gross profit {c} and {d}')
        self.assertEqual(prepare(wrong,q,expected=raw['resolved'])['reports'],[])
    def test_duplicate_tools_are_deduplicated_and_conflicting_values_fail(self):
        a,b=self.ids[8:10];q=f'Compare sales and gross profit {a} and {b}'
        raw=self.get(q);safe=prepare(raw,q);self.assertEqual(len(sections(safe,q)),1)
        bad=copy.deepcopy(raw);bad['reports']=[copy.deepcopy(raw['reports'][0]),copy.deepcopy(raw['reports'][0])]
        bad['reports'][1]['data'][0]['location_a']+=100
        safe=prepare(bad,q);self.assertFalse(safe['semantic_complete']);self.assertFalse(safe['reports'])
        self.assertIn('conflicting_evidence',safe['rejected_evidence'])
    def test_stock_projection_contains_only_requested_risk_and_category(self):
        a,b=self.ids[10:12];q=f'Compare inventory risk {a} and {b}';safe=prepare(self.get(q),q)
        view=sections(safe,q)[0]
        self.assertEqual(set(view['data'][0]),{'category','recorded_risk_a','recorded_risk_b'})
        self.assertIsNone(view['chart']);self.assertNotIn('stock_value_a',view['data'][0])
    def test_trends_and_rankings_offer_only_relevant_optional_chart(self):
        for q in ('Monthly sales','Highest gross profit products'):
            safe=prepare(self.get(q),q);view=sections(safe,q)[0]
            self.assertIsNotNone(view['chart'])
            metric='sales' if q.startswith('Monthly') else 'gross_profit'
            self.assertEqual(view['measures'],[metric]);self.assertEqual(view['chart']['y'],metric)
    def test_arabic_english_followups_keep_the_metric_and_frozen_scope(self):
        a,b=self.ids[15:17];state=ba.fresh_state();self.get(f'Compare sales {a} and {b}',state)
        saved=[]
        for q in ('And gross profit?','نفس الفرعين، هامش الربح؟','طب الشهر اللي قبله؟'):
            r=self.get(q,state);s=prepare(r,q);view=sections(s,q)[0];saved.append((r,q))
            expected=r['resolved']['request']['metrics'][0]
            self.assertEqual(view['measures'],[expected]);self.assertEqual([x['branch_id'] for x in view['data']],[a,b])
        self.assertNotEqual(saved[0][0]['resolved']['scope']['start'],saved[-1][0]['resolved']['scope']['start'])
        self.assertTrue(prepare(saved[0][0],saved[0][1])['semantic_complete'])
    def test_unscoped_cached_reports_and_private_fields_never_display(self):
        q='gross profit';r=self.get(q);r.pop('resolved')
        self.assertFalse(prepare(r,q)['reports'])
        r=self.get(q);r['reports'][0]['data'][0]['customer_id']='PRIVATE'
        self.assertNotIn('customer_id',prepare(r,q)['reports'][0]['data'][0])
    def test_forecast_projection_and_wrong_forecast_dates(self):
        scope={**self.scope,'category':self.category};q='Forecast next 3 months'
        r=self.get(q,scope=scope);safe=prepare(r,q);v=sections(safe,q)[0]
        self.assertEqual(v['measures'],['central','lower','upper']);self.assertNotIn('sales',v['data'][0])
        bad=copy.deepcopy(r);bad['reports'][0]['data'][0]['month']='2040-01-01'
        self.assertFalse(prepare(bad,q)['reports'])
    def test_ltr_identifiers_isolated_without_rendering_html(self):
        text=isolate('الموقع ABC123 حقق 1,234.56 جنيه','العربية')
        self.assertIn('\u2066ABC123\u2069',text);self.assertNotIn('<',text)

class EvidenceUITests(unittest.TestCase):
    def test_relevant_table_no_automatic_chart_no_technical_paragraphs(self):
        from streamlit.testing.v1 import AppTest
        root=Path(__file__).resolve().parents[1]
        app=AppTest.from_file(str(root/'app.py'),default_timeout=120).run()
        app.sidebar.radio[1].set_value('AI Business Assistant').run()
        ids=kpi.branches().branch_id.tolist();q=f'Compare gross profit {ids[20]} and {ids[47]}'
        app.chat_input[0].set_value(q).run();self.assertFalse(app.exception)
        last=app.chat_message[-1]
        self.assertEqual(len(last.dataframe),1);self.assertEqual(last.dataframe[0].value.shape,(2,2))
        self.assertEqual(len(last.get('plotly_chart')),0)
        text=' '.join(e.value for e in last.markdown)+ ' '.join(e.value for e in last.caption)
        for phrase in ('Interpreted request','Evidence type','profit5_pair','location_ranking'):self.assertNotIn(phrase,text)
        self.assertTrue(any(e.label=='Methodology & Sources' for e in last.expander))
        # A stale summary/table cannot bypass the frozen request on the next rerun.
        dialog=app.session_state['dialog'];bad=dialog[-1]['result'];bad['reports'][0]['meta']['branch_a']=ids[-1]
        app.run();self.assertFalse(app.exception)
        self.assertEqual(len(app.chat_message[-1].dataframe),0)
        self.assertTrue(any('rejected' in w.value for w in app.chat_message[-1].warning))
        app.button(key='full_clear').click().run()
        app.chat_input[0].set_value('Monthly sales').run();self.assertFalse(app.exception)
        self.assertEqual(len(app.chat_message[-1].get('vega_lite_chart')),0)
        toggle=next(c for c in app.checkbox if c.label=='Show chart')
        toggle.check().run();self.assertFalse(app.exception)
        self.assertEqual(len(app.chat_message[-1].get('vega_lite_chart')),1)

if __name__=='__main__':unittest.main()
