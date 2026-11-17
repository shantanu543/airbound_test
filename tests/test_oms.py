import io
import json
import os
import tempfile
import unittest

from oms import create_app


class OMSApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp.name, "oms.sqlite3")
        self.app = create_app(self.db_path)

    def tearDown(self):
        self.temp.cleanup()

    def request(self, method, path, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": "",
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/json",
            "wsgi.input": io.BytesIO(body),
        }
        captured = {}

        def start_response(status, headers):
            captured["status"] = int(status.split()[0])
            captured["headers"] = dict(headers)

        response = b"".join(self.app(environ, start_response))
        return captured["status"], json.loads(response.decode("utf-8")) if response else None

    def create_order(self, reference="AB-1001"):
        return self.request("POST", "/api/orders", {
            "reference": reference,
            "recipient": "Mira Shah",
            "pickup": "Airbound Hub",
            "dropoff": "North Clinic",
            "package_weight_kg": 1.4,
            "priority": "urgent",
        })

    def test_health_and_operator_page_are_served(self):
        status, health = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/", "QUERY_STRING": "",
                   "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO()}
        headers = {}
        page = b"".join(self.app(environ, lambda value, items: headers.update(status=value)))
        self.assertIn(b"Operations overview", page)
        self.assertEqual(headers["status"], "200 OK")

    def test_create_and_list_orders(self):
        status, order = self.create_order()
        self.assertEqual(status, 201)
        self.assertEqual(order["status"], "created")
        self.assertEqual(order["reference"], "AB-1001")
        status, listing = self.request("GET", "/api/orders")
        self.assertEqual(status, 200)
        self.assertEqual(len(listing["items"]), 1)

    def test_order_creation_validates_required_fields_and_weight(self):
        status, error = self.request("POST", "/api/orders", {"reference": "AB-1"})
        self.assertEqual(status, 400)
        self.assertIn("error", error)
        status, error = self.request("POST", "/api/orders", {
            "reference": "AB-2", "recipient": "A", "pickup": "B", "dropoff": "C",
            "package_weight_kg": 60, "priority": "standard",
        })
        self.assertEqual(status, 400)

    def test_status_transition_adds_tracking_event(self):
        _, order = self.create_order()
        status, updated = self.request("PATCH", "/api/orders/%s/status" % order["id"], {"status": "picked_up"})
        self.assertEqual(status, 200)
        self.assertEqual(updated["status"], "picked_up")
        status, detail = self.request("GET", "/api/orders/%s" % order["id"])
        self.assertEqual(status, 200)
        self.assertEqual(detail["events"][-1]["status"], "picked_up")

    def test_rejects_invalid_order_transition(self):
        _, order = self.create_order()
        status, _ = self.request("PATCH", "/api/orders/%s/status" % order["id"], {"status": "delivered"})
        self.assertEqual(status, 409)

    def test_create_flight_and_assign_order(self):
        _, order = self.create_order()
        status, flight = self.request("POST", "/api/flights", {
            "flight_code": "FLT-201", "drone_id": "DR-07", "pilot": "A. Rao",
            "origin": "Airbound Hub", "destination": "North Clinic",
            "departure_at": "2026-11-17T10:00:00+05:30", "capacity_kg": 4.0,
        })
        self.assertEqual(status, 201)
        status, result = self.request("POST", "/api/flights/%s/assign" % flight["id"], {"order_id": order["id"]})
        self.assertEqual(status, 200)
        self.assertEqual(result["assigned_order_ids"], [order["id"]])
        _, listing = self.request("GET", "/api/flights")
        self.assertEqual(len(listing["items"]), 1)
        self.assertEqual(listing["items"][0]["assigned_count"], 1)

    def test_flight_capacity_is_enforced(self):
        _, first = self.create_order("AB-1")
        _, second = self.create_order("AB-2")
        _, flight = self.request("POST", "/api/flights", {
            "flight_code": "FLT-202", "drone_id": "DR-08", "pilot": "J. Das",
            "origin": "Airbound Hub", "destination": "North Clinic",
            "departure_at": "2026-11-17T11:00:00+05:30", "capacity_kg": 2.0,
        })
        self.assertEqual(self.request("POST", "/api/flights/%s/assign" % flight["id"], {"order_id": first["id"]})[0], 200)
        self.assertEqual(self.request("POST", "/api/flights/%s/assign" % flight["id"], {"order_id": second["id"]})[0], 409)

    def test_assignment_requires_matching_route(self):
        _, order = self.create_order()
        _, flight = self.request("POST", "/api/flights", {
            "flight_code": "FLT-203", "drone_id": "DR-09", "pilot": "N. Ali",
            "origin": "Other Hub", "destination": "North Clinic",
            "departure_at": "2026-11-17T12:00:00", "capacity_kg": 4.0,
        })
        status, error = self.request("POST", "/api/flights/%s/assign" % flight["id"], {"order_id": order["id"]})
        self.assertEqual(status, 409)
        self.assertIn("route", error["error"])

    def test_flight_requires_valid_departure_datetime(self):
        status, error = self.request("POST", "/api/flights", {
            "flight_code": "FLT-BAD", "drone_id": "DR-10", "pilot": "N. Ali",
            "origin": "North Hub", "destination": "North Clinic",
            "departure_at": "tomorrow morning", "capacity_kg": 4.0,
        })
        self.assertEqual(status, 400)
        self.assertIn("ISO 8601", error["error"])

    def test_tracking_event_endpoint(self):
        _, order = self.create_order()
        self.request("PATCH", "/api/orders/%s/status" % order["id"], {"status": "picked_up"})
        status, event = self.request("POST", "/api/orders/%s/events" % order["id"], {
            "status": "in_transit", "location": "Route waypoint 3", "note": "Telemetry update",
        })
        self.assertEqual(status, 201)
        self.assertEqual(event["location"], "Route waypoint 3")


if __name__ == "__main__":
    unittest.main()
