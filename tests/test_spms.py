import unittest
import os
import sys
import json

# Add backend directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app
from vessel_berth_backend import check_berth_collision
from yard_container_backend import init_yard_data, evaluate_stacking_rules

class SPMSTestSuite(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        init_yard_data()

    def test_01_index_route(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_02_vessel_page(self):
        response = self.client.get("/vessel")
        self.assertEqual(response.status_code, 200)

    def test_03_yard_page(self):
        response = self.client.get("/yard")
        self.assertEqual(response.status_code, 200)

    def test_04_get_vessels(self):
        response = self.client.get("/api/v1/vessels")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_05_get_berths(self):
        response = self.client.get("/api/v1/berths")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 6)

    def test_06_get_port_calls(self):
        response = self.client.get("/api/v1/port-calls")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)

    def test_07_port_call_invalid_imo(self):
        payload = {"imo": "12345"}  # invalid length
        response = self.client.post("/api/v1/port-calls", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["code"], "ERR_INVALID_IMO")

    def test_08_port_call_exceeds_draft(self):
        payload = {
            "imo": "9321483",
            "berth_id": "B6",
            "draft": 15.8  # B6 depth is 14.5m
        }
        response = self.client.post("/api/v1/port-calls", json=payload)
        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data["code"], "ERR_DRAFT_EXCEEDS")

    def test_09_port_call_collision_detected(self):
        # CALL-2026-001 is at B1 (50m-220m) from 2026-11-07 06:00 to 18:00
        payload = {
            "imo": "9110023",
            "berth_id": "B1",
            "start_meter": 60,
            "start_time": "2026-11-07 07:00",
            "duration_hours": 4
        }
        response = self.client.post("/api/v1/port-calls", json=payload)
        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertEqual(data["code"], "ERR_BERTH_COLLISION_DETECTED")

    def test_10_ai_optimize_berth(self):
        response = self.client.post("/api/v1/ai/optimize-berth")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["code"], "SUCCESS")
        self.assertGreater(data["scheduled_vessels_count"], 0)

    def test_11_yard_slots(self):
        response = self.client.get("/api/v1/yard/slots?block=A")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_12_yard_containers(self):
        response = self.client.get("/api/v1/yard/containers")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_13_yard_reefer_stacking_rule(self):
        # Reefer container must be placed on reefer-plug slot
        reefer_cont = {
            "container_no": "TESTREEFER01",
            "is_reefer": True,
            "weight_kg": 20000,
            "is_hazardous": False
        }
        # A-01-02-1 has no reefer plug
        valid, msg = evaluate_stacking_rules(reefer_cont, "A-01-02-1")
        self.assertFalse(valid)
        self.assertIn("không có ổ cắm điện 3 pha", msg)

    def test_14_yard_floating_container_rule(self):
        # Tier 3 without Tier 2 is invalid
        cont = {
            "container_no": "TESTNORM01",
            "is_reefer": False,
            "weight_kg": 15000,
            "is_hazardous": False
        }
        valid, msg = evaluate_stacking_rules(cont, "A-01-02-3")
        self.assertFalse(valid)
        self.assertIn("chưa có container đỡ", msg)

    def test_15_integration_tests_endpoint(self):
        response = self.client.post("/api/v1/tests/run-all")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["total"], 15)
        self.assertEqual(data["passed"], 15)

if __name__ == "__main__":
    unittest.main()
