import unittest
import json
import os
import tempfile
from datetime import date, timedelta
from app import app
from database import init_db, seed_sample_data, get_db_connection

class NalamCareAPITestCase(unittest.TestCase):
    def setUp(self):
        # Create a temporary database for test isolation
        self.db_fd, self.db_path = tempfile.mkstemp()
        import database
        database.DB_PATH = self.db_path

        init_db(self.db_path)
        seed_sample_data(self.db_path)
        self.client = app.test_client()

    def tearDown(self):
        try:
            os.close(self.db_fd)
        except OSError:
            pass
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except (PermissionError, OSError):
            pass

    def test_01_health_check(self):
        """1. Flask health endpoint returns HTTP 200."""
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["database"], "connected")
        self.assertIn("metrics", data)

    def test_02_medicine_registration_succeeds(self):
        """2. Medicine registration succeeds."""
        payload = {
            "medicine_code": "MED-TEST-001",
            "name": "Test Medicine",
            "strength": "250 mg",
            "category": "Antibiotic",
            "unit": "Tablets",
            "min_stock_level": 300
        }
        res = self.client.post('/api/medicines', json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["medicine_code"], "MED-TEST-001")
        self.assertEqual(data["min_stock_level"], 300)

    def test_03_duplicate_medicine_rejected(self):
        """3. Duplicate medicine registration is rejected."""
        payload = {
            "medicine_code": "MED-PAR-500", # already exists in seed data
            "name": "Paracetamol Duplicate",
            "strength": "500 mg",
            "category": "Analgesic",
            "unit": "Tablets"
        }
        res = self.client.post('/api/medicines', json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("already exists", res.get_json()["error"])

    def test_04_batch_registration_succeeds(self):
        """4. Batch registration succeeds for an existing medicine."""
        # Find ID of Paracetamol
        conn = get_db_connection(self.db_path)
        med_id = conn.execute("SELECT id FROM medicines WHERE medicine_code = 'MED-PAR-500'").fetchone()[0]
        conn.close()

        payload = {
            "medicine_id": med_id,
            "batch_number": "PAR-TEST-999",
            "supplier": "TNMSC Depot",
            "received_date": "2026-04-01",
            "expiry_date": "2028-04-01",
            "received_quantity": 1000,
            "facility_name": "Central Medical Store - Coimbatore"
        }
        res = self.client.post('/api/batches', json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["batch_number"], "PAR-TEST-999")

        # Verify initial receipt was recorded in stock transactions
        res_trans = self.client.get(f'/api/transactions?batch_id={data["id"]}')
        trans_list = res_trans.get_json()
        self.assertEqual(len(trans_list), 1)
        self.assertEqual(trans_list[0]["transaction_type"], "RECEIPT")
        self.assertEqual(trans_list[0]["quantity"], 1000)

    def test_05_invalid_dates_rejected(self):
        """5. Invalid expiry and received dates are rejected."""
        conn = get_db_connection(self.db_path)
        med_id = conn.execute("SELECT id FROM medicines LIMIT 1").fetchone()[0]
        conn.close()

        # Case A: Expiry date before received date
        payload = {
            "medicine_id": med_id,
            "batch_number": "BATCH-INV-1",
            "supplier": "Pharma Corp",
            "received_date": "2026-05-10",
            "expiry_date": "2026-05-01", # Earlier than received!
            "received_quantity": 500
        }
        res = self.client.post('/api/batches', json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("strictly later", res.get_json()["error"])

        # Case B: Malformed date
        payload["expiry_date"] = "not-a-date"
        res = self.client.post('/api/batches', json=payload)
        self.assertEqual(res.status_code, 400)

    def test_06_transactions_empty_returns_200(self):
        """6. GET /api/transactions returns HTTP 200, including when zero transactions exist."""
        # Clean transactions table
        conn = get_db_connection(self.db_path)
        conn.execute("DELETE FROM stock_transactions;")
        conn.commit()
        conn.close()

        res = self.client.get('/api/transactions')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [])

        # Also test with trailing slash
        res_slash = self.client.get('/api/transactions/')
        self.assertEqual(res_slash.status_code, 200)
        self.assertEqual(res_slash.get_json(), [])

    def test_07_valid_transaction_saved_and_retrieved(self):
        """7. Valid stock transactions are saved and appear in transaction history."""
        conn = get_db_connection(self.db_path)
        batch = conn.execute("SELECT id FROM batches WHERE batch_number = 'PAR-2026-B1'").fetchone()
        conn.close()
        batch_id = batch[0]

        payload = {
            "batch_id": batch_id,
            "transaction_type": "ISSUE",
            "quantity": 50,
            "facility_name": "PHC Kaniyur",
            "reason": "OPD Prescription dispensing",
            "reference_number": "TEST-ISS-01",
            "performed_by": "Pharmacist Test"
        }
        res = self.client.post('/api/transactions', json=payload)
        self.assertEqual(res.status_code, 201)

        # Check appearance in history
        res_hist = self.client.get('/api/transactions?type=ISSUE')
        self.assertEqual(res_hist.status_code, 200)
        refs = [t["reference_number"] for t in res_hist.get_json()]
        self.assertIn("TEST-ISS-01", refs)

    def test_08_and_09_stock_decreases_and_oversell_rejected(self):
        """8. Stock decreases correctly after an issue. 9. Issue larger than available stock rejected."""
        conn = get_db_connection(self.db_path)
        batch_id = conn.execute("SELECT id FROM batches WHERE batch_number = 'PAR-2026-B1'").fetchone()[0]
        conn.close()

        # Check stock before
        res_stock = self.client.get(f'/api/stock?facility=PHC Kaniyur')
        item = next(s for s in res_stock.get_json() if s["batch_id"] == batch_id)
        initial_stock = item["current_stock"]

        # Issue 10 units
        issue_payload = {
            "batch_id": batch_id,
            "transaction_type": "ISSUE",
            "quantity": 10,
            "facility_name": "PHC Kaniyur",
            "reason": "Patient prescription",
            "performed_by": "Nurse"
        }
        res_issue = self.client.post('/api/transactions', json=issue_payload)
        self.assertEqual(res_issue.status_code, 201)
        self.assertEqual(res_issue.get_json()["new_facility_balance"], initial_stock - 10)

        # Attempt to issue more than remaining stock
        oversell_payload = {
            "batch_id": batch_id,
            "transaction_type": "ISSUE",
            "quantity": initial_stock + 99999,
            "facility_name": "PHC Kaniyur",
            "reason": "Excess issue test"
        }
        res_oversell = self.client.post('/api/transactions', json=oversell_payload)
        self.assertEqual(res_oversell.status_code, 400)
        self.assertIn("Insufficient stock", res_oversell.get_json()["error"])

    def test_10_damage_and_expiry_reduce_stock(self):
        """10. Damage and expiry reduce usable stock."""
        conn = get_db_connection(self.db_path)
        batch_id = conn.execute("SELECT id FROM batches WHERE batch_number = 'ORS-2026-B1'").fetchone()[0]
        conn.close()

        # PHC Annur has ORS stock
        res_stock = self.client.get('/api/stock?facility=PHC Annur')
        ors_stock = next(s for s in res_stock.get_json() if s["batch_id"] == batch_id)["current_stock"]

        damage_payload = {
            "batch_id": batch_id,
            "transaction_type": "DAMAGE",
            "quantity": 5,
            "facility_name": "PHC Annur",
            "reason": "Water packet leak damage"
        }
        res_dmg = self.client.post('/api/transactions', json=damage_payload)
        self.assertEqual(res_dmg.status_code, 201)
        self.assertEqual(res_dmg.get_json()["new_facility_balance"], ors_stock - 5)

    def test_11_transfers_atomic_and_preserve_total_stock(self):
        """11. Transfers update both facilities without changing total stock."""
        conn = get_db_connection(self.db_path)
        batch_id = conn.execute("SELECT id FROM batches WHERE batch_number = 'PAR-2026-B1'").fetchone()[0]
        conn.close()

        # Total system stock of this batch before transfer
        res_stock_before = self.client.get('/api/stock')
        total_before = sum(s["current_stock"] for s in res_stock_before.get_json() if s["batch_id"] == batch_id)

        # Transfer 200 units from CMS to PHC Annur
        transfer_payload = {
            "batch_id": batch_id,
            "transaction_type": "TRANSFER_OUT",
            "quantity": 200,
            "facility_name": "Central Medical Store - Coimbatore",
            "related_facility": "PHC Annur",
            "reason": "Emergency redistribution indent",
            "performed_by": "CMS Superintendent"
        }
        res_tr = self.client.post('/api/transactions', json=transfer_payload)
        self.assertEqual(res_tr.status_code, 201)

        # Total system stock of this batch after transfer must be IDENTICAL
        res_stock_after = self.client.get('/api/stock')
        total_after = sum(s["current_stock"] for s in res_stock_after.get_json() if s["batch_id"] == batch_id)
        self.assertEqual(total_before, total_after)

        # Check PHC Annur received the stock
        res_annur = self.client.get('/api/stock?facility=PHC Annur')
        annur_item = next((s for s in res_annur.get_json() if s["batch_id"] == batch_id), None)
        self.assertIsNotNone(annur_item)
        self.assertGreaterEqual(annur_item["current_stock"], 200)

    def test_12_expired_stock_cannot_be_issued(self):
        """12. Expired stock cannot be issued."""
        # Create an expired batch
        conn = get_db_connection(self.db_path)
        med_id = conn.execute("SELECT id FROM medicines WHERE medicine_code = 'MED-PAR-500'").fetchone()[0]
        cursor = conn.execute("""
            INSERT INTO batches (medicine_id, batch_number, supplier, received_date, expiry_date, received_quantity)
            VALUES (?, 'PAR-EXPIRED-TEST', 'Supplier', '2025-01-01', '2025-12-31', 100)
        """, (med_id,))
        batch_id = cursor.lastrowid
        conn.execute("""
            INSERT INTO stock_transactions (batch_id, transaction_type, quantity, transaction_date, facility_name, reason)
            VALUES (?, 'RECEIPT', 100, '2025-01-01', 'PHC Kaniyur', 'Past receipt')
        """, (batch_id,))
        conn.commit()
        conn.close()

        # Attempt to issue
        issue_payload = {
            "batch_id": batch_id,
            "transaction_type": "ISSUE",
            "quantity": 10,
            "facility_name": "PHC Kaniyur",
            "reason": "Prescription issue attempt"
        }
        res = self.client.post('/api/transactions', json=issue_payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("expired", res.get_json()["error"].lower())

    def test_13_dashboard_matches_database(self):
        """13. Dashboard statistics match the database."""
        res = self.client.get('/api/dashboard')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        conn = get_db_connection(self.db_path)
        actual_meds = conn.execute("SELECT COUNT(*) FROM medicines").fetchone()[0]
        conn.close()

        self.assertEqual(data["kpis"]["total_medicines"], actual_meds)
        self.assertIn("total_usable_stock_units", data["kpis"])
        self.assertIn("medicines_at_stockout_risk", data["kpis"])
        self.assertIn("recent_movements", data)

    def test_14_threshold_update_persists(self):
        """14. Threshold updates persist and update stockout status."""
        conn = get_db_connection(self.db_path)
        med = conn.execute("SELECT id FROM medicines WHERE medicine_code = 'MED-RAN-150'").fetchone()
        conn.close()
        med_id = med[0]

        res = self.client.post('/api/settings/threshold', json={
            "medicine_id": med_id,
            "min_stock_level": 5000 # higher than current stock to trigger alert
        })
        self.assertEqual(res.status_code, 200)

        # Verify medicine now reports Below Minimum Threshold
        res_meds = self.client.get('/api/medicines')
        ran = next(m for m in res_meds.get_json() if m["id"] == med_id)
        self.assertEqual(ran["min_stock_level"], 5000)
        self.assertTrue(ran["is_stockout_risk"])

    def test_15_foreign_key_enforced_and_migration_idempotent(self):
        """15. Foreign keys enforced and database migration is safe and idempotent."""
        # A: Invalid batch_id in transaction rejected
        payload = {
            "batch_id": 999999, # Non-existent batch
            "transaction_type": "ISSUE",
            "quantity": 5,
            "facility_name": "PHC Kaniyur"
        }
        res = self.client.post('/api/transactions', json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("not found", res.get_json()["error"].lower())

        # B: Safe migration idempotence: re-running init_db on existing database does not duplicate data
        conn = get_db_connection(self.db_path)
        batches_before = conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        trans_before = conn.execute("SELECT COUNT(*) FROM stock_transactions").fetchone()[0]
        conn.close()

        init_db(self.db_path)

        conn = get_db_connection(self.db_path)
        batches_after = conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        trans_after = conn.execute("SELECT COUNT(*) FROM stock_transactions").fetchone()[0]
        conn.close()

        self.assertEqual(batches_before, batches_after)
        self.assertEqual(trans_before, trans_after)

if __name__ == '__main__':
    unittest.main()
