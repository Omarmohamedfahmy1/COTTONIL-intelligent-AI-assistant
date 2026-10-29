"""Cold-ish process and warm aggregate timings; no saved training or private exports."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services import metrics,forecasting,customers,customer_models
from services.business_assistant import run,fresh_state
from services.assistant_config import Settings
SCOPE=dict(start='2025-10-01',end='2026-09-30',branch=None,location_type=None,category=None)
def main():
    jobs=[('company_kpi',lambda:metrics.overview(**SCOPE)),
        ('branch_category_kpi',lambda:metrics.overview(**{**SCOPE,'branch':'BR001','category':'Socks'})),
        ('products_table',lambda:metrics.product_performance(**SCOPE,limit=100)),
        ('forecast',lambda:forecasting.forecast_report(horizon=3)),
        ('customer_aggregates',lambda:customers.dashboard(**SCOPE)),
        ('customer_approved_research',customer_models.research),
        ('assistant_three_domains',lambda:run('Compare sales profit and inventory BR001 and BR002',SCOPE,fresh_state(),settings=Settings()))]
    rows=[]
    for name,fn in jobs:
        times=[]
        for _ in range(2):
            start=time.perf_counter();fn();times.append(time.perf_counter()-start)
        rows.append(dict(workflow=name,coldish_seconds=times[0],warm_seconds=times[1]));print(name,times,flush=True)
        (ROOT/'reports/phase_10_performance.json').write_text(json.dumps(dict(methodology='Fresh process, first then repeated invocation; OS SQLite cache not flushed. Approved research may refit in memory, never writes saved models. Single local sample, no SLA.',timings=rows,
            bounded_caches={'forecast':32,'customer_dashboard':16,'customer_data':8,'customer_research':2},assistant='Per-turn memo retained only through bounded manual retry; reports/history bounded; no global unbounded answer cache.'),indent=2),encoding='utf-8')
if __name__=='__main__':main()
