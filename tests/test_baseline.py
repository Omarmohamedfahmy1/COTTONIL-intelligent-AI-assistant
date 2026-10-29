import csv
from contextlib import closing
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from scripts.build_db import DEFAULT_DB, build_database, identifier
from scripts.validate_db import validate


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "fixture.zip"
        self.db = self.root / "fixture.sqlite"

    def archive(self, members):
        with zipfile.ZipFile(self.source, "w") as archive:
            for name, rows in members.items():
                text = io.StringIO(newline="")
                csv.writer(text).writerows(rows)
                archive.writestr(name, text.getvalue().encode("utf-8-sig"))

    def test_roundtrip_arabic_leading_zero_null_and_sql_literal(self):
        self.archive({"nested/sample.csv": [["sample_id", "label", "empty"], ["001", "قطن ' ; DROP TABLE sample; --", ""]]})
        original = self.source.read_bytes()
        self.assertEqual(build_database(self.source, self.db), {"sample": 1})
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT * FROM sample").fetchone(), ("001", "قطن ' ; DROP TABLE sample; --", None))
        self.assertEqual(original, self.source.read_bytes())

    def test_existing_database_protected(self):
        self.db.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            build_database(self.source, self.db)
        self.assertEqual(self.db.read_bytes(), b"existing")

    def test_failed_rebuild_preserves_existing_database(self):
        self.archive({"sample.csv": [["sample_id"], ["1", "bad width"]]})
        self.db.write_bytes(b"existing")
        with self.assertRaisesRegex(ValueError, "row width"):
            build_database(self.source, self.db, force=True)
        self.assertEqual(self.db.read_bytes(), b"existing")
        self.assertFalse(self.db.with_name(self.db.name + ".building").exists())

    def test_duplicate_table_rejected(self):
        self.archive({"a/sample.csv": [["id"], ["1"]], "b/sample.csv": [["id"], ["2"]]})
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_database(self.source, self.db)
        self.assertFalse(self.db.exists())

    def test_unsafe_identifier_rejected(self):
        with self.assertRaises(ValueError):
            identifier('x"; DROP TABLE sample; --')

    def test_empty_archive_rejected(self):
        self.archive({})
        with self.assertRaisesRegex(ValueError, "no CSV"):
            build_database(self.source, self.db)

    def test_readonly_validation_does_not_create_missing_db(self):
        with self.assertRaises(sqlite3.OperationalError):
            validate(self.db)
        self.assertFalse(self.db.exists())


@unittest.skipUnless(DEFAULT_DB.exists(), "Build local Cottonil DB for real-data integration test")
class RealDataIntegrationTests(unittest.TestCase):
    def test_original_dataset_integrity_relationships_and_audit(self):
        result = validate(DEFAULT_DB)
        failures = {k: v for k, v in result["checks"].items() if not v["passed"]}
        self.assertEqual(failures, {})


if __name__ == "__main__":
    unittest.main()
