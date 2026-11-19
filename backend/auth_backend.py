import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, g
import db
from auth_utils import (
    hash_password,
    verify_password,
    create_access_token,
    jwt_required,
    role_required,
    ACCESS_TOKEN_EXPIRE_SECONDS
)

auth_bp = Blueprint("auth_bp", __name__)


def record_audit(user_id: str, username: str, action: str, resource: str, status: str, details: str = ""):
    try:
        conn = db.get_db()
        cur = conn.cursor()
        ip_addr = request.remote_addr or "127.0.0.1"
        cur.execute("""
        INSERT INTO spms_audit_logs (log_id, user_id, username, action, resource, status, ip_address, details, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"LOG-{uuid.uuid4().hex[:8].upper()}",
            user_id,
            username,
            action,
            resource,
            status,
            ip_addr,
            details,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging audit: {e}")


@auth_bp.route("/api/v1/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({
            "status": "ERROR",
            "code": "MISSING_CREDENTIALS",
            "message": "Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu"
        }), 400

    conn = db.get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM spms_users WHERE username = ?", (username,))
    user = cur.fetchone()

    if not user:
        record_audit(None, username, "USER_LOGIN", "AUTH_PORTAL", "FAILED", "Tài khoản không tồn tại")
        conn.close()
        return jsonify({
            "status": "ERROR",
            "code": "INVALID_CREDENTIALS",
            "message": "Tên đăng nhập hoặc mật khẩu không chính xác"
        }), 401

    if not user["is_active"]:
        record_audit(user["user_id"], username, "USER_LOGIN", "AUTH_PORTAL", "FAILED", "Tài khoản đã bị vô hiệu hóa")
        conn.close()
        return jsonify({
            "status": "ERROR",
            "code": "ACCOUNT_DISABLED",
            "message": "Tài khoản của bạn đã bị khóa hoặc vô hiệu hóa. Vui lòng liên hệ quản trị viên."
        }), 403

    if user["is_locked"]:
        record_audit(user["user_id"], username, "USER_LOGIN", "AUTH_PORTAL", "FAILED", "Tài khoản bị khóa do đăng nhập sai")
        conn.close()
        return jsonify({
            "status": "ERROR",
            "code": "ACCOUNT_LOCKED",
            "message": "Tài khoản đã bị tạm khóa do nhập sai mật khẩu quá 5 lần"
        }), 403

    if not verify_password(password, user["password_hash"], user["salt"]):
        failed_count = user["failed_login_attempts"] + 1
        is_locked = 1 if failed_count >= 5 else 0
        cur.execute("UPDATE spms_users SET failed_login_attempts = ?, is_locked = ? WHERE user_id = ?",
                    (failed_count, is_locked, user["user_id"]))
        conn.commit()
        record_audit(user["user_id"], username, "USER_LOGIN", "AUTH_PORTAL", "FAILED", f"Sai mật khẩu lần {failed_count}")
        conn.close()
        return jsonify({
            "status": "ERROR",
            "code": "INVALID_CREDENTIALS",
            "message": "Tên đăng nhập hoặc mật khẩu không chính xác"
        }), 401

    # Reset failed login count and record last login
    cur.execute("UPDATE spms_users SET failed_login_attempts = 0, last_login_at = ? WHERE user_id = ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user["user_id"]))

    # Fetch roles
    cur.execute("""
    SELECT r.role_id, r.role_name
    FROM spms_user_roles ur
    JOIN spms_roles r ON ur.role_id = r.role_id
    WHERE ur.user_id = ?
    """, (user["user_id"],))
    role_rows = cur.fetchall()
    roles = [r["role_id"] for r in role_rows]

    # Fetch permissions
    cur.execute("""
    SELECT DISTINCT p.permission_id
    FROM spms_role_permissions rp
    JOIN spms_permissions p ON rp.permission_id = p.permission_id
    WHERE rp.role_id IN ({})
    """.format(",".join(["?"] * len(roles))) if roles else "SELECT 1 WHERE 0", roles)
    perm_rows = cur.fetchall()
    permissions = [p["permission_id"] for p in perm_rows]

    # Generate Tokens
    access_token = create_access_token(
        user_id=user["user_id"],
        username=user["username"],
        roles=roles,
        permissions=permissions,
        terminal=user["terminal_code"]
    )

    refresh_token = f"RT-{uuid.uuid4().hex}"
    expiry_date = datetime.fromtimestamp(datetime.now().timestamp() + 86400 * 30).strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
    INSERT INTO spms_refresh_tokens (token_id, user_id, token_value, expiry_date, is_revoked)
    VALUES (?, ?, ?, ?, 0)
    """, (str(uuid.uuid4()), user["user_id"], refresh_token, expiry_date))

    conn.commit()
    conn.close()

    record_audit(user["user_id"], username, "USER_LOGIN", "AUTH_PORTAL", "SUCCESS", "Đăng nhập JWT thành công")

    return jsonify({
        "status": "SUCCESS",
        "message": "Đăng nhập thành công",
        "data": {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
            "refresh_token": refresh_token,
            "user": {
                "user_id": user["user_id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "email": user["email"],
                "department": user["department"],
                "terminal_code": user["terminal_code"],
                "roles": roles,
                "permissions": permissions
            }
        }
    }), 200


@auth_bp.route("/api/v1/auth/refresh", methods=["POST"])
def refresh_token():
    data = request.get_json(silent=True) or {}
    rt = data.get("refresh_token", "").strip()

    if not rt:
        return jsonify({
            "status": "ERROR",
            "code": "MISSING_REFRESH_TOKEN",
            "message": "Vui lòng cung cấp refresh_token"
        }), 400

    conn = db.get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT rt.*, u.username, u.terminal_code, u.is_active, u.is_locked
    FROM spms_refresh_tokens rt
    JOIN spms_users u ON rt.user_id = u.user_id
    WHERE rt.token_value = ? AND rt.is_revoked = 0
    """, (rt,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({
            "status": "ERROR",
            "code": "INVALID_REFRESH_TOKEN",
            "message": "Refresh token không hợp lệ hoặc đã bị thu hồi"
        }), 401

    if not row["is_active"] or row["is_locked"]:
        conn.close()
        return jsonify({
            "status": "ERROR",
            "code": "ACCOUNT_DISABLED",
            "message": "Tài khoản hiện không còn hoạt động"
        }), 403

    # Load roles & perms
    cur.execute("SELECT role_id FROM spms_user_roles WHERE user_id = ?", (row["user_id"],))
    roles = [r["role_id"] for r in cur.fetchall()]

    cur.execute("""
    SELECT DISTINCT permission_id FROM spms_role_permissions WHERE role_id IN ({})
    """.format(",".join(["?"] * len(roles))) if roles else "SELECT 1 WHERE 0", roles)
    permissions = [p["permission_id"] for p in cur.fetchall()]

    new_access_token = create_access_token(
        user_id=row["user_id"],
        username=row["username"],
        roles=roles,
        permissions=permissions,
        terminal=row["terminal_code"]
    )
    conn.close()

    return jsonify({
        "status": "SUCCESS",
        "message": "Làm mới access token thành công",
        "data": {
            "access_token": new_access_token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS
        }
    }), 200


@auth_bp.route("/api/v1/auth/logout", methods=["POST"])
@jwt_required()
def logout():
    user = g.current_user
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("UPDATE spms_refresh_tokens SET is_revoked = 1 WHERE user_id = ?", (user["user_id"],))
    conn.commit()
    conn.close()

    record_audit(user["user_id"], user["sub"], "USER_LOGOUT", "AUTH_PORTAL", "SUCCESS", "Đăng xuất an toàn")

    return jsonify({
        "status": "SUCCESS",
        "message": "Đăng xuất thành công, toàn bộ token phiên làm việc đã được thu hồi"
    }), 200


@auth_bp.route("/api/v1/auth/me", methods=["GET"])
@jwt_required()
def get_me():
    user = g.current_user
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, full_name, email, phone_number, terminal_code, department, is_active FROM spms_users WHERE user_id = ?", (user["user_id"],))
    profile = cur.fetchone()
    conn.close()

    if not profile:
        return jsonify({"status": "ERROR", "message": "Người dùng không tồn tại"}), 404

    return jsonify({
        "status": "SUCCESS",
        "data": {
            "user_id": profile["user_id"],
            "username": profile["username"],
            "full_name": profile["full_name"],
            "email": profile["email"],
            "phone_number": profile["phone_number"],
            "terminal_code": profile["terminal_code"],
            "department": profile["department"],
            "roles": user.get("roles", []),
            "permissions": user.get("permissions", [])
        }
    }), 200


@auth_bp.route("/api/v1/auth/users", methods=["GET"])
@jwt_required()
@role_required("ROLE_ADMIN")
def list_users():
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT u.user_id, u.username, u.full_name, u.email, u.terminal_code, u.department, u.is_active, u.is_locked, u.last_login_at,
           GROUP_CONCAT(r.role_id, ', ') AS roles
    FROM spms_users u
    LEFT JOIN spms_user_roles ur ON u.user_id = ur.user_id
    LEFT JOIN spms_roles r ON ur.role_id = r.role_id
    GROUP BY u.user_id
    ORDER BY u.created_at ASC
    """)
    users = [dict(row) for row in cur.fetchall()]
    conn.close()

    return jsonify({
        "status": "SUCCESS",
        "total": len(users),
        "data": users
    }), 200


@auth_bp.route("/api/v1/auth/roles", methods=["GET"])
@jwt_required()
def list_roles():
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM spms_roles ORDER BY role_id ASC")
    roles = [dict(row) for row in cur.fetchall()]
    conn.close()

    return jsonify({
        "status": "SUCCESS",
        "data": roles
    }), 200


@auth_bp.route("/api/v1/auth/audit-logs", methods=["GET"])
@jwt_required()
@role_required("ROLE_ADMIN")
def list_audit_logs():
    limit = request.args.get("limit", 50, type=int)
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM spms_audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    logs = [dict(row) for row in cur.fetchall()]
    conn.close()

    return jsonify({
        "status": "SUCCESS",
        "count": len(logs),
        "data": logs
    }), 200
