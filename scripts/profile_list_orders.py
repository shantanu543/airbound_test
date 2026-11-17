"""Reproduce the local order-list microbenchmark (no third-party packages)."""
import argparse
import io
import json
import os
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import oms


def run(order_count, repeats):
    with tempfile.TemporaryDirectory() as directory:
        db_path = os.path.join(directory, "profile.sqlite3")
        app = oms.create_app(db_path)
        stamp = "2026-11-17T00:00:00+00:00"
        rows = [("AB-%05d" % index, "Recipient %d" % index, "North Hub", "Clinic",
                 1.0, "standard", "created", stamp, stamp) for index in range(order_count)]
        with oms.connect(db_path) as db:
            db.executemany("""INSERT INTO orders
                (reference, recipient, pickup, dropoff, package_weight_kg, priority, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows)

        select_count = [0]
        original_connect = oms.connect

        def traced_connect(path):
            connection = original_connect(path)
            connection.set_trace_callback(lambda sql: select_count.__setitem__(
                0, select_count[0] + int(sql.lstrip().upper().startswith("SELECT"))))
            return connection

        oms.connect = traced_connect
        elapsed = []
        try:
            for _ in range(repeats):
                select_count[0] = 0
                environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/api/orders", "QUERY_STRING": "",
                           "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO()}
                started = time.perf_counter()
                response = b"".join(app(environ, lambda status, headers: None))
                elapsed.append((time.perf_counter() - started) * 1000)
                assert len(json.loads(response)["items"]) == order_count
            print("orders=%d repeats=%d median_ms=%.2f SELECTs_per_request=%d" %
                  (order_count, repeats, statistics.median(elapsed), select_count[0]))
        finally:
            oms.connect = original_connect


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--orders", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=5)
    arguments = parser.parse_args()
    run(arguments.orders, arguments.repeats)
