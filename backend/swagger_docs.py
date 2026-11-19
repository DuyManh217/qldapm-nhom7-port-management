# ==============================================================================
# TỔNG CÔNG TY TÂN CẢNG SÀI GÒN (SNP) - HỆ THỐNG ĐIỀU HÀNH KHAI THÁC CẢNG SPMS
# NGƯỜI THỰC HIỆN: Đào Văn Sơn - B23DCCN961
# VAI TRÒ: Backend Engineer / Lập trình viên Backend
# MODULE: Tài liệu hóa Giao diện Lập trình OpenAPI 3.0 & Trình duyệt tương tác Swagger UI
# ==============================================================================

import json
from flask import Blueprint, jsonify, render_template_string

swagger_bp = Blueprint("swagger_bp", __name__)

# Cấu hình đặc tả OpenAPI 3.0.3 chuẩn doanh nghiệp
# Người thực hiện: Đào Văn Sơn - B23DCCN961
OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Hệ thống Quản lý Cảng biển Thông minh (SPMS) - REST API Spec",
        "description": "Đặc tả kỹ thuật OpenAPI 3.0 cho Hệ thống Điều hành Khai thác Cảng SPMS - Tổng Công ty Tân Cảng Sài Gòn (SNP). Bao gồm Phân hệ Xác thực JWT & Phân quyền RBAC, Quản lý Tàu & Cầu bến (Vessel & Berth), Quản lý Bãi & Container (Yard & Container) và Nhật ký Kiểm toán (Audit Logs).",
        "version": "1.0.0",
        "contact": {
            "name": "Đào Văn Sơn (B23DCCN961) & Đội Dự án Nhóm 7",
            "email": "daoduymanh217@gmail.com",
            "url": "https://github.com/DuyManh217/qldapm-nhom7-port-management"
        },
        "license": {
            "name": "SNP Enterprise Commercial License",
            "url": "https://saigonnewport.com.vn"
        }
    },
    "servers": [
        {
            "url": "http://localhost:8088",
            "description": "SPMS Local Development & Demo Server"
        },
        {
            "url": "https://spms-catlai.saigonnewport.com.vn",
            "description": "Production Server - Cảng Tân Cảng Cát Lái"
        }
    ],
    "components": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Nhập mã JWT Access Token nhận được từ endpoint /api/v1/auth/login. Định dạng: Bearer <token>"
            }
        },
        "schemas": {
            "LoginRequest": {
                "type": "object",
                "required": ["username", "password"],
                "properties": {
                    "username": {"type": "string", "example": "admin"},
                    "password": {"type": "string", "example": "Admin@123"}
                }
            },
            "UserCreateRequest": {
                "type": "object",
                "required": ["username", "password", "full_name", "email", "role_id"],
                "properties": {
                    "username": {"type": "string", "example": "dispatcher_new"},
                    "password": {"type": "string", "example": "Pass@123456"},
                    "full_name": {"type": "string", "example": "Trần Văn Điều Độ"},
                    "email": {"type": "string", "example": "dieudo_new@saigonnewport.com.vn"},
                    "phone_number": {"type": "string", "example": "0987654321"},
                    "department": {"type": "string", "example": "Phòng Điều độ Tàu"},
                    "terminal_code": {"type": "string", "example": "CTL"},
                    "role_id": {"type": "string", "example": "ROLE_DISPATCHER"}
                }
            },
            "VesselCreateRequest": {
                "type": "object",
                "required": ["imo", "name", "carrier", "loa", "beam", "max_draft", "dwt", "teu"],
                "properties": {
                    "imo": {"type": "string", "example": "9998877"},
                    "name": {"type": "string", "example": "TAN CANG EXPLORER"},
                    "carrier": {"type": "string", "example": "SNP Lines"},
                    "loa": {"type": "number", "example": 220.0},
                    "beam": {"type": "number", "example": 32.0},
                    "max_draft": {"type": "number", "example": 12.5},
                    "dwt": {"type": "integer", "example": 35000},
                    "teu": {"type": "integer", "example": 2800}
                }
            },
            "PortCallCreateRequest": {
                "type": "object",
                "required": ["imo", "berth_id", "start_meter", "end_meter", "start_time", "end_time"],
                "properties": {
                    "imo": {"type": "string", "example": "9321483"},
                    "berth_id": {"type": "string", "example": "B1"},
                    "start_meter": {"type": "number", "example": 0.0},
                    "end_meter": {"type": "number", "example": 400.0},
                    "start_time": {"type": "string", "example": "2026-11-20 08:00"},
                    "end_time": {"type": "string", "example": "2026-11-21 12:00"},
                    "eta": {"type": "string", "example": "2026-11-20 07:30"},
                    "etd": {"type": "string", "example": "2026-11-21 12:00"}
                }
            },
            "AtomicMoveRequest": {
                "type": "object",
                "required": ["container_no", "source_slot_id", "target_slot_id"],
                "properties": {
                    "container_no": {"type": "string", "example": "MSCU1294801"},
                    "source_slot_id": {"type": "string", "example": "A-01-01-2"},
                    "target_slot_id": {"type": "string", "example": "A-01-02-1"}
                }
            }
        }
    },
    "paths": {
        "/api/v1/auth/login": {
            "post": {
                "summary": "Đăng nhập người dùng & Cấp JWT Token",
                "tags": ["Xác thực & Bảo mật (Auth)"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/LoginRequest"}}}
                },
                "responses": {
                    "200": {"description": "Đăng nhập thành công, trả về access_token và refresh_token"},
                    "401": {"description": "Sai tài khoản hoặc mật khẩu (INVALID_CREDENTIALS)"},
                    "403": {"description": "Tài khoản bị khóa hoặc vô hiệu hóa"}
                }
            }
        },
        "/api/v1/auth/refresh": {
            "post": {
                "summary": "Làm mới JWT Access Token",
                "tags": ["Xác thực & Bảo mật (Auth)"],
                "responses": {
                    "200": {"description": "Cấp lại Access Token mới thành công"},
                    "401": {"description": "Refresh token không hợp lệ hoặc đã bị thu hồi"}
                }
            }
        },
        "/api/v1/auth/logout": {
            "post": {
                "summary": "Đăng xuất & Thu hồi phiên làm việc",
                "security": [{"BearerAuth": []}],
                "tags": ["Xác thực & Bảo mật (Auth)"],
                "responses": {
                    "200": {"description": "Đăng xuất thành công, thu hồi token"}
                }
            }
        },
        "/api/v1/auth/me": {
            "get": {
                "summary": "Lấy thông tin tài khoản hiện tại & Quyền hạn",
                "security": [{"BearerAuth": []}],
                "tags": ["Xác thực & Bảo mật (Auth)"],
                "responses": {
                    "200": {"description": "Thông tin hồ sơ, vai trò và quyền hạn của người dùng"}
                }
            }
        },
        "/api/v1/auth/users": {
            "get": {
                "summary": "Danh sách toàn bộ người dùng hệ thống (Admin only)",
                "security": [{"BearerAuth": []}],
                "tags": ["Quản trị Người dùng & Vai trò (User/Role)"],
                "responses": {
                    "200": {"description": "Danh sách tài khoản người dùng"},
                    "403": {"description": "Không có quyền truy cập (Yêu cầu ROLE_ADMIN)"}
                }
            },
            "post": {
                "summary": "Tạo tài khoản người dùng mới (Admin only)",
                "security": [{"BearerAuth": []}],
                "tags": ["Quản trị Người dùng & Vai trò (User/Role)"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/UserCreateRequest"}}}
                },
                "responses": {
                    "201": {"description": "Tạo người dùng thành công"},
                    "400": {"description": "Tên đăng nhập hoặc email đã tồn tại"}
                }
            }
        },
        "/api/v1/auth/roles": {
            "get": {
                "summary": "Danh mục Vai trò & Ma trận Phân quyền",
                "security": [{"BearerAuth": []}],
                "tags": ["Quản trị Người dùng & Vai trò (User/Role)"],
                "responses": {
                    "200": {"description": "Danh sách các vai trò hệ thống"}
                }
            }
        },
        "/api/v1/auth/audit-logs": {
            "get": {
                "summary": "Truy vấn Nhật ký Kiểm toán Bảo mật (Audit Trail)",
                "security": [{"BearerAuth": []}],
                "tags": ["Nhật ký Kiểm toán (Audit Logs)"],
                "parameters": [
                    {"name": "action", "in": "query", "schema": {"type": "string"}, "description": "Lọc theo hành động (VD: USER_LOGIN, PORT_CALL_CREATE)"},
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 50}, "description": "Số bản ghi tối đa"}
                ],
                "responses": {
                    "200": {"description": "Danh sách bản ghi nhật ký kiểm toán"}
                }
            }
        },
        "/api/v1/vessels": {
            "get": {
                "summary": "Lấy danh mục tàu biển cập cảng",
                "tags": ["Phân hệ Tàu & Cầu bến (Vessel & Berth)"],
                "responses": {"200": {"description": "Danh sách thông số kỹ thuật tàu biển"}}
            },
            "post": {
                "summary": "Đăng ký thêm hồ sơ tàu biển mới",
                "tags": ["Phân hệ Tàu & Cầu bến (Vessel & Berth)"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/VesselCreateRequest"}}}
                },
                "responses": {
                    "201": {"description": "Thêm tàu thành công"},
                    "400": {"description": "Trùng số IMO hoặc thông số kỹ thuật không hợp lệ"}
                }
            }
        },
        "/api/v1/berths": {
            "get": {
                "summary": "Lấy danh sách cầu bến & mớn nước cho phép",
                "tags": ["Phân hệ Tàu & Cầu bến (Vessel & Berth)"],
                "responses": {"200": {"description": "Danh sách 6 cầu bến B1-B6 Cảng Cát Lái"}}
            }
        },
        "/api/v1/port-calls": {
            "get": {
                "summary": "Lấy kế hoạch các lượt tàu cập bến",
                "tags": ["Phân hệ Tàu & Cầu bến (Vessel & Berth)"],
                "responses": {"200": {"description": "Danh sách kế hoạch cập bến"}}
            },
            "post": {
                "summary": "Lập kế hoạch cập bến mới (Kiểm tra mớn nước & va chạm)",
                "tags": ["Phân hệ Tàu & Cầu bến (Vessel & Berth)"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PortCallCreateRequest"}}}
                },
                "responses": {
                    "201": {"description": "Lập kế hoạch cập bến thành công"},
                    "400": {"description": "Mớn nước vượt quá giới hạn hoặc va chạm thời gian/không gian cầu bến"}
                }
            }
        },
        "/api/v1/ai/optimize-berth": {
            "post": {
                "summary": "Tối ưu hóa xếp cầu bến thông minh AI",
                "tags": ["Thuật toán AI Cầu bến"],
                "responses": {"200": {"description": "Sinh lịch xếp bến tối ưu hóa giảm thời gian chờ tàu"}}
            }
        },
        "/api/v1/vessel/kpi": {
            "get": {
                "summary": "KPI hiệu suất khai thác cầu bến thời gian thực",
                "tags": ["Phân hệ Tàu & Cầu bến (Vessel & Berth)"],
                "responses": {"200": {"description": "Tỷ lệ chiếm dụng cầu bến, năng suất dỡ hàng moves/h"}}
            }
        },
        "/api/v1/yard/slots": {
            "get": {
                "summary": "Lấy sơ đồ lưới bãi container (192 slots)",
                "tags": ["Phân hệ Bãi & Container (Yard & Container)"],
                "responses": {"200": {"description": "Danh sách ô bãi Block A, B, C"}}
            }
        },
        "/api/v1/yard/containers": {
            "get": {
                "summary": "Danh sách container hiện hữu trên bãi",
                "tags": ["Phân hệ Bãi & Container (Yard & Container)"],
                "responses": {"200": {"description": "Thông tin container, loại cont, trọng lượng, cont lạnh, nguy hiểm"}}
            }
        },
        "/api/v1/yard/atomic-move": {
            "post": {
                "summary": "Di chuyển container bãi nguyên tử (Atomic Move) với Khóa phân tán",
                "tags": ["Phân hệ Bãi & Container (Yard & Container)"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AtomicMoveRequest"}}}
                },
                "responses": {
                    "200": {"description": "Di chuyển container an toàn thành công"},
                    "409": {"description": "Xung đột khóa ô bãi (Slot lock conflict) hoặc vi phạm quy tắc xếp tầng"}
                }
            }
        },
        "/api/v1/yard/alerts": {
            "get": {
                "summary": "Cảnh báo an toàn bãi container thời gian thực",
                "tags": ["Phân hệ Bãi & Container (Yard & Container)"],
                "responses": {"200": {"description": "Danh sách cảnh báo cont lạnh, cont nguy hiểm"}}
            }
        },
        "/api/v1/yard/kpi": {
            "get": {
                "summary": "KPI công suất sử dụng bãi container",
                "tags": ["Phân hệ Bãi & Container (Yard & Container)"],
                "responses": {"200": {"description": "Tỷ lệ lấp đầy bãi, số lượng cẩu RTG hoạt động"}}
            }
        },
        "/api/v1/tests/run-all": {
            "post": {
                "summary": "Thực thi toàn bộ bộ kiểm thử tự động hệ thống (Test Runner)",
                "tags": ["Kiểm thử Tự động (Automated Test Suite)"],
                "responses": {"200": {"description": "Kết quả chạy 40+ unit & integration test cases"}}
            }
        }
    }
}

SWAGGER_UI_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SPMS - Tài liệu Lập trình Giao diện API (Swagger UI / OpenAPI 3.0)</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui.css" />
    <link rel="icon" type="image/png" href="https://saigonnewport.com.vn/favicon.ico" />
    <style>
        body { margin: 0; padding: 0; background: #fafafa; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .topbar { background-color: #0b2f64; padding: 12px 24px; color: white; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
        .topbar h1 { margin: 0; font-size: 1.15rem; font-weight: 600; letter-spacing: 0.5px; }
        .topbar a { color: #93c5fd; text-decoration: none; font-size: 0.85rem; font-weight: 500; }
        .topbar a:hover { text-decoration: underline; }
        .badge { background: #2563eb; color: white; padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px; }
    </style>
</head>
<body>
    <div class="topbar">
        <div style="display: flex; align-items: center;">
            <h1>⚓ TỔNG CÔNG TY TÂN CẢNG SÀI GÒN · HỆ THỐNG SPMS</h1>
            <span class="badge">OpenAPI 3.0 / Swagger UI</span>
        </div>
        <div>
            <a href="/" target="_blank">← Trở về Dashboard SPMS</a>
            <span style="color: #64748b; margin: 0 8px;">|</span>
            <a href="/api/v1/openapi.json" target="_blank">Tải OpenAPI JSON</a>
        </div>
    </div>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {
            window.ui = SwaggerUIBundle({
                url: "/api/v1/openapi.json",
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                layout: "StandaloneLayout",
                docExpansion: "list",
                filter: true
            });
        };
    </script>
</body>
</html>
"""


# ------------------------------------------------------------------------------
# Function: get_openapi_json
# Endpoint: GET /api/v1/openapi.json
# Người thực hiện: Đào Văn Sơn - B23DCCN961
# Mục đích sử dụng: Cung cấp tài liệu đặc tả API chuẩn OpenAPI 3.0 dưới định dạng JSON cho các hệ thống đối tác hoặc công cụ tự động (Swagger, Postman)
# ------------------------------------------------------------------------------
@swagger_bp.route("/api/v1/openapi.json", methods=["GET"])
def get_openapi_json():
    """Trả về đặc tả OpenAPI 3.0 dạng JSON chuẩn của hệ thống SPMS."""
    return jsonify(OPENAPI_SPEC)


# ------------------------------------------------------------------------------
# Function: swagger_ui
# Endpoint: GET /api/docs (và bí danh /docs, /swagger)
# Người thực hiện: Đào Văn Sơn - B23DCCN961
# Mục đích sử dụng: Hiển thị giao diện Swagger UI tương tác trực quan tại runtime trên trình duyệt web, hỗ trợ kiểm thử trực tiếp các endpoint API của 2 module Vessel & Yard cùng module Auth
# ------------------------------------------------------------------------------
@swagger_bp.route("/api/docs", methods=["GET"])
@swagger_bp.route("/docs", methods=["GET"])
@swagger_bp.route("/swagger", methods=["GET"])
def swagger_ui():
    """Phục vụ trang Swagger UI tương tác trực tiếp trên trình duyệt."""
    return render_template_string(SWAGGER_UI_HTML)
