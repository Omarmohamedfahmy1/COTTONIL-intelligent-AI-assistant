"""run: python -m unittest discover -s tests -v (after database import)."""
import unittest
from datetime import date
from pathlib import Path
from analytics import DB,overview,branch_performance,product_performance,inventory_snapshot,company_sales_fully_observed_months
from assistant_engine import answer_tool, offline_reply
from predictive import forecast,customer_results

S='2026-01-01';E='2026-09-30';CTX={'start':S,'end':E,'branch':None}

@unittest.skipUnless(DB.exists(),'Import the original zip first')
class IntegrationTests(unittest.TestCase):
    def test_executive(self):
        a=overview(S,E)
        self.assertGreater(a['sales'],0)
        self.assertGreater(a['gross_profit'],0)
        self.assertEqual(a['branches'],80)
        self.assertGreater(a['orders'],a['customers'])
    def test_branches_count(self):
        a=branch_performance(S,E)
        self.assertEqual(len(a),80)
        self.assertAlmostEqual(float(a.sales.sum()),overview(S,E)['sales'],places=1)
    def test_product_vs_order_revenue(self):
        df=product_performance(S,E,limit=1000)
        self.assertAlmostEqual(df.sales.sum(),overview(S,E)['sales'],delta=1)
        self.assertAlmostEqual(df.gross_profit.sum(),overview(S,E)['gross_profit'],delta=1)
    def test_inventory_grain(self):
        snapshot, df=inventory_snapshot(E)
        self.assertEqual(snapshot,'2026-09')
        self.assertEqual(len(df),16)
        self.assertTrue((df.suggested_30d_replenishment>=0).all())
    def test_forecast_out_of_sample(self):
        f=forecast(company_sales_fully_observed_months(),6)
        self.assertEqual(len(f['predicted']),6)
        self.assertGreaterEqual(f['validation_wape_pct'],0)
        self.assertEqual(f['predicted'][0]['month'],'2026-10')
    def test_assistant_uses_exact_overview(self):
        out=answer_tool('company_overview',CTX)
        self.assertAlmostEqual(out['data'][0]['sales'],overview(S,E)['sales'],places=1)
    def test_assistant_is_bilingual(self):
        for q in ['ايه أقل الفروع مبيعات','Which branches have the highest revenue?',
                  'توقع المبيعات الشهر الجاي','Show top products by profit']:
            txt,reports=offline_reply(q,CTX)
            self.assertTrue(txt and reports)
    def test_invalid_tool_blocked(self):
        with self.assertRaises(ValueError):answer_tool('delete_database',CTX)
        with self.assertRaises(ValueError):answer_tool('company_overview',CTX,{'branch_id':'NONEXISTENT'})
    def test_customer_eval_disclosed(self):
        scores,meta=customer_results()
        if scores is not None:
            self.assertLess(meta['churn_validation_roc_auc'],.6)
            resp=answer_tool('customer_intelligence',CTX)
            self.assertIs(resp['meta']['valid_churn_predictions'],False)

if __name__=='__main__':unittest.main()
