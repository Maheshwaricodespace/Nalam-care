# NalamCare — Medicine Stock-Out Early Warning System
**For Primary Health Centres (PHCs) & Central Medical Stores — Government of Tamil Nadu**

NalamCare is a full-stack inventory monitoring and early warning system specifically architected for government Primary Health Centres (PHCs), sub-centres, and central medical warehouses. It replaces vulnerable manual registers with an immutable double-entry stock ledger, guarantees negative-stock prevention, monitors expiry dates, tracks consumption velocity, and generates automated early warnings before essential medicines run out.

---

## 🚀 Running the Application in VS Code

Run the backend and frontend in **two separate PowerShell terminals** in VS Code:

### Terminal 1: Backend (Flask + SQLite)

```powershell
# Navigate to backend folder
cd c:\Users\LENOVO\OneDrive\Documents\NalamCare\backend

# Run the Flask API Server (port 5000)
py app.py
```

*The Flask backend will start at: `http://127.0.0.1:5000`*

### Terminal 2: Frontend (React + Vite)

```powershell
# Navigate to frontend folder
cd c:\Users\LENOVO\OneDrive\Documents\NalamCare\frontend

# Install dependencies (first time only)
npm.cmd install

# Start the Vite development server
npm.cmd run dev
```

*The Vite frontend will open at: `http://localhost:5173`*

---

## 🧪 Running Automated Tests

To execute the 14-point automated test suite covering all data integrity, ledger atomicity, transfer consistency, and API requirements:

```powershell
cd c:\Users\LENOVO\OneDrive\Documents\NalamCare\backend
py test_api.py
```

---

## 🛠️ Architecture & Features

### 1. Root Cause Resolution for the 404 Error
- **The Issue**: When requests hit `/api/transactions` without trailing slashes in Flask, default strict routing or blueprint misconfiguration can result in 404. Furthermore, if the ledger table is absent or returns empty, unhandled route handlers fail.
- **The Solution**: 
  - Routes are configured with `strict_slashes=False` on the unified Flask instance.
  - Safe, idempotent database initialization (`init_db`) runs automatically on startup.
  - `GET /api/transactions` returns HTTP 200 with `[]` if no transactions exist.

### 2. Double-Entry Style Stock Ledger
- **Table**: `stock_transactions`
- **Supported Types**:
  - `RECEIPT`: Inward consignment (increases stock).
  - `ISSUE`: Outpatient/Inpatient dispensing (decreases stock; prevents overdraft and blocks expired stock).
  - `RETURN`: Stock returned to dispensary (increases stock).
  - `DAMAGE`: Damaged/broken stock quarantine (decreases usable stock).
  - `EXPIRED`: Bio-medical destruction write-off (decreases stock).
  - `TRANSFER_OUT` / `TRANSFER_IN`: Atomic two-legged inter-facility movement preserving total system balance.
  - `ADJUSTMENT`: Auditable correction with explicit direction (`IN` or `OUT`).
- **Initial Consignments**: Batches register an initial `RECEIPT` exactly once, preventing double counting.

### 3. Explainable Stock-Out Early Warning Forecast
- Analyzes daily dispensing records (`ISSUE`) over the past 30 days to calculate `daily_burn_rate`.
- Evaluates runway: `estimated_days_to_stockout = floor(available_stock / daily_burn_rate)`.
- If fewer than 2 consumption records exist, transparently flags `"Insufficient usage history"` rather than inventing numbers.
- Fires warning when `estimated_days_to_stockout <= 14 days` or when stock drops below configured safety thresholds.

### 4. Shelf-Life & Expiry Management
- Tracks expiry status per batch:
  - 🔴 **Expired**: Blocked from being issued to patients.
  - 🟠 **Critical Near-Expiry (&le; 30 Days)**: Alerted for rapid rotation.
  - 🟡 **Warning Near-Expiry (&le; 60 Days)**: Flagged for transfer or planned consumption.
  - 🟢 **Safe**: Shelf-life > 60 days.

### 5. Government PHC Multi-Facility Support
- Multi-facility selector:
  - Central Medical Store - Coimbatore (Central drug warehouse)
  - PHC Kaniyur
  - PHC Alandurai
  - PHC Madukkarai
  - PHC Annur
- Role-based permissions switcher (Store Keeper, Pharmacist, Medical Officer, District Administrator).
- Low-connectivity / offline mode readiness indicator.
- Demonstration banner with 1-click sample data reload.

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check, DB connectivity, record counters |
| `GET` | `/api/dashboard` | Aggregated KPIs, alerts summary, recent movements |
| `GET` | `/api/medicines` | Medicine catalogue, total & usable stock, forecast |
| `POST` | `/api/medicines` | Register medicine (validates unique code) |
| `GET` | `/api/batches` | Registered batches with shelf-life status |
| `POST` | `/api/batches` | Register batch & record initial receipt atomically |
| `GET` | `/api/transactions` | Full immutable transaction ledger audit trail |
| `POST` | `/api/transactions` | Record movement (issue, receipt, transfer, write-off) |
| `GET` | `/api/stock` | Batch-level inventory by facility |
| `GET` | `/api/alerts` | Active stock-outs, forecast warnings, expiry alerts |
| `GET` | `/api/reports/stock` | Run-rate audit report with burn rates & runway |
| `POST` | `/api/settings/threshold` | Update minimum safety stock threshold |
| `POST` | `/api/seed` | Reset & reload demonstration sample data |
