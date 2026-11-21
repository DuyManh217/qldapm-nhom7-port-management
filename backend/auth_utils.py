# ==============================================================================
# TỔNG CÔNG TY TÂN CẢNG SÀI GÒN (SNP) - HỆ THỐNG ĐIỀU HÀNH KHAI THÁC CẢNG SPMS
# NGƯỜI THỰC HIỆN: Đào Văn Sơn - B23DCCN961
# VAI TRÒ: Backend Engineer / Lập trình viên Backend
# MODULE: Tiện ích Bảo mật, Mã hóa mật khẩu, JWT RFC 7519 & Middleware Phân quyền RBAC
# ==============================================================================

import hmac
import hashlib
import base64
import json
import time
import os
import uuid
from functools import wraps
from flask import request, jsonify, g

# Khóa bí mật dùng để ký token JWT (lấy từ biến môi trường hoặc dùng mặc định an toàn)
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", os.environ.get("SPMS_JWT_SECRET", "spms-super-secret-key-catlai-2026"))
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 3600  # Thời hạn sống của Access Token: 1 giờ (theo đặc tả Doc 79)
REFRESH_TOKEN_EXPIRE_SECONDS = 86400 * 30  # Thời hạn sống của Refresh Token: 30 ngày

# Bảng ánh xạ vai trò tương đương (Đảm bảo đồng bộ 100% giữa Doc 79, Doc 96 và Schema.sql)
ROLE_ALIASES = {
    "ROLE_ADMIN": ["PORT_ADMIN", "ROLE_ADMIN"],
    "PORT_ADMIN": ["ROLE_ADMIN", "PORT_ADMIN"],
    "ROLE_DISPATCHER": ["VESSEL_DISPATCHER", "ROLE_DISPATCHER"],
    "VESSEL_DISPATCHER": ["ROLE_DISPATCHER", "VESSEL_DISPATCHER"],
    "ROLE_OPERATOR": ["YARD_PLANNER", "ROLE_OPERATOR", "SAFETY_INSPECTOR"],
    "YARD_PLANNER": ["ROLE_OPERATOR", "YARD_PLANNER"],
    "SAFETY_INSPECTOR": ["ROLE_OPERATOR", "SAFETY_INSPECTOR"],
    "ROLE_SECURITY": ["GATE_OPERATOR", "ROLE_SECURITY"],
    "GATE_OPERATOR": ["ROLE_SECURITY", "GATE_OPERATOR"],
    "ROLE_ACCOUNTANT": ["ROLE_ACCOUNTANT"],
    "ROLE_CUSTOMER": ["ROLE_CUSTOMER"]
}


# ------------------------------------------------------------------------------
# Function: b64url_encode
# Mục đích sử dụng: Mã hóa dữ liệu dạng bytes sang chuỗi Base64URL an toàn không có padding '=' (theo chuẩn JWT RFC 7519)
# ------------------------------------------------------------------------------
def b64url_encode(data: bytes) -> str:
    """Mã hóa bytes sang chuỗi Base64URL không padding theo chuẩn JWT RFC 7519."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


# ------------------------------------------------------------------------------
# Function: b64url_decode
# Mục đích sử dụng: Giải mã chuỗi Base64URL về mảng bytes gốc (tự động bổ sung padding '=' nếu thiếu)
# ------------------------------------------------------------------------------
def b64url_decode(s: str) -> bytes:
    """Giải mã chuỗi Base64URL về mảng bytes gốc."""
    padding = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + padding)


# ------------------------------------------------------------------------------
# Function: hash_password
# Mục đích sử dụng: Băm mật khẩu người dùng bằng giải thuật PBKDF2-HMAC-SHA256 với 100.000 vòng lặp và muối ngẫu nhiên (Salt)
# ------------------------------------------------------------------------------
def hash_password(password: str, salt: str = None):
    """
    Băm mật khẩu người dùng bằng PBKDF2-HMAC-SHA256 (100.000 vòng).
    Trả về: (mã hash dạng hex, chuỗi muối salt)
    """
    if not salt:
        salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return dk.hex(), salt


# ------------------------------------------------------------------------------
# Function: verify_password
# Mục đích sử dụng: Đối chiếu mật khẩu người dùng nhập vào với mã hash và muối đã lưu trong CSDL (chống Timing Attack)
# ------------------------------------------------------------------------------
def verify_password(password: str, hashed: str, salt: str) -> bool:
    """Kiểm tra mật khẩu nhập vào có khớp với mã băm trong CSDL hay không."""
    h_calc, _ = hash_password(password, salt)
    return hmac.compare_digest(h_calc, hashed)


# ------------------------------------------------------------------------------
# Function: create_access_token
# Mục đích sử dụng: Khởi tạo JWT Bearer Access Token chứa đầy đủ thông tin định danh và phân quyền theo chuẩn RFC 7519 & Doc 79
# ------------------------------------------------------------------------------
def create_access_token(
    user_id: str,
    username: str,
    roles: list,
    permissions: list,
    full_name: str = "",
    email: str = "",
    terminal: str = "CTL",
    ttl: int = ACCESS_TOKEN_EXPIRE_SECONDS
) -> str:
    """
    Sinh JWT Access Token chuẩn RFC 7519 ký HMAC-SHA256.
    Payload chứa: sub (user_id), username, full_name, email, roles, permissions, terminal_code, iss, aud, iat, exp, jti.
    """
    now = int(time.time())
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}

    # Mở rộng toàn diện các role alias tương ứng để đảm bảo phân quyền xuyên suốt
    expanded_roles = set(roles)
    for r in list(expanded_roles):
        for alias in ROLE_ALIASES.get(r, []):
            expanded_roles.add(alias)

    payload = {
        "sub": user_id,
        "user_id": user_id,
        "username": username,
        "full_name": full_name or username,
        "email": email or f"{username}@saigonnewport.com.vn",
        "roles": list(expanded_roles),
        "permissions": permissions,
        "terminal_code": terminal,
        "iss": "SPMS-AUTH-AUTHORITY",
        "aud": "SPMS-PORTAL-WEB",
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4())
    }
    h_b64 = b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    msg = f"{h_b64}.{p_b64}".encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).digest()
    sig_b64 = b64url_encode(sig)
    return f"{h_b64}.{p_b64}.{sig_b64}"


# ------------------------------------------------------------------------------
# Function: decode_access_token
# Mục đích sử dụng: Giải mã chuỗi JWT, kiểm tra tính toàn vẹn của chữ ký số HMAC-SHA256 và kiểm tra thời hạn hết hạn (exp)
# ------------------------------------------------------------------------------
def decode_access_token(token: str) -> dict:
    """
    Giải mã và xác thực tính hợp lệ của JWT token.
    Bắt lỗi nếu token sai định dạng, sai chữ ký số hoặc đã hết hạn.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("ERR_AUTH_TOKEN_INVALID: Định dạng token không hợp lệ")
    h_b64, p_b64, sig_b64 = parts
    msg = f"{h_b64}.{p_b64}".encode("utf-8")
    expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).digest()
    if not hmac.compare_digest(b64url_encode(expected_sig), sig_b64):
        raise ValueError("ERR_AUTH_TOKEN_INVALID: Chữ ký số JWT không hợp lệ hoặc bị giả mạo")
    payload = json.loads(b64url_decode(p_b64).decode("utf-8"))
    if "exp" in payload and payload["exp"] < time.time():
        raise ValueError("ERR_AUTH_TOKEN_EXPIRED: Token đã hết hạn, vui lòng đăng nhập lại")
    return payload


# ------------------------------------------------------------------------------
# Function: jwt_required (Alias: token_required)
# Mục đích sử dụng: Decorator bảo vệ các endpoint API yêu cầu người dùng phải gửi kèm JWT Bearer token hợp lệ trong header Authorization
# ------------------------------------------------------------------------------
def jwt_required(optional: bool = False):
    """
    Decorator kiểm tra JWT Bearer token trong Header Authorization của request.
    Nếu hợp lệ, lưu thông tin payload vào biến toàn cục flask.g.current_user.
    """
    # --------------------------------------------------------------------------
    # Function: decorator
    # --------------------------------------------------------------------------
    def decorator(f):
        # ----------------------------------------------------------------------
        # Function: wrapper
        # ----------------------------------------------------------------------
        @wraps(f)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            token = None
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1].strip()

            if not token:
                if optional:
                    g.current_user = None
                    return f(*args, **kwargs)
                return jsonify({
                    "status": "ERROR",
                    "code": "UNAUTHORIZED",
                    "error": "ERR_AUTH_MISSING_TOKEN",
                    "message": "Thiếu mã xác thực Bearer token"
                }), 401

            try:
                payload = decode_access_token(token)
                g.current_user = payload
            except ValueError as e:
                err_str = str(e)
                code = "ERR_AUTH_TOKEN_EXPIRED" if "EXPIRED" in err_str else "ERR_AUTH_TOKEN_INVALID"
                return jsonify({
                    "status": "ERROR",
                    "code": "INVALID_TOKEN",
                    "error": code,
                    "message": err_str
                }), 401

            return f(*args, **kwargs)
        return wrapper
    return decorator


# ------------------------------------------------------------------------------
# Function: role_required (Alias: roles_required)
# Mục đích sử dụng: Decorator kiểm soát phân quyền đa vai trò RBAC (Role-Based Access Control). Chỉ cho phép các vai trò được cấp phép truy cập (Superuser PORT_ADMIN / ROLE_ADMIN luôn có toàn quyền)
# ------------------------------------------------------------------------------
def role_required(*allowed_roles):
    """
    Decorator kiểm tra vai trò người dùng trong g.current_user.
    PORT_ADMIN hoặc ROLE_ADMIN được bypass toàn quyền.
    Trả về 403 Forbidden nếu không đủ vai trò.
    """
    # --------------------------------------------------------------------------
    # Function: decorator
    # --------------------------------------------------------------------------
    def decorator(f):
        # ----------------------------------------------------------------------
        # Function: wrapper
        # ----------------------------------------------------------------------
        @wraps(f)
        def wrapper(*args, **kwargs):
            current_user = getattr(g, "current_user", None)
            if not current_user:
                return jsonify({
                    "status": "ERROR",
                    "code": "UNAUTHORIZED",
                    "error": "ERR_AUTH_UNAUTHENTICATED",
                    "message": "Chưa xác thực người dùng"
                }), 401

            user_roles = current_user.get("roles", [])
            # Admin role (PORT_ADMIN hoặc ROLE_ADMIN) có toàn quyền tối cao
            if "PORT_ADMIN" in user_roles or "ROLE_ADMIN" in user_roles:
                return f(*args, **kwargs)

            # Mở rộng các role cho phép để kiểm tra
            target_roles = set(allowed_roles)
            for r in allowed_roles:
                for alias in ROLE_ALIASES.get(r, []):
                    target_roles.add(alias)

            if any(role in user_roles for role in target_roles):
                return f(*args, **kwargs)

            return jsonify({
                "status": "ERROR",
                "code": "FORBIDDEN",
                "error": "ERR_AUTH_FORBIDDEN",
                "message": f"Không có quyền thực hiện tác nghiệp này (Cần vai trò: {', '.join(allowed_roles)})"
            }), 403
        return wrapper
    return decorator


# ------------------------------------------------------------------------------
# Function: permission_required
# Mục đích sử dụng: Decorator kiểm tra quyền hạn chi tiết (granular permission) của người dùng trước khi thực thi endpoint API
# ------------------------------------------------------------------------------
def permission_required(permission: str):
    """Decorator kiểm tra quyền hạn chi tiết của người dùng."""
    # --------------------------------------------------------------------------
    # Function: decorator
    # --------------------------------------------------------------------------
    def decorator(f):
        # ----------------------------------------------------------------------
        # Function: wrapper
        # ----------------------------------------------------------------------
        @wraps(f)
        def wrapper(*args, **kwargs):
            current_user = getattr(g, "current_user", None)
            if not current_user:
                return jsonify({
                    "status": "ERROR",
                    "code": "UNAUTHORIZED",
                    "error": "ERR_AUTH_UNAUTHENTICATED",
                    "message": "Chưa xác thực người dùng"
                }), 401

            user_roles = current_user.get("roles", [])
            if "PORT_ADMIN" in user_roles or "ROLE_ADMIN" in user_roles:
                return f(*args, **kwargs)

            user_perms = current_user.get("permissions", [])
            if permission in user_perms:
                return f(*args, **kwargs)

            return jsonify({
                "status": "ERROR",
                "code": "FORBIDDEN",
                "error": "ERR_AUTH_FORBIDDEN",
                "message": f"Từ chối truy cập: Thiếu quyền hạn '{permission}'"
            }), 403
        return wrapper
    return decorator


# Các bí danh (Aliases) chuẩn hóa theo đúng tên hàm trong Tài liệu Doc 79 (Mục 3.2)
token_required = jwt_required
roles_required = role_required
