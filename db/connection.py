"""Internal read-only access; SQL is authored by services, never by users/LLMs."""
from contextlib import closing
from pathlib import Path
import sqlite3
import pandas as pd

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'cottonil.db'


def read(sql, args=()):
    with closing(sqlite3.connect(Path(DB_PATH).resolve().as_uri() + '?mode=ro', uri=True)) as con:
        con.execute('PRAGMA query_only=ON')
        return pd.read_sql_query(sql, con, params=tuple(args))
