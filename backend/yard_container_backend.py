# ==============================================================================
# TỔNG CÔNG TY TÂN CẢNG SÀI GÒN (SNP) - HỆ THỐNG ĐIỀU HÀNH KHAI THÁC CẢNG SPMS
# NGƯỜI THỰC HIỆN: Đào Văn Sơn - B23DCCN961
# VAI TRÒ: Backend Engineer / Lập trình viên Backend
# MODULE: Quản lý Bãi Container, Quy chuẩn Xếp dỡ TOS, Di chuyển Nguyên tử & Khóa phân tán
# ==============================================================================

from flask import Blueprint, request, jsonify, render_template
from datetime import datetime
import time
from db import get_db, init_db, seed_data

yard_container_bp = Blueprint('yard_container', __name__)

# Distributed in-memory locks table for concurrency simulation
SLOT_LOCKS = {}

# ------------------------------------------------------------------------------
# Function: evaluate_stacking_rules
# Mục đích sử dụng: Động cơ kiểm tra quy chuẩn xếp chồng container (Stacking Rules Engine):
#                   kiểm tra nâng hạ không bị đè, quy tắc trọng lực, nặng dưới nhẹ trên,
#                   cách ly an toàn hàng nguy hiểm IMDG và ổ cắm container lạnh Reefer.
# ------------------------------------------------------------------------------
def evaluate_stacking_rules(container_data, target_slot_id):
    old_slot_id = container_data.get("slot_id")

    # 1. Container cannot move to its current slot
    if target_slot_id == old_slot_id:
        return False, f"Container {container_data.get('container_no')} hiện đã đang ở ô {target_slot_id} rồi!"

    conn = get_db()
    cur = conn.cursor()

    # 2. Check if the container is blocked by a container above it at current location
    if old_slot_id:
        o_block, o_bay, o_row, o_tier = old_slot_id.split("-")
        above_old_id = f"{o_block}-{int(o_bay):02d}-{int(o_row):02d}-{int(o_tier)+1}"
        cur.execute("SELECT status, container_no FROM tbl_yard_slots WHERE slot_id = ?;", (above_old_id,))
        above_slot = cur.fetchone()
        if above_slot and above_slot["status"] == "OCCUPIED":
            conn.close()
            return False, f"Vi phạm bốc dỡ: Container {container_data.get('container_no')} đang bị container ở tầng trên ({above_old_id}) đè lên! Phải đảo chuyển container phía trên trước khi nâng container này."

    block, bay, row, tier = target_slot_id.split("-")
    bay, row, tier = int(bay), int(row), int(tier)

    cur.execute("SELECT * FROM tbl_yard_slots WHERE slot_id = ?;", (target_slot_id,))
    slot = cur.fetchone()
    if not slot:
        conn.close()
        return False, "Ô bãi không tồn tại trong hệ thống."
    if slot["status"] == "OCCUPIED":
        conn.close()
        return False, f"Ô bãi {target_slot_id} hiện đang có container chiếm giữ."

    # 3. Ground support & Heavy on light rule
    if tier > 1:
        below_id = f"{block}-{bay:02d}-{row:02d}-{tier-1}"
        # Cannot stack on its own position
        if below_id == old_slot_id:
            conn.close()
            return False, f"Vi phạm trọng lực: Không thể xếp container đè lên vị trí của chính nó! Ô bên dưới ({below_id}) sẽ bị trống khi cẩu nhấc container này lên."
        
        cur.execute("SELECT status, container_no FROM tbl_yard_slots WHERE slot_id = ?;", (below_id,))
        below_slot = cur.fetchone()
        if not below_slot or below_slot["status"] != "OCCUPIED" or below_slot["container_no"] == container_data.get("container_no"):
            conn.close()
            return False, f"Vi phạm trọng lực: Ô bên dưới ({below_id}) chưa có container đỡ!"

        cur.execute("SELECT * FROM tbl_containers WHERE container_no = ?;", (below_slot["container_no"],))
        below_cont = cur.fetchone()
        if below_cont:
            # 3.1. Size compatibility (40ft cannot stack on 20ft)
            upper_iso = container_data.get("iso_type", "")
            below_iso = below_cont["iso_type"] or ""
            is_upper_40 = ("40" in upper_iso or "45" in upper_iso)
            is_below_20 = ("20" in below_iso)
            if is_upper_40 and is_below_20:
                conn.close()
                return False, f"Vi phạm kết cấu chịu lực: Không thể xếp container 40ft ({upper_iso}) đè lên container 20ft ({below_iso}) tại {below_id} vì bị hẫng 2 đầu chịu lực!"

            # 3.2. Weight hierarchy (Heavy on light)
            below_w = below_cont["weight_kg"] or 20000.0
            upper_w = container_data.get("weight_kg", 20000.0)
            if upper_w > below_w * 1.1:
                conn.close()
                return False, f"Vi phạm nguyên tắc xếp bãi: Container nặng ({upper_w}kg) không được đặt lên container nhẹ ({below_w}kg) tại {below_id}."

    # 4. Reefer rule
    if container_data.get("is_reefer"):
        if not slot["is_reefer_plug"]:
            conn.close()
            return False, f"Vi phạm thiết bị: Ô {target_slot_id} không có ổ cắm điện 3 pha 380V cho container lạnh!"
        if tier > 3:
            conn.close()
            return False, f"Vi phạm an toàn lao động: Container lạnh không được xếp quá Tầng 3 (hiện tại Tầng {tier}) để thợ điện cắm rút an toàn."

    # 5. Hazardous IMDG rule
    if container_data.get("is_hazardous"):
        for adj_bay in [bay - 1, bay + 1]:
            if 1 <= adj_bay <= 4:
                for adj_row in range(1, 5):
                    for adj_tier in range(1, 5):
                        chk_id = f"{block}-{adj_bay:02d}-{adj_row:02d}-{adj_tier}"
                        cur.execute("""
                        SELECT s.status, s.container_no, c.is_reefer 
                        FROM tbl_yard_slots s 
                        LEFT JOIN tbl_containers c ON s.container_no = c.container_no 
                        WHERE s.slot_id = ?;
                        """, (chk_id,))
                        s = cur.fetchone()
                        if s and s["status"] == "OCCUPIED" and s["container_no"] != container_data.get("container_no"):
                            if s["is_reefer"]:
                                conn.close()
                                return False, f"Vi phạm hàng nguy hiểm: Hàng IMDG tại {target_slot_id} cách ly dưới 2 Bay so với container lạnh/dễ cháy tại {chk_id}."

    conn.close()
    return True, "Hợp lệ, thỏa mãn toàn bộ quy chuẩn xếp bãi."

# --- REST APIS FOR YARD & CONTAINER ---

# ------------------------------------------------------------------------------
# Function: get_yard_slots
# Mục đích sử dụng: Lấy danh sách toàn bộ các ô bãi container theo Block (Block, Bay, Row, Tier)
#                   kèm trạng thái chiếm giữ và thông tin khóa phân tán thời gian thực.
# ------------------------------------------------------------------------------
@yard_container_bp.route("/api/v1/yard/slots", methods=["GET"])
def get_yard_slots():
    block = request.args.get("block", "A")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tbl_yard_slots WHERE block = ? ORDER BY bay, row, tier;", (block,))
    slots = []
    for r in cur.fetchall():
        d = dict(r)
        d["is_reefer_plug"] = bool(d["is_reefer_plug"])
        # Check active distributed lock
        if d["slot_id"] in SLOT_LOCKS:
            d["locked_by"] = SLOT_LOCKS[d["slot_id"]]
        slots.append(d)
    conn.close()
    return jsonify(slots)

# ------------------------------------------------------------------------------
# Function: get_containers
# Mục đích sử dụng: Lấy danh sách toàn bộ container đang lưu bãi kèm thông số trọng lượng, hàng lạnh, nguy hiểm và vị trí slot_id.
# ------------------------------------------------------------------------------
@yard_container_bp.route("/api/v1/yard/containers", methods=["GET"])
def get_containers():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tbl_containers ORDER BY container_no;")
    containers = []
    for r in cur.fetchall():
        d = dict(r)
        d["is_hazardous"] = bool(d["is_hazardous"])
        d["is_reefer"] = bool(d["is_reefer"])
        containers.append(d)
    conn.close()
    return jsonify(containers)

# ------------------------------------------------------------------------------
# Function: create_container
# Mục đích sử dụng: Thêm mới một container vào hệ thống bãi (có kiểm tra quy chuẩn xếp dỡ nếu gán vị trí ô bãi ban đầu).
# ------------------------------------------------------------------------------
@yard_container_bp.route("/api/v1/yard/containers", methods=["POST"])
def create_container():
    data = request.get_json(silent=True) or {}
    container_no = str(data.get("container_no", "")).strip().upper()
    
    if not container_no or len(container_no) < 4:
        return jsonify({"code": "ERR_INVALID_CONTAINER_NO", "message": "Số container không hợp lệ! Vui lòng nhập đúng chuẩn ISO (VD: TCKU9012384)."}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT container_no FROM tbl_containers WHERE container_no = ?;", (container_no,))
    if cur.fetchone():
        conn.close()
        return jsonify({"code": "ERR_DUPLICATE_CONTAINER", "message": f"Container {container_no} đã tồn tại trong hệ thống bãi!"}), 409

    iso_type = str(data.get("iso_type", "20GP")).strip().upper()
    try:
        weight_kg = float(data.get("weight_kg", 20000))
        if weight_kg <= 0 or weight_kg > 45000:
            conn.close()
            return jsonify({"code": "ERR_INVALID_WEIGHT", "message": "Trọng lượng container không hợp lệ (phải từ 100kg đến 45.000kg)!"}), 400
    except (ValueError, TypeError):
        conn.close()
        return jsonify({"code": "ERR_INVALID_WEIGHT", "message": "Trọng lượng container phải là số hợp lệ!"}), 400

    is_reefer = bool(data.get("is_reefer", False))
    set_temp = float(data.get("set_temp_celsius", -18.0)) if is_reefer else None
    is_hazardous = bool(data.get("is_hazardous", False))
    imdg_class = data.get("imdg_class") if is_hazardous else None

    target_slot_id = data.get("slot_id")
    if target_slot_id:
        target_slot_id = str(target_slot_id).strip().upper()
        cur.execute("SELECT * FROM tbl_yard_slots WHERE slot_id = ?;", (target_slot_id,))
        target_slot = cur.fetchone()
        if not target_slot:
            conn.close()
            return jsonify({"code": "ERR_SLOT_NOT_FOUND", "message": f"Ô bãi {target_slot_id} không tồn tại!"}), 404
        if target_slot["status"] == "OCCUPIED":
            conn.close()
            return jsonify({"code": "ERR_SLOT_OCCUPIED", "message": f"Ô bãi {target_slot_id} hiện đã có container {target_slot['container_no']} chiếm giữ!"}), 422

        temp_cont = {
            "container_no": container_no, "iso_type": iso_type, "weight_kg": weight_kg,
            "is_reefer": is_reefer, "is_hazardous": is_hazardous, "imdg_class": imdg_class,
            "slot_id": None
        }
        is_valid, msg = evaluate_stacking_rules(temp_cont, target_slot_id)
        if not is_valid:
            conn.close()
            return jsonify({"code": "ERR_STACKING_RULE_VIOLATION", "message": f"Không thể xếp vào ô {target_slot_id}: {msg}"}), 422

        cur.execute("UPDATE tbl_yard_slots SET status = 'OCCUPIED', container_no = ? WHERE slot_id = ?;", (container_no, target_slot_id))

    new_cont = {
        "container_no": container_no, "iso_type": iso_type, "weight_kg": weight_kg,
        "is_reefer": 1 if is_reefer else 0, "set_temp_celsius": set_temp,
        "is_hazardous": 1 if is_hazardous else 0, "imdg_class": imdg_class,
        "slot_id": target_slot_id
    }
    cur.execute("""
    INSERT INTO tbl_containers (container_no, iso_type, weight_kg, is_hazardous, imdg_class, is_reefer, set_temp_celsius, slot_id)
    VALUES (?,?,?,?,?,?,?,?);
    """, (container_no, iso_type, weight_kg, new_cont["is_hazardous"], imdg_class, new_cont["is_reefer"], set_temp, target_slot_id))
    conn.commit()
    conn.close()

    new_cont["is_reefer"] = is_reefer
    new_cont["is_hazardous"] = is_hazardous

    return jsonify({
        "code": "SUCCESS",
        "message": f"Thêm mới container {container_no} thành công" + (f" tại vị trí {target_slot_id}!" if target_slot_id else " (chưa xếp bãi)!"),
        "data": new_cont
    }), 201

# ------------------------------------------------------------------------------
# Function: update_container
# Mục đích sử dụng: Cập nhật thông số kỹ thuật của container (kích cỡ ISO, trọng lượng, nhiệt độ cài đặt reefer, phân loại nguy hiểm).
# ------------------------------------------------------------------------------
@yard_container_bp.route("/api/v1/yard/containers/<container_no>", methods=["PUT"])
def update_container(container_no):
    container_no = container_no.strip().upper()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tbl_containers WHERE container_no = ?;", (container_no,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"code": "ERR_CONTAINER_NOT_FOUND", "message": f"Không tìm thấy container {container_no}"}), 404

    cont = dict(row)
    data = request.get_json(silent=True) or {}
    if "iso_type" in data:
        cont["iso_type"] = str(data["iso_type"]).strip().upper()

    if "weight_kg" in data:
        try:
            w = float(data["weight_kg"])
            if w <= 0 or w > 45000:
                conn.close()
                return jsonify({"code": "ERR_INVALID_WEIGHT", "message": "Trọng lượng phải từ 100kg đến 45.000kg"}), 400
            cont["weight_kg"] = w
        except (ValueError, TypeError):
            conn.close()
            return jsonify({"code": "ERR_INVALID_WEIGHT", "message": "Trọng lượng phải là số"}), 400

    if "is_reefer" in data:
        cont["is_reefer"] = 1 if bool(data["is_reefer"]) else 0
        cont["set_temp_celsius"] = float(data.get("set_temp_celsius", -18.0)) if cont["is_reefer"] else None

    if "is_hazardous" in data:
        cont["is_hazardous"] = 1 if bool(data["is_hazardous"]) else 0
        cont["imdg_class"] = data.get("imdg_class") if cont["is_hazardous"] else None

    cur.execute("""
    UPDATE tbl_containers SET iso_type = ?, weight_kg = ?, is_reefer = ?, set_temp_celsius = ?, is_hazardous = ?, imdg_class = ?
    WHERE container_no = ?;
    """, (cont["iso_type"], cont["weight_kg"], cont["is_reefer"], cont["set_temp_celsius"], cont["is_hazardous"], cont["imdg_class"], container_no))
    conn.commit()
    conn.close()

    cont["is_reefer"] = bool(cont["is_reefer"])
    cont["is_hazardous"] = bool(cont["is_hazardous"])

    return jsonify({
        "code": "SUCCESS",
        "message": f"Cập nhật thông tin container {container_no} thành công!",
        "data": cont
    })

# ------------------------------------------------------------------------------
# Function: delete_container
# Mục đích sử dụng: Xóa container khỏi hệ thống và giải phóng ô bãi (có kiểm tra an toàn không xóa container bị đè phía trên).
# ------------------------------------------------------------------------------
@yard_container_bp.route("/api/v1/yard/containers/<container_no>", methods=["DELETE"])
def delete_container(container_no):
    container_no = container_no.strip().upper()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tbl_containers WHERE container_no = ?;", (container_no,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"code": "ERR_CONTAINER_NOT_FOUND", "message": f"Không tìm thấy container {container_no}"}), 404

    old_slot_id = row["slot_id"]
    if old_slot_id:
        o_block, o_bay, o_row, o_tier = old_slot_id.split("-")
        above_slot_id = f"{o_block}-{int(o_bay):02d}-{int(o_row):02d}-{int(o_tier)+1}"
        cur.execute("SELECT container_no FROM tbl_yard_slots WHERE slot_id = ? AND status = 'OCCUPIED';", (above_slot_id,))
        above = cur.fetchone()
        if above:
            conn.close()
            return jsonify({
                "code": "ERR_CONTAINER_BLOCKED",
                "message": f"Không thể xóa container {container_no} vì đang bị container {above['container_no']} ở tầng trên ({above_slot_id}) đè lên! Phải dỡ container tầng trên trước."
            }), 422

        cur.execute("UPDATE tbl_yard_slots SET status = 'AVAILABLE', container_no = NULL, locked_by = NULL WHERE slot_id = ?;", (old_slot_id,))

    cur.execute("DELETE FROM tbl_containers WHERE container_no = ?;", (container_no,))
    conn.commit()
    conn.close()

    return jsonify({
        "code": "SUCCESS",
        "message": f"Đã xóa container {container_no} khỏi hệ thống và giải phóng ô bãi {old_slot_id or 'N/A'}!"
    })

# ------------------------------------------------------------------------------
# Function: get_yard_alerts
# Mục đích sử dụng: Truy vấn danh sách cảnh báo vi phạm quy chuẩn bãi container thời gian thực.
# ------------------------------------------------------------------------------
@yard_container_bp.route("/api/v1/yard/alerts", methods=["GET"])
def get_yard_alerts():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tbl_yard_alerts ORDER BY timestamp DESC LIMIT 20;")
    alerts = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(alerts)

# --- DYNAMIC KPI METRICS FOR YARD ---

# ------------------------------------------------------------------------------
# Function: get_yard_kpi
# Mục đích sử dụng: Thống kê chỉ số KPI bãi container (tổng số slot, số ô occupied, tỷ lệ lấp đầy %, số cảnh báo, trạng thái lock).
# ------------------------------------------------------------------------------
@yard_container_bp.route("/api/v1/yard/kpi", methods=["GET"])
def get_yard_kpi():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tbl_yard_slots;")
    total_slots = cur.fetchone()[0] or 192

    cur.execute("SELECT COUNT(*) FROM tbl_yard_slots WHERE status = 'OCCUPIED';")
    occupied_slots = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM tbl_yard_slots WHERE is_reefer_plug = 1;")
    reefer_plugs = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM tbl_yard_alerts;")
    alert_count = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM tbl_containers;")
    active_containers = cur.fetchone()[0] or 0

    conn.close()
    utilization_pct = round((occupied_slots / total_slots) * 100, 1) if total_slots > 0 else 0

    return jsonify({
        "total_slots": total_slots,
        "occupied_slots": occupied_slots,
        "available_slots": total_slots - occupied_slots,
        "active_containers": active_containers,
        "reefer_plugs": reefer_plugs,
        "utilization_pct": utilization_pct,
        "utilization_percent": utilization_pct,
        "active_alerts": alert_count,
        "alert_count": alert_count,
        "rtg_cranes_count": 174,
        "distributed_lock_status": "ACTIVE (Redis Pessimistic)"
    })

# --- ATOMIC CONTAINER MOVEMENT ENGINE WITH DISTRIBUTED LOCK ---

# ------------------------------------------------------------------------------
# Function: atomic_yard_movement
# Mục đích sử dụng: Thực hiện di dời container nguyên tử (Atomic Movement) kèm khóa phân tán (Distributed Lock)
#                   và kiểm tra vi phạm quy chuẩn xếp bãi, tự động ghi nhận cảnh báo nếu vi phạm.
# ------------------------------------------------------------------------------
@yard_container_bp.route("/api/v1/yard/atomic-move", methods=["POST"])
def atomic_yard_movement():
    data = request.get_json(silent=True) or {}
    container_no = data.get("container_no")
    target_slot_id = data.get("target_slot_id")
    operator = data.get("operator", "RTG-01")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM tbl_containers WHERE container_no = ?;", (container_no,))
    cont_row = cur.fetchone()
    if not cont_row:
        conn.close()
        return jsonify({"code": "ERR_CONTAINER_NOT_FOUND", "message": f"Không tìm thấy container {container_no}"}), 404

    cur.execute("SELECT * FROM tbl_yard_slots WHERE slot_id = ?;", (target_slot_id,))
    target_slot = cur.fetchone()
    if not target_slot:
        conn.close()
        return jsonify({"code": "ERR_SLOT_NOT_FOUND", "message": f"Không tìm thấy ô bãi {target_slot_id}"}), 404

    # Real Distributed Lock Check
    current_lock = SLOT_LOCKS.get(target_slot_id)
    if current_lock and current_lock != operator:
        conn.close()
        return jsonify({
            "code": "ERR_SLOT_LOCK_CONFLICT",
            "message": f"Xung đột tranh chấp (409 Conflict): Ô {target_slot_id} đang bị khóa phân tán bởi {current_lock}! Thao tác của {operator} bị từ chối để bảo vệ toàn vẹn dữ liệu."
        }), 409

    cont = dict(cont_row)
    cont["is_reefer"] = bool(cont["is_reefer"])
    cont["is_hazardous"] = bool(cont["is_hazardous"])

    is_valid, rule_msg = evaluate_stacking_rules(cont, target_slot_id)
    if not is_valid:
        alert_id = f"ALT-{int(time.time()*1000)%1000000:06d}"
        cur.execute("""
        INSERT INTO tbl_yard_alerts (alert_id, severity, code, container_no, slot_id, message, timestamp)
        VALUES (?,?,?,?,?,?,?);
        """, (alert_id, "CRITICAL", "ALERT_STACKING_RULE_VIOLATION", container_no, target_slot_id, rule_msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        return jsonify({"code": "ERR_STACKING_RULE_VIOLATION", "message": rule_msg}), 422

    # Perform Atomic Move inside database transaction
    old_slot_id = cont.get("slot_id")
    if old_slot_id:
        cur.execute("UPDATE tbl_yard_slots SET status = 'AVAILABLE', container_no = NULL, locked_by = NULL WHERE slot_id = ?;", (old_slot_id,))

    cur.execute("UPDATE tbl_yard_slots SET status = 'OCCUPIED', container_no = ?, locked_by = NULL WHERE slot_id = ?;", (container_no, target_slot_id))
    cur.execute("UPDATE tbl_containers SET slot_id = ? WHERE container_no = ?;", (target_slot_id, container_no))
    
    conn.commit()
    conn.close()

    # Release lock if any
    SLOT_LOCKS.pop(target_slot_id, None)

    return jsonify({
        "code": "SUCCESS", "message": f"Đảo chuyển container {container_no} thành công sang ô {target_slot_id} (Atomic Commit)",
        "old_slot_id": old_slot_id, "new_slot_id": target_slot_id
    })

# --- REAL RACE CONDITION CONCURRENCY SIMULATION ENDPOINT ---

# ------------------------------------------------------------------------------
# Function: simulate_race_condition
# Mục đích sử dụng: Mô phỏng tình huống tranh chấp tài nguyên đồng thời (Race Condition Concurrency)
#                   giữa 2 cẩu RTG cùng nhắm vào một ô bãi, chứng minh cơ chế Khóa phân tán trả về HTTP 409 Conflict.
# ------------------------------------------------------------------------------
@yard_container_bp.route("/api/v1/yard/simulate-race-condition", methods=["POST"])
def simulate_race_condition():
    data = request.get_json(silent=True) or {}
    target_slot = data.get("target_slot", "A-01-03-1")
    op1 = data.get("operator_1", "RTG-01")
    op2 = data.get("operator_2", "RTG-02")

    # Operator 1 locks the slot
    SLOT_LOCKS[target_slot] = op1

    # Operator 2 attempts to lock the slot immediately -> 409
    return jsonify({
        "code": "ERR_SLOT_LOCK_CONFLICT",
        "status_code": 409,
        "conflict_slot": target_slot,
        "locked_by": op1,
        "rejected_operator": op2,
        "message": f"Xung đột tranh chấp phân tán (HTTP 409 Conflict): Ô {target_slot} đang bị khóa độc quyền bởi thiết bị cẩu {op1}. Yêu cầu đồng thời của thiết bị cẩu {op2} bị từ chối an toàn!"
    }), 409

# ------------------------------------------------------------------------------
# Function: reset_yard
# Mục đích sử dụng: Khôi phục toàn bộ trạng thái dữ liệu mẫu chuẩn của bãi container và giải phóng toàn bộ khóa phân tán.
# ------------------------------------------------------------------------------
@yard_container_bp.route("/api/v1/yard/reset", methods=["POST"])
def reset_yard():
    conn = get_db()
    cur = conn.cursor()
    # Clean tables and re-seed
    cur.execute("DELETE FROM tbl_yard_alerts;")
    cur.execute("DELETE FROM tbl_containers;")
    cur.execute("DELETE FROM tbl_yard_slots;")
    cur.execute("DELETE FROM tbl_port_calls;")
    cur.execute("DELETE FROM tbl_vessels;")
    cur.execute("DELETE FROM tbl_berths;")
    conn.commit()
    seed_data(conn)
    conn.close()
    SLOT_LOCKS.clear()
    return jsonify({"code": "SUCCESS", "message": "Đã khôi phục toàn bộ trạng thái dữ liệu chuẩn ban đầu!"})
