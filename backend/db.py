import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spms.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

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
        FOREIGN KEY (imo) REFERENCES tbl_vessels(imo) ON DELETE CASCADE
    );
    """)

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

    conn.commit()

    # Seed data if empty
    cur.execute("SELECT COUNT(*) FROM tbl_berths;")
    if cur.fetchone()[0] == 0:
        seed_data(conn)

    cur.execute("SELECT COUNT(*) FROM spms_users;")
    if cur.fetchone()[0] == 0:
        seed_auth_data(conn)

    conn.close()

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
    ]
    cur.executemany("INSERT INTO tbl_vessels (imo, name, carrier, loa, beam, max_draft, dwt, teu) VALUES (?,?,?,?,?,?,?,?)", vessels)

    # Seed port calls
    calls = [
        ("CALL-2026-001", "9110023", "HAI AN BELL", "B1", 50.0, 220.0, "2026-11-07 06:00", "2026-11-07 18:00", "MOORED", "2026-11-07 05:30", "2026-11-07 18:00", 450, 520, 650, 970),
        ("CALL-2026-002", "9234567", "TAN CANG GLORY", "B2", 350.0, 540.0, "2026-11-07 08:00", "2026-11-07 22:00", "OPERATING", "2026-11-07 07:15", "2026-11-07 22:00", 780, 600, 420, 1380),
        ("CALL-2026-003", "9229843", "MSC LAUREN", "B3", 800.0, 1200.0, "2026-11-07 12:00", "2026-11-08 04:00", "APPROVED", "2026-11-07 11:30", "2026-11-08 04:00", 1500, 1200, 0, 2700),
    ]
    cur.executemany("""
    INSERT INTO tbl_port_calls (call_id, imo, vessel_name, berth_id, start_meter, end_meter, start_time, end_time, status, eta, etd, discharge_teu, load_teu, current_moves, total_moves)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, calls)

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
