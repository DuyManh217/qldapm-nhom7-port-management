# ==============================================================================
# TỔNG CÔNG TY TÂN CẢNG SÀI GÒN (SNP) - HỆ THỐNG ĐIỀU HÀNH KHAI THÁC CẢNG SPMS
# BỘ KIỂM THỬ TỰ ĐỘNG TOÀN DIỆN (AUTOMATED TEST SUITE)
# NGƯỜI THỰC HIỆN: Đào Văn Sơn - B23DCCN961
# VAI TRÒ: Backend Engineer / Lập trình viên Backend
# MÔ TẢ: Kiểm thử toàn diện API Xác thực JWT RFC 7519, Phân quyền RBAC, CRUD Người dùng/Vai trò,
#        OpenAPI 3.0/Swagger UI, Nhật ký Kiểm toán (Audit Log), Tàu/Cầu bến và Bãi Container
# ==============================================================================

import unittest
import os
import sys
import json
import time

# Add backend directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app
from vessel_berth_backend import check_berth_collision
from yard_container_backend import evaluate_stacking_rules
from db import get_db, seed_data, seed_auth_data

class SPMSTestSuite(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM tbl_yard_alerts;")
        cur.execute("DELETE FROM tbl_containers;")
        cur.execute("DELETE FROM tbl_yard_slots;")
        cur.execute("DELETE FROM tbl_port_calls;")
        cur.execute("DELETE FROM tbl_vessels;")
        cur.execute("DELETE FROM tbl_berths;")
        cur.execute("DELETE FROM spms_users WHERE user_id NOT IN ('USR-001','USR-002','USR-003','USR-004','USR-005','USR-006');")
        conn.commit()
        seed_data(conn)
        cur.execute("SELECT COUNT(*) FROM spms_users;")
        if cur.fetchone()[0] == 0:
            seed_auth_data(conn)
        conn.close()

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

    def test_09b_port_call_invalid_schedule_etd_before_eta(self):
        payload = {
            "imo": "9110023",
            "berth_id": "B1",
            "start_meter": 60,
            "start_time": "2026-11-25 14:00",
            "end_time": "2026-11-24 10:00"
        }
        response = self.client.post("/api/v1/port-calls", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["code"], "ERR_INVALID_SCHEDULE")

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
        self.assertGreaterEqual(data["total"], 25)
        self.assertEqual(data["passed"], data["total"])

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
        # Move container MSCU1294801 (top container at A-01-01-2) to empty ground slot A-01-02-1
        payload = {
            "container_no": "MSCU1294801",
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
        res2 = self.client.post("/api/v1/yard/atomic-move", json={"container_no": "MSCU1294801", "target_slot_id": "Z-99-99-9"})
        self.assertEqual(res2.status_code, 404)

        # Stacking violation: place reefer on non-reefer slot -> 422
        res3 = self.client.post("/api/v1/yard/atomic-move", json={"container_no": "TCKU9012384", "target_slot_id": "A-02-01-1"})
        self.assertEqual(res3.status_code, 422)

        # Stacking violation: attempt to lift bottom container EMCU8921470 while MSCU1294801 is on top -> 422
        res4 = self.client.post("/api/v1/yard/atomic-move", json={"container_no": "EMCU8921470", "target_slot_id": "A-01-03-1"})
        self.assertEqual(res4.status_code, 422)
        self.assertIn("đang bị container ở tầng trên", res4.get_json()["message"])

        # Stacking violation: attempt to self-stack on tier 2 (floating) -> 422
        res5 = self.client.post("/api/v1/yard/atomic-move", json={"container_no": "TCKU9012384", "target_slot_id": "A-01-04-2"})
        self.assertEqual(res5.status_code, 422)
        self.assertIn("vị trí của chính nó", res5.get_json()["message"])

    def test_23_create_container_success(self):
        # Create a new container on an empty ground slot
        payload = {
            "container_no": "NEWU1234567",
            "iso_type": "40HC",
            "weight_kg": 24000,
            "is_reefer": False,
            "slot_id": "A-01-03-1"
        }
        res = self.client.post("/api/v1/yard/containers", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["code"], "SUCCESS")
        self.assertEqual(data["data"]["container_no"], "NEWU1234567")

    def test_24_create_container_validation_errors(self):
        # Invalid format container number
        res1 = self.client.post("/api/v1/yard/containers", json={"container_no": "A"})
        self.assertEqual(res1.status_code, 400)

        # Duplicate container
        res2 = self.client.post("/api/v1/yard/containers", json={"container_no": "EMCU8921470"})
        self.assertEqual(res2.status_code, 409)

        # Stacking violation: reefer on non-reefer slot
        res3 = self.client.post("/api/v1/yard/containers", json={
            "container_no": "REEF1111111",
            "iso_type": "40RH",
            "weight_kg": 20000,
            "is_reefer": True,
            "slot_id": "A-01-02-1" # Not a reefer slot
        })
        self.assertEqual(res3.status_code, 422)

    def test_25_update_container(self):
        payload = {
            "iso_type": "40GP",
            "weight_kg": 25000
        }
        res = self.client.put("/api/v1/yard/containers/EMCU8921470", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["data"]["iso_type"], "40GP")
        self.assertEqual(data["data"]["weight_kg"], 25000)

    def test_26_delete_container(self):
        # Blocked: attempt to delete bottom container EMCU8921470 while MSCU1294801 is on top
        res1 = self.client.delete("/api/v1/yard/containers/EMCU8921470")
        self.assertEqual(res1.status_code, 422)
        self.assertIn("đang bị container", res1.get_json()["message"])

        # Success: delete top container MSCU1294801
        res2 = self.client.delete("/api/v1/yard/containers/MSCU1294801")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()["code"], "SUCCESS")

        # Now bottom container can be deleted
        res3 = self.client.delete("/api/v1/yard/containers/EMCU8921470")
        self.assertEqual(res3.status_code, 200)

    def test_27_update_vessel(self):
        payload = {
            "name": "EVER GIVEN RENAMED",
            "loa": 400.0,
            "max_draft": 16.5,
            "carrier": "Evergreen Marine Corp"
        }
        res = self.client.put("/api/v1/vessels/9321483", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["code"], "SUCCESS")
        self.assertEqual(data["data"]["name"], "EVER GIVEN RENAMED")
        self.assertEqual(data["data"]["max_draft"], 16.5)

        # Updating non-existent vessel -> 404
        res2 = self.client.put("/api/v1/vessels/9999999", json={"name": "FAKE"})
        self.assertEqual(res2.status_code, 404)

    def test_28_vessel_kpi_endpoint(self):
        res = self.client.get("/api/v1/vessel/kpi")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["total_berth_meters"], 2040.0)
        self.assertEqual(data["total_berths"], 6)
        self.assertGreaterEqual(data["active_port_calls"], 0)
        self.assertIn("utilization_percent", data)
        self.assertGreater(data["moves_rate_per_hour"], 0)

    def test_29_yard_kpi_endpoint(self):
        res = self.client.get("/api/v1/yard/kpi")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertGreater(data["total_slots"], 0)
        self.assertGreaterEqual(data["occupied_slots"], 0)
        self.assertIn("utilization_percent", data)
        self.assertEqual(data["rtg_cranes_count"], 174)
        self.assertIn("distributed_lock_status", data)

    def test_30_simulate_race_condition(self):
        res = self.client.post("/api/v1/yard/simulate-race-condition")
        self.assertEqual(res.status_code, 409)
        data = res.get_json()
        self.assertEqual(data["code"], "ERR_SLOT_LOCK_CONFLICT")
        self.assertIn("Xung đột tranh chấp", data["message"])

    # ==========================================================================
    # CÁC TEST CASES XÁC THỰC JWT, PHÂN QUYỀN RBAC, CRUD USER/ROLE & OPENAPI/SWAGGER
    # ==========================================================================

    # --------------------------------------------------------------------------
    # Function: test_31_auth_login_success
    # Mục đích sử dụng: Kiểm tra đăng nhập thành công với tài khoản quản trị (admin),
    #                   xác minh trả về HTTP 200, access_token, refresh_token và ROLE_ADMIN.
    # --------------------------------------------------------------------------
    def test_31_auth_login_success(self):
        payload = {"username": "admin", "password": "Admin@123"}
        res = self.client.post("/api/v1/auth/login", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertIn("access_token", data["data"])
        self.assertIn("refresh_token", data["data"])
        self.assertEqual(data["data"]["user"]["username"], "admin")
        self.assertIn("ROLE_ADMIN", data["data"]["user"]["roles"])

    # --------------------------------------------------------------------------
    # Function: test_32_auth_login_invalid_password
    # Mục đích sử dụng: Kiểm tra đăng nhập thất bại khi sai mật khẩu, trả về HTTP 401 và mã lỗi INVALID_CREDENTIALS.
    # --------------------------------------------------------------------------
    def test_32_auth_login_invalid_password(self):
        payload = {"username": "admin", "password": "WrongPassword@999"}
        res = self.client.post("/api/v1/auth/login", json=payload)
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data["code"], "INVALID_CREDENTIALS")

    # --------------------------------------------------------------------------
    # Function: test_33_auth_login_nonexistent_user
    # Mục đích sử dụng: Kiểm tra đăng nhập với tài khoản không tồn tại, trả về HTTP 401 và mã lỗi INVALID_CREDENTIALS.
    # --------------------------------------------------------------------------
    def test_33_auth_login_nonexistent_user(self):
        payload = {"username": "non_existent_user", "password": "AnyPassword"}
        res = self.client.post("/api/v1/auth/login", json=payload)
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data["code"], "INVALID_CREDENTIALS")

    # --------------------------------------------------------------------------
    # Function: test_34_auth_get_me_with_token
    # Mục đích sử dụng: Kiểm tra truy xuất thông tin cá nhân qua endpoint /auth/me kèm Bearer token hợp lệ.
    # --------------------------------------------------------------------------
    def test_34_auth_get_me_with_token(self):
        login_res = self.client.post("/api/v1/auth/login", json={"username": "dispatcher1", "password": "Dispatch@123"})
        token = login_res.get_json()["data"]["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        res = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["data"]["username"], "dispatcher1")
        self.assertIn("ROLE_DISPATCHER", data["data"]["roles"])

    # --------------------------------------------------------------------------
    # Function: test_35_auth_unauthorized_missing_token
    # Mục đích sử dụng: Kiểm tra chặn truy cập và trả về HTTP 401 UNAUTHORIZED khi gọi API yêu cầu xác thực mà không truyền token.
    # --------------------------------------------------------------------------
    def test_35_auth_unauthorized_missing_token(self):
        res = self.client.get("/api/v1/auth/me")
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data["code"], "UNAUTHORIZED")

    # --------------------------------------------------------------------------
    # Function: test_36_auth_refresh_token
    # Mục đích sử dụng: Kiểm tra cấp lại Access Token mới từ Refresh Token hợp lệ khi Access Token hết hạn.
    # --------------------------------------------------------------------------
    def test_36_auth_refresh_token(self):
        login_res = self.client.post("/api/v1/auth/login", json={"username": "operator1", "password": "Oper@123"})
        rt = login_res.get_json()["data"]["refresh_token"]

        res = self.client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertIn("access_token", data["data"])

    # --------------------------------------------------------------------------
    # Function: test_37_auth_rbac_admin_allowed
    # Mục đích sử dụng: Kiểm tra quyền hạn quản trị viên truy cập thành công API danh sách người dùng (/auth/users).
    # --------------------------------------------------------------------------
    def test_37_auth_rbac_admin_allowed(self):
        login_res = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123"})
        token = login_res.get_json()["data"]["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        res = self.client.get("/api/v1/auth/users", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertGreaterEqual(data["total"], 6)

    # --------------------------------------------------------------------------
    # Function: test_38_auth_rbac_forbidden_for_non_admin
    # Mục đích sử dụng: Kiểm tra ngăn chặn truy cập và trả về HTTP 403 FORBIDDEN khi người dùng không đủ quyền quản trị gọi API quản lý người dùng.
    # --------------------------------------------------------------------------
    def test_38_auth_rbac_forbidden_for_non_admin(self):
        login_res = self.client.post("/api/v1/auth/login", json={"username": "dispatcher1", "password": "Dispatch@123"})
        token = login_res.get_json()["data"]["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        res = self.client.get("/api/v1/auth/users", headers=headers)
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertEqual(data["code"], "FORBIDDEN")

    # --------------------------------------------------------------------------
    # Function: test_39_auth_logout_revokes_tokens
    # Mục đích sử dụng: Kiểm tra đăng xuất thu hồi Refresh Token vào danh sách đen, ngăn chặn việc tái sử dụng refresh token sau khi logout.
    # --------------------------------------------------------------------------
    def test_39_auth_logout_revokes_tokens(self):
        login_res = self.client.post("/api/v1/auth/login", json={"username": "accountant1", "password": "Acc@123"})
        token = login_res.get_json()["data"]["access_token"]
        rt = login_res.get_json()["data"]["refresh_token"]

        headers = {"Authorization": f"Bearer {token}"}
        logout_res = self.client.post("/api/v1/auth/logout", headers=headers)
        self.assertEqual(logout_res.status_code, 200)

        # Refresh token must be revoked
        ref_res = self.client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        self.assertEqual(ref_res.status_code, 401)

    # --------------------------------------------------------------------------
    # Function: test_40_auth_audit_logs_recorded
    # Mục đích sử dụng: Kiểm tra hệ thống tự động ghi nhật ký kiểm toán (Audit Logs) khi người dùng thực hiện thao tác đăng nhập.
    # --------------------------------------------------------------------------
    def test_40_auth_audit_logs_recorded(self):
        login_res = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123"})
        token = login_res.get_json()["data"]["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        res = self.client.get("/api/v1/auth/audit-logs", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertGreater(data["count"], 0)

    # --------------------------------------------------------------------------
    # Function: test_41_openapi_json_spec
    # Mục đích sử dụng: Kiểm tra đặc tả tài liệu API chuẩn OpenAPI 3.0.3 tại endpoint /api/v1/openapi.json, bao gồm định nghĩa các API và cơ chế BearerAuth.
    # --------------------------------------------------------------------------
    def test_41_openapi_json_spec(self):
        res = self.client.get("/api/v1/openapi.json")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["openapi"], "3.0.3")
        self.assertIn("Hệ thống Quản lý Cảng biển Thông minh (SPMS)", data["info"]["title"])
        self.assertIn("/api/v1/auth/login", data["paths"])
        self.assertIn("/api/v1/vessels", data["paths"])
        self.assertIn("/api/v1/yard/atomic-move", data["paths"])
        self.assertIn("BearerAuth", data["components"]["securitySchemes"])

    # --------------------------------------------------------------------------
    # Function: test_42_swagger_ui_html
    # Mục đích sử dụng: Kiểm tra giao diện người dùng Swagger UI hiển thị đúng qua các đường dẫn /api/docs, /docs và /swagger.
    # --------------------------------------------------------------------------
    def test_42_swagger_ui_html(self):
        res = self.client.get("/api/docs")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"swagger-ui", res.data)
        self.assertIn(b"/api/v1/openapi.json", res.data)

        # Test route /docs and /swagger
        res_docs = self.client.get("/docs")
        self.assertEqual(res_docs.status_code, 200)

    # --------------------------------------------------------------------------
    # Function: test_43_create_user_by_admin
    # Mục đích sử dụng: Kiểm tra quản trị viên tạo mới tài khoản người dùng và gán vai trò, đồng thời xác minh phát hiện lỗi trùng tên đăng nhập.
    # --------------------------------------------------------------------------
    def test_43_create_user_by_admin(self):
        login_res = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123"})
        token = login_res.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        uname = f"planner_{int(time.time() * 1000) % 100000}"
        payload = {
            "username": uname,
            "password": "Password@123",
            "full_name": "Phan Văn Kế Hoạch",
            "email": f"{uname}@saigonnewport.com.vn",
            "department": "Phòng Khai thác Bãi",
            "terminal_code": "CTL",
            "role_id": "ROLE_OPERATOR"
        }
        res = self.client.post("/api/v1/auth/users", json=payload, headers=headers)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["data"]["username"], uname)

        # Creating duplicate username -> 400
        dup_res = self.client.post("/api/v1/auth/users", json=payload, headers=headers)
        self.assertEqual(dup_res.status_code, 400)

    # --------------------------------------------------------------------------
    # Function: test_44_update_user_by_admin
    # Mục đích sử dụng: Kiểm tra quản trị viên cập nhật thông tin người dùng (họ tên, phòng ban, trạng thái khóa) qua endpoint PUT /auth/users/<id>.
    # --------------------------------------------------------------------------
    def test_44_update_user_by_admin(self):
        login_res = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123"})
        token = login_res.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Update existing user dispatcher1
        update_payload = {
            "full_name": "Trần Đình Điều Độ Cập Nhật",
            "department": "Trung tâm Điều độ Tập trung",
            "is_locked": 0
        }
        res = self.client.put("/api/v1/auth/users/USR-002", json=update_payload, headers=headers)
        self.assertEqual(res.status_code, 200)

        # Verify update
        get_res = self.client.get("/api/v1/auth/users/USR-002", headers=headers)
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.get_json()["data"]["full_name"], "Trần Đình Điều Độ Cập Nhật")

    # --------------------------------------------------------------------------
    # Function: test_45_delete_user_by_admin
    # Mục đích sử dụng: Kiểm tra quản trị viên xóa người dùng và các phân quyền liên quan, xác minh truy vấn lại trả về 404.
    # --------------------------------------------------------------------------
    def test_45_delete_user_by_admin(self):
        login_res = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123"})
        token = login_res.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create temporary user to delete
        temp_user = {
            "username": "temp_user_delete",
            "password": "TempPassword@123",
            "full_name": "Người Dùng Tạm",
            "email": "temp_delete@test.com",
            "role_id": "ROLE_CUSTOMER"
        }
        create_res = self.client.post("/api/v1/auth/users", json=temp_user, headers=headers)
        uid = create_res.get_json()["data"]["user_id"]

        del_res = self.client.delete(f"/api/v1/auth/users/{uid}", headers=headers)
        self.assertEqual(del_res.status_code, 200)

        # Check deleted -> 404
        check_res = self.client.get(f"/api/v1/auth/users/{uid}", headers=headers)
        self.assertEqual(check_res.status_code, 404)

    # --------------------------------------------------------------------------
    # Function: test_46_audit_logs_advanced_filter
    # Mục đích sử dụng: Kiểm tra bộ lọc tìm kiếm nâng cao nhật ký kiểm toán (theo action, status, phân trang limit).
    # --------------------------------------------------------------------------
    def test_46_audit_logs_advanced_filter(self):
        login_res = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123"})
        token = login_res.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        res = self.client.get("/api/v1/auth/audit-logs?action=USER_LOGIN&status=SUCCESS&limit=10", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertGreater(data["count"], 0)
        for log in data["data"]:
            self.assertIn("USER_LOGIN", log["action"])
            self.assertEqual(log["status"], "SUCCESS")

if __name__ == "__main__":
    unittest.main()
