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
        full_name=user["full_name"],
        email=user["email"],
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
    uid = user.get("user_id") or user.get("sub")
    uname = user.get("username") or user.get("sub")
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("UPDATE spms_refresh_tokens SET is_revoked = 1 WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()

    record_audit(uid, uname, "USER_LOGOUT", "AUTH_PORTAL", "SUCCESS", "Đăng xuất an toàn")

    return jsonify({
        "status": "SUCCESS",
        "message": "Đăng xuất thành công, toàn bộ token phiên làm việc đã được thu hồi"
    }), 200


@auth_bp.route("/api/v1/auth/me", methods=["GET"])
@jwt_required()
def get_me():
    user = g.current_user
    uid = user.get("user_id") or user.get("sub")
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, full_name, email, phone_number, terminal_code, department, is_active FROM spms_users WHERE user_id = ?", (uid,))
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


@auth_bp.route("/api/v1/auth/users", methods=["POST"])
@jwt_required()
@role_required("ROLE_ADMIN", "PORT_ADMIN")
def create_user():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    full_name = data.get("full_name", "").strip()
    email = data.get("email", "").strip()
    department = data.get("department", "Phòng Điều độ & Khai thác").strip()
    terminal_code = data.get("terminal_code", "CTL").strip()
    phone_number = data.get("phone_number", "")
    role_id = data.get("role_id", "ROLE_OPERATOR").strip()

    if not username or not password or not full_name or not email:
        return jsonify({
            "status": "ERROR",
            "code": "MISSING_FIELDS",
            "message": "Vui lòng điền đầy đủ username, password, full_name và email"
        }), 400

    conn = db.get_db()
    cur = conn.cursor()

    # Check existing username or email
    cur.execute("SELECT user_id FROM spms_users WHERE username = ? OR email = ?", (username, email))
    if cur.fetchone():
        conn.close()
        return jsonify({
            "status": "ERROR",
            "code": "USER_ALREADY_EXISTS",
            "message": "Tên đăng nhập hoặc email đã tồn tại trong hệ thống"
        }), 400

    user_id = f"USR-{uuid.uuid4().hex[:8].upper()}"
    h, salt = hash_password(password)

    cur.execute("""
    INSERT INTO spms_users (user_id, username, password_hash, salt, full_name, email, phone_number, terminal_code, department)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, username, h, salt, full_name, email, phone_number, terminal_code, department))

    # Assign role
    cur.execute("INSERT INTO spms_user_roles (user_id, role_id) VALUES (?, ?)", (user_id, role_id))
    conn.commit()
    conn.close()

    admin_user = g.current_user.get("username") or g.current_user.get("sub")
    record_audit(g.current_user.get("user_id"), admin_user, "USER_CREATE", "SPMS_USERS", "SUCCESS", f"Tạo tài khoản: {username} ({role_id})")

    return jsonify({
        "status": "SUCCESS",
        "message": f"Tạo thành công tài khoản người dùng {username}",
        "data": {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "email": email,
            "department": department,
            "terminal_code": terminal_code,
            "role": role_id
        }
    }), 201


@auth_bp.route("/api/v1/auth/users/<user_id>", methods=["GET"])
@jwt_required()
def get_user_by_id(user_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT u.user_id, u.username, u.full_name, u.email, u.phone_number, u.terminal_code, u.department, u.is_active, u.is_locked,
           GROUP_CONCAT(r.role_id, ', ') AS roles
    FROM spms_users u
    LEFT JOIN spms_user_roles ur ON u.user_id = ur.user_id
    LEFT JOIN spms_roles r ON ur.role_id = r.role_id
    WHERE u.user_id = ?
    GROUP BY u.user_id
    """, (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"status": "ERROR", "code": "USER_NOT_FOUND", "message": "Không tìm thấy người dùng"}), 404

    return jsonify({
        "status": "SUCCESS",
        "data": dict(row)
    }), 200


@auth_bp.route("/api/v1/auth/users/<user_id>", methods=["PUT"])
@jwt_required()
@role_required("ROLE_ADMIN", "PORT_ADMIN")
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM spms_users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    if not user:
        conn.close()
        return jsonify({"status": "ERROR", "code": "USER_NOT_FOUND", "message": "Người dùng không tồn tại"}), 404

    full_name = data.get("full_name", user["full_name"])
    email = data.get("email", user["email"])
    department = data.get("department", user["department"])
    phone_number = data.get("phone_number", user["phone_number"])
    is_active = data.get("is_active", user["is_active"])
    is_locked = data.get("is_locked", user["is_locked"])

    cur.execute("""
    UPDATE spms_users
    SET full_name = ?, email = ?, department = ?, phone_number = ?, is_active = ?, is_locked = ?
    WHERE user_id = ?
    """, (full_name, email, department, phone_number, is_active, is_locked, user_id))

    # If role update requested
    if "role_id" in data:
        cur.execute("DELETE FROM spms_user_roles WHERE user_id = ?", (user_id,))
        cur.execute("INSERT INTO spms_user_roles (user_id, role_id) VALUES (?, ?)", (user_id, data["role_id"]))

    conn.commit()
    conn.close()

    admin_user = g.current_user.get("username") or g.current_user.get("sub")
    record_audit(g.current_user.get("user_id"), admin_user, "USER_UPDATE", "SPMS_USERS", "SUCCESS", f"Cập nhật tài khoản: {user['username']}")

    return jsonify({
        "status": "SUCCESS",
        "message": f"Cập nhật thông tin tài khoản {user['username']} thành công"
    }), 200


@auth_bp.route("/api/v1/auth/users/<user_id>", methods=["DELETE"])
@jwt_required()
@role_required("ROLE_ADMIN", "PORT_ADMIN")
def delete_user(user_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("SELECT username FROM spms_users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"status": "ERROR", "code": "USER_NOT_FOUND", "message": "Người dùng không tồn tại"}), 404

    username = row["username"]
    cur.execute("DELETE FROM spms_users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    admin_user = g.current_user.get("username") or g.current_user.get("sub")
    record_audit(g.current_user.get("user_id"), admin_user, "USER_DELETE", "SPMS_USERS", "SUCCESS", f"Xóa tài khoản: {username}")

    return jsonify({
        "status": "SUCCESS",
        "message": f"Đã xóa vĩnh viễn tài khoản {username}"
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
@role_required("ROLE_ADMIN", "PORT_ADMIN")
def list_audit_logs():
    limit = request.args.get("limit", 50, type=int)
    action_filter = request.args.get("action", "").strip()
    status_filter = request.args.get("status", "").strip()
    user_filter = request.args.get("username", "").strip()

    conn = db.get_db()
    cur = conn.cursor()

    query = "SELECT * FROM spms_audit_logs WHERE 1=1"
    params = []

    if action_filter:
        query += " AND action LIKE ?"
        params.append(f"%{action_filter}%")
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    if user_filter:
        query += " AND username = ?"
        params.append(user_filter)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    cur.execute(query, params)
    logs = [dict(row) for row in cur.fetchall()]
    conn.close()

    return jsonify({
        "status": "SUCCESS",
        "count": len(logs),
        "data": logs
    }), 200
