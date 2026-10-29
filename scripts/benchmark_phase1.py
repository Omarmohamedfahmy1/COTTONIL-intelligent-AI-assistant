"""Measure representative shared queries; output contains timings, not records."""
import argparse
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import analytics


def benchmark():
    branch = analytics.branches().branch_id.iloc[0]
    queries = {
        'company_overview': lambda: analytics.overview('2026-01-01', '2026-09-30'),
        'branch_overview': lambda: analytics.overview('2026-01-01', '2026-09-30', branch),
        'categories': lambda: analytics.category_performance('2026-01-01', '2026-09-30'),
        'branch_ranking': lambda: analytics.branch_performance('2026-01-01', '2026-09-30'),
    }
    timings = {}
    for name, query in queries.items():
        query()  # warm OS/SQLite caches; each service still opens fresh read-only connections
        samples = []
        for _ in range(3):
            start = perf_counter()
            query()
            samples.append(round((perf_counter() - start) * 1000, 3))
        timings[name] = {'samples_ms': samples, 'median_ms': statistics.median(samples)}
    return timings


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'reports'/'phase_1_performance.json')
    args = parser.parse_args()
    existing = json.loads(args.output.read_text()) if args.output.exists() else {}
    existing[args.label] = benchmark()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(existing, indent=2), encoding='utf-8')
    print(json.dumps({args.label: existing[args.label]}, indent=2))
