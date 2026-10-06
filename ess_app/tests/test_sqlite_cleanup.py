import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import server


class SQLiteLegacyCleanupTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("CREATE TABLE products (id TEXT PRIMARY KEY, data_json TEXT NOT NULL)")

    def tearDown(self):
        self.conn.close()

    def test_old_product_metadata_is_stripped_without_changing_price_or_inventory(self):
        legacy = {
            "id": "INF-005", "ref": "INF-005", "name": "Photocopieur",
            "family": "Imprimantes", "pack": "Sur devis", "sellPrice": None,
            "catalogPrice": None, "stock": 3, "quoteOnly": True,
        }
        cleaned = server.clean_local_product(legacy)
        self.assertNotIn("quoteOnly", cleaned)
        self.assertEqual(cleaned["pack"], "Conditionnement non précisé")
        self.assertIsNone(cleaned["sellPrice"])
        self.assertEqual(cleaned["stock"], 3)
        self.assertEqual(legacy["pack"], "Sur devis")  # cleanup returns a copy

    def test_old_order_markers_are_removed_but_history_is_preserved(self):
        legacy = {
            "number": "WEB-OLD-1", "status": "quote_sent", "total": None,
            "customer": {"name": "Client"},
            "items": [{"id": "INF-005", "qty": 1, "quoteRequested": True}],
            "quoteRequested": True,
        }
        cleaned = server.clean_local_order(legacy)
        self.assertEqual(cleaned["number"], "WEB-OLD-1")
        self.assertEqual(cleaned["status"], "contacted")
        self.assertNotIn("quoteRequested", cleaned)
        self.assertNotIn("quoteRequested", cleaned["items"][0])
        self.assertIsNone(cleaned["total"])
        self.assertIn("quoteRequested", legacy)  # cleanup returns a copy

    def test_local_store_refuses_an_unpriced_product(self):
        legacy = {
            "id": "INF-005", "ref": "INF-005", "name": "Photocopieur",
            "family": "Imprimantes", "pack": "Sur devis", "sellPrice": None,
            "stock": None, "quoteOnly": True, "active": True,
        }
        self.conn.execute(
            "INSERT INTO products(id,data_json) VALUES(?,?)",
            (legacy["id"], json.dumps(legacy)),
        )
        body = {
            "customer": {"name": "Client Test", "phone": "+221771234567"},
            "fulfillment": {"method": "pickup"},
            "items": [{"id": "INF-005", "qty": 1}],
        }
        with self.assertRaisesRegex(ValueError, "Prix bientôt disponible"):
            server.build_store_order(self.conn, body)

    def test_database_startup_migrates_legacy_flags_and_preserves_local_history(self):
        old_data, old_uploads, old_db, old_seed = server.DATA, server.UPLOADS, server.DB_PATH, server.SEED_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                server.DATA = root / "data"
                server.UPLOADS = root / "assets" / "uploads"
                server.DB_PATH = server.DATA / "app.sqlite"
                server.SEED_PATH = server.DATA / "catalog.json"
                server.DATA.mkdir(parents=True)
                seed_product = {
                    "id": "INF-005", "ref": "INF-005", "name": "Photocopieur",
                    "family": "Imprimantes", "pack": "Sur devis", "sellPrice": None,
                    "quoteOnly": True, "active": True,
                }
                server.SEED_PATH.write_text(json.dumps({"products": [seed_product]}), encoding="utf-8")
                server.init_db()
                with server.connection() as conn:
                    conn.execute("INSERT INTO sales(number,date,payload_json) VALUES(?,?,?)",
                                 ("V-1", "2026-01-01", json.dumps({"number": "V-1", "date": "2026-01-01"})))
                    old_order = {
                        "number": "WEB-OLD-1", "createdAt": "2026-01-01", "status": "quote_sent",
                        "items": [{"id": "INF-005", "qty": 1, "quoteRequested": True}],
                        "quoteRequested": True,
                    }
                    conn.execute("INSERT INTO web_orders(number,created_at,status,payload_json) VALUES(?,?,?,?)",
                                 (old_order["number"], old_order["createdAt"], old_order["status"], json.dumps(old_order)))
                server.init_db()
                with server.connection() as conn:
                    product = json.loads(conn.execute("SELECT data_json FROM products WHERE id='INF-005'").fetchone()[0])
                    order_row = conn.execute("SELECT status,payload_json FROM web_orders WHERE number='WEB-OLD-1'").fetchone()
                    order = json.loads(order_row["payload_json"])
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 1)
                self.assertNotIn("quoteOnly", product)
                self.assertEqual(product["pack"], "Conditionnement non précisé")
                self.assertEqual(order_row["status"], "contacted")
                self.assertEqual(order["status"], "contacted")
                self.assertNotIn("quoteRequested", order)
                self.assertNotIn("quoteRequested", order["items"][0])
        finally:
            server.DATA, server.UPLOADS, server.DB_PATH, server.SEED_PATH = old_data, old_uploads, old_db, old_seed

    def test_sqlite_admin_contains_no_quote_ui_or_controls(self):
        html = (Path(server.ROOT) / "index.html").read_text(encoding="utf-8").lower()
        for obsolete in ("sur devis", "quoteonly", "quoterequested", "quote_sent"):
            self.assertNotIn(obsolete, html)
        self.assertIn("prix bientôt disponible", html)


if __name__ == "__main__":
    unittest.main()
