"""Stream original CSVs into SQLite without extracting or modifying the ZIP.

Uses the MVP numeric affinities; IDs and dates remain TEXT and empty fields NULL.
Publication is atomic.
"""
import argparse
from contextlib import closing
import csv
import hashlib
import io
from pathlib import Path
import re
import sqlite3
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.schema import prepare_connection, DATE_VIEWS
DEFAULT_DB = ROOT / "data" / "cottonil.db"


def column_type(name):
    """Numeric affinities retained from the supplied MVP importer."""
    name = name.lower()
    if name.endswith(('_egp', '_usd')) or name in {'stockout_risk_score', 'price_multiplier'}:
        return 'REAL'
    if name in {'quantity', 'quantity_units', 'closing_units', 'return_quantity', 'items_count',
                'payment_terms_days', 'impressions', 'clicks', 'orders_attributed', 'capacity_units'}:
        return 'INTEGER'
    return 'TEXT'


def identifier(value):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return '"' + value + '"'


def build_database(source, destination, force=False):
    source, destination = Path(source), Path(destination)
    if destination.exists() and not force:
        raise FileExistsError(f"Database exists: {destination}; use --force to replace")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".building")
    if temporary.exists():
        raise FileExistsError(f"Build already present: {temporary}")
    counts = {}
    try:
        with closing(sqlite3.connect(temporary)) as conn, conn, zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                path = Path(member.filename)
                if path.suffix.lower() != ".csv":
                    continue
                table = path.stem.lower()
                if table in counts:
                    raise ValueError(f"Duplicate CSV table: {table}")
                with archive.open(member) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
                    reader = csv.reader(stream)
                    columns = next(reader)
                    if not columns or len({c.lower() for c in columns}) != len(columns):
                        raise ValueError(f"Invalid header: {table}")
                    conn.execute(f"CREATE TABLE {identifier(table)} (" + ",".join(identifier(c) + ' ' + column_type(c) for c in columns) + ")")
                    insert = f"INSERT INTO {identifier(table)} VALUES (" + ",".join("?" for _ in columns) + ")"
                    batch, count = [], 0
                    for row in reader:
                        if len(row) != len(columns):
                            raise ValueError(f"Invalid row width in {table}, record {count + len(batch) + 2}")
                        batch.append(tuple(v if v != "" else None for v in row))
                        if len(batch) >= 10000:
                            conn.executemany(insert, batch)
                            count += len(batch)
                            batch.clear()
                    conn.executemany(insert, batch)
                    counts[table] = count + len(batch)
                    print(f"Imported {table}: {counts[table]:,}", flush=True)
                    for column in columns:
                        if column.endswith("_id") or column in ("order_date", "year_month"):
                            conn.execute(f"CREATE INDEX {identifier('ix_' + table + '_' + column)} ON {identifier(table)} ({identifier(column)})")
            if not counts:
                raise ValueError("Archive contains no CSV tables")
            # Keep generic fixture imports usable; real Cottonil builds receive
            # the same additive views/indexes as an existing Phase 0 database.
            required = {'sales_orders','sales_order_items','products_catalog','sales_returns','monthly_stock', *DATE_VIEWS}
            if required.issubset(counts):
                prepare_connection(conn)
            with source.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            conn.execute("CREATE TABLE _source_metadata (sha256 TEXT, storage_note TEXT)")
            conn.execute("INSERT INTO _source_metadata VALUES (?, ?)", (digest, "MVP numeric affinities; IDs/dates TEXT; empty fields NULL"))
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity check failed")
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--db", default=DEFAULT_DB, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for table, count in sorted(build_database(args.zip, args.db, args.force).items()):
        print(f"{table}: {count:,}")
    print(f"Database: {args.db.resolve()}")
