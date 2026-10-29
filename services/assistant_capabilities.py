"""Auditable contracts for the 36 existing operations, independent of model prose."""
from dataclasses import dataclass,replace

FINANCE=frozenset('sales gross_profit gross_margin_pct orders aov customers units growth_pct'.split())
PROFIT=frozenset('sales gross_profit gross_margin_pct units'.split())
STOCK=frozenset('stock_units stock_value recorded_risk cover_days estimated_replenishment'.split())

@dataclass(frozen=True)
class Capability:
    domain:str
    role:str
    metrics:frozenset
    grains:tuple
    entities:tuple
    dates:str='transaction window'
    required:tuple=()
    limits:str='Aggregate-only; original KPI definitions and public row limits apply.'

def cap(domain,role,metrics,grains,entities=('company','location'),dates='transaction window',required=(),limits='Aggregate-only; original KPI definitions and public row limits apply.'):
    return Capability(domain,role,frozenset(metrics),tuple(grains),tuple(entities),dates,tuple(required),limits)

CAPABILITIES={
 'company_overview':cap('sales','summary',FINANCE,('company','location')),
 'executive_comparison':cap('sales','period_comparison',FINANCE,('company','location','time'),dates='equal-length prior transaction window'),
 'executive_stock':cap('inventory','legacy_snapshot',STOCK,('company','location','category'),dates='legacy latest recorded month <= end',limits='Legacy policy; never substitute for Phase 6 risk/cover.'),
 'sales_seasonality':cap('sales','seasonality',('avg_sales','observed_months'),('time',),dates='complete observed calendar months'),
 'sales4_trends':cap('sales','trend',FINANCE,('time',)),
 'sales4_products':cap('sales','products',PROFIT,('product',),('company','location','product')),
 'location_ranking':cap('sales','locations',FINANCE,('locations',),('locations',)),
 'declining_locations':cap('sales','decline',('growth_pct','sales'),('locations',),('locations',)),
 'two_location_comparison':cap('sales','pair',FINANCE,('location_pair',),('location_pair',),required=('branch_a','branch_b')),
 'location_detail':cap('sales','summary',FINANCE,('location',),('location',),required=('branch',)),
 'profit5_products':cap('profitability','products',PROFIT,('product',),('company','location','product')),
 'profit5_categories':cap('profitability','categories',PROFIT,('category',)),
 'profit5_locations':cap('profitability','locations',PROFIT,('locations',),('locations',)),
 'profit5_screening':cap('profitability','screening',PROFIT,('product',),limits='Approved default high-volume/low-margin screening; no arbitrary rule code.'),
 'profit5_leaders':cap('profitability','leaders',PROFIT,('product',)),
 'profit5_pair':cap('profitability','pair',PROFIT|{'orders'},('location_pair',),('location_pair',),required=('branch_a','branch_b')),
 'profit5_trends':cap('profitability','trend',PROFIT,('time',)),
 **{name:cap('inventory',role,STOCK,grains,entities,dates='latest completed monthly location/category snapshot <= end',required=required,
       limits='No SKU balances or inferred warehouse allocation; cover/replenishment are heuristics.')
    for name,role,grains,entities,required in (
     ('inventory6_stock','snapshot',('company','location','category'),('company','location'),()),
     ('inventory6_risk','risk',('company','location','category'),('company','location'),()),
     ('inventory6_cover','cover',('company','location','category'),('company','location'),()),
     ('inventory6_replenishment','replenishment',('company','location','category'),('company','location'),()),
     ('inventory6_warehouse','warehouse',('warehouse','category'),('warehouse',),()),
     ('inventory6_transfers','transfers',('warehouse','location','time'),('warehouse','location'),()),
     ('inventory6_pair','pair',('location_pair',),('location_pair',),('branch_a','branch_b')))},
 **{name:cap('forecast',role,('central','lower','upper','wape_pct','mae','rmse'),grains,('company','location','category'),
       dates='next approved 1/3/6 months from complete source origin; evaluation uses fixed chronological splits',required=required,
       limits='Revenue EGP or category demand units; no SKU forecasts; experimental states and uncalibrated bands retained.')
    for name,role,grains,required in (
     ('forecast7_values','forecast',('company','location','category'),()),
     ('forecast7_accuracy','evaluation',('company','location','category'),()),
     ('forecast7_growth','growth',('category',),()),
     ('forecast7_categories','category_pair',('category',),('categories',)))},
 **{name:cap('customers',role,(),('company',),('company',),dates='fixed latest complete 12 months; research has fixed mature cutoffs',
      limits='Public aggregates only, k=5; no individual IDs/features/predictions; customer models unreliable.')
    for name,role in (('customer8_summary','summary'),('customer8_segments','segments'),('customer8_cohorts','retention'),
       ('customer8_repeat','activity'),('customer8_changes','changes'),('customer8_churn','churn'),('customer8_value','value'))},
 'category_risk_sales':cap('sales_inventory','aligned_categories',('sales','growth_pct','max_recorded_risk'),('category',),dates='transaction comparison and completed stock snapshot are distinct',limits='Descriptive category alignment, not causation or stockout probability.'),
}

# Field-level capabilities mirror existing adapters; no new business metrics.
EXACT_METRICS={
 'sales4_trends':{'sales','gross_profit','orders','units','aov'},
 'executive_stock':{'stock_units','stock_value','high_risk_categories','estimated_30d_replenishment_units'},
 'location_ranking':FINANCE-{'gross_margin_pct'},
 'executive_comparison':(FINANCE-{'units'})|{'branches'},
 'profit5_categories':{'sales','gross_profit','gross_margin_pct'},
 'profit5_locations':{'sales','gross_profit','gross_margin_pct'},
 'inventory6_pair':{'stock_units','stock_value','recorded_risk'},
 'inventory6_stock':{'stock_units','stock_value','recorded_risk','max_recorded_risk','mean_recorded_risk','high_risk_combinations'},
 'inventory6_risk':{'stock_units','stock_value','recorded_risk','max_recorded_risk','mean_recorded_risk','high_risk_combinations'},
 'inventory6_warehouse':{'stock_units','stock_value','recorded_risk','max_recorded_risk','mean_recorded_risk'},
 'inventory6_cover':{'stock_units','recorded_risk','sold_units','daily_units','cover_days','estimated_replenishment'},
 'inventory6_replenishment':{'stock_units','recorded_risk','sold_units','daily_units','cover_days','estimated_replenishment'},
 'inventory6_transfers':{'transfer_count','transfer_units','transport_cost'},
 'forecast7_values':{'central','lower','upper'},
 'forecast7_accuracy':{'wape_pct','mae','rmse','smape_pct','bias','bias_pct'},
 'forecast7_growth':{'forecast_units','recent_actual_units','forecast_vs_recent_pct','test_wape_pct'},
 'forecast7_categories':{'forecast_units','recent_actual_units','forecast_vs_recent_pct','test_wape_pct'},
 'customer8_summary':{'c8_registered','c8_identified','c8_repeat_rate','c8_frequency','c8_average_spend','c8_identification_pct'},
 'customer8_segments':{'c8_customers','c8_orders','c8_revenue'},
 'customer8_cohorts':{'c8_cohort_size','c8_active','c8_retention_pct'},
 'customer8_repeat':{'c8_customers','c8_orders','c8_frequency','c8_repeat_rate','c8_revenue'},
 'customer8_changes':{'c8_customers','c8_previous_frequency','c8_current_frequency','c8_frequency_change'},
 'customer8_churn':{'c8_roc_auc','c8_average_precision','c8_brier','c8_ece'},
 'customer8_value':{'c8_predicted_revenue','c8_eligible'},
}
for _name,_metrics in EXACT_METRICS.items():CAPABILITIES[_name]=replace(CAPABILITIES[_name],metrics=frozenset(_metrics))
for _name,_grain in {'customer8_cohorts':'cohort','customer8_segments':'segment','customer8_repeat':'time','customer8_changes':'segment_change'}.items():CAPABILITIES[_name]=replace(CAPABILITIES[_name],grains=(_grain,))

def description(name):
    c=CAPABILITIES[name]
    return f'{c.domain}; {c.role}; metrics={"/".join(sorted(c.metrics))}; grain={"/".join(c.grains)}; entities={"/".join(c.entities)}; dates={c.dates}. {c.limits}'

def compatible_grain(name,request):
    """Semantic grain gating in addition to existing scope/argument validation."""
    c=CAPABILITIES[name];grain=request.get('aggregation','company')
    if name=='profit5_trends' and request.get('parameters',{}).get('grain','monthly')!='monthly':return False
    if request.get('forecast'):return c.domain=='forecast' or (c.domain=='sales' and c.role=='trend')
    if c.domain in ('inventory','sales_inventory') and grain=='product':return False
    if c.domain in ('customers','inventory','sales_inventory'):return True  # Independent privacy/snapshot/pair policies still apply.
    return grain in c.grains
