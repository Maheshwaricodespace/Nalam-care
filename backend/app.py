import os
import sqlite3
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from database import get_db_connection, init_db, seed_sample_data, get_batch_facility_stock

app = Flask(__name__)
# Enable CORS for all routes and common Vite local origins
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Ensure database tables exist upon app startup
init_db()

# --- Helper Functions ---

def parse_iso_date(date_str):
    """Validate ISO date format YYYY-MM-DD."""
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

def calculate_burn_rate_and_forecast(conn, medicine_id, available_stock, days_lookback=30):
    """
    Rule-based explainable stock-out prediction:
    Calculates average daily consumption (ISSUE) over past `days_lookback` days.
    """
    cutoff_date = (date.today() - timedelta(days=days_lookback)).isoformat()
    cursor = conn.execute("""
        SELECT st.quantity, st.transaction_date
        FROM stock_transactions st
        JOIN batches b ON st.batch_id = b.id
        WHERE b.medicine_id = ?
          AND st.transaction_type = 'ISSUE'
          AND st.transaction_date >= ?
        ORDER BY st.transaction_date ASC
    """, (medicine_id, cutoff_date))
    rows = cursor.fetchall()

    if not rows or len(rows) < 2:
        return {
            "daily_burn_rate": None,
            "estimated_days_to_stockout": None,
            "consumption_status": "Insufficient usage history",
            "recent_consumption_units": sum(r["quantity"] for r in rows),
            "consumption_records_count": len(rows)
        }

    total_consumed = sum(r["quantity"] for r in rows)
    first_date = parse_iso_date(rows[0]["transaction_date"])
    last_date = parse_iso_date(rows[-1]["transaction_date"])
    days_span = max(1, (last_date - first_date).days if (first_date and last_date) else days_lookback)

    daily_burn_rate = round(total_consumed / days_span, 2)

    if daily_burn_rate <= 0:
        return {
            "daily_burn_rate": 0,
            "estimated_days_to_stockout": None,
            "consumption_status": "Zero daily consumption",
            "recent_consumption_units": total_consumed,
            "consumption_records_count": len(rows)
        }

    estimated_days = int(available_stock // daily_burn_rate) if daily_burn_rate > 0 else 9999

    return {
        "daily_burn_rate": daily_burn_rate,
        "estimated_days_to_stockout": estimated_days,
        "consumption_status": "Predictable forecast available",
        "recent_consumption_units": total_consumed,
        "consumption_records_count": len(rows)
    }

def fetch_medicines_data(conn, facility=None):
    """Internal helper to retrieve processed medicines with stock and forecasting."""
    today_str = date.today().isoformat()
    facility_filter = "AND st.facility_name = ?" if facility else ""
    params = (facility,) if facility else ()

    query = f"""
        SELECT 
            m.id, m.medicine_code, m.name, m.strength, m.category, m.unit, m.min_stock_level, m.created_at,
            COUNT(DISTINCT b.id) AS total_batches,
            COALESCE(SUM(
                CASE 
                    WHEN st.transaction_type IN ('RECEIPT', 'RETURN', 'TRANSFER_IN') THEN st.quantity
                    WHEN st.transaction_type = 'ADJUSTMENT' AND st.adjustment_direction = 'IN' THEN st.quantity
                    WHEN st.transaction_type IN ('ISSUE', 'DAMAGE', 'EXPIRED', 'TRANSFER_OUT') THEN -st.quantity
                    WHEN st.transaction_type = 'ADJUSTMENT' AND st.adjustment_direction = 'OUT' THEN -st.quantity
                    ELSE 0
                END
            ), 0) AS total_stock,
            COALESCE(SUM(
                CASE 
                    WHEN b.expiry_date >= '{today_str}' THEN
                        CASE 
                            WHEN st.transaction_type IN ('RECEIPT', 'RETURN', 'TRANSFER_IN') THEN st.quantity
                            WHEN st.transaction_type = 'ADJUSTMENT' AND st.adjustment_direction = 'IN' THEN st.quantity
                            WHEN st.transaction_type IN ('ISSUE', 'DAMAGE', 'EXPIRED', 'TRANSFER_OUT') THEN -st.quantity
                            WHEN st.transaction_type = 'ADJUSTMENT' AND st.adjustment_direction = 'OUT' THEN -st.quantity
                            ELSE 0
                        END
                    ELSE 0
                END
            ), 0) AS usable_stock
        FROM medicines m
        LEFT JOIN batches b ON m.id = b.medicine_id
        LEFT JOIN stock_transactions st ON b.id = st.batch_id {facility_filter}
        GROUP BY m.id
        ORDER BY m.name ASC
    """
    cursor = conn.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        min_level = r["min_stock_level"]
        usable = max(0, r["usable_stock"])
        r["usable_stock"] = usable
        r["total_stock"] = max(0, r["total_stock"])

        if min_level is None or min_level <= 0:
            r["threshold_status"] = "Unconfigured"
            r["is_stockout_risk"] = False
        elif usable == 0:
            r["threshold_status"] = "Out of Stock"
            r["is_stockout_risk"] = True
        elif usable <= min_level:
            r["threshold_status"] = "Below Minimum Threshold"
            r["is_stockout_risk"] = True
        else:
            r["threshold_status"] = "Adequate Stock"
            r["is_stockout_risk"] = False

        forecast = calculate_burn_rate_and_forecast(conn, r["id"], usable)
        r["forecast"] = forecast

    return rows

def fetch_stock_data(conn, facility=None):
    """Internal helper to retrieve batch-level stock balances."""
    today_str = date.today().isoformat()
    today = date.today()

    facility_filter = "WHERE st.facility_name = ?" if facility else ""
    params = (facility,) if facility else ()

    query = f"""
        SELECT 
            m.id AS medicine_id,
            m.medicine_code,
            m.name AS medicine_name,
            m.strength,
            m.category,
            m.unit,
            m.min_stock_level,
            b.id AS batch_id,
            b.batch_number,
            b.supplier,
            b.expiry_date,
            st.facility_name,
            SUM(
                CASE 
                    WHEN st.transaction_type IN ('RECEIPT', 'RETURN', 'TRANSFER_IN') THEN st.quantity
                    WHEN st.transaction_type = 'ADJUSTMENT' AND st.adjustment_direction = 'IN' THEN st.quantity
                    WHEN st.transaction_type IN ('ISSUE', 'DAMAGE', 'EXPIRED', 'TRANSFER_OUT') THEN -st.quantity
                    WHEN st.transaction_type = 'ADJUSTMENT' AND st.adjustment_direction = 'OUT' THEN -st.quantity
                    ELSE 0
                END
            ) AS current_stock
        FROM medicines m
        JOIN batches b ON m.id = b.medicine_id
        JOIN stock_transactions st ON b.id = st.batch_id
        {facility_filter}
        GROUP BY m.id, b.id, st.facility_name
        HAVING current_stock > 0
        ORDER BY m.name ASC, b.expiry_date ASC
    """
    cursor = conn.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        exp_date = parse_iso_date(r["expiry_date"])
        r["is_expired"] = r["expiry_date"] < today_str
        if exp_date:
            days = (exp_date - today).days
            r["days_to_expiry"] = days
            if days < 0:
                r["shelf_life_status"] = "EXPIRED"
            elif days <= 30:
                r["shelf_life_status"] = "EXPIRING_30_DAYS"
            elif days <= 60:
                r["shelf_life_status"] = "EXPIRING_60_DAYS"
            else:
                r["shelf_life_status"] = "GOOD"
        else:
            r["days_to_expiry"] = None
            r["shelf_life_status"] = "UNKNOWN"

    return rows

# How long (in days) a refill is still reported as a "completed" restock request
REQUEST_COMPLETED_WINDOW_DAYS = 14

def get_restock_request_status(conn, medicine_id, facility, usable_stock, min_stock_level):
    """
    Tracks the restock request lifecycle for one medicine so the stock report
    does not keep showing the old low-stock state after the store has been refilled.

    - PENDING   : stock is still at/below the minimum level, refill is required.
    - COMPLETED : a refill (RECEIPT / TRANSFER_IN) arrived recently, the stock was
                  at/below the minimum before it, and it is above the minimum now.
    - NONE      : nothing to report.
    """
    none_result = {"request_status": "NONE", "request_message": None}

    if not min_stock_level or min_stock_level <= 0:
        return none_result

    if usable_stock <= min_stock_level:
        return {
            "request_status": "PENDING",
            "request_message": f"Restock request pending: stock is {usable_stock}/{min_stock_level}, refill required."
        }

    facility_filter = "AND st.facility_name = ?" if facility else ""
    cutoff = (date.today() - timedelta(days=REQUEST_COMPLETED_WINDOW_DAYS)).isoformat()
    params = [medicine_id, cutoff]
    if facility:
        params.append(facility)

    arrival = conn.execute(f"""
        SELECT st.id, st.quantity, st.transaction_type, st.transaction_date, st.related_facility
        FROM stock_transactions st
        JOIN batches b ON st.batch_id = b.id
        WHERE b.medicine_id = ?
          AND st.transaction_type IN ('RECEIPT', 'TRANSFER_IN')
          AND st.transaction_date >= ?
          {facility_filter}
        ORDER BY st.transaction_date DESC, st.id DESC
        LIMIT 1
    """, params).fetchone()

    if not arrival:
        return none_result

    before_params = [medicine_id, arrival["id"]]
    if facility:
        before_params.append(facility)

    balance_before = conn.execute(f"""
        SELECT COALESCE(SUM(
            CASE
                WHEN st.transaction_type IN ('RECEIPT', 'RETURN', 'TRANSFER_IN') THEN st.quantity
                WHEN st.transaction_type = 'ADJUSTMENT' AND st.adjustment_direction = 'IN' THEN st.quantity
                WHEN st.transaction_type IN ('ISSUE', 'DAMAGE', 'EXPIRED', 'TRANSFER_OUT') THEN -st.quantity
                WHEN st.transaction_type = 'ADJUSTMENT' AND st.adjustment_direction = 'OUT' THEN -st.quantity
                ELSE 0
            END
        ), 0)
        FROM stock_transactions st
        JOIN batches b ON st.batch_id = b.id
        WHERE b.medicine_id = ?
          AND st.id < ?
          {facility_filter}
    """, before_params).fetchone()[0]

    # Stock was already healthy before this arrival, so it was not a restock request
    if balance_before > min_stock_level:
        return none_result

    source = f" from {arrival['related_facility']}" if arrival["related_facility"] else ""
    return {
        "request_status": "COMPLETED",
        "request_message": (
            f"Request completed: {arrival['quantity']} units received{source} on "
            f"{arrival['transaction_date']}. Stock is now {usable_stock} (minimum {min_stock_level})."
        )
    }

def fetch_alerts_data(conn, facility=None):
    """Internal helper to retrieve structured stock and expiry alerts."""
    medicines = fetch_medicines_data(conn, facility)
    stock_rows = fetch_stock_data(conn, facility)

    stockout_alerts = []
    forecast_warnings = []

    for m in medicines:
        min_stock = m.get("min_stock_level") or 0
        usable = m.get("usable_stock", 0)
        forecast = m.get("forecast", {})

        if min_stock > 0:
            if usable == 0:
                stockout_alerts.append({
                    "severity": "CRITICAL",
                    "type": "STOCKOUT_ZERO",
                    "medicine_id": m["id"],
                    "medicine_code": m["medicine_code"],
                    "medicine_name": m["name"],
                    "strength": m["strength"],
                    "unit": m["unit"],
                    "usable_stock": 0,
                    "min_stock_level": min_stock,
                    "message": f"Zero usable stock! Minimum required is {min_stock} {m['unit']}."
                })
            elif usable <= min_stock:
                stockout_alerts.append({
                    "severity": "HIGH",
                    "type": "STOCKOUT_BELOW_MIN",
                    "medicine_id": m["id"],
                    "medicine_code": m["medicine_code"],
                    "medicine_name": m["name"],
                    "strength": m["strength"],
                    "unit": m["unit"],
                    "usable_stock": usable,
                    "min_stock_level": min_stock,
                    "message": f"Stock is below minimum threshold ({usable}/{min_stock} {m['unit']})."
                })

        est_days = forecast.get("estimated_days_to_stockout")
        if est_days is not None and est_days <= 14 and usable > 0:
            forecast_warnings.append({
                "severity": "WARNING",
                "type": "FORECAST_STOCKOUT",
                "medicine_id": m["id"],
                "medicine_code": m["medicine_code"],
                "medicine_name": m["name"],
                "strength": m["strength"],
                "estimated_days": est_days,
                "daily_burn_rate": forecast.get("daily_burn_rate"),
                "usable_stock": usable,
                "message": f"Stock-out predicted in ~{est_days} days based on recent consumption of {forecast.get('daily_burn_rate')} {m['unit']}/day."
            })

    expired_alerts = []
    expiring_30_alerts = []
    expiring_60_alerts = []

    for item in stock_rows:
        status = item.get("shelf_life_status")
        alert_data = {
            "batch_id": item["batch_id"],
            "batch_number": item["batch_number"],
            "medicine_id": item["medicine_id"],
            "medicine_code": item["medicine_code"],
            "medicine_name": item["medicine_name"],
            "strength": item["strength"],
            "facility_name": item["facility_name"],
            "quantity": item["current_stock"],
            "expiry_date": item["expiry_date"],
            "days_to_expiry": item["days_to_expiry"]
        }
        if status == "EXPIRED":
            expired_alerts.append(alert_data)
        elif status == "EXPIRING_30_DAYS":
            expiring_30_alerts.append(alert_data)
        elif status == "EXPIRING_60_DAYS":
            expiring_60_alerts.append(alert_data)

    return {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "critical_stockouts": len([a for a in stockout_alerts if a["severity"] == "CRITICAL"]),
            "high_stockout_risks": len([a for a in stockout_alerts if a["severity"] == "HIGH"]),
            "forecast_warnings": len(forecast_warnings),
            "expired_batches": len(expired_alerts),
            "expiring_within_30_days": len(expiring_30_alerts),
            "expiring_within_60_days": len(expiring_60_alerts)
        },
        "stockout_alerts": stockout_alerts,
        "forecast_warnings": forecast_warnings,
        "expired_batches": expired_alerts,
        "expiring_within_30_days": expiring_30_alerts,
        "expiring_within_60_days": expiring_60_alerts
    }

# --- Routes ---

@app.route("/", methods=["GET"], strict_slashes=False)
def index():
    return jsonify({
        "system": "NalamCare — Medicine Stock-Out Early Warning System",
        "jurisdiction": "Primary Health Centres (PHC) & Central Medical Stores, Tamil Nadu",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": [
            "/api/health",
            "/api/dashboard",
            "/api/medicines",
            "/api/batches",
            "/api/transactions",
            "/api/stock",
            "/api/alerts",
            "/api/reports/stock",
            "/api/facilities"
        ]
    }), 200

@app.route("/api/health", methods=["GET"], strict_slashes=False)
def health_check():
    try:
        conn = get_db_connection()
        facilities_count = conn.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
        medicines_count = conn.execute("SELECT COUNT(*) FROM medicines").fetchone()[0]
        batches_count = conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        transactions_count = conn.execute("SELECT COUNT(*) FROM stock_transactions").fetchone()[0]
        conn.close()

        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat(),
            "environment": "development/hackathon",
            "metrics": {
                "facilities": facilities_count,
                "medicines": medicines_count,
                "batches": batches_count,
                "transactions": transactions_count
            }
        }), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route("/api/facilities", methods=["GET"], strict_slashes=False)
def get_facilities():
    conn = get_db_connection()
    cursor = conn.execute("SELECT id, code, name, type, district FROM facilities ORDER BY id ASC")
    facilities = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(facilities), 200

@app.route("/api/medicines", methods=["GET"], strict_slashes=False)
def get_medicines():
    facility = request.args.get("facility")
    conn = get_db_connection()
    medicines = fetch_medicines_data(conn, facility)
    conn.close()
    return jsonify(medicines), 200

@app.route("/api/medicines", methods=["POST"], strict_slashes=False)
def create_medicine():
    data = request.get_json() or {}
    code = (data.get("medicine_code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    strength = (data.get("strength") or "").strip()
    category = (data.get("category") or "").strip()
    unit = (data.get("unit") or "").strip()
    min_stock_level = data.get("min_stock_level", 0)

    if not code or not name or not unit:
        return jsonify({"error": "medicine_code, name, and unit are required fields."}), 400

    try:
        min_stock_level = int(min_stock_level) if min_stock_level is not None else 0
        if min_stock_level < 0:
            return jsonify({"error": "min_stock_level cannot be negative."}), 400
    except ValueError:
        return jsonify({"error": "min_stock_level must be a valid integer."}), 400

    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO medicines (medicine_code, name, strength, category, unit, min_stock_level)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, name, strength, category or "Essential Medicine", unit, min_stock_level))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()

        return jsonify({
            "id": new_id,
            "medicine_code": code,
            "name": name,
            "strength": strength,
            "category": category or "Essential Medicine",
            "unit": unit,
            "min_stock_level": min_stock_level,
            "message": "Medicine registered successfully."
        }), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": f"Medicine code '{code}' already exists."}), 400
    except Exception as e:
        conn.close()
        return jsonify({"error": "Failed to create medicine: " + str(e)}), 500

@app.route("/api/batches", methods=["GET"], strict_slashes=False)
def get_batches():
    medicine_id = request.args.get("medicine_id")
    facility = request.args.get("facility")
    conn = get_db_connection()
    today = date.today()

    conditions = []
    params = []

    if medicine_id:
        conditions.append("b.medicine_id = ?")
        params.append(medicine_id)

    facility_clause = "AND st.facility_name = ?" if facility else ""
    if facility:
        params.append(facility)

    where_str = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT 
            b.id, b.medicine_id, b.batch_number, b.supplier, b.received_date, b.expiry_date,
            b.received_quantity, b.created_at,
            m.medicine_code, m.name AS medicine_name, m.strength, m.unit, m.category,
            COALESCE(SUM(
                CASE 
                    WHEN st.transaction_type IN ('RECEIPT', 'RETURN', 'TRANSFER_IN') THEN st.quantity
                    WHEN st.transaction_type = 'ADJUSTMENT' AND st.adjustment_direction = 'IN' THEN st.quantity
                    WHEN st.transaction_type IN ('ISSUE', 'DAMAGE', 'EXPIRED', 'TRANSFER_OUT') THEN -st.quantity
                    WHEN st.transaction_type = 'ADJUSTMENT' AND st.adjustment_direction = 'OUT' THEN -st.quantity
                    ELSE 0
                END
            ), 0) AS current_stock
        FROM batches b
        JOIN medicines m ON b.medicine_id = m.id
        LEFT JOIN stock_transactions st ON b.id = st.batch_id {facility_clause}
        {where_str}
        GROUP BY b.id
        ORDER BY b.expiry_date ASC
    """

    cursor = conn.execute(query, params)
    batches = [dict(r) for r in cursor.fetchall()]

    for b in batches:
        exp_date = parse_iso_date(b["expiry_date"])
        if exp_date:
            days_to_expiry = (exp_date - today).days
            b["days_to_expiry"] = days_to_expiry
            if days_to_expiry < 0:
                b["expiry_status"] = "EXPIRED"
            elif days_to_expiry <= 30:
                b["expiry_status"] = "CRITICAL_NEAR_EXPIRY"
            elif days_to_expiry <= 60:
                b["expiry_status"] = "WARNING_NEAR_EXPIRY"
            else:
                b["expiry_status"] = "SAFE"
        else:
            b["days_to_expiry"] = None
            b["expiry_status"] = "UNKNOWN"

    conn.close()
    return jsonify(batches), 200

@app.route("/api/batches", methods=["POST"], strict_slashes=False)
def create_batch():
    data = request.get_json() or {}
    medicine_id = data.get("medicine_id")
    batch_number = (data.get("batch_number") or "").strip().upper()
    supplier = (data.get("supplier") or "").strip()
    received_date_str = (data.get("received_date") or "").strip()
    expiry_date_str = (data.get("expiry_date") or "").strip()
    received_quantity = data.get("received_quantity")
    receiving_facility = (data.get("facility_name") or "Central Medical Store - Coimbatore").strip()
    performed_by = (data.get("performed_by") or "Pharmacist / Store Keeper").strip()

    if not medicine_id or not batch_number or not supplier or not received_date_str or not expiry_date_str or received_quantity is None:
        return jsonify({"error": "All batch fields are required: medicine_id, batch_number, supplier, received_date, expiry_date, received_quantity."}), 400

    rec_date = parse_iso_date(received_date_str)
    exp_date = parse_iso_date(expiry_date_str)

    if not rec_date:
        return jsonify({"error": "Invalid received_date. Must be a valid ISO date YYYY-MM-DD."}), 400
    if not exp_date:
        return jsonify({"error": "Invalid expiry_date. Must be a valid ISO date YYYY-MM-DD."}), 400

    if exp_date <= rec_date:
        return jsonify({"error": "expiry_date must be strictly later than received_date."}), 400

    try:
        received_quantity = int(received_quantity)
        if received_quantity <= 0:
            return jsonify({"error": "received_quantity must be a positive integer."}), 400
    except ValueError:
        return jsonify({"error": "received_quantity must be a valid integer."}), 400

    conn = get_db_connection()
    try:
        med = conn.execute("SELECT id FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
        if not med:
            conn.close()
            return jsonify({"error": f"Medicine ID {medicine_id} does not exist."}), 400

        with conn:
            cursor = conn.execute("""
                INSERT INTO batches (medicine_id, batch_number, supplier, received_date, expiry_date, received_quantity)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (medicine_id, batch_number, supplier, received_date_str, expiry_date_str, received_quantity))
            new_batch_id = cursor.lastrowid

            ref_num = f"GRN-{batch_number}"
            conn.execute("""
                INSERT INTO stock_transactions (
                    batch_id, transaction_type, quantity, transaction_date,
                    facility_name, reason, reference_number, performed_by
                ) VALUES (?, 'RECEIPT', ?, ?, ?, 'Initial batch consignment receipt', ?, ?)
            """, (new_batch_id, received_quantity, received_date_str, receiving_facility, ref_num, performed_by))

        conn.close()
        return jsonify({
            "id": new_batch_id,
            "medicine_id": medicine_id,
            "batch_number": batch_number,
            "supplier": supplier,
            "received_date": received_date_str,
            "expiry_date": expiry_date_str,
            "received_quantity": received_quantity,
            "facility_name": receiving_facility,
            "message": "Batch registered and initial receipt recorded in stock ledger."
        }), 201

    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": f"Batch number '{batch_number}' already exists for this medicine."}), 400
    except Exception as e:
        conn.close()
        return jsonify({"error": "Failed to create batch: " + str(e)}), 500

@app.route("/api/transactions", methods=["GET"], strict_slashes=False)
def get_transactions():
    """
    Returns transaction audit history.
    Always returns HTTP 200 and [] if no transactions exist (fixes 404 requirement).
    """
    facility = request.args.get("facility")
    medicine_id = request.args.get("medicine_id")
    batch_id = request.args.get("batch_id")
    ttype = request.args.get("type")
    limit = request.args.get("limit", 100)

    try:
        limit = int(limit)
    except ValueError:
        limit = 100

    conn = get_db_connection()
    conditions = []
    params = []

    if facility:
        conditions.append("(st.facility_name = ? OR st.related_facility = ?)")
        params.extend([facility, facility])

    if medicine_id:
        conditions.append("b.medicine_id = ?")
        params.append(medicine_id)

    if batch_id:
        conditions.append("st.batch_id = ?")
        params.append(batch_id)

    if ttype:
        conditions.append("st.transaction_type = ?")
        params.append(ttype.upper())

    where_str = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    query = f"""
        SELECT 
            st.id, st.batch_id, st.transaction_type, st.quantity, st.transaction_date,
            st.facility_name, st.related_facility, st.reason, st.reference_number,
            st.performed_by, st.adjustment_direction, st.created_at,
            b.batch_number, b.expiry_date,
            m.id AS medicine_id, m.medicine_code, m.name AS medicine_name, m.strength, m.unit
        FROM stock_transactions st
        JOIN batches b ON st.batch_id = b.id
        JOIN medicines m ON b.medicine_id = m.id
        {where_str}
        ORDER BY st.transaction_date DESC, st.id DESC
        LIMIT ?
    """

    cursor = conn.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(rows), 200

@app.route("/api/transactions", methods=["POST"], strict_slashes=False)
def create_transaction():
    """
    Create a stock movement transaction with rigorous integrity validation.
    Prevents negative stock, blocks issuing expired batches, supports atomic transfers.
    """
    data = request.get_json() or {}
    batch_id = data.get("batch_id")
    transaction_type = (data.get("transaction_type") or "").strip().upper()
    quantity = data.get("quantity")
    facility_name = (data.get("facility_name") or "").strip()
    related_facility = (data.get("related_facility") or "").strip() or None
    transaction_date = (data.get("transaction_date") or date.today().isoformat()).strip()
    reason = (data.get("reason") or "").strip()
    reference_number = (data.get("reference_number") or "").strip()
    performed_by = (data.get("performed_by") or "Authorized Pharmacist").strip()
    adjustment_direction = (data.get("adjustment_direction") or "IN").strip().upper()

    valid_types = ('RECEIPT', 'ISSUE', 'RETURN', 'DAMAGE', 'EXPIRED', 'TRANSFER_IN', 'TRANSFER_OUT', 'ADJUSTMENT')
    if transaction_type not in valid_types:
        return jsonify({"error": f"Invalid transaction_type. Must be one of: {', '.join(valid_types)}"}), 400

    if not batch_id or not facility_name:
        return jsonify({"error": "batch_id and facility_name are required."}), 400

    t_date = parse_iso_date(transaction_date)
    if not t_date:
        return jsonify({"error": "Invalid transaction_date. Must be a valid ISO date YYYY-MM-DD."}), 400

    try:
        quantity = int(quantity)
        if quantity <= 0:
            return jsonify({"error": "quantity must be a positive integer greater than zero."}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "quantity must be a valid positive integer."}), 400

    if transaction_type == "ADJUSTMENT" and adjustment_direction not in ("IN", "OUT"):
        return jsonify({"error": "ADJUSTMENT requires adjustment_direction 'IN' or 'OUT'."}), 400

    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT b.id, b.batch_number, b.expiry_date, m.name AS medicine_name
            FROM batches b
            JOIN medicines m ON b.medicine_id = m.id
            WHERE b.id = ?
        """, (batch_id,))
        batch = cursor.fetchone()

        if not batch:
            conn.close()
            return jsonify({"error": f"Batch ID {batch_id} not found."}), 400

        today_str = date.today().isoformat()
        is_expired = batch["expiry_date"] < today_str

        # Expiry check: Cannot ISSUE or TRANSFER_OUT expired medicine!
        if is_expired and transaction_type in ('ISSUE', 'TRANSFER_OUT'):
            conn.close()
            return jsonify({
                "error": f"Batch {batch['batch_number']} ({batch['medicine_name']}) expired on {batch['expiry_date']}. Expired stock cannot be issued or transferred. Record as 'EXPIRED' transaction for disposal write-off."
            }), 400

        # Check current available stock at this facility for deductions
        current_stock = get_batch_facility_stock(conn, batch_id, facility_name)

        is_deduction = (
            transaction_type in ('ISSUE', 'DAMAGE', 'EXPIRED', 'TRANSFER_OUT')
            or (transaction_type == 'ADJUSTMENT' and adjustment_direction == 'OUT')
        )

        if is_deduction and quantity > current_stock:
            conn.close()
            return jsonify({
                "error": f"Insufficient stock. Facility '{facility_name}' has only {current_stock} units of Batch {batch['batch_number']}, cannot deduct {quantity} units."
            }), 400

        # Inter-Facility Transfers (Atomic 2-Legged Transaction)
        if transaction_type == "TRANSFER_OUT":
            if not related_facility:
                conn.close()
                return jsonify({"error": "TRANSFER_OUT requires a target related_facility."}), 400
            if facility_name == related_facility:
                conn.close()
                return jsonify({"error": "Origin and destination facilities cannot be the same for a transfer."}), 400

            transfer_ref = reference_number or f"TR-{batch['batch_number']}-{int(datetime.now().timestamp())}"

            with conn:
                conn.execute("""
                    INSERT INTO stock_transactions (
                        batch_id, transaction_type, quantity, transaction_date,
                        facility_name, related_facility, reason, reference_number, performed_by
                    ) VALUES (?, 'TRANSFER_OUT', ?, ?, ?, ?, ?, ?, ?)
                """, (batch_id, quantity, transaction_date, facility_name, related_facility, reason or "Inter-facility transfer dispatch", transfer_ref, performed_by))

                conn.execute("""
                    INSERT INTO stock_transactions (
                        batch_id, transaction_type, quantity, transaction_date,
                        facility_name, related_facility, reason, reference_number, performed_by
                    ) VALUES (?, 'TRANSFER_IN', ?, ?, ?, ?, ?, ?, ?)
                """, (batch_id, quantity, transaction_date, related_facility, facility_name, reason or "Inter-facility transfer arrival", transfer_ref, performed_by))

            conn.close()
            return jsonify({
                "message": f"Successfully transferred {quantity} units from {facility_name} to {related_facility}.",
                "reference_number": transfer_ref,
                "batch_id": batch_id,
                "quantity": quantity
            }), 201

        # Standard Single-Legged Transaction
        ref_num = reference_number or f"{transaction_type[:3]}-{int(datetime.now().timestamp())}"
        direction_val = adjustment_direction if transaction_type == "ADJUSTMENT" else None

        with conn:
            cursor = conn.execute("""
                INSERT INTO stock_transactions (
                    batch_id, transaction_type, quantity, transaction_date,
                    facility_name, related_facility, reason, reference_number, performed_by, adjustment_direction
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (batch_id, transaction_type, quantity, transaction_date, facility_name, related_facility, reason, ref_num, performed_by, direction_val))
            trans_id = cursor.lastrowid

        new_balance = get_batch_facility_stock(conn, batch_id, facility_name)
        conn.close()

        return jsonify({
            "id": trans_id,
            "batch_id": batch_id,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "transaction_date": transaction_date,
            "facility_name": facility_name,
            "new_facility_balance": new_balance,
            "reference_number": ref_num,
            "message": f"{transaction_type} transaction recorded successfully."
        }), 201

    except Exception as e:
        conn.close()
        return jsonify({"error": "Transaction failed: " + str(e)}), 500

@app.route("/api/stock", methods=["GET"], strict_slashes=False)
def get_stock():
    facility = request.args.get("facility")
    conn = get_db_connection()
    stock_rows = fetch_stock_data(conn, facility)
    conn.close()
    return jsonify(stock_rows), 200

@app.route("/api/alerts", methods=["GET"], strict_slashes=False)
def get_alerts():
    facility = request.args.get("facility")
    conn = get_db_connection()
    alerts = fetch_alerts_data(conn, facility)
    conn.close()
    return jsonify(alerts), 200

@app.route("/api/dashboard", methods=["GET"], strict_slashes=False)
def get_dashboard():
    facility = request.args.get("facility")
    conn = get_db_connection()

    total_medicines = conn.execute("SELECT COUNT(*) FROM medicines").fetchone()[0]
    medicines = fetch_medicines_data(conn, facility)
    total_usable_units = sum(m.get("usable_stock", 0) for m in medicines)
    stockout_count = sum(1 for m in medicines if m.get("is_stockout_risk", False))

    alerts_data = fetch_alerts_data(conn, facility)

    stock_items = fetch_stock_data(conn, facility)
    active_batch_ids = {s["batch_id"] for s in stock_items}
    total_active_batches = len(active_batch_ids)

    # Recent transactions
    facility_filter = "WHERE (st.facility_name = ? OR st.related_facility = ?)" if facility else ""
    params = (facility, facility, 10) if facility else (10,)
    cursor = conn.execute(f"""
        SELECT 
            st.id, st.batch_id, st.transaction_type, st.quantity, st.transaction_date,
            st.facility_name, st.related_facility, st.reason, st.reference_number,
            st.performed_by,
            b.batch_number,
            m.name AS medicine_name, m.unit
        FROM stock_transactions st
        JOIN batches b ON st.batch_id = b.id
        JOIN medicines m ON b.medicine_id = m.id
        {facility_filter}
        ORDER BY st.transaction_date DESC, st.id DESC
        LIMIT ?
    """, params)
    recent_transactions = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return jsonify({
        "timestamp": datetime.now().isoformat(),
        "facility_filter": facility or "All Facilities",
        "kpis": {
            "total_medicines": total_medicines,
            "total_active_batches": total_active_batches,
            "total_usable_stock_units": total_usable_units,
            "medicines_at_stockout_risk": stockout_count,
            "expired_batches_count": alerts_data["summary"]["expired_batches"],
            "near_expiry_30_days_count": alerts_data["summary"]["expiring_within_30_days"],
            "near_expiry_60_days_count": alerts_data["summary"]["expiring_within_60_days"],
            "early_warnings_count": alerts_data["summary"]["forecast_warnings"]
        },
        "alerts_summary": alerts_data["summary"],
        "recent_movements": recent_transactions,
        "critical_alerts": alerts_data["stockout_alerts"] + alerts_data["forecast_warnings"]
    }), 200

@app.route("/api/reports/stock", methods=["GET"], strict_slashes=False)
def get_stock_report():
    facility = request.args.get("facility")
    conn = get_db_connection()

    med_list = fetch_medicines_data(conn, facility)
    stock_list = fetch_stock_data(conn, facility)

    report = []
    for m in med_list:
        batches_for_med = [s for s in stock_list if s["medicine_id"] == m["id"]]
        forecast = m.get("forecast", {})
        req = get_restock_request_status(conn, m["id"], facility, m["usable_stock"], m["min_stock_level"])
        report.append({
            "medicine_code": m["medicine_code"],
            "name": m["name"],
            "strength": m["strength"],
            "category": m["category"],
            "unit": m["unit"],
            "min_stock_level": m["min_stock_level"] if m["min_stock_level"] > 0 else "Unconfigured",
            "total_stock": m["total_stock"],
            "usable_stock": m["usable_stock"],
            "status": "Request Completed" if req["request_status"] == "COMPLETED" else m["threshold_status"],
            "request_status": req["request_status"],
            "request_message": req["request_message"],
            "active_batch_count": len(batches_for_med),
            "daily_burn_rate": forecast.get("daily_burn_rate", "N/A"),
            "estimated_days_remaining": forecast.get("estimated_days_to_stockout", "N/A"),
            "consumption_status": forecast.get("consumption_status")
        })

    conn.close()
    return jsonify({
        "generated_at": datetime.now().isoformat(),
        "facility": facility or "All Facilities",
        "total_items": len(report),
        "report_data": report
    }), 200

@app.route("/api/settings/threshold", methods=["POST"], strict_slashes=False)
def update_threshold():
    data = request.get_json() or {}
    medicine_id = data.get("medicine_id")
    min_stock_level = data.get("min_stock_level")

    if not medicine_id or min_stock_level is None:
        return jsonify({"error": "medicine_id and min_stock_level are required."}), 400

    try:
        min_stock_level = int(min_stock_level)
        if min_stock_level < 0:
            return jsonify({"error": "min_stock_level cannot be negative."}), 400
    except ValueError:
        return jsonify({"error": "min_stock_level must be an integer."}), 400

    conn = get_db_connection()
    cursor = conn.execute("UPDATE medicines SET min_stock_level = ? WHERE id = ?", (min_stock_level, medicine_id))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()

    if rows_affected == 0:
        return jsonify({"error": f"Medicine ID {medicine_id} not found."}), 404

    return jsonify({
        "medicine_id": medicine_id,
        "min_stock_level": min_stock_level,
        "message": "Minimum threshold updated successfully."
    }), 200

@app.route("/api/seed", methods=["POST"], strict_slashes=False)
def reset_seed_data():
    try:
        init_db()
        seed_sample_data()
        return jsonify({"message": "Sample demonstration data reloaded successfully."}), 200
    except Exception as e:
        return jsonify({"error": "Failed to seed data: " + str(e)}), 500

# --- Error Handlers ---

@app.errorhandler(404)
def handle_404(e):
    return jsonify({"error": "Route not found.", "status_code": 404}), 404

@app.errorhandler(405)
def handle_405(e):
    return jsonify({"error": "Method not allowed for this route.", "status_code": 405}), 405

@app.errorhandler(500)
def handle_500(e):
    return jsonify({"error": "Internal server error.", "status_code": 500}), 500

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
