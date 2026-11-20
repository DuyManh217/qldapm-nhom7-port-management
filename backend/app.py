# ==============================================================================
# TỔNG CÔNG TY TÂN CẢNG SÀI GÒN (SNP) - HỆ THỐNG ĐIỀU HÀNH KHAI THÁC CẢNG SPMS
# NGƯỜI THỰC HIỆN: Đào Văn Sơn - B23DCCN961
# VAI TRÒ: Backend Engineer / Lập trình viên Backend
# MODULE: Máy chủ Trung tâm Flask Web Application & Định tuyến Hệ thống
# ==============================================================================

import os
import sys
import unittest
import time
from flask import Flask, render_template, jsonify

# Add backend directory to path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from vessel_berth_backend import vessel_berth_bp
from yard_container_backend import yard_container_bp
from auth_backend import auth_bp
from swagger_docs import swagger_bp
import db

# Initialize database
db.init_db()

# Templates from frontend folder
frontend_dir = os.path.abspath(os.path.join(backend_dir, "..", "frontend"))
app = Flask(__name__, template_folder=frontend_dir)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# Register modules
app.register_blueprint(vessel_berth_bp)
app.register_blueprint(yard_container_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(swagger_bp)

# ------------------------------------------------------------------------------
# Function: home
# Mục đích sử dụng: Phục vụ trang chủ giao diện web tích hợp (Portal) của hệ thống SPMS.
# ------------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")

# ------------------------------------------------------------------------------
# Function: vessel_page
# Mục đích sử dụng: Phục vụ giao diện điều hành phân hệ Tàu & Cầu bến (Vessel & Berth).
# ------------------------------------------------------------------------------
@app.route("/vessel")
def vessel_page():
    return render_template("vessel_berth.html")

# ------------------------------------------------------------------------------
# Function: yard_page
# Mục đích sử dụng: Phục vụ giao diện điều hành phân hệ Bãi Container (Yard & Container).
# ------------------------------------------------------------------------------
@app.route("/yard")
def yard_page():
    return render_template("yard_container.html")

# ------------------------------------------------------------------------------
# Function: run_tests
# Mục đích sử dụng: API kích hoạt chạy toàn bộ bộ kiểm thử tự động (46 test cases) thời gian thực và trả về kết quả JSON.
# ------------------------------------------------------------------------------
# REAL DYNAMIC AUTOMATED TESTS ENDPOINT
@app.route("/api/v1/tests/run-all", methods=["POST"])
def run_tests():
    tests_dir = os.path.abspath(os.path.join(backend_dir, "..", "tests"))
    loader = unittest.TestLoader()
    suite = loader.discover(tests_dir, pattern="test_*.py")
    
    results = []
    
    # Flatten test suite to extract individual test instances
    def extract_tests(suite_or_case):
        tests = []
        if isinstance(suite_or_case, unittest.TestSuite):
            for sub in suite_or_case:
                tests.extend(extract_tests(sub))
        elif isinstance(suite_or_case, unittest.TestCase):
            tests.append(suite_or_case)
        return tests

    all_tests = extract_tests(suite)

    for test in all_tests:
        # Prevent recursion if triggered from within integration test
        if "integration_tests_endpoint" in test._testMethodName:
            continue

        t0 = time.time()
        test_result = unittest.TestResult()
        test.run(test_result)
        latency = round((time.time() - t0) * 1000, 2)
        
        status = "PASS" if test_result.wasSuccessful() else "FAIL"
        raw_name = test._testMethodName
        test_id = raw_name.replace("test_", "TC_").upper()
        
        # Categorize logically based on test intent
        category = "Chức năng API"
        name_desc = raw_name
        if "swagger" in raw_name or "openapi" in raw_name:
            category = "Tài liệu hóa OpenAPI/Swagger"
            name_desc = f"Kiểm tra đặc tả OpenAPI 3.0 & Swagger UI ({raw_name})"
        elif "auth" in raw_name or "login" in raw_name or "jwt" in raw_name or "rbac" in raw_name or "user" in raw_name:
            category = "Xác thực & Quản trị User/Role"
            name_desc = f"Kiểm soát định danh JWT, RBAC & CRUD người dùng ({raw_name})"
        elif "index" in raw_name or "page" in raw_name:
            category = "Giao diện Web"
            name_desc = f"Truy cập định tuyến giao diện Web ({raw_name})"
        elif "vessel" in raw_name:
            category = "Phân hệ Tàu & Cầu bến"
            name_desc = f"Quản lý & xử lý dữ liệu tàu biển ({raw_name})"
        elif "berth" in raw_name or "draft" in raw_name or "collision" in raw_name:
            category = "Thuật toán Cầu bến"
            name_desc = f"Kiểm tra mớn nước & va chạm không gian/thời gian ({raw_name})"
        elif "yard" in raw_name or "reefer" in raw_name or "floating" in raw_name or "stacking" in raw_name:
            category = "Quy tắc Xếp bãi (AI)"
            name_desc = f"Kiểm soát trọng lực, cont lạnh & hàng nguy hiểm ({raw_name})"
        elif "move" in raw_name:
            category = "Tác nghiệp Nguyên tử"
            name_desc = f"Đảo chuyển container bãi & khóa phân tán ({raw_name})"
        elif "container" in raw_name:
            category = "Phân hệ Bãi & Container"
            name_desc = f"Quản lý vòng đời container ({raw_name})"

        results.append({
            "id": test_id,
            "name": name_desc,
            "category": category,
            "status": status,
            "latency_ms": max(0.5, latency)
        })

    passed_count = sum(1 for r in results if r["status"] == "PASS")
    return jsonify({
        "total": len(results),
        "passed": passed_count,
        "results": results
    })

if __name__ == "__main__":
    port = 8088
    print("=" * 65)
    print(f"  SPMS FULL STACK SERVER RUNNING: http://localhost:{port}")
    print("  - Module 1 (Vessel & Berth)  : http://localhost:8088/vessel")
    print("  - Module 2 (Yard & Container): http://localhost:8088/yard")
    print("  - Portal Hợp Nhất           : http://localhost:8088/")
    print("  - Database Backend           : SQLite3 ACID Persistent (backend/spms.db)")
    print("=" * 65)
    app.run(host="0.0.0.0", port=port, debug=False)
