import hmac
import hashlib
import base64
import json
import time
import os
import uuid
from functools import wraps
from flask import request, jsonify, g

SECRET_KEY = os.environ.get("SPMS_JWT_SECRET", "spms-secret-key-saigon-newport-cat-lai-2026")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 3600  # 1 hour
REFRESH_TOKEN_EXPIRE_SECONDS = 86400 * 30  # 30 days


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


def create_access_token(user_id: str, username: str, roles: list, permissions: list, terminal: str = "CTL", ttl: int = ACCESS_TOKEN_EXPIRE_SECONDS) -> str:
    now = int(time.time())
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": username,
        "user_id": user_id,
        "terminal_code": terminal,
        "roles": roles,
        "permissions": permissions,
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
        raise ValueError("Invalid token format")
    h_b64, p_b64, sig_b64 = parts
    msg = f"{h_b64}.{p_b64}".encode("utf-8")
    expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).digest()
    if not hmac.compare_digest(b64url_encode(expected_sig), sig_b64):
        raise ValueError("Invalid JWT signature")
    payload = json.loads(b64url_decode(p_b64).decode("utf-8"))
    if "exp" in payload and payload["exp"] < time.time():
        raise ValueError("Token has expired")
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
                    "message": "Yêu cầu cung cấp Authorization Bearer token hợp lệ"
                }), 401

            try:
                payload = decode_access_token(token)
                g.current_user = payload
            except ValueError as e:
                return jsonify({
                    "status": "ERROR",
                    "code": "INVALID_TOKEN",
                    "message": f"Token không hợp lệ hoặc đã hết hạn: {str(e)}"
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
                    "message": "Chưa xác thực người dùng"
                }), 401

            user_roles = current_user.get("roles", [])
            # Admin has full authority over all endpoints
            if "ROLE_ADMIN" in user_roles:
                return f(*args, **kwargs)

            # Check if user has any allowed role
            if any(r in allowed_roles for r in user_roles):
                return f(*args, **kwargs)

            return jsonify({
                "status": "ERROR",
                "code": "FORBIDDEN",
                "message": f"Từ chối truy cập: Người dùng không có vai trò phù hợp ({', '.join(allowed_roles)})"
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
                    "message": "Chưa xác thực người dùng"
                }), 401

            user_roles = current_user.get("roles", [])
            if "ROLE_ADMIN" in user_roles:
                return f(*args, **kwargs)

            user_perms = current_user.get("permissions", [])
            if permission in user_perms:
                return f(*args, **kwargs)

            return jsonify({
                "status": "ERROR",
                "code": "FORBIDDEN",
                "message": f"Từ chối truy cập: Thiếu quyền hạn '{permission}'"
            }), 403
        return wrapper
    return decorator
