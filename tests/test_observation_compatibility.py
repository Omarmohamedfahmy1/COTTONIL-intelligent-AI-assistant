"""Contract-based comparison safety across every supported business domain."""
import copy,itertools,unittest,json
from services.assistant_findings import observations,comparison,coverage
from services.assistant_quality import assess
from ui.assistant_answers import assemble,critical_warnings
from ui.assistant_evidence import prepare

PERIOD='2025-01-01 to 2025-12-31'
def report(tool,rows,metric='gross_profit',column_unit='EGP',**meta):
    return dict(meta=dict(tool=tool,period=PERIOD,branch_id='all',category=None,location_type=None,
        units={metric:column_unit},**meta),data=rows)

def request(metric):return dict(metrics=[metric],answer_components=['facts','description','investigation'])

class ObservationCompatibility(unittest.TestCase):
    def test_review_counterexample_retains_facts_not_a_false_priority(self):
        for labels,values,ar in itertools.product((('Product-X','Category-Y'),('Article-A','Class-B')),((21,300),(810,12)),(False,True)):
            with self.subTest(labels=labels,values=values,ar=ar):
                reports=[report('profit5_products',[dict(product_id=labels[0],gross_profit=values[0])]),report('profit5_categories',[dict(category=labels[1],gross_profit=values[1])])]
                req=request('gross_profit');cells=observations(reports,req);cov=coverage(reports,req)
                self.assertEqual(len(cells),2);self.assertEqual([c['value'] for c in cells],list(values));self.assertIsNone(comparison(cells))
                self.assertEqual(cov['supported_answer_components'],['facts']);self.assertEqual(set(cov['missing_answer_components']),{'description','investigation'})
                result=dict(reports=reports,resolved=dict(request=req),answer_state='partial',**cov)
                q='اشرح مجمل الربح وأولويات المراجعة' if ar else 'Explain gross profit and review priorities'
                text=assemble(result,'English',q)
                self.assertNotIn('highest shown',text);self.assertNotIn('ملاحظة وصفية',text)
                self.assertIn(f'{values[0]:,.2f}',text);self.assertTrue(critical_warnings(result,'Arabic' if ar else 'English'))

    def test_compatible_populations_across_all_domains(self):
        cases=[
            ('sales4_products','sales','product_id',{},'EGP'),
            ('profit5_products','gross_profit','product_id',{},'EGP'),
            ('profit5_locations','gross_profit','branch_id',{},'EGP'),
            ('sales4_trends','sales','period',dict(grain='monthly'),'EGP'),
            ('inventory6_stock','stock_units','category',dict(snapshot='2025-12'),'units'),
            ('inventory6_warehouse','stock_units','category',dict(snapshot='2025-12',warehouse_id='Warehouse-Q'),'units'),
            ('forecast7_values','central','month',dict(origin='2025-12-31',horizon=3,target='revenue',unit='EGP'),'EGP'),
            ('forecast7_growth','forecast_units','category',dict(origin='2025-12-31',horizon=3,target='units'),'units'),
            ('customer8_segments','c8_customers','c8_segment',{},'customers'),
            ('customer8_repeat','c8_customers','month',{},'customers'),
        ]
        for tool,metric,dimension,meta,unit in cases:
            for labels,values in itertools.product((('Entity-U','Entity-V'),('Entity-M','Entity-N')),((12,44),(90,15))):
                with self.subTest(tool=tool,values=values):
                    rows=[{dimension:name,metric:value} for name,value in zip(labels,values)]
                    r=report(tool,rows,metric,unit,**meta);cells=observations([r],request(metric));pair=comparison(cells)
                    self.assertIsNotNone(pair);self.assertEqual(pair['high']['value'],max(values))
                    for cell in cells:
                        for key in ('entity_type','aggregation_grain','metric','unit','period','scope','time_basis','measure'):self.assertIsNotNone(cell[key],key)
                    self.assertFalse(coverage([r],request(metric))['missing_answer_components'])

    def test_incompatible_grains_across_all_domains(self):
        cases=[
            ('gross_profit',report('profit5_products',[dict(product_id='X',gross_profit=12)]),report('profit5_categories',[dict(category='Y',gross_profit=90)])),
            ('sales',report('company_overview',[dict(sales=12)],'sales'),report('location_detail',[dict(sales=90)],'sales',branch_a=None)),
            ('sales',report('sales4_trends',[dict(period='2025-02',sales=12)],'sales',grain='monthly'),report('profit5_categories',[dict(category='Y',sales=90)],'sales')),
            ('stock_units',report('inventory6_cover',[dict(location_id='X',category='C',stock_units=12)],'stock_units','units',snapshot='2025-12'),report('inventory6_warehouse',[dict(warehouse_id='Y',category='C',stock_units=90)],'stock_units','units',snapshot='2025-12')),
            ('c8_customers',report('customer8_segments',[dict(c8_segment='X',c8_customers=12)],'c8_customers','customers'),report('customer8_repeat',[dict(month='2025-02',c8_customers=90)],'c8_customers','customers')),
            ('c8_cohort_size',report('customer8_cohorts',[dict(c8_cohort='X',c8_cohort_size=12)],'c8_cohort_size','customers'),report('customer8_cohorts',[dict(c8_cohort='Y',c8_age=1,c8_cohort_size=90)],'c8_cohort_size','customers')),
            ('central',report('forecast7_values',[dict(month='2026-01',central=12)],'central','EGP',origin='2025-12-31',horizon=3),report('forecast7_values',[dict(category='Y',central=90)],'central','EGP',origin='2025-12-31',horizon=3)),
        ]
        # A real branch summary is scoped in metadata, not invented from its row.
        cases[1][2]['meta']['branch_id']='Location-Y'
        for metric,left,right in cases:
            for ordered in ([left,right],[right,left]):
                with self.subTest(metric=metric,tools=[r['meta']['tool'] for r in ordered]):
                    cells=observations(ordered,request(metric));self.assertEqual(len(cells),2)
                    self.assertIsNone(comparison(cells));self.assertIn('facts',coverage(ordered,request(metric))['supported_answer_components'])
                    self.assertIn('investigation',coverage(ordered,request(metric))['missing_answer_components'])

    def test_scope_units_time_basis_and_filters_are_comparison_boundaries(self):
        base=report('profit5_products',[dict(product_id='X',gross_profit=10)])
        cases=[('unit',lambda r:r['meta']['units'].update(gross_profit='USD')),
            ('period',lambda r:r['meta'].update(period='2024-01-01 to 2024-12-31')),
            ('location_filter',lambda r:r['meta'].update(branch_id='Location-Z')),
            ('category_filter',lambda r:r['meta'].update(category='Category-Z')),
            ('location_type',lambda r:r['meta'].update(location_type='Retail branch')),
            ('threshold',lambda r:r['meta'].update(min_revenue=100)),
            ('financial_basis',lambda r:r['meta'].update(financial_basis='Different recorded basis'))]
        for name,change in cases:
            r=copy.deepcopy(base);r['data'][0].update(product_id='Y',gross_profit=80);change(r)
            with self.subTest(boundary=name):self.assertIsNone(comparison(observations([base,r],request('gross_profit'))))
        for tool,metric,key,unit,meta,boundary in (
            ('inventory6_stock','stock_units','category','units',dict(snapshot='2025-12'),dict(snapshot='2025-11')),
            ('inventory6_warehouse','stock_units','category','units',dict(snapshot='2025-12',warehouse_id='WH-X'),dict(warehouse_id='WH-Y')),
            ('forecast7_values','central','month','EGP',dict(origin='2025-12-31',horizon=3),dict(origin='2025-11-30')),
            ('forecast7_values','central','month','EGP',dict(origin='2025-12-31',horizon=3),dict(horizon=6)),
            ('customer8_cohorts','c8_active','c8_cohort','customers',{},{})):
            left=report(tool,[{key:'X',metric:10}],metric,unit,**meta);right=report(tool,[{key:'Y',metric:80}],metric,unit,**meta);right['meta'].update(boundary)
            if tool=='customer8_cohorts':left['data'][0]['c8_age']=1;right['data'][0]['c8_age']=2
            with self.subTest(tool=tool,boundary=boundary):self.assertIsNone(comparison(observations([left,right],request(metric))))

    def test_legitimate_equivalent_adapters_and_canonical_scope(self):
        left=report('sales4_products',[dict(product_id='X',sales=20)],'sales',product_ids=['Y','X'])
        right=report('profit5_products',[dict(product_id='Y',sales=40)],'sales',product_ids=['X','Y'])
        self.assertIsNotNone(comparison(observations([left,right],request('sales'))))
        for op in ('inventory6_stock','inventory6_risk'):
            left=report(op,[dict(category='X',stock_units=20)],'stock_units','units',snapshot='2025-12')
            right=report('inventory6_stock',[dict(category='Y',stock_units=40)],'stock_units','units',snapshot='2025-12')
            self.assertIsNotNone(comparison(observations([left,right],request('stock_units'))))

    def test_missing_provenance_never_licenses_cross_report_comparisons(self):
        for tool,metric,key in (('profit5_products','gross_profit','product_id'),('inventory6_stock','stock_units','category'),('forecast7_values','central','month')):
            left=report(tool,[{key:'X',metric:12}],metric);right=report(tool,[{key:'Y',metric:90}],metric)
            left['meta'].pop('branch_id');right['meta'].pop('branch_id')
            self.assertIsNone(comparison(observations([left,right],request(metric))))
        left=report('sales4_products',[dict(product_id='X',sales=12)],'sales');right=report('profit5_products',[dict(product_id='Y',sales=90)],'sales')
        left['meta'].pop('units');right['meta'].pop('units')
        self.assertIsNone(comparison(observations([left,right],request('sales'))))

    def test_unavailable_suppressed_unknown_sources_and_conflicts(self):
        for value,state in itertools.product((None,True,float('nan'),float('inf')),('available','unavailable')):
            left=report('profit5_products',[dict(product_id='X',gross_profit=12)])
            right=report('profit5_products',[dict(product_id='Y',gross_profit=value)],state=state)
            cells=observations([left,right],request('gross_profit'))
            self.assertEqual(len(cells),1);self.assertIsNone(comparison(cells))
        unknown=report('unknown_operation',[dict(product_id='X',gross_profit=12),dict(product_id='Y',gross_profit=90)])
        self.assertIsNone(comparison(observations([unknown],request('gross_profit'))))
        conflict=report('profit5_products',[dict(product_id='X',gross_profit=12),dict(product_id='X',gross_profit=90),dict(product_id='Y',gross_profit=20)])
        self.assertIsNone(comparison(observations([conflict],request('gross_profit'))))

    def test_full_pipeline_is_partial_and_keeps_valid_facts(self):
        scope=dict(start='2025-01-01',end='2025-12-31',branch=None,category=None,location_type=None)
        req=dict(request('gross_profit'),aggregation='product',parameters={},domains=['profitability'])
        resolved=dict(scope=scope,pair=[],request=req)
        reports=[report('profit5_products',[dict(product_id='X',gross_profit=12)]),report('profit5_categories',[dict(category='Y',gross_profit=90)])]
        result=dict(reports=reports,resolved=resolved)
        result.update(assess(reports,['profit5_products','profit5_categories'],resolved))
        self.assertEqual(result['answer_state'],'partial');self.assertFalse(result['semantic_complete'])
        safe=prepare(result,'Explain gross profit and review priorities',resolved)
        self.assertTrue(safe['reports']);self.assertIn('12.00',assemble(safe,'English','Explain gross profit and review priorities'))
        self.assertNotIn('highest shown',assemble(safe,'English','Explain gross profit and review priorities'))

    def test_pair_slices_and_approved_period_comparisons(self):
        meta=dict(branch_a='Location-X',branch_b='Location-Y',snapshot='2025-12')
        pair=report('inventory6_pair',[dict(category='Category-X',stock_units_a=20,stock_units_b=40)],'stock_units','units',**meta)
        self.assertIsNotNone(comparison(observations([pair],request('stock_units'))))
        pair['data'].append(dict(category='Category-Y',stock_units_a=100,stock_units_b=200))
        matched=comparison(observations([pair],request('stock_units')))
        self.assertIsNotNone(matched)
        self.assertEqual(matched['high']['stratum'],matched['low']['stratum'])
        self.assertIn('Category-X',matched['high']['entity'])
        pair['data'][0]['stock_units_b']=pair['data'][0]['stock_units_a']
        tied=dict(answer_state='full',reports=[pair],resolved=dict(request=request('stock_units')))
        self.assertIn('within this group',assemble(tied,'English','Explain stock review priorities'))
        self.assertIn('داخل المجموعة',assemble(tied,'Arabic','اشرح المخزون وأولويات المراجعة'))
        periods=report('executive_comparison',[dict(metric='sales',current=20,previous=30)],'sales',previous_period='2024-01-01 to 2024-12-31')
        cells=observations([periods],request('sales'));self.assertIsNotNone(comparison(cells))
        self.assertNotEqual(cells[0]['time_coordinate'],cells[1]['time_coordinate'])

    def test_actual_shape_and_measure_contract_override_desired_grain(self):
        source=report('profit5_products',[dict(product_id='Product-X',category='Category-X',branch_id='Location-X',gross_profit=14),dict(product_id='Product-Y',category='Category-Y',branch_id='Location-X',gross_profit=28)])
        before=copy.deepcopy(source);req=dict(request('gross_profit'),aggregation='company')
        cells=observations([source],req)
        self.assertEqual([c['entity'] for c in cells],['Product-X','Product-Y'])
        self.assertTrue(all(c['aggregation_grain']==('product',) for c in cells))
        self.assertEqual(source,before);self.assertIsNotNone(comparison(cells))
        self.assertIsNotNone(comparison(json.loads(json.dumps(cells))))
        raw=report('inventory6_stock',[dict(category='Category-X',recorded_risk=0.2)],'recorded_risk','recorded score',snapshot='2025-12')
        maximum=report('inventory6_stock',[dict(category='Category-Y',max_recorded_risk=0.8)],'recorded_risk','recorded score',snapshot='2025-12')
        self.assertIsNone(comparison(observations([raw,maximum],request('recorded_risk'))))
        bad=report('company_overview',[dict(product_id='Product-X',gross_profit=14),dict(product_id='Product-Y',gross_profit=28)])
        self.assertIsNone(comparison(observations([bad],request('gross_profit'))))

if __name__=='__main__':unittest.main()
