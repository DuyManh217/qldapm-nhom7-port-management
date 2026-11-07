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

    def test_16_add_vessel_success(self):
        payload = {
            "imo": "9988776",
            "name": "VN STAR 01",
            "carrier": "VIMC Lines",
            "loa": 215.0,
            "beam": 32.2,
            "max_draft": 11.5,
            "dwt": 32000,
            "teu": 2200
        }
        response = self.client.post("/api/v1/vessels", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["code"], "SUCCESS")
        self.assertEqual(data["data"]["name"], "VN STAR 01")

        # Verify it now appears in GET /api/v1/vessels
        v_res = self.client.get("/api/v1/vessels")
        v_data = v_res.get_json()
        imos = [v["imo"] for v in v_data]
        self.assertIn("9988776", imos)

    def test_17_add_vessel_duplicate_imo(self):
        # 9321483 (EVER GIVEN) already exists
        payload = {
            "imo": "9321483",
            "name": "DUPLICATE VESSEL",
            "loa": 300.0,
            "beam": 40.0,
            "max_draft": 14.0
        }
        response = self.client.post("/api/v1/vessels", json=payload)
        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertEqual(data["code"], "ERR_VESSEL_EXISTS")

    def test_18_add_vessel_invalid_specs(self):
        # Invalid IMO length (less than 7 digits)
        payload = {
            "imo": "1234",
            "name": "INVALID IMO",
            "loa": 200.0
        }
        response = self.client.post("/api/v1/vessels", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["code"], "ERR_INVALID_IMO")

        # Invalid LOA <= 0
        payload2 = {
            "imo": "9999991",
            "name": "INVALID LOA",
            "loa": -10.0
        }
        response2 = self.client.post("/api/v1/vessels", json=payload2)
        self.assertEqual(response2.status_code, 400)
        data2 = response2.get_json()
        self.assertEqual(data2["code"], "ERR_INVALID_DIMENSIONS")

    def test_19_delete_port_call(self):
        # Delete an existing port call
        res = self.client.delete("/api/v1/port-calls/CALL-2026-001")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["code"], "SUCCESS")

        # Deleting a non-existent port call returns 404
        res2 = self.client.delete("/api/v1/port-calls/NON_EXISTENT_CALL")
        self.assertEqual(res2.status_code, 404)

    def test_20_delete_vessel(self):
        # Add a temporary vessel
        temp_payload = {
            "imo": "8877665",
            "name": "TEMP VESSEL FOR DELETE",
            "loa": 180.0,
            "beam": 25.0,
            "max_draft": 10.0
        }
        self.client.post("/api/v1/vessels", json=temp_payload)

        # Deleting the vessel should succeed
        res = self.client.delete("/api/v1/vessels/8877665")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["code"], "SUCCESS")

        # Deleting it again should return 404
        res2 = self.client.delete("/api/v1/vessels/8877665")
        self.assertEqual(res2.status_code, 404)

        # Deleting a vessel currently docked (e.g. 9234567 TAN CANG GLORY at CALL-2026-002) returns 409
        res3 = self.client.delete("/api/v1/vessels/9234567")
        self.assertEqual(res3.status_code, 409)
        data3 = res3.get_json()
        self.assertEqual(data3["code"], "ERR_VESSEL_CURRENTLY_DOCKED")

    def test_21_manual_atomic_move_success(self):
        # Move container EMCU8921470 from A-01-01-1 to A-01-02-1
        payload = {
            "container_no": "EMCU8921470",
            "target_slot_id": "A-01-02-1",
            "operator": "RTG-01"
        }
        res = self.client.post("/api/v1/yard/atomic-move", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["code"], "SUCCESS")
        self.assertEqual(data["new_slot_id"], "A-01-02-1")

    def test_22_manual_atomic_move_errors(self):
        # Non-existent container -> 404
        res1 = self.client.post("/api/v1/yard/atomic-move", json={"container_no": "FAKE9999999", "target_slot_id": "A-01-02-1"})
        self.assertEqual(res1.status_code, 404)

        # Non-existent slot -> 404
        res2 = self.client.post("/api/v1/yard/atomic-move", json={"container_no": "EMCU8921470", "target_slot_id": "Z-99-99-9"})
        self.assertEqual(res2.status_code, 404)

        # Stacking violation: place reefer on non-reefer slot -> 422
        res3 = self.client.post("/api/v1/yard/atomic-move", json={"container_no": "TCKU9012384", "target_slot_id": "A-02-01-1"})
        self.assertEqual(res3.status_code, 422)

if __name__ == "__main__":
    unittest.main()
