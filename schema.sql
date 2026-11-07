-- ========================================================
-- TỔNG CÔNG TY TÂN CẢNG SÀI GÒN - HỆ THỐNG SPMS
-- TOÀN BỘ LƯỢC ĐỒ CSDL POSTGIS (MODULE 1, MODULE 2 & AUTH)
-- ========================================================


-- ----------------------------------------------------
-- File: 01_schema_auth_rbac.sql
-- ----------------------------------------------------
-- Kịch bản khởi tạo lược đồ Cơ sở dữ liệu Xác thực & Phân quyền SPMS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Bảng Vai trò người dùng (spms_roles)
CREATE TABLE IF NOT EXISTS spms_roles (
    role_id VARCHAR(32) PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255),
    is_system_role BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Bảng Danh mục Quyền hạn chi tiết (spms_permissions)
CREATE TABLE IF NOT EXISTS spms_permissions (
    permission_id VARCHAR(64) PRIMARY KEY,
    permission_name VARCHAR(100) NOT NULL,
    module VARCHAR(32) NOT NULL,
    description VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Bảng Tài khoản người dùng (spms_users)
CREATE TABLE IF NOT EXISTS spms_users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    phone_number VARCHAR(20),
    terminal_code VARCHAR(10) NOT NULL DEFAULT 'CTL', -- CTL (Cát Lái), TCIT, TCTT, ALL
    department VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_attempts INT NOT NULL DEFAULT 0,
    lock_until TIMESTAMP WITH TIME ZONE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Bảng liên kết Người dùng - Vai trò (spms_user_roles)
CREATE TABLE IF NOT EXISTS spms_user_roles (
    user_id UUID NOT NULL REFERENCES spms_users(user_id) ON DELETE CASCADE,
    role_id VARCHAR(32) NOT NULL REFERENCES spms_roles(role_id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(50),
    PRIMARY KEY (user_id, role_id)
);

-- 5. Bảng liên kết Vai trò - Quyền hạn (spms_role_permissions)
CREATE TABLE IF NOT EXISTS spms_role_permissions (
    role_id VARCHAR(32) NOT NULL REFERENCES spms_roles(role_id) ON DELETE CASCADE,
    permission_id VARCHAR(64) NOT NULL REFERENCES spms_permissions(permission_id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- 6. Bảng lưu trữ Refresh Token (spms_refresh_tokens)
CREATE TABLE IF NOT EXISTS spms_refresh_tokens (
    token_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES spms_users(user_id) ON DELETE CASCADE,
    token_value VARCHAR(255) NOT NULL UNIQUE,
    expiry_date TIMESTAMP WITH TIME ZONE NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_agent VARCHAR(255),
    client_ip VARCHAR(45)
);

-- Tạo các chỉ mục tối ưu hiệu năng truy vấn phân quyền
CREATE INDEX idx_users_username ON spms_users(username);
CREATE INDEX idx_users_email ON spms_users(email);
CREATE INDEX idx_users_terminal ON spms_users(terminal_code);
CREATE INDEX idx_refresh_token_val ON spms_refresh_tokens(token_value);

-- ----------------------------------------------------
-- File: 02_schema_user_role_audit.sql
-- ----------------------------------------------------
-- Kịch bản DDL Cơ sở Dữ liệu Phân hệ Quản trị User, Role & Audit Log SPMS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Bảng Vai trò (spms_roles)
CREATE TABLE IF NOT EXISTS spms_roles (
    role_id VARCHAR(32) PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255),
    is_system_role BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Bảng Quyền hạn chức năng (spms_permissions)
CREATE TABLE IF NOT EXISTS spms_permissions (
    permission_id VARCHAR(64) PRIMARY KEY,
    permission_name VARCHAR(100) NOT NULL,
    module VARCHAR(32) NOT NULL,
    description VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Bảng Người dùng (spms_users)
CREATE TABLE IF NOT EXISTS spms_users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    phone_number VARCHAR(20),
    terminal_code VARCHAR(10) NOT NULL DEFAULT 'CTL',
    department VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_attempts INT NOT NULL DEFAULT 0,
    lock_until TIMESTAMP WITH TIME ZONE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Bảng liên kết N-N: User - Role (spms_user_roles)
CREATE TABLE IF NOT EXISTS spms_user_roles (
    user_id UUID NOT NULL REFERENCES spms_users(user_id) ON DELETE CASCADE,
    role_id VARCHAR(32) NOT NULL REFERENCES spms_roles(role_id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(50),
    PRIMARY KEY (user_id, role_id)
);

-- 5. Bảng liên kết N-N: Role - Permission (spms_role_permissions)
CREATE TABLE IF NOT EXISTS spms_role_permissions (
    role_id VARCHAR(32) NOT NULL REFERENCES spms_roles(role_id) ON DELETE CASCADE,
    permission_id VARCHAR(64) NOT NULL REFERENCES spms_permissions(permission_id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- 6. Bảng Nhật ký Kiểm toán Tự động (spms_audit_logs)
CREATE TABLE IF NOT EXISTS spms_audit_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    username VARCHAR(50),
    user_role VARCHAR(50),
    terminal_code VARCHAR(10),
    action VARCHAR(100) NOT NULL,
    module VARCHAR(50) NOT NULL,
    http_method VARCHAR(10) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    user_agent TEXT,
    status_code INT NOT NULL,
    execution_time_ms BIGINT NOT NULL,
    request_payload JSONB,
    response_payload JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Thiết lập các chỉ mục tối ưu hóa hiệu năng tìm kiếm nhật ký kiểm toán
CREATE INDEX idx_audit_created_at ON spms_audit_logs(created_at DESC);
CREATE INDEX idx_audit_username ON spms_audit_logs(username);
CREATE INDEX idx_audit_module_action ON spms_audit_logs(module, action);
CREATE INDEX idx_audit_terminal ON spms_audit_logs(terminal_code);
CREATE INDEX idx_audit_req_payload ON spms_audit_logs USING GIN (request_payload);

-- ----------------------------------------------------
-- File: 01_schema_vessel_berth.sql
-- ----------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS marine;

-- 1. Bảng Danh mục tàu biển quốc tế (Vessel Master)
CREATE TABLE marine.tbl_vessels (
    vessel_id VARCHAR(64) PRIMARY KEY,
    imo_number VARCHAR(7) UNIQUE NOT NULL,
    vessel_name VARCHAR(128) NOT NULL,
    call_sign VARCHAR(32) NOT NULL,
    flag_country VARCHAR(64) NOT NULL,
    carrier_code VARCHAR(16) NOT NULL,
    loa_meters NUMERIC(6, 2) NOT NULL,
    beam_meters NUMERIC(5, 2) NOT NULL,
    max_draft_meters NUMERIC(4, 2) NOT NULL,
    dwt NUMERIC(10, 2) NOT NULL,
    teu_capacity INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 2. Bảng Hạ tầng cầu bến cảng biển
CREATE TABLE marine.tbl_berths (
    berth_id VARCHAR(32) PRIMARY KEY,
    terminal_code VARCHAR(16) NOT NULL,
    berth_name VARCHAR(64) NOT NULL,
    start_meter NUMERIC(7, 2) NOT NULL,
    end_meter NUMERIC(7, 2) NOT NULL,
    design_depth_meters NUMERIC(4, 2) NOT NULL,
    max_displacement_tonnage NUMERIC(10, 2) NOT NULL,
    geom geometry(LineString, 4326),
    status VARCHAR(24) DEFAULT 'ACTIVE' NOT NULL
);

-- 3. Bảng Lượt tàu ghé cảng (Port Call)
CREATE TABLE marine.tbl_port_calls (
    call_id VARCHAR(64) PRIMARY KEY,
    vessel_id VARCHAR(64) REFERENCES marine.tbl_vessels(vessel_id) NOT NULL,
    inbound_voyage VARCHAR(32) NOT NULL,
    outbound_voyage VARCHAR(32) NOT NULL,
    terminal_code VARCHAR(16) NOT NULL,
    eta TIMESTAMPTZ NOT NULL,
    etd TIMESTAMPTZ NOT NULL,
    ata TIMESTAMPTZ,
    atd TIMESTAMPTZ,
    arrival_draft NUMERIC(4, 2) NOT NULL,
    discharge_teu INT DEFAULT 0 NOT NULL,
    load_teu INT DEFAULT 0 NOT NULL,
    status VARCHAR(32) DEFAULT 'PLANNED' NOT NULL,
    version BIGINT DEFAULT 0 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 4. Bảng Kế hoạch Phân bổ Cầu bến (Berth Allocation)
CREATE TABLE marine.tbl_berth_allocations (
    allocation_id VARCHAR(64) PRIMARY KEY,
    call_id VARCHAR(64) UNIQUE REFERENCES marine.tbl_port_calls(call_id) NOT NULL,
    berth_id VARCHAR(32) REFERENCES marine.tbl_berths(berth_id) NOT NULL,
    allocated_start_time TIMESTAMPTZ NOT NULL,
    allocated_end_time TIMESTAMPTZ NOT NULL,
    start_meter NUMERIC(7, 2) NOT NULL,
    end_meter NUMERIC(7, 2) NOT NULL,
    safe_margin_bow_meters NUMERIC(4, 2) DEFAULT 15.0 NOT NULL,
    safe_margin_stern_meters NUMERIC(4, 2) DEFAULT 15.0 NOT NULL,
    allocation_status VARCHAR(24) DEFAULT 'TENTATIVE' NOT NULL,
    approved_by VARCHAR(64),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 5. Bảng Mốc Vận hành Khai thác Cảng (Operation Milestones)
CREATE TABLE marine.tbl_operation_milestones (
    milestone_id VARCHAR(64) PRIMARY KEY,
    call_id VARCHAR(64) REFERENCES marine.tbl_port_calls(call_id) NOT NULL,
    milestone_type VARCHAR(32) NOT NULL,
    recorded_time TIMESTAMPTZ NOT NULL,
    recorded_by VARCHAR(64) NOT NULL,
    source VARCHAR(24) DEFAULT 'DISPATCHER' NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Chỉ mục tối ưu hóa truy vấn không gian & thời gian
CREATE INDEX idx_berth_geom ON marine.tbl_berths USING GIST(geom);
CREATE INDEX idx_berth_alloc_time ON marine.tbl_berth_allocations (berth_id, allocated_start_time, allocated_end_time);
CREATE INDEX idx_port_call_eta ON marine.tbl_port_calls (terminal_code, eta);
CREATE INDEX idx_vessel_imo ON marine.tbl_vessels (imo_number);

-- ----------------------------------------------------
-- File: 01_schema_yard_container.sql
-- ----------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS yard;

-- 1. Bảng Khối Bãi Container (Yard Blocks)
CREATE TABLE yard.tbl_yard_blocks (
    block_id VARCHAR(32) PRIMARY KEY,
    terminal_code VARCHAR(16) NOT NULL,
    block_name VARCHAR(64) NOT NULL,
    total_bays INT NOT NULL,
    total_rows INT NOT NULL,
    max_tier INT DEFAULT 5 NOT NULL,
    block_type VARCHAR(24) DEFAULT 'GENERAL' NOT NULL, -- GENERAL, REEFER, DG, EMPTY
    boundary_geom geometry(Polygon, 4326),
    status VARCHAR(24) DEFAULT 'ACTIVE' NOT NULL
);

-- 2. Bảng Ô Bãi Chi Tiết (Yard Slots)
CREATE TABLE yard.tbl_yard_slots (
    slot_id VARCHAR(64) PRIMARY KEY,
    block_id VARCHAR(32) REFERENCES yard.tbl_yard_blocks(block_id) NOT NULL,
    bay_no INT NOT NULL,
    row_no INT NOT NULL,
    tier_no INT NOT NULL,
    slot_status VARCHAR(24) DEFAULT 'AVAILABLE' NOT NULL, -- AVAILABLE, RESERVED, OCCUPIED, BLOCKED
    is_reefer_plug BOOLEAN DEFAULT FALSE NOT NULL,
    max_weight_capacity NUMERIC(8, 2) DEFAULT 35000.0 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT uq_slot_coordinate UNIQUE (block_id, bay_no, row_no, tier_no)
);

-- 3. Bảng Hồ Sơ Container (Containers Master)
CREATE TABLE yard.tbl_containers (
    container_id VARCHAR(64) PRIMARY KEY,
    container_no VARCHAR(11) UNIQUE NOT NULL, -- Chuẩn ISO 6346 (VD: TCLU1234567)
    iso_code VARCHAR(4) NOT NULL,             -- VD: 22G1, 45G1, 45R1
    carrier_code VARCHAR(16) NOT NULL,
    size_feet INT NOT NULL,                   -- 20, 40, 45
    tare_weight NUMERIC(8, 2) NOT NULL,
    payload_weight NUMERIC(8, 2) NOT NULL,
    gross_weight NUMERIC(8, 2) NOT NULL,
    is_dangerous BOOLEAN DEFAULT FALSE NOT NULL,
    imo_class VARCHAR(16),
    is_reefer BOOLEAN DEFAULT FALSE NOT NULL,
    set_temperature NUMERIC(5, 2),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 4. Bảng Lượt Lưu Bãi & Trạng Thái Tọa Độ Hiện Tại (Container Stays)
CREATE TABLE yard.tbl_container_stays (
    stay_id VARCHAR(64) PRIMARY KEY,
    container_id VARCHAR(64) REFERENCES yard.tbl_containers(container_id) NOT NULL,
    terminal_code VARCHAR(16) NOT NULL,
    current_slot_id VARCHAR(64) REFERENCES yard.tbl_yard_slots(slot_id),
    status VARCHAR(32) DEFAULT 'STACKED' NOT NULL, -- INBOUND, STACKED, MOUNTED, OUTBOUND
    customs_hold BOOLEAN DEFAULT FALSE NOT NULL,
    carrier_hold BOOLEAN DEFAULT FALSE NOT NULL,
    inbound_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    outbound_time TIMESTAMPTZ,
    version BIGINT DEFAULT 0 NOT NULL
);

-- Chỉ mục hiệu năng cao
CREATE INDEX idx_yard_slot_lookup ON yard.tbl_yard_slots (block_id, bay_no, row_no, tier_no);
CREATE INDEX idx_container_iso ON yard.tbl_containers (container_no);
CREATE INDEX idx_container_stay_status ON yard.tbl_container_stays (terminal_code, status);
CREATE INDEX idx_block_geom ON yard.tbl_yard_blocks USING GIST(boundary_geom);

-- ----------------------------------------------------
-- File: 02_schema_ai_stacking_recommendation.sql
-- ----------------------------------------------------
-- DDL Khởi tạo CSDL Đề xuất Xếp bãi AI SPMS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Bảng Phiên Đề xuất Xếp bãi AI (spms_ai_stacking_recommendations)
CREATE TABLE IF NOT EXISTS spms_ai_stacking_recommendations (
    recommendation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    container_no VARCHAR(11) NOT NULL REFERENCES spms_containers(container_no),
    source_type VARCHAR(20) NOT NULL,            -- GATE_IN, DISCHARGE_VESSEL, SHIFTING_INTERNAL
    source_location VARCHAR(32),                 -- Cổng số, hầm tàu hoặc ô nguồn
    allocated_slot_id VARCHAR(32) REFERENCES spms_yard_slots(slot_id),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING, ACCEPTED, REJECTED, EXPIRED
    confidence_score NUMERIC(5,4) NOT NULL,      -- Độ tin cậy thuật toán (0.0000 - 1.0000)
    reshuffle_risk_index NUMERIC(4,3) NOT NULL,  -- Nguy cơ đảo chuyển dự báo (0.000 - 1.000)
    recommendation_reason TEXT,                  -- Giải trình thuật toán AI
    dispatcher_feedback VARCHAR(20),             -- ACCURATE, OVERRIDDEN, REJECTED
    dispatcher_override_reason VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- 2. Bảng Danh sách Ô Ứng viên Đạt chuẩn do AI Xếp hạng (spms_ai_stacking_candidates)
CREATE TABLE IF NOT EXISTS spms_ai_stacking_candidates (
    candidate_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recommendation_id UUID NOT NULL REFERENCES spms_ai_stacking_recommendations(recommendation_id) ON DELETE CASCADE,
    slot_id VARCHAR(32) NOT NULL REFERENCES spms_yard_slots(slot_id),
    ranking_order INT NOT NULL,                  -- Thứ hạng (Top 1, 2, 3)
    total_score NUMERIC(8,4) NOT NULL,           -- Tổng điểm đánh giá
    turnaround_cost NUMERIC(8,2) NOT NULL,       -- Điểm chi phí cẩu RTG/xe kéo
    weight_stability_score NUMERIC(5,2) NOT NULL,-- Điểm an toàn trọng tải xếp tầng
    departure_alignment_score NUMERIC(5,2) NOT NULL, -- Điểm trùng khớp thứ tự xuất hàng
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stack_rec_container ON spms_ai_stacking_recommendations(container_no);
CREATE INDEX idx_stack_rec_status ON spms_ai_stacking_recommendations(status);
CREATE INDEX idx_stack_candidates_rec ON spms_ai_stacking_candidates(recommendation_id);

-- ----------------------------------------------------
-- File: 03_schema_yard_alerts.sql
-- ----------------------------------------------------
-- 1. Bảng Quản trị Sự kiện Cảnh báo Tổng thể Bãi (spms_yard_alerts)
CREATE TABLE IF NOT EXISTS spms_yard_alerts (
    alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_code VARCHAR(50) NOT NULL,             -- OVERDUE_DWELL, REEFER_TEMP_BREACH, IMDG_SEGREGATION_FAIL
    severity VARCHAR(20) NOT NULL,               -- INFO, WARNING, CRITICAL, FATAL
    category VARCHAR(30) NOT NULL,               -- YARD_STORAGE, REEFER_COLD_CHAIN, HAZARDOUS_SAFETY
    container_no VARCHAR(11) REFERENCES spms_containers(container_no),
    slot_id VARCHAR(32) REFERENCES spms_yard_slots(slot_id),
    block_id VARCHAR(16) NOT NULL,
    alert_title VARCHAR(200) NOT NULL,
    alert_details JSONB NOT NULL,                -- Thông số chi tiết cảnh báo
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, ACKNOWLEDGED, RESOLVED, SUPPRESSED
    acknowledged_by VARCHAR(50),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(50),
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Bảng Theo dõi Cảnh báo Chuỗi Lạnh Container Reefer (spms_reefer_telemetry_alerts)
CREATE TABLE IF NOT EXISTS spms_reefer_telemetry_alerts (
    reefer_alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id UUID NOT NULL REFERENCES spms_yard_alerts(alert_id) ON DELETE CASCADE,
    container_no VARCHAR(11) NOT NULL,
    set_point_celsius NUMERIC(4,2) NOT NULL,
    actual_supply_celsius NUMERIC(4,2) NOT NULL,
    actual_return_celsius NUMERIC(4,2) NOT NULL,
    temp_deviation_celsius NUMERIC(4,2) NOT NULL, -- Độ lệch nhiệt độ (|actual - set|)
    power_status VARCHAR(20) NOT NULL,           -- CONNECTED, UNPLUGGED, POWER_OUTAGE
    duration_minutes INT NOT NULL DEFAULT 0,     -- Thời lượng xảy ra sự cố (phút)
    technician_work_order_id VARCHAR(36)
);

-- 3. Bảng Lưu vết Vi phạm Cách ly Hàng Nguy hiểm IMDG (spms_imdg_safety_violations)
CREATE TABLE IF NOT EXISTS spms_imdg_safety_violations (
    violation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id UUID NOT NULL REFERENCES spms_yard_alerts(alert_id) ON DELETE CASCADE,
    container_a_no VARCHAR(11) NOT NULL,
    imdg_class_a VARCHAR(10) NOT NULL,
    slot_a_id VARCHAR(32) NOT NULL,
    container_b_no VARCHAR(11) NOT NULL,
    imdg_class_b VARCHAR(10) NOT NULL,
    slot_b_id VARCHAR(32) NOT NULL,
    actual_distance_bays INT NOT NULL,           -- Khoảng cách thực tế tính theo số Bay
    required_min_bays INT NOT NULL,              -- Khoảng cách tối thiểu theo IMDG Code
    violation_level VARCHAR(20) NOT NULL         -- ADJACENT_PROHIBITED, SAME_BAY_FORBIDDEN
);

CREATE INDEX idx_yard_alerts_status ON spms_yard_alerts(status);
CREATE INDEX idx_yard_alerts_category ON spms_yard_alerts(category);
CREATE INDEX idx_yard_alerts_container ON spms_yard_alerts(container_no);
CREATE INDEX idx_yard_alerts_block ON spms_yard_alerts(block_id);
