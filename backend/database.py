import sqlite3
import os
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(__file__), "nalamcare.db")

def get_db_connection(db_file=None):
    """Return a connection to the SQLite database with row factory and foreign keys enabled."""
    path = db_file or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(db_file=None):
    """Safe, idempotent initialization and migration of the NalamCare database."""
    conn = get_db_connection(db_file)
    with conn:
        # 1. Facilities
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                district TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Medicines
        conn.execute("""
            CREATE TABLE IF NOT EXISTS medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                medicine_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                strength TEXT NOT NULL,
                category TEXT NOT NULL,
                unit TEXT NOT NULL,
                min_stock_level INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 3. Batches
        conn.execute("""
            CREATE TABLE IF NOT EXISTS batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                medicine_id INTEGER NOT NULL REFERENCES medicines(id) ON DELETE CASCADE,
                batch_number TEXT NOT NULL,
                supplier TEXT NOT NULL,
                received_date TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                received_quantity INTEGER NOT NULL CHECK(received_quantity > 0),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(medicine_id, batch_number)
            );
        """)

        # 4. Stock Transactions (Ledger)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE RESTRICT,
                transaction_type TEXT NOT NULL CHECK(transaction_type IN (
                    'RECEIPT', 'ISSUE', 'RETURN', 'DAMAGE', 'EXPIRED', 'TRANSFER_IN', 'TRANSFER_OUT', 'ADJUSTMENT'
                )),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                transaction_date TEXT NOT NULL,
                facility_name TEXT NOT NULL,
                related_facility TEXT,
                reason TEXT,
                reference_number TEXT,
                performed_by TEXT,
                adjustment_direction TEXT CHECK(adjustment_direction IN ('IN', 'OUT') OR adjustment_direction IS NULL),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create indexes for fast ledger calculations
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trans_batch_facility ON stock_transactions(batch_id, facility_name);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trans_date ON stock_transactions(transaction_date);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_batch_expiry ON batches(expiry_date);")

        # Migration: Ensure existing batches without a ledger transaction receive an initial RECEIPT exactly once
        cursor = conn.execute("""
            SELECT b.id, b.batch_number, b.supplier, b.received_date, b.received_quantity
            FROM batches b
            LEFT JOIN stock_transactions t ON b.id = t.batch_id
            WHERE t.id IS NULL;
        """)
        unmigrated_batches = cursor.fetchall()
        for batch in unmigrated_batches:
            conn.execute("""
                INSERT INTO stock_transactions (
                    batch_id, transaction_type, quantity, transaction_date,
                    facility_name, reason, reference_number, performed_by
                ) VALUES (?, 'RECEIPT', ?, ?, 'Central Medical Store - Coimbatore', 'Initial batch migration receipt', ?, 'System Migration')
            """, (
                batch["id"],
                batch["received_quantity"],
                batch["received_date"],
                f"MIG-{batch['batch_number']}"
            ))

    conn.close()

def get_batch_facility_stock(conn, batch_id, facility_name):
    """
    Calculate real-time stock balance for a specific batch at a specific facility.
    Receipts, returns, transfer-ins, and positive adjustments add stock.
    Issues, damage, expired, transfer-outs, and negative adjustments reduce stock.
    """
    cursor = conn.execute("""
        SELECT transaction_type, quantity, adjustment_direction
        FROM stock_transactions
        WHERE batch_id = ? AND facility_name = ?
    """, (batch_id, facility_name))
    rows = cursor.fetchall()

    balance = 0
    for r in rows:
        ttype = r["transaction_type"]
        qty = r["quantity"]
        direction = r["adjustment_direction"]

        if ttype in ('RECEIPT', 'RETURN', 'TRANSFER_IN'):
            balance += qty
        elif ttype in ('ISSUE', 'DAMAGE', 'EXPIRED', 'TRANSFER_OUT'):
            balance -= qty
        elif ttype == 'ADJUSTMENT':
            if direction == 'IN':
                balance += qty
            elif direction == 'OUT':
                balance -= qty

    return balance

def seed_sample_data(db_file=None):
    """
    Seed realistic Primary Health Centre (PHC) sample demonstration data.
    Clearly marks demonstration records.
    """
    conn = get_db_connection(db_file)
    with conn:
        # Clear existing demo records safely
        conn.execute("DELETE FROM stock_transactions;")
        conn.execute("DELETE FROM batches;")
        conn.execute("DELETE FROM medicines;")
        conn.execute("DELETE FROM facilities;")

        # 1. Insert Government Facilities
        facilities_data = [
            ("CMS-CBE", "Central Medical Store - Coimbatore", "Central Medical Store", "Coimbatore"),
            ("PHC-KAN", "PHC Kaniyur", "Primary Health Centre", "Coimbatore"),
            ("PHC-ALN", "PHC Alandurai", "Primary Health Centre", "Coimbatore"),
            ("PHC-MDK", "PHC Madukkarai", "Primary Health Centre", "Coimbatore"),
            ("PHC-ANN", "PHC Annur", "Primary Health Centre", "Coimbatore")
        ]
        conn.executemany("""
            INSERT INTO facilities (code, name, type, district) VALUES (?, ?, ?, ?)
        """, facilities_data)

        # 2. Insert Essential Medicines (NLEM / EDL standard government medicines)
        medicines_data = [
            ("MED-PAR-500", "Paracetamol", "500 mg", "Analgesic & Antipyretic", "Tablets", 1000),
            ("MED-AMX-500", "Amoxicillin", "500 mg", "Antibiotic", "Capsules", 500),
            ("MED-MET-500", "Metformin", "500 mg", "Antidiabetic", "Tablets", 800),
            ("MED-AML-005", "Amlodipine", "5 mg", "Antihypertensive", "Tablets", 600),
            ("MED-ORS-SCT", "Oral Rehydration Salts (ORS)", "21.8 g", "Electrolyte Solution", "Sachets", 400),
            ("MED-IFA-100", "Iron & Folic Acid", "100 mg elemental iron", "Maternal Health", "Tablets", 1200),
            ("MED-ATV-020", "Atorvastatin", "20 mg", "Cardiovascular", "Tablets", 300),
            ("MED-AZI-500", "Azithromycin", "500 mg", "Antibiotic", "Tablets", 250),
            ("MED-INS-HUM", "Human Insulin (Regular)", "40 IU/ml", "Antidiabetic", "Vials", 150),
            ("MED-CET-010", "Cetirizine", "10 mg", "Antihistamine", "Tablets", 450),
            ("MED-ALB-400", "Albendazole", "400 mg", "Anthelmintic", "Tablets", 350),
            ("MED-RAN-150", "Pantoprazole", "40 mg", "Gastrointestinal", "Tablets", 0) # 0 means unconfigured threshold
        ]
        conn.executemany("""
            INSERT INTO medicines (medicine_code, name, strength, category, unit, min_stock_level)
            VALUES (?, ?, ?, ?, ?, ?)
        """, medicines_data)

        # Map codes to IDs
        med_ids = {}
        for row in conn.execute("SELECT id, medicine_code FROM medicines"):
            med_ids[row["medicine_code"]] = row["id"]

        # 3. Insert Batches (with various shelf-lives: safe, near expiry <=30d, <=60d, expired)
        batches_data = [
            (med_ids["MED-PAR-500"], "PAR-2026-B1", "Tamil Nadu Medical Services Corp (TNMSC)", "2026-01-10", "2027-08-31", 5000),
            (med_ids["MED-PAR-500"], "PAR-2026-B2", "Apex Healthcare Supplies", "2026-03-01", "2026-11-05", 2000), # Expiring in ~25 days
            (med_ids["MED-AMX-500"], "AMX-2025-E1", "Cipla Generic Supplies", "2025-05-10", "2026-09-15", 800), # Expired ~26 days ago
            (med_ids["MED-AMX-500"], "AMX-2026-B1", "Cipla Generic Supplies", "2026-02-15", "2027-06-30", 3000),
            (med_ids["MED-MET-500"], "MET-2026-B1", "Sun Pharma Direct", "2026-01-20", "2027-12-31", 4000),
            (med_ids["MED-AML-005"], "AML-2026-N1", "TNMSC Depot Coimbatore", "2026-02-01", "2026-11-20", 1500), # Expiring in ~40 days
            (med_ids["MED-ORS-SCT"], "ORS-2026-B1", "Zydus Lifesciences", "2026-01-15", "2027-10-31", 2500),
            (med_ids["MED-IFA-100"], "IFA-2026-B1", "TNMSC Depot Coimbatore", "2026-03-05", "2027-04-30", 6000),
            (med_ids["MED-ATV-020"], "ATV-2026-B1", "Lupin Pharmaceuticals", "2026-02-10", "2027-09-30", 1000),
            (med_ids["MED-AZI-500"], "AZI-2026-B1", "Alkem Laboratories", "2026-03-12", "2027-11-30", 800),
            (med_ids["MED-INS-HUM"], "INS-2026-B1", "Biocon Biologics", "2026-04-01", "2026-12-15", 300), # Expiring in ~65 days
            (med_ids["MED-CET-010"], "CET-2026-B1", "Apex Healthcare Supplies", "2026-02-20", "2027-05-31", 1200),
            (med_ids["MED-ALB-400"], "ALB-2026-B1", "TNMSC Depot Coimbatore", "2026-01-18", "2027-03-31", 900),
            (med_ids["MED-RAN-150"], "RAN-2026-B1", "Zydus Lifesciences", "2026-02-25", "2027-01-31", 1100)
        ]
        conn.executemany("""
            INSERT INTO batches (medicine_id, batch_number, supplier, received_date, expiry_date, received_quantity)
            VALUES (?, ?, ?, ?, ?, ?)
        """, batches_data)

        # Map batch numbers to batch IDs
        batch_ids = {}
        for row in conn.execute("SELECT id, batch_number FROM batches"):
            batch_ids[row["batch_number"]] = row["id"]

        # 4. Stock Transactions Ledger:
        # Every initial batch is received at Central Medical Store - Coimbatore
        initial_transactions = []
        for batch in batches_data:
            b_num = batch[1]
            b_id = batch_ids[b_num]
            b_date = batch[3]
            b_qty = batch[5]
            initial_transactions.append((
                b_id, 'RECEIPT', b_qty, b_date,
                'Central Medical Store - Coimbatore', None,
                'Initial government central consignment receipt', f"GRN-{b_num}", 'Dr. R. Senthamil (Store Superintendent)', None
            ))

        conn.executemany("""
            INSERT INTO stock_transactions (
                batch_id, transaction_type, quantity, transaction_date,
                facility_name, related_facility, reason, reference_number, performed_by, adjustment_direction
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, initial_transactions)

        # 5. Add Realistic Inter-Facility Transfers & Dispensing Movements
        movements = [
            # Transfer Paracetamol PAR-2026-B1 from CMS to PHC Kaniyur
            (batch_ids["PAR-2026-B1"], 'TRANSFER_OUT', 1200, "2026-03-15", "Central Medical Store - Coimbatore", "PHC Kaniyur", "Monthly indents supply", "TR-CMS-KAN-001", "Pharmacist K. Murugan", None),
            (batch_ids["PAR-2026-B1"], 'TRANSFER_IN', 1200, "2026-03-15", "PHC Kaniyur", "Central Medical Store - Coimbatore", "Monthly indents receipt", "TR-CMS-KAN-001", "Staff Nurse P. Malathi", None),

            # Transfer Paracetamol PAR-2026-B2 from CMS to PHC Alandurai
            (batch_ids["PAR-2026-B2"], 'TRANSFER_OUT', 800, "2026-03-16", "Central Medical Store - Coimbatore", "PHC Alandurai", "Indent supply", "TR-CMS-ALN-001", "Pharmacist K. Murugan", None),
            (batch_ids["PAR-2026-B2"], 'TRANSFER_IN', 800, "2026-03-16", "PHC Alandurai", "Central Medical Store - Coimbatore", "Indent receipt", "TR-CMS-ALN-001", "Pharmacist S. Kavitha", None),

            # Dispense / Issue Paracetamol at PHC Kaniyur (Daily OPD dispensing over recent days to generate consumption history)
            (batch_ids["PAR-2026-B1"], 'ISSUE', 150, "2026-10-01", "PHC Kaniyur", None, "OPD General Patient Dispensing", "OPD-20261001-01", "Pharmacist S. Suresh", None),
            (batch_ids["PAR-2026-B1"], 'ISSUE', 180, "2026-10-03", "PHC Kaniyur", None, "OPD General Patient Dispensing", "OPD-20261003-01", "Pharmacist S. Suresh", None),
            (batch_ids["PAR-2026-B1"], 'ISSUE', 140, "2026-10-06", "PHC Kaniyur", None, "OPD General Patient Dispensing", "OPD-20261006-01", "Pharmacist S. Suresh", None),
            (batch_ids["PAR-2026-B1"], 'ISSUE', 200, "2026-10-09", "PHC Kaniyur", None, "OPD General Patient Dispensing", "OPD-20261009-01", "Pharmacist S. Suresh", None),

            # Transfer Amoxicillin AMX-2026-B1 to PHC Madukkarai
            (batch_ids["AMX-2026-B1"], 'TRANSFER_OUT', 1000, "2026-03-20", "Central Medical Store - Coimbatore", "PHC Madukkarai", "Antibiotic quota", "TR-CMS-MDK-001", "Pharmacist K. Murugan", None),
            (batch_ids["AMX-2026-B1"], 'TRANSFER_IN', 1000, "2026-03-20", "PHC Madukkarai", "Central Medical Store - Coimbatore", "Antibiotic quota receipt", "TR-CMS-MDK-001", "Pharmacist V. Anand", None),

            # Issue Amoxicillin at PHC Madukkarai
            (batch_ids["AMX-2026-B1"], 'ISSUE', 300, "2026-10-02", "PHC Madukkarai", None, "Respiratory infection clinic", "OPD-MDK-001", "Pharmacist V. Anand", None),
            (batch_ids["AMX-2026-B1"], 'ISSUE', 250, "2026-10-05", "PHC Madukkarai", None, "Respiratory infection clinic", "OPD-MDK-002", "Pharmacist V. Anand", None),

            # Expired batch written off: AMX-2025-E1 at CMS write-off
            (batch_ids["AMX-2025-E1"], 'EXPIRED', 800, "2026-09-16", "Central Medical Store - Coimbatore", None, "Expired batch quarantine write-off for bio-waste destruction", "EXP-20260916-01", "Dr. R. Senthamil (Store Superintendent)", None),

            # Transfer Metformin to PHC Kaniyur
            (batch_ids["MET-2026-B1"], 'TRANSFER_OUT', 1500, "2026-03-18", "Central Medical Store - Coimbatore", "PHC Kaniyur", "NCD Clinic Indent", "TR-CMS-KAN-002", "Pharmacist K. Murugan", None),
            (batch_ids["MET-2026-B1"], 'TRANSFER_IN', 1500, "2026-03-18", "PHC Kaniyur", "Central Medical Store - Coimbatore", "NCD Clinic Indent Receipt", "TR-CMS-KAN-002", "Staff Nurse P. Malathi", None),

            # Issue Metformin (NCD Clinic)
            (batch_ids["MET-2026-B1"], 'ISSUE', 200, "2026-10-01", "PHC Kaniyur", None, "NCD Diabetes Screening Camp", "NCD-KAN-001", "Pharmacist S. Suresh", None),
            (batch_ids["MET-2026-B1"], 'ISSUE', 220, "2026-10-05", "PHC Kaniyur", None, "Weekly NCD Outpatient Clinic", "NCD-KAN-002", "Pharmacist S. Suresh", None),
            (batch_ids["MET-2026-B1"], 'ISSUE', 190, "2026-10-08", "PHC Kaniyur", None, "Weekly NCD Outpatient Clinic", "NCD-KAN-003", "Pharmacist S. Suresh", None),

            # ORS Transfer to PHC Annur
            (batch_ids["ORS-2026-B1"], 'TRANSFER_OUT', 500, "2026-04-01", "Central Medical Store - Coimbatore", "PHC Annur", "Diarrhoea preparedness quota", "TR-CMS-ANN-001", "Pharmacist K. Murugan", None),
            (batch_ids["ORS-2026-B1"], 'TRANSFER_IN', 500, "2026-04-01", "PHC Annur", "Central Medical Store - Coimbatore", "Diarrhoea preparedness quota receipt", "TR-CMS-ANN-001", "Pharmacist M. Deepa", None),

            # Small damaged batch adjustment
            (batch_ids["ORS-2026-B1"], 'DAMAGE', 15, "2026-05-10", "PHC Annur", None, "Monsoon packaging moisture damage", "DMG-ANN-001", "Pharmacist M. Deepa", None)
        ]

        conn.executemany("""
            INSERT INTO stock_transactions (
                batch_id, transaction_type, quantity, transaction_date,
                facility_name, related_facility, reason, reference_number, performed_by, adjustment_direction
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, movements)

    conn.close()

if __name__ == "__main__":
    init_db()
    seed_sample_data()
    print("NalamCare database initialized and seeded successfully.")
