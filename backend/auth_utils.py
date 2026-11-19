import hmac
import hashlib
import base64
import json
import time
import os
import uuid
from functools import wraps
from flask import request, jsonify, g

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", os.environ.get("SPMS_JWT_SECRET", "spms-super-secret-key-catlai-2026"))
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 3600  # 1 hour (theo đặc tả Row 79)
REFRESH_TOKEN_EXPIRE_SECONDS = 86400 * 30  # 30 days

# Role Aliases mapping (đảm bảo tương thích 100% giữa Row 79, Row 96 và Schema.sql)
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


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def b64url_decode(s: str) -> bytes:
    padding = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + padding)


def hash_password(password: str, salt: str = None):
    if not salt:
        salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return dk.hex(), salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    h_calc, _ = hash_password(password, salt)
    return hmac.compare_digest(h_calc, hashed)


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
    now = int(time.time())
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}

    # Mở rộng toàn diện các role alias tương ứng
    expanded_roles = set(roles)
    for r in list(expanded_roles):
        for alias in ROLE_ALIASES.get(r, []):
            expanded_roles.add(alias)

    # Chuẩn hóa JWT Payload theo đúng RFC 7519 & Tài liệu Row 79 (Mục 3.1)
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


def decode_access_token(token: str) -> dict:
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


def jwt_required(optional: bool = False):
    def decorator(f):
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


def role_required(*allowed_roles):
    def decorator(f):
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
            # Admin role (PORT_ADMIN hoặc ROLE_ADMIN) có toàn quyền
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


def permission_required(permission: str):
    def decorator(f):
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


# Aliases chuẩn hóa theo đúng tên hàm trong Tài liệu Row 79 (Mục 3.2)
token_required = jwt_required
roles_required = role_required
