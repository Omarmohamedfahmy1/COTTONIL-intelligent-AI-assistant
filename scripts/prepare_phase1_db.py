"""Install additive Phase 1 views/indexes on a local generated database."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.connection import DB_PATH
from db.schema import INDEXES, DATE_VIEWS, prepare_connection


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DB_PATH)
    args = parser.parse_args()
    with closing(sqlite3.connect(args.db.resolve().as_uri()+'?mode=rw', uri=True)) as conn, conn:
        prepare_connection(conn)
        conn.execute('ANALYZE')
    print(f'Prepared {len(INDEXES)} indexes and {len(DATE_VIEWS)} normalized date views; original rows unchanged')
