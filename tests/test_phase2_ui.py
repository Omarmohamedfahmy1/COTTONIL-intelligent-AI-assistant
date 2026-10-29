"""Presentation contracts and actual Streamlit navigation/filter/dialog execution."""
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

import pandas as pd
from streamlit.testing.v1 import AppTest
import analytics as api
from ui.i18n import TEXT,CATEGORIES,PAGES,t
from ui.components import public_frame,translated_frame,money

ROOT=Path(__file__).resolve().parents[1]


class LocalizationTests(unittest.TestCase):
    def test_catalog_has_both_languages_for_every_key(self):
        for key,values in TEXT.items():
            self.assertEqual(len(values),2,key)
            self.assertTrue(all(isinstance(v,str) and v.strip() for v in values),key)
        for page in PAGES:
            self.assertIn(page,TEXT)
        with self.assertRaises(KeyError):t('missing_key')

    def test_localized_tables_preserve_values_and_hide_private_columns(self):
        frame=pd.DataFrame({'customer_id':['PRIVATE_CUSTOMER'],'churn_probability':[.9],
            'category':['Socks'],'sales':[123.45],'is_complete_month':[True]})
        result=translated_frame(frame,'العربية',reverse=True)
        self.assertNotIn('customer_id',public_frame(frame))
        self.assertNotIn('PRIVATE_CUSTOMER',result.to_csv())
        self.assertEqual(result[t('sales','العربية')].iloc[0],123.45)
        self.assertEqual(result[t('category','العربية')].iloc[0],'جوارب')
        self.assertEqual(result[t('is_complete_month','العربية')].iloc[0],'نعم')
        self.assertEqual(money(None,'English'),'Unavailable')

    def test_ui_modules_do_not_define_business_kpis(self):
        # UI reads the authoritative facade; direct UI SQL is only a fixed category
        # master lookup, and no backend file was rewritten during this UI phase.
        backend=['analytics.py','predictive.py','assistant_engine.py','db/__init__.py','db/connection.py','db/schema.py',
                 'services/__init__.py','services/filters.py','services/metrics.py']
        approved=ROOT.parent/'Cottonil_Phase1_Review.zip'
        if not approved.exists():
            self.skipTest('Approved Phase 1 snapshot is local review evidence, not a repository dependency')
        with zipfile.ZipFile(approved) as archive:
            for name in backend:
                self.assertEqual((ROOT/name).read_bytes(),archive.read(name),name)


@unittest.skipUnless(api.DB.exists(),'Build the local database for UI integration')
class UIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
        self.clean()

    def clean(self):
        self.assertFalse(self.app.exception,[e.message for e in self.app.exception])
        self.assertFalse(self.app.error,[e.value for e in self.app.error])

    def select(self,key):
        return self.app.sidebar.selectbox(key=key+('_en' if self.app.session_state['language']=='English' else '_ar'))

    def page(self,name):
        self.app.sidebar.radio[1].set_value(name).run()
        self.clean()

    def test_all_eight_pages_both_languages_and_assistant_access(self):
        for language in ('العربية','English'):
            self.app.sidebar.radio(key='language').set_value(language).run()
            for name in PAGES:
                with self.subTest(language=language,page=name):
                    self.page(name)
                    self.assertEqual(self.app.title[0].value,t(name,language))
                    self.assertEqual(self.app.button(key='assistant_access').label,t('ask',language))

    def test_master_categories_are_fully_translated(self):
        values=api.read('SELECT DISTINCT category_en FROM products_catalog').category_en
        self.assertTrue(set(values).issubset(CATEGORIES))

    def test_all_four_filters_preserve_state_and_match_services(self):
        self.assertEqual(self.select('filter_category').value,'__all__')
        self.assertEqual(self.select('filter_category').options[0],t('all_categories','العربية'))
        branch=api.branches().query("retail_location_type=='Retail branch'").branch_id.iloc[0]
        self.select('filter_type').set_value('Retail branch').run()
        self.select('filter_branch').set_value(branch).run()
        self.select('filter_category').set_value('Socks').run()
        self.app.sidebar.date_input(key='filter_dates').set_value((date(2026,1,1),date(2026,9,30))).run()
        self.clean()
        expected=api.overview('2026-01-01','2026-09-30',branch,location_type='Retail branch',category='Socks')
        self.assertEqual(self.app.metric[0].value,money(expected['sales'],'العربية'))
        scope=dict(self.app.session_state['active_scope'])
        self.page('Sales Analytics')
        self.app.sidebar.radio(key='language').set_value('English').run()
        self.page('Executive Overview')
        self.assertEqual(dict(self.app.session_state['active_scope']),scope)
        self.assertEqual(self.app.metric[0].value,money(expected['sales'],'English'))
        self.select('filter_type').set_value('Point of sale / reseller').run()
        self.clean()
        self.assertIsNone(self.app.session_state['active_scope']['branch'])

    def test_branch_benchmark_discloses_scope(self):
        branch=api.branches().branch_id.iloc[0]
        self.select('filter_branch').set_value(branch).run()
        self.page('Branch Performance')
        self.assertIn(t('benchmark_note','العربية'),[e.value for e in self.app.info])
        self.assertEqual(len(self.app.dataframe[0].value),80)

    def test_empty_date_location_scope(self):
        first,last=api.metadata()
        empty=api.read('''SELECT branch_id FROM branches b WHERE NOT EXISTS
            (SELECT 1 FROM sales_orders o WHERE o.branch_id=b.branch_id AND o.order_date=?) LIMIT 1''',(str(first),))
        self.assertFalse(empty.empty,'No naturally empty location/day available in this dataset')
        self.app.sidebar.date_input(key='filter_dates').set_value((first,first)).run()
        self.select('filter_branch').set_value(empty.iloc[0,0]).run()
        self.clean()
        self.assertEqual(self.app.metric[2].value,'0')
        self.assertIn(t('empty','العربية'),[m.value for m in self.app.info])

    def test_partial_date_selection_has_localized_warning(self):
        self.app.sidebar.date_input(key='filter_dates').set_value((date(2026,1,1),)).run()
        self.assertFalse(self.app.exception)
        self.assertIn(t('invalid_dates','العربية'),[m.value for m in self.app.warning])
        self.assertFalse(self.app.metric)

    def test_quick_assistant_keeps_page_and_filter_context(self):
        branch=api.branches().branch_id.iloc[0]
        self.select('filter_branch').set_value(branch).run()
        self.select('filter_category').set_value('Socks').run()
        self.page('Inventory Intelligence')
        scope=dict(self.app.session_state['active_scope'])
        self.app.button(key='assistant_access').click().run()
        self.clean()
        self.assertTrue(self.app.session_state['assistant_open'])
        self.app.button(key='quick_q_sales').click().run()
        self.clean()
        report=self.app.session_state['dialog'][-1]['reports'][0]
        self.assertEqual(report['meta']['branch_id'],branch)
        self.assertEqual(report['meta']['category'],'Socks')
        self.app.button(key='assistant_close').click().run()
        self.clean()
        self.assertFalse(self.app.session_state['assistant_open'])
        self.assertEqual(self.app.session_state['page'],'Inventory Intelligence')
        self.assertEqual(dict(self.app.session_state['active_scope']),scope)

    def test_offline_responses_follow_interface_language(self):
        self.page('AI Business Assistant')
        for language in ('English','العربية'):
            self.app.sidebar.radio(key='language').set_value(language).run()
            self.app.button(key='full_q_sales').click().run()
            self.clean()
            answer=self.app.session_state['dialog'][-1]['content']
            self.assertTrue(answer.startswith('Sales before refunds:' if language=='English' else 'المبيعات قبل الاستردادات:'))
            self.assertTrue(self.app.session_state['dialog'][-1]['reports'])

    def test_unsupported_question_and_connected_mode_without_key(self):
        self.page('AI Business Assistant')
        self.app.chat_input(key='full_question').set_value('xyz unsupported').run()
        self.clean()
        # Typed-question language now overrides the dashboard language.
        self.assertEqual(self.app.session_state['dialog'][-1]['content'],t('unsupported','English'))
        with patch.dict('os.environ',{'OPENAI_API_KEY':''}):
            self.app.radio(key='full_mode_ar').set_value('connected').run()
            self.app.button(key='full_q_sales').click().run()
        self.clean()
        self.assertEqual(self.app.session_state['dialog'][-1]['content'],t('no_key','العربية'))
        self.assertFalse(self.app.session_state['dialog'][-1]['reports'])

    def test_customer_page_never_displays_customer_identifiers(self):
        self.page('Customer Intelligence')
        for element in self.app.dataframe:
            self.assertNotIn('customer_id',element.value.columns)
        self.assertIn(t('value_note','العربية'),[e.value for e in self.app.caption])

    def test_provider_errors_do_not_reveal_credentials_or_raw_errors(self):
        self.page('AI Business Assistant')
        self.app.radio(key='full_mode_ar').set_value('connected').run()
        self.app.text_input(key='full_api_key').set_value('test-value-not-a-real-key').run()
        with patch('ui.assistant.run_llm',side_effect=RuntimeError('PRIVATE_ERROR_SENTINEL')):
            self.app.button(key='full_q_sales').click().run()
        self.clean()
        response=self.app.session_state['dialog'][-1]
        self.assertEqual(response['content'],t('provider_error','العربية'))
        self.assertNotIn('PRIVATE_ERROR_SENTINEL',response['content'])


if __name__=='__main__':
    unittest.main()
