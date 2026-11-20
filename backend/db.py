# ==============================================================================
# TỔNG CÔNG TY TÂN CẢNG SÀI GÒN (SNP) - HỆ THỐNG ĐIỀU HÀNH KHAI THÁC CẢNG SPMS
# NGƯỜI THỰC HIỆN: Đào Văn Sơn - B23DCCN961
# VAI TRÒ: Backend Engineer / Lập trình viên Backend
# MODULE: Cơ sở dữ liệu SQLite, Lược đồ quan hệ & Dữ liệu mẫu (Database Engine & Seed Data)
# ==============================================================================

import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spms.db")

# ------------------------------------------------------------------------------
# Function: get_db
# Mục đích sử dụng: Khởi tạo kết nối SQLite với Row factory và kích hoạt Foreign Keys PRAGMA.
# ------------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

# ------------------------------------------------------------------------------
# Function: init_db
# Mục đích sử dụng: Khởi tạo cấu trúc các bảng CSDL cho 2 phân hệ Vessel/Berth, Yard/Container và bảng bảo mật User/Role/Audit.
# ------------------------------------------------------------------------------
def init_db():
    conn = get_db()
    cur = conn.cursor()

    # 1. Bảng Cầu bến (tbl_berths)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_berths (
        berth_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        start_meter REAL NOT NULL,
        end_meter REAL NOT NULL,
        depth_draft REAL NOT NULL,
        port TEXT NOT NULL DEFAULT 'CAT_LAI'
    );
    """)

    # 2. Bảng Danh mục tàu (tbl_vessels)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_vessels (
        imo TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        carrier TEXT NOT NULL,
        loa REAL NOT NULL,
        beam REAL NOT NULL,
        max_draft REAL NOT NULL,
        dwt INTEGER NOT NULL,
        teu INTEGER NOT NULL,
        mmsi TEXT,
        call_sign TEXT,
        flag_state TEXT DEFAULT 'Panama',
        vessel_type TEXT DEFAULT 'CONTAINER_SHIP',
        status TEXT DEFAULT 'ACTIVE',
        information_source TEXT DEFAULT 'Đăng kiểm / Lloyd''s',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3. Bảng Lượt cập bến (tbl_port_calls)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_port_calls (
        call_id TEXT PRIMARY KEY,
        imo TEXT NOT NULL,
        vessel_name TEXT NOT NULL,
        berth_id TEXT NOT NULL,
        start_meter REAL NOT NULL,
        end_meter REAL NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'APPROVED',
        eta TEXT NOT NULL,
        etd TEXT NOT NULL,
        discharge_teu INTEGER DEFAULT 500,
        load_teu INTEGER DEFAULT 500,
        current_moves INTEGER DEFAULT 0,
        total_moves INTEGER DEFAULT 1000,
        service_route TEXT DEFAULT 'IA1 (Nội Á)',
        voyage TEXT DEFAULT '441N / 442S',
        agent TEXT DEFAULT 'SNP Agency',
        arrival_draft REAL DEFAULT 11.8,
        departure_draft REAL DEFAULT 12.2,
        berthing_side TEXT DEFAULT 'Port',
        closed_at TEXT,
        change_reason TEXT,
        FOREIGN KEY (imo) REFERENCES tbl_vessels(imo) ON DELETE CASCADE
    );
    """)

    # 3.1 Bảng Phiên bản Kế hoạch Bến (tbl_berth_plan_versions - WF-VB-03 & WF-VB-04)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_berth_plan_versions (
        version_id TEXT PRIMARY KEY,
        version_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        created_by TEXT NOT NULL DEFAULT 'Nguyễn Văn B (ACT_BP)',
        approved_by TEXT,
        effective_at TEXT,
        change_reason TEXT,
        is_locked INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3.2 Bảng Mốc sự kiện Lượt tàu & Đối chiếu đa nguồn (tbl_port_call_milestones - WF-VB-02 & WF-VB-05)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_port_call_milestones (
        milestone_id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_id TEXT NOT NULL,
        milestone_code TEXT NOT NULL,
        milestone_name TEXT NOT NULL,
        carrier_time TEXT,
        tos_time TEXT,
        ai_time TEXT,
        ai_confidence REAL,
        confirmed_time TEXT,
        confirmed_by TEXT,
        actual_time TEXT,
        status TEXT DEFAULT 'PENDING',
        FOREIGN KEY (call_id) REFERENCES tbl_port_calls(call_id) ON DELETE CASCADE
    );
    """)

    # 3.3 Bảng Dịch vụ Hàng hải Điều phối (tbl_nautical_services - WF-VB-05)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_nautical_services (
        service_id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_id TEXT NOT NULL,
        service_type TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        requested_time TEXT NOT NULL,
        location TEXT NOT NULL,
        confirmation_status TEXT NOT NULL DEFAULT 'CONFIRMED',
        actual_time TEXT,
        FOREIGN KEY (call_id) REFERENCES tbl_port_calls(call_id) ON DELETE CASCADE
    );
    """)

    # 3.4 Bảng Checklist Sẵn sàng Cập/Rời Bến (tbl_readiness_checklist - WF-VB-05)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_readiness_checklist (
        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_id TEXT NOT NULL,
        step_number INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PASS',
        checked_by TEXT NOT NULL,
        note TEXT,
        FOREIGN KEY (call_id) REFERENCES tbl_port_calls(call_id) ON DELETE CASCADE
    );
    """)

    # 3.5 Bảng Phân bổ Cẩu bờ & Giám sát Xếp dỡ (tbl_crane_assignments - WF-VB-06)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_crane_assignments (
        assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_id TEXT NOT NULL,
        crane_id TEXT NOT NULL,
        bay_no TEXT NOT NULL,
        planned_moves INTEGER NOT NULL DEFAULT 500,
        completed_moves INTEGER NOT NULL DEFAULT 0,
        crane_status TEXT NOT NULL DEFAULT 'WORKING',
        moves_per_hour REAL NOT NULL DEFAULT 28.5,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (call_id) REFERENCES tbl_port_calls(call_id) ON DELETE CASCADE
    );
    """)

    # Đồng bộ các cột mới vào CSDL nếu đã tồn tại bảng cũ
    for col, ctype in [
        ("mmsi", "TEXT"), ("call_sign", "TEXT"), ("flag_state", "TEXT DEFAULT 'Panama'"),
        ("vessel_type", "TEXT DEFAULT 'CONTAINER_SHIP'"), ("status", "TEXT DEFAULT 'ACTIVE'"),
        ("information_source", "TEXT DEFAULT 'Đăng kiểm / Lloyd''s'")
    ]:
        try:
            cur.execute(f"ALTER TABLE tbl_vessels ADD COLUMN {col} {ctype};")
        except sqlite3.OperationalError:
            pass

    for col, ctype in [
        ("service_route", "TEXT DEFAULT 'IA1 (Nội Á)'"), ("voyage", "TEXT DEFAULT '441N / 442S'"),
        ("agent", "TEXT DEFAULT 'SNP Agency'"), ("arrival_draft", "REAL DEFAULT 11.8"),
        ("departure_draft", "REAL DEFAULT 12.2"), ("berthing_side", "TEXT DEFAULT 'Port'"),
        ("closed_at", "TEXT"), ("change_reason", "TEXT")
    ]:
        try:
            cur.execute(f"ALTER TABLE tbl_port_calls ADD COLUMN {col} {ctype};")
        except sqlite3.OperationalError:
            pass

    # 4. Bảng Ô bãi (tbl_yard_slots)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_yard_slots (
        slot_id TEXT PRIMARY KEY,
        block TEXT NOT NULL,
        bay INTEGER NOT NULL,
        row INTEGER NOT NULL,
        tier INTEGER NOT NULL,
        is_reefer_plug INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'AVAILABLE',
        container_no TEXT,
        locked_by TEXT
    );
    """)

    # 5. Bảng Container (tbl_containers)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_containers (
        container_no TEXT PRIMARY KEY,
        iso_type TEXT NOT NULL DEFAULT '20GP',
        weight_kg REAL NOT NULL DEFAULT 20000,
        is_hazardous INTEGER NOT NULL DEFAULT 0,
        imdg_class TEXT,
        is_reefer INTEGER NOT NULL DEFAULT 0,
        set_temp_celsius REAL,
        slot_id TEXT,
        FOREIGN KEY (slot_id) REFERENCES tbl_yard_slots(slot_id)
    );
    """)

    # 6. Bảng Cảnh báo an toàn bãi (tbl_yard_alerts)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_yard_alerts (
        alert_id TEXT PRIMARY KEY,
        severity TEXT NOT NULL,
        code TEXT NOT NULL,
        container_no TEXT,
        slot_id TEXT,
        message TEXT NOT NULL,
        timestamp TEXT NOT NULL
    );
    """)

    # ==========================================================================
    # CÁC BẢNG BẢO MẬT, USER/ROLE & NHẬT KÝ KIỂM TOÁN (DOC 79, DOC 96, SCHEMA.SQL)
    # ==========================================================================

    # 7. Bảng Vai trò người dùng (spms_roles)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS spms_roles (
        role_id TEXT PRIMARY KEY,
        role_name TEXT NOT NULL UNIQUE,
        description TEXT,
        is_system_role INTEGER NOT NULL DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 8. Bảng Danh mục quyền hạn (spms_permissions)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS spms_permissions (
        permission_id TEXT PRIMARY KEY,
        permission_name TEXT NOT NULL,
        module TEXT NOT NULL,
        description TEXT
    );
    """)

    # 9. Bảng Tài khoản người dùng (spms_users)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS spms_users (
        user_id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone_number TEXT,
        terminal_code TEXT NOT NULL DEFAULT 'CTL',
        department TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        is_locked INTEGER NOT NULL DEFAULT 0,
        failed_login_attempts INTEGER NOT NULL DEFAULT 0,
        last_login_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 10. Bảng liên kết Người dùng - Vai trò (spms_user_roles)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS spms_user_roles (
        user_id TEXT NOT NULL,
        role_id TEXT NOT NULL,
        assigned_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, role_id),
        FOREIGN KEY (user_id) REFERENCES spms_users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (role_id) REFERENCES spms_roles(role_id) ON DELETE CASCADE
    );
    """)

    # 11. Bảng liên kết Vai trò - Quyền hạn (spms_role_permissions)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS spms_role_permissions (
        role_id TEXT NOT NULL,
        permission_id TEXT NOT NULL,
        PRIMARY KEY (role_id, permission_id),
        FOREIGN KEY (role_id) REFERENCES spms_roles(role_id) ON DELETE CASCADE,
        FOREIGN KEY (permission_id) REFERENCES spms_permissions(permission_id) ON DELETE CASCADE
    );
    """)

    # 12. Bảng Refresh Token (spms_refresh_tokens)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS spms_refresh_tokens (
        token_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        token_value TEXT NOT NULL UNIQUE,
        expiry_date TEXT NOT NULL,
        is_revoked INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES spms_users(user_id) ON DELETE CASCADE
    );
    """)

    # 13. Bảng Nhật ký kiểm toán bảo mật (spms_audit_logs)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS spms_audit_logs (
        log_id TEXT PRIMARY KEY,
        user_id TEXT,
        username TEXT NOT NULL,
        action TEXT NOT NULL,
        resource TEXT NOT NULL,
        status TEXT NOT NULL,
        ip_address TEXT,
        details TEXT,
        timestamp TEXT NOT NULL
    );
    """)

    # 14. Bảng Nhật ký kiểm toán phân hệ Tàu & Cầu bến (tbl_audit_logs - WF-VB-08)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tbl_audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        action TEXT NOT NULL,
        performed_by TEXT NOT NULL,
        change_summary TEXT,
        previous_state TEXT,
        new_state TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Đồng bộ các cột bí danh phục vụ tính tương thích (backward/forward compatibility)
    for col_def in [
        ("tbl_berths", "berth_name TEXT"),
        ("tbl_berths", "depth REAL"),
        ("tbl_vessels", "vessel_name TEXT")
    ]:
        try:
            cur.execute(f"ALTER TABLE {col_def[0]} ADD COLUMN {col_def[1]};")
        except Exception:
            pass

    try:
        cur.execute("UPDATE tbl_berths SET berth_name = name WHERE berth_name IS NULL OR berth_name = '';")
        cur.execute("UPDATE tbl_berths SET depth = depth_draft WHERE depth IS NULL;")
        cur.execute("UPDATE tbl_vessels SET vessel_name = name WHERE vessel_name IS NULL OR vessel_name = '';")
    except Exception:
        pass

    conn.commit()

    # Seed data if empty
    cur.execute("SELECT COUNT(*) FROM tbl_berths;")
    if cur.fetchone()[0] == 0:
        seed_data(conn)

    cur.execute("SELECT COUNT(*) FROM tbl_audit_logs;")
    if cur.fetchone()[0] == 0:
        sample_audits = [
            ("VESSEL", "9321483", "CREATE", "admin", "Đăng ký hồ sơ tàu EVER GIVEN"),
            ("PORT_CALL", "PC-2609-014", "ALLOCATE", "Nguyễn Văn B (ACT_BP)", "Phân bổ cầu bến B3 cho tàu MSC GEMMA"),
            ("BERTH_PLAN", "V.14", "SUBMIT", "Nguyễn Văn B (ACT_BP)", "Trình duyệt kế hoạch phân bổ bến tuần 43")
        ]
        cur.executemany("""
        INSERT INTO tbl_audit_logs (entity_type, entity_id, action, performed_by, change_summary)
        VALUES (?, ?, ?, ?, ?)
        """, sample_audits)
        conn.commit()

    cur.execute("SELECT COUNT(*) FROM spms_users;")
    if cur.fetchone()[0] == 0:
        seed_auth_data(conn)

    conn.close()

# ------------------------------------------------------------------------------
# Function: seed_data
# Mục đích sử dụng: Khởi tạo dữ liệu mẫu ban đầu cho Cầu bến (B1-B6), Danh mục tàu (Vessel Master), Port Calls, Mốc sự kiện, Dịch vụ hàng hải, Checklist và Cẩu bờ.
# ------------------------------------------------------------------------------
def seed_data(conn):
    cur = conn.cursor()
    # Seed berths
    berths = [
        ("B1", "Cầu bến B1", 0.0, 300.0, 16.0, "CAT_LAI"),
        ("B2", "Cầu bến B2", 300.0, 600.0, 16.0, "CAT_LAI"),
        ("B3", "Cầu bến B3", 600.0, 950.0, 15.5, "CAT_LAI"),
        ("B4", "Cầu bến B4", 950.0, 1300.0, 15.5, "CAT_LAI"),
        ("B5", "Cầu bến B5", 1300.0, 1650.0, 15.0, "CAT_LAI"),
        ("B6", "Cầu bến B6", 1650.0, 2040.0, 14.5, "CAT_LAI"),
    ]
    cur.executemany("INSERT INTO tbl_berths (berth_id, name, start_meter, end_meter, depth_draft, port) VALUES (?,?,?,?,?,?)", berths)

    # Seed vessels
    vessels = [
        ("9321483", "EVER GIVEN", "Evergreen", 400.0, 59.0, 16.0, 220940, 20124),
        ("9811000", "MAERSK MC-KINNEY", "Maersk Line", 399.0, 59.0, 16.0, 194849, 18270),
        ("9484431", "CMA CGM ANTOINE", "CMA CGM", 396.0, 54.0, 16.0, 186470, 16020),
        ("9229843", "MSC LAUREN", "MSC", 366.0, 48.0, 15.2, 140000, 12500),
        ("9434888", "ONE APUS", "ONE", 364.0, 51.0, 15.0, 139500, 14052),
        ("9708461", "COSCO SHIPPING UNIVERSE", "COSCO", 400.0, 58.6, 16.0, 199000, 21237),
        ("9110023", "HAI AN BELL", "Hai An Lines", 154.0, 25.0, 8.5, 14000, 1040),
        ("9234567", "TAN CANG GLORY", "SNP Shipping", 172.0, 27.5, 9.2, 18500, 1700),
        ("9618298", "MSC GEMMA", "MSC", 294.0, 40.0, 12.5, 85000, 6500),
        ("9784251", "MAERSK HANOI", "Maersk Line", 350.0, 48.2, 14.5, 145000, 11000),
        ("9622980", "OOCL VIETNAM", "OOCL", 330.0, 45.0, 14.0, 100000, 8800),
        ("9514789", "SITC HAINAN", "SITC", 180.0, 28.0, 9.5, 22000, 1800),
    ]
    cur.executemany("INSERT INTO tbl_vessels (imo, name, carrier, loa, beam, max_draft, dwt, teu) VALUES (?,?,?,?,?,?,?,?)", vessels)

    # Seed port calls
    calls = [
        ("CALL-2026-001", "9110023", "HAI AN BELL", "B1", 50.0, 220.0, "2026-11-07 06:00", "2026-11-07 18:00", "MOORED", "2026-11-07 05:30", "2026-11-07 18:00", 450, 520, 650, 970),
        ("CALL-2026-002", "9234567", "TAN CANG GLORY", "B2", 350.0, 540.0, "2026-11-07 08:00", "2026-11-07 22:00", "OPERATING", "2026-11-07 07:15", "2026-11-07 22:00", 780, 600, 420, 1380),
        ("CALL-2026-003", "9229843", "MSC LAUREN", "B3", 800.0, 1200.0, "2026-11-07 12:00", "2026-11-08 04:00", "APPROVED", "2026-11-07 11:30", "2026-11-08 04:00", 1500, 1200, 0, 2700),
        ("PC-2609-011", "9321483", "EVER GIVEN", "B1", 10.0, 290.0, "2026-10-18 08:00", "2026-10-18 16:50", "DEPARTED", "2026-10-18 07:30", "2026-10-18 16:50", 450, 250, 700, 700),
        ("PC-2609-012", "9784251", "MAERSK HANOI", "B3", 560.0, 910.0, "2026-10-18 10:30", "2026-10-19 19:45", "OPERATING", "2026-10-18 10:00", "2026-10-19 19:45", 540, 540, 950, 1080),
        ("PC-2609-014", "9618298", "MSC GEMMA", "B3", 565.0, 859.0, "2026-10-18 20:15", "2026-10-19 14:30", "CONFIRMED", "2026-10-18 13:15", "2026-10-19 19:30", 420, 380, 0, 800),
        ("PC-2609-015", "9484431", "CMA CGM ANTOINE", "B2", 310.0, 530.0, "2026-10-18 14:00", "2026-10-19 12:00", "DISRUPTION", "2026-10-18 13:30", "2026-10-19 12:00", 320, 320, 210, 640),
        ("PC-2609-016", "9622980", "OOCL VIETNAM", "B4", 930.0, 1210.0, "2026-10-18 16:00", "2026-10-19 08:00", "APPROVED", "2026-10-18 15:30", "2026-10-19 08:00", 600, 500, 0, 1100),
    ]
    cur.executemany("""
    INSERT INTO tbl_port_calls (call_id, imo, vessel_name, berth_id, start_meter, end_meter, start_time, end_time, status, eta, etd, discharge_teu, load_teu, current_moves, total_moves)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, calls)

    # Seed berth plan versions (WF-VB-04)
    versions = [
        ("V.13", "Bản Kế hoạch Bến Tuần 42/2026", "OFFICIAL_PUBLISHED", "Nguyễn Văn B (ACT_BP)", "Trần Minh D (ACT_PA)", "2026-10-18 10:00", "Đã công bố chính thức và khóa thực hiện", 1),
        ("V.14", "Bản Kế hoạch Phân bổ Cầu bến Tuần 43/2026", "PENDING_APPROVAL", "Nguyễn Văn B (ACT_BP)", None, None, "Đang chờ Trưởng phòng Điều độ phê duyệt", 0),
    ]
    cur.executemany("""
    INSERT OR REPLACE INTO tbl_berth_plan_versions (version_id, version_name, status, created_by, approved_by, effective_at, change_reason, is_locked)
    VALUES (?,?,?,?,?,?,?,?)
    """, versions)

    # Seed milestones (WF-VB-02 & WF-VB-05)
    milestones = [
        ("PC-2609-014", "ETA", "Thời gian đến phao số 0", "2026-10-18 12:00", "2026-10-18 12:30", "2026-10-18 13:15", 89.0, "2026-10-18 13:15", "AI_ENGINE", None, "CONFIRMED"),
        ("PC-2609-014", "ETD", "Thời gian rời bến", "2026-10-19 18:00", "2026-10-19 15:00", "2026-10-19 19:30", 85.0, "2026-10-19 19:30", "ACT_BP", None, "CONFIRMED"),
        ("PC-2609-014", "POB", "Hoa tiêu lên tàu (Pilot on Board)", None, None, None, None, "2026-10-18 19:00", "ACT_BP", "2026-10-18 19:05", "CONFIRMED"),
        ("PC-2609-014", "FIRST_LINE", "Dây buộc đầu tiên cập bến", None, None, None, None, "2026-10-18 20:10", "ACT_BP", "2026-10-18 20:12", "CONFIRMED"),
        ("PC-2609-014", "ALL_FAST", "Cố định toàn bộ dây (All Fast)", None, None, None, None, "2026-10-18 20:30", "ACT_BP", None, "PENDING"),
    ]
    cur.executemany("""
    INSERT INTO tbl_port_call_milestones (call_id, milestone_code, milestone_name, carrier_time, tos_time, ai_time, ai_confidence, confirmed_time, confirmed_by, actual_time, status)
    VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, milestones)

    # Seed nautical services (WF-VB-05)
    services = [
        ("PC-2609-014", "Hoa tiêu (Pilot)", "Hoa tiêu Hàng hải KV", "2026-10-18 19:00", "Phao số 0", "CONFIRMED", "2026-10-18 19:05"),
        ("PC-2609-014", "Lai dắt (Tugboat)", "Tugboat-01, Tugboat-02", "2026-10-18 19:45", "Khu quay trở", "REQUESTED", None),
        ("PC-2609-014", "Buộc dây (Mooring)", "Tổ Buộc dây Bến 3", "2026-10-18 20:10", "Cọc bích B3-12..20", "CONFIRMED", None),
    ]
    cur.executemany("""
    INSERT INTO tbl_nautical_services (call_id, service_type, provider_id, requested_time, location, confirmation_status, actual_time)
    VALUES (?,?,?,?,?,?,?)
    """, services)

    # Seed readiness checklist (WF-VB-05)
    checklist = [
        ("PC-2609-014", 1, "Bến trống & Đệm va an toàn", "PASS", "ACT_RO (18/10 18:30)", "Kiểm tra đo đạc đạt chuẩn 15m"),
        ("PC-2609-014", 2, "Điều kiện Thời tiết & Thủy triều", "PASS", "Trạm Khí tượng", "Gió cấp 4 < cấp 6; Tầm nhìn 3 hải lý; Triều cường +2.4m"),
        ("PC-2609-014", 3, "Nguồn lực Cầu bờ (QC-05, QC-06, QC-07)", "PASS", "Tổ Thiết bị & IoT", "3 cẩu sẵn sàng vận hành"),
        ("PC-2609-014", 4, "Dịch vụ Hàng hải (Hoa tiêu + 02 Tàu lai)", "PENDING", "Đội Tàu lai SNP", "Đang bố trí tàu lai thứ 2"),
        ("PC-2609-014", 5, "Thủ tục Cục Hàng hải VN & Chi cục Hải quan", "PASS", "Phòng Thủ tục Cảng", "Đã thông quan & đính kèm lệnh điều động"),
    ]
    cur.executemany("""
    INSERT INTO tbl_readiness_checklist (call_id, step_number, item_name, status, checked_by, note)
    VALUES (?,?,?,?,?,?)
    """, checklist)

    # Seed crane assignments (WF-VB-06)
    cranes = [
        ("PC-2609-012", "QC-05", "Bay 14", 540, 480, "WORKING", 28.5),
        ("PC-2609-012", "QC-06", "Bay 22", 540, 470, "WORKING", 28.5),
        ("PC-2609-015", "QC-02", "Bay 08", 320, 90, "PAUSED", 0.0),
        ("PC-2609-015", "QC-03", "Bay 18", 320, 120, "WORKING", 24.5),
        ("PC-2609-011", "QC-01", "Bay 12", 700, 700, "STANDBY", 0.0),
    ]
    cur.executemany("""
    INSERT INTO tbl_crane_assignments (call_id, crane_id, bay_no, planned_moves, completed_moves, crane_status, moves_per_hour)
    VALUES (?,?,?,?,?,?,?)
    """, cranes)

    # Seed yard slots
    slots = []
    for b in ["A", "B", "C"]:
        for bay in range(1, 5):
            for row in range(1, 5):
                for tier in range(1, 5):
                    slot_id = f"{b}-{bay:02d}-{row:02d}-{tier}"
                    is_reefer_plug = 1 if (row == 4 and tier <= 3) else 0
                    slots.append((slot_id, b, bay, row, tier, is_reefer_plug, "AVAILABLE", None, None))
    cur.executemany("INSERT INTO tbl_yard_slots (slot_id, block, bay, row, tier, is_reefer_plug, status, container_no, locked_by) VALUES (?,?,?,?,?,?,?,?,?)", slots)

    # Seed containers
    containers = [
        ("EMCU8921470", "40HC", 28400.0, 0, None, 0, None, "A-01-01-1"),
        ("MSCU1294801", "20GP", 14200.0, 0, None, 0, None, "A-01-01-2"),
        ("TCKU9012384", "40RH", 22500.0, 0, None, 1, -18.0, "A-01-04-1"),
        ("CMAU7483920", "20GP", 26800.0, 1, "Class 3 - Flammable", 0, None, "B-02-02-1"),
        ("ONEU3391024", "40HC", 11200.0, 0, None, 0, None, "C-03-03-1"),
    ]
    cur.executemany("""
    INSERT INTO tbl_containers (container_no, iso_type, weight_kg, is_hazardous, imdg_class, is_reefer, set_temp_celsius, slot_id)
    VALUES (?,?,?,?,?,?,?,?)
    """, containers)

    # Update occupied slots
    for c in containers:
        cur.execute("UPDATE tbl_yard_slots SET status = 'OCCUPIED', container_no = ? WHERE slot_id = ?", (c[0], c[7]))

    # Seed alert
    cur.execute("""
    INSERT INTO tbl_yard_alerts (alert_id, severity, code, container_no, slot_id, message, timestamp)
    VALUES ('ALT-001', 'WARNING', 'WARN_REEFER_POWER_CHECK', 'TCKU9012384', 'A-01-04-1', 'Container lạnh TCKU9012384 kết nối lưới 3 pha 380V. Nhiệt độ: -18.2°C (Bình thường)', ?)
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))

    conn.commit()

# ------------------------------------------------------------------------------
# Function: seed_auth_data
# Mục đích sử dụng: Khởi tạo dữ liệu mẫu cho các vai trò (spms_roles), quyền hạn (spms_permissions) và tài khoản người dùng mặc định kèm mật khẩu băm PBKDF2 (admin, dispatcher, operator, security, accountant, customer)
# ------------------------------------------------------------------------------
def seed_auth_data(conn):
    try:
        from auth_utils import hash_password
    except ImportError:
        # Fallback if imported from parent directory
        from backend.auth_utils import hash_password

    cur = conn.cursor()

    # 1. Seed Roles
    roles = [
        ("ROLE_ADMIN", "Quản trị viên Hệ thống", "Toàn quyền quản trị danh mục, người dùng, hệ thống và audit log"),
        ("ROLE_DISPATCHER", "Điều độ viên Cảng biển", "Lập kế hoạch cầu bến, điều động tàu, phân bổ ô bãi và cẩu"),
        ("ROLE_OPERATOR", "Nhân viên Khai thác Cảng", "Thao tác nâng hạ, kiểm đếm container và đảo chuyển bãi"),
        ("ROLE_SECURITY", "Lực lượng An ninh Cổng", "Kiểm soát xe cổng Smart Gate, camera OCR biển số và barie"),
        ("ROLE_ACCOUNTANT", "Kế toán Cảng", "Quản lý hóa đơn dịch vụ, ký quỹ ePort và biểu phí cảng"),
        ("ROLE_CUSTOMER", "Khách hàng Doanh nghiệp Logistics", "Tra cứu tàu, container, đặt lịch hẹn và e-EIR"),
    ]
    cur.executemany("INSERT INTO spms_roles (role_id, role_name, description) VALUES (?,?,?)", roles)

    # 2. Seed Permissions
    permissions = [
        ("system:admin", "Quản trị toàn hệ thống", "AUTH", "Toàn quyền cấu hình và quản trị hệ thống"),
        ("user:manage", "Quản lý tài khoản người dùng", "AUTH", "Xem, tạo, sửa và khóa tài khoản"),
        ("audit:read", "Xem nhật ký bảo mật", "AUTH", "Truy xuất lịch sử tác nghiệp và đăng nhập"),
        ("vessel:read", "Xem danh sách tàu và lịch cập bến", "VESSEL", "Xem danh mục tàu, bến và port calls"),
        ("vessel:manage", "Quản trị danh mục tàu & Port Calls", "VESSEL", "Thêm, cập nhật, hủy bỏ kế hoạch cập bến"),
        ("berth:optimize", "Tối ưu hóa xếp cầu bến AI", "VESSEL", "Chạy mô hình tối ưu berth allocation"),
        ("yard:read", "Xem trạng thái bãi và container", "YARD", "Xem bản đồ bãi 2D, danh sách container"),
        ("yard:move", "Di chuyển đảo bãi container", "YARD", "Thực hiện lệnh atomic move container"),
        ("container:manage", "Quản trị danh mục container", "YARD", "Thêm, sửa, xóa thông tin container"),
        ("gate:control", "Kiểm soát làn cổng Smart Gate", "GATE", "Điều khiển barie và xử lý ngoại lệ xe cổng"),
        ("billing:manage", "Quản trị thanh toán và hóa đơn", "BILLING", "Xuất hóa đơn và xác nhận thanh toán"),
    ]
    cur.executemany("INSERT INTO spms_permissions (permission_id, permission_name, module, description) VALUES (?,?,?,?)", permissions)

    # 3. Seed Role-Permissions
    role_perms = [
        # ADMIN: All permissions
        ("ROLE_ADMIN", "system:admin"),
        ("ROLE_ADMIN", "user:manage"),
        ("ROLE_ADMIN", "audit:read"),
        ("ROLE_ADMIN", "vessel:read"),
        ("ROLE_ADMIN", "vessel:manage"),
        ("ROLE_ADMIN", "berth:optimize"),
        ("ROLE_ADMIN", "yard:read"),
        ("ROLE_ADMIN", "yard:move"),
        ("ROLE_ADMIN", "container:manage"),
        ("ROLE_ADMIN", "gate:control"),
        ("ROLE_ADMIN", "billing:manage"),
        # DISPATCHER
        ("ROLE_DISPATCHER", "vessel:read"),
        ("ROLE_DISPATCHER", "vessel:manage"),
        ("ROLE_DISPATCHER", "berth:optimize"),
        ("ROLE_DISPATCHER", "yard:read"),
        ("ROLE_DISPATCHER", "yard:move"),
        # OPERATOR
        ("ROLE_OPERATOR", "yard:read"),
        ("ROLE_OPERATOR", "yard:move"),
        ("ROLE_OPERATOR", "container:manage"),
        # SECURITY
        ("ROLE_SECURITY", "gate:control"),
        ("ROLE_SECURITY", "yard:read"),
        # ACCOUNTANT
        ("ROLE_ACCOUNTANT", "billing:manage"),
        # CUSTOMER
        ("ROLE_CUSTOMER", "vessel:read"),
        ("ROLE_CUSTOMER", "yard:read"),
    ]
    cur.executemany("INSERT INTO spms_role_permissions (role_id, permission_id) VALUES (?,?)", role_perms)

    # 4. Seed Users
    default_users = [
        ("USR-001", "admin", "Admin@123", "Nguyễn Văn Quản Trị", "admin.spms@saigonnewport.com.vn", "0901234567", "ALL", "Phòng CNTT", "ROLE_ADMIN"),
        ("USR-002", "dispatcher1", "Dispatch@123", "Trần Đình Điều Độ", "dieu_do.catlai@saigonnewport.com.vn", "0902345678", "CTL", "Phòng Điều độ Tàu & Yard", "ROLE_DISPATCHER"),
        ("USR-003", "operator1", "Oper@123", "Lê Văn Hiện Trường", "khai_thac.catlai@saigonnewport.com.vn", "0903456789", "CTL", "Phòng Khai thác Container", "ROLE_OPERATOR"),
        ("USR-004", "security1", "Sec@123", "Hoàng An Ninh Cổng", "an_ninh.catlai@saigonnewport.com.vn", "0904567890", "CTL", "Đội Bảo vệ Cổng Smart Gate", "ROLE_SECURITY"),
        ("USR-005", "accountant1", "Acc@123", "Phạm Thị Kế Toán", "ke_toan@saigonnewport.com.vn", "0905678901", "ALL", "Phòng Kế toán & Dịch vụ", "ROLE_ACCOUNTANT"),
        ("USR-006", "customer1", "Cust@123", "Công ty Vận tải Biển Đông", "customer@dongshipping.com", "0906789012", "CTL", "Khách hàng Logistics", "ROLE_CUSTOMER"),
    ]

    for uid, uname, pwd, fname, email, phone, term, dept, role in default_users:
        h, salt = hash_password(pwd)
        cur.execute("""
        INSERT INTO spms_users (user_id, username, password_hash, salt, full_name, email, phone_number, terminal_code, department)
        VALUES (?,?,?,?,?,?,?,?,?)
        """, (uid, uname, h, salt, fname, email, phone, term, dept))
        cur.execute("INSERT INTO spms_user_roles (user_id, role_id) VALUES (?,?)", (uid, role))

    conn.commit()

# Initialize database on module import
init_db()
