"""Small, dependency-free WSGI API for an operations management prototype."""
import json
import math
import os
import re
import sqlite3
from datetime import datetime, timezone
from wsgiref.simple_server import make_server


ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_ROOT = os.path.join(ROOT, "web")
MAX_BODY_BYTES = 1024 * 1024
ORDER_STATUSES = {"created", "planned", "picked_up", "in_transit", "delivered", "failed"}
TRANSITIONS = {
    "created": {"planned", "picked_up", "failed"},
    "planned": {"picked_up", "failed"},
    "picked_up": {"in_transit", "failed"},
    "in_transit": {"delivered", "failed"},
    "delivered": set(),
    "failed": set(),
}
PRIORITIES = {"standard", "urgent"}


class APIError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 3000")
    return conn


def initialize(db_path):
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent)
    with connect(db_path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT NOT NULL UNIQUE,
            recipient TEXT NOT NULL,
            pickup TEXT NOT NULL,
            dropoff TEXT NOT NULL,
            package_weight_kg REAL NOT NULL CHECK (package_weight_kg > 0 AND package_weight_kg <= 25),
            priority TEXT NOT NULL CHECK (priority IN ('standard', 'urgent')),
            status TEXT NOT NULL DEFAULT 'created',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_orders_status_created ON orders(status, created_at DESC);
        CREATE TABLE IF NOT EXISTS parcel_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            occurred_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_order_time ON parcel_events(order_id, occurred_at, id);
        CREATE TABLE IF NOT EXISTS flights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flight_code TEXT NOT NULL UNIQUE,
            drone_id TEXT NOT NULL,
            pilot TEXT NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            departure_at TEXT NOT NULL,
            capacity_kg REAL NOT NULL CHECK (capacity_kg > 0),
            status TEXT NOT NULL DEFAULT 'planned',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_flights_departure ON flights(departure_at);
        CREATE TABLE IF NOT EXISTS flight_orders (
            flight_id INTEGER NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
            order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
            PRIMARY KEY (flight_id, order_id)
        );
        """)


def row_dict(row):
    return dict(row) if row is not None else None


def required_string(data, key, max_length=180):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise APIError(400, "%s is required" % key)
    value = value.strip()
    if len(value) > max_length:
        raise APIError(400, "%s must be at most %s characters" % (key, max_length))
    return value


def positive_number(data, key, maximum=None):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise APIError(400, "%s must be a number" % key)
    if value <= 0 or (maximum is not None and value > maximum):
        limit = " and at most %s" % maximum if maximum is not None else ""
        raise APIError(400, "%s must be greater than zero%s" % (key, limit))
    return float(value)


def parse_json_body(environ):
    raw_length = environ.get("CONTENT_LENGTH") or "0"
    try:
        length = int(raw_length)
    except ValueError:
        raise APIError(400, "Invalid Content-Length")
    if length < 0 or length > MAX_BODY_BYTES:
        raise APIError(413, "Request body is too large")
    raw = environ["wsgi.input"].read(length)
    if not raw:
        return {}
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise APIError(400, "Request body must be valid JSON")
    if not isinstance(result, dict):
        raise APIError(400, "Request body must be a JSON object")
    return result


def order_payload(db, order_id, include_events=False):
    order = row_dict(db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())
    if order is None:
        raise APIError(404, "Order not found")
    flight = db.execute("""SELECT f.id, f.flight_code, f.drone_id, f.departure_at
        FROM flights f JOIN flight_orders fo ON fo.flight_id = f.id
        WHERE fo.order_id = ?""", (order_id,)).fetchone()
    order["flight"] = row_dict(flight)
    if include_events:
        order["events"] = [row_dict(row) for row in db.execute(
            "SELECT id, status, location, note, occurred_at FROM parcel_events WHERE order_id = ? ORDER BY id",
            (order_id,))]
    return order


def create_order(db, data):
    reference = required_string(data, "reference", 40)
    recipient = required_string(data, "recipient")
    pickup = required_string(data, "pickup")
    dropoff = required_string(data, "dropoff")
    weight = positive_number(data, "package_weight_kg", 25)
    priority = data.get("priority", "standard")
    if not isinstance(priority, str) or priority not in PRIORITIES:
        raise APIError(400, "priority must be standard or urgent")
    timestamp = now_iso()
    try:
        cursor = db.execute("""INSERT INTO orders
            (reference, recipient, pickup, dropoff, package_weight_kg, priority, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'created', ?, ?)""",
            (reference, recipient, pickup, dropoff, weight, priority, timestamp, timestamp))
    except sqlite3.IntegrityError:
        raise APIError(409, "Order reference already exists")
    order_id = cursor.lastrowid
    db.execute("INSERT INTO parcel_events (order_id, status, location, note, occurred_at) VALUES (?, ?, ?, ?, ?)",
               (order_id, "created", pickup, "Order created", timestamp))
    return order_payload(db, order_id)


def create_flight(db, data):
    fields = {key: required_string(data, key, 100) for key in
              ("flight_code", "drone_id", "pilot", "origin", "destination", "departure_at")}
    try:
        datetime.fromisoformat(fields["departure_at"].replace("Z", "+00:00"))
    except ValueError:
        raise APIError(400, "departure_at must be an ISO 8601 date and time")
    capacity = positive_number(data, "capacity_kg")
    try:
        cursor = db.execute("""INSERT INTO flights
            (flight_code, drone_id, pilot, origin, destination, departure_at, capacity_kg, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'planned', ?)""",
            (fields["flight_code"], fields["drone_id"], fields["pilot"], fields["origin"],
             fields["destination"], fields["departure_at"], capacity, now_iso()))
    except sqlite3.IntegrityError:
        raise APIError(409, "Flight code already exists")
    return flight_payload(db, cursor.lastrowid)


def flight_payload(db, flight_id):
    flight = row_dict(db.execute("SELECT * FROM flights WHERE id = ?", (flight_id,)).fetchone())
    if flight is None:
        raise APIError(404, "Flight not found")
    flight["assigned_order_ids"] = [row[0] for row in db.execute(
        "SELECT order_id FROM flight_orders WHERE flight_id = ? ORDER BY order_id", (flight_id,))]
    flight["assigned_count"] = len(flight["assigned_order_ids"])
    flight["assigned_weight_kg"] = db.execute(
        "SELECT COALESCE(SUM(o.package_weight_kg), 0) FROM orders o JOIN flight_orders fo ON fo.order_id = o.id WHERE fo.flight_id = ?",
        (flight_id,)).fetchone()[0]
    return flight


def list_order_payloads(db):
    """Fetch the list view in one query instead of two lookups per order."""
    rows = db.execute("""SELECT o.*, f.id AS flight_id, f.flight_code, f.drone_id, f.departure_at
        FROM orders o
        LEFT JOIN flight_orders fo ON fo.order_id = o.id
        LEFT JOIN flights f ON f.id = fo.flight_id
        ORDER BY o.created_at DESC, o.id DESC""").fetchall()
    items = []
    for row in rows:
        order = {key: row[key] for key in row.keys() if key not in
                 ("flight_id", "flight_code", "drone_id", "departure_at")}
        order["flight"] = ({"id": row["flight_id"], "flight_code": row["flight_code"],
                            "drone_id": row["drone_id"], "departure_at": row["departure_at"]}
                           if row["flight_id"] is not None else None)
        items.append(order)
    return items


def list_flight_payloads(db):
    """Aggregate payload totals and assigned IDs in one pass over flight assignments."""
    rows = db.execute("""SELECT f.*, COUNT(fo.order_id) AS assigned_count,
        COALESCE(SUM(o.package_weight_kg), 0) AS assigned_weight_kg,
        GROUP_CONCAT(fo.order_id) AS order_ids
        FROM flights f
        LEFT JOIN flight_orders fo ON fo.flight_id = f.id
        LEFT JOIN orders o ON o.id = fo.order_id
        GROUP BY f.id ORDER BY f.departure_at, f.id""").fetchall()
    items = []
    for row in rows:
        flight = row_dict(row)
        ids = flight.pop("order_ids")
        flight["assigned_order_ids"] = [int(value) for value in ids.split(",")] if ids else []
        items.append(flight)
    return items


def create_app(db_path=None):
    db_path = db_path or os.path.join(ROOT, "data", "oms.sqlite3")
    initialize(db_path)

    def application(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        try:
            if path.startswith("/api/"):
                with connect(db_path) as db:
                    result, status = route_api(db, method, path, environ)
                body = json.dumps(result, separators=(",", ":")).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            else:
                result, status, content_type = serve_static(method, path)
                body = result
        except APIError as exc:
            status = exc.status
            body = json.dumps({"error": exc.message}).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        except Exception:
            status = 500
            body = json.dumps({"error": "Internal server error"}).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        labels = {200: "OK", 201: "Created", 400: "Bad Request", 404: "Not Found",
                  405: "Method Not Allowed", 409: "Conflict", 413: "Payload Too Large", 500: "Internal Server Error"}
        start_response("%d %s" % (status, labels.get(status, "Error")), [
            ("Content-Type", content_type), ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")])
        return [body]

    return application


def route_api(db, method, path, environ):
    body = None
    if method in ("POST", "PATCH"):
        body = parse_json_body(environ)
    if path == "/api/health" and method == "GET":
        return {"status": "ok"}, 200
    if path == "/api/orders" and method == "GET":
        return {"items": list_order_payloads(db)}, 200
    if path == "/api/orders" and method == "POST":
        return create_order(db, body), 201
    match = re.fullmatch(r"/api/orders/(\d+)", path)
    if match and method == "GET":
        return order_payload(db, int(match.group(1)), True), 200
    match = re.fullmatch(r"/api/orders/(\d+)/status", path)
    if match and method == "PATCH":
        order_id = int(match.group(1))
        current = db.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if current is None:
            raise APIError(404, "Order not found")
        next_status = required_string(body, "status", 30)
        if next_status not in ORDER_STATUSES or next_status not in TRANSITIONS[current[0]]:
            raise APIError(409, "Invalid order status transition from %s to %s" % (current[0], next_status))
        timestamp = now_iso()
        db.execute("UPDATE orders SET status = ?, updated_at = ? WHERE id = ?", (next_status, timestamp, order_id))
        db.execute("INSERT INTO parcel_events (order_id, status, location, note, occurred_at) VALUES (?, ?, ?, ?, ?)",
                   (order_id, next_status, body.get("location", ""), body.get("note", "Status updated"), timestamp))
        return order_payload(db, order_id, True), 200
    match = re.fullmatch(r"/api/orders/(\d+)/events", path)
    if match and method == "POST":
        order_id = int(match.group(1))
        current = db.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if current is None:
            raise APIError(404, "Order not found")
        next_status = required_string(body, "status", 30)
        if next_status not in ORDER_STATUSES or next_status not in TRANSITIONS[current[0]]:
            raise APIError(409, "Invalid order status transition from %s to %s" % (current[0], next_status))
        location = required_string(body, "location", 180)
        note = body.get("note", "")
        if not isinstance(note, str) or len(note) > 500:
            raise APIError(400, "note must be a string of at most 500 characters")
        timestamp = now_iso()
        db.execute("UPDATE orders SET status = ?, updated_at = ? WHERE id = ?", (next_status, timestamp, order_id))
        cursor = db.execute("INSERT INTO parcel_events (order_id, status, location, note, occurred_at) VALUES (?, ?, ?, ?, ?)",
                            (order_id, next_status, location, note, timestamp))
        event = row_dict(db.execute("SELECT id, status, location, note, occurred_at FROM parcel_events WHERE id = ?",
                                    (cursor.lastrowid,)).fetchone())
        return event, 201
    if path == "/api/flights" and method == "GET":
        return {"items": list_flight_payloads(db)}, 200
    if path == "/api/flights" and method == "POST":
        return create_flight(db, body), 201
    match = re.fullmatch(r"/api/flights/(\d+)/assign", path)
    if match and method == "POST":
        flight_id = int(match.group(1))
        flight = db.execute("SELECT * FROM flights WHERE id = ?", (flight_id,)).fetchone()
        if flight is None:
            raise APIError(404, "Flight not found")
        order_id = body.get("order_id")
        if isinstance(order_id, bool) or not isinstance(order_id, int):
            raise APIError(400, "order_id must be an integer")
        order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order is None:
            raise APIError(404, "Order not found")
        if order["status"] not in ("created", "planned"):
            raise APIError(409, "Only created or planned orders can be assigned")
        if order["pickup"] != flight["origin"] or order["dropoff"] != flight["destination"]:
            raise APIError(409, "Order route does not match flight route")
        existing = db.execute("SELECT flight_id FROM flight_orders WHERE order_id = ?", (order_id,)).fetchone()
        if existing:
            raise APIError(409, "Order is already assigned to a flight")
        total = db.execute("SELECT COALESCE(SUM(o.package_weight_kg), 0) FROM orders o JOIN flight_orders fo ON fo.order_id = o.id WHERE fo.flight_id = ?",
                           (flight_id,)).fetchone()[0]
        if total + order["package_weight_kg"] > flight["capacity_kg"]:
            raise APIError(409, "Flight payload capacity would be exceeded")
        db.execute("INSERT INTO flight_orders (flight_id, order_id) VALUES (?, ?)", (flight_id, order_id))
        timestamp = now_iso()
        db.execute("UPDATE orders SET status = 'planned', updated_at = ? WHERE id = ?", (timestamp, order_id))
        db.execute("INSERT INTO parcel_events (order_id, status, location, note, occurred_at) VALUES (?, 'planned', ?, ?, ?)",
                   (order_id, flight["origin"], "Assigned to %s" % flight["flight_code"], timestamp))
        return flight_payload(db, flight_id), 200
    if path.startswith("/api/"):
        raise APIError(404, "API route not found")
    raise APIError(405, "Method not allowed")


def serve_static(method, path):
    if method not in ("GET", "HEAD"):
        return b"Method not allowed", 405, "text/plain; charset=utf-8"
    path = "/index.html" if path in ("", "/") else path
    normalized = os.path.normpath(path.lstrip("/"))
    target = os.path.abspath(os.path.join(STATIC_ROOT, normalized))
    if not target.startswith(os.path.abspath(STATIC_ROOT) + os.sep) and target != os.path.abspath(STATIC_ROOT):
        return b"Not found", 404, "text/plain; charset=utf-8"
    if not os.path.isfile(target):
        return b"Not found", 404, "text/plain; charset=utf-8"
    types = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
    extension = os.path.splitext(target)[1]
    with open(target, "rb") as source:
        content = source.read()
    return content if method == "GET" else b"", 200, types.get(extension, "application/octet-stream")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    application = create_app()
    print("Airbound OMS running at http://127.0.0.1:%d" % port)
    make_server("0.0.0.0", port, application).serve_forever()
