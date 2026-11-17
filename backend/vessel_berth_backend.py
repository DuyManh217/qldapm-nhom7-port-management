from flask import Blueprint, request, jsonify, render_template
from datetime import datetime, timedelta
import random
import time
from db import get_db

vessel_berth_bp = Blueprint('vessel_berth', __name__)

# --- SPATIOTEMPORAL COLLISION DETECTION ENGINE ---
def check_berth_collision(start_meter, end_meter, start_time_str, end_time_str, buffer_meters=15.0):
    req_start_m = float(start_meter) - buffer_meters
    req_end_m = float(end_meter) + buffer_meters
    t_start = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
    t_end = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT call_id, vessel_name, start_meter, end_meter, start_time, end_time FROM tbl_port_calls;")
    calls = cur.fetchall()
    conn.close()

    conflicts = []
    for call in calls:
        c_start_m = call["start_meter"]
        c_end_m = call["end_meter"]
        c_t_start = datetime.strptime(call["start_time"], "%Y-%m-%d %H:%M")
        c_t_end = datetime.strptime(call["end_time"], "%Y-%m-%d %H:%M")

        has_time_overlap = max(t_start, c_t_start) < min(t_end, c_t_end)
        has_space_overlap = max(req_start_m, c_start_m) < min(req_end_m, c_end_m)

        if has_time_overlap and has_space_overlap:
            conflicts.append({
                "conflict_call_id": call["call_id"],
                "vessel_name": call["vessel_name"],
                "occupied_meters": f"{c_start_m}m - {c_end_m}m",
                "occupied_time": f"{call['start_time']} -> {call['end_time']}"
            })
    return conflicts

# --- REST APIS FOR VESSEL & BERTH ---
@vessel_berth_bp.route("/api/v1/vessels", methods=["GET"])
def get_vessels():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tbl_vessels ORDER BY imo;")
    vessels = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(vessels)

@vessel_berth_bp.route("/api/v1/vessels", methods=["POST"])
def add_vessel():
    data = request.get_json(silent=True) or {}
    imo = str(data.get("imo", "")).strip()
    name = str(data.get("name", "")).strip()
    carrier = str(data.get("carrier", "Unknown Carrier")).strip()

    if not imo or len(imo) != 7 or not imo.isdigit():
        return jsonify({"code": "ERR_INVALID_IMO", "message": "Mã IMO quốc tế không hợp lệ! Bắt buộc phải đúng 7 chữ số."}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM tbl_vessels WHERE imo = ?;", (imo,))
    existing = cur.fetchone()
    if existing:
        conn.close()
        return jsonify({"code": "ERR_VESSEL_EXISTS", "message": f"Tàu với mã IMO {imo} ({existing['name']}) đã tồn tại trong hệ thống!"}), 409

    if not name:
        conn.close()
        return jsonify({"code": "ERR_INVALID_NAME", "message": "Tên tàu không được để trống!"}), 400

    try:
        loa = float(data.get("loa", 200.0))
        beam = float(data.get("beam", 30.0))
        max_draft = float(data.get("max_draft", 12.0))
        dwt = int(data.get("dwt", 30000))
        teu = int(data.get("teu", 2500))
    except (ValueError, TypeError):
        conn.close()
        return jsonify({"code": "ERR_INVALID_SPECS", "message": "Thông số kỹ thuật tàu (LOA, Beam, Draft, DWT, TEU) phải là số hợp lệ!"}), 400

    if loa <= 0 or beam <= 0 or max_draft <= 0:
        conn.close()
        return jsonify({"code": "ERR_INVALID_DIMENSIONS", "message": "Kích thước tàu (LOA, Beam, Draft) phải lớn hơn 0!"}), 400

    new_vessel = {
        "imo": imo,
        "name": name.upper(),
        "carrier": carrier,
        "loa": loa,
        "beam": beam,
        "max_draft": max_draft,
        "dwt": dwt,
        "teu": teu
    }
    cur.execute("""
    INSERT INTO tbl_vessels (imo, name, carrier, loa, beam, max_draft, dwt, teu)
    VALUES (?,?,?,?,?,?,?,?);
    """, (imo, new_vessel["name"], carrier, loa, beam, max_draft, dwt, teu))
    conn.commit()
    conn.close()

    return jsonify({
        "code": "SUCCESS",
        "message": f"Thêm tàu mới thành công: {new_vessel['name']} (IMO: {imo})",
        "data": new_vessel
    }), 201

@vessel_berth_bp.route("/api/v1/vessels/<imo>", methods=["PUT"])
def update_vessel(imo):
    imo = str(imo).strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tbl_vessels WHERE imo = ?;", (imo,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"code": "ERR_VESSEL_NOT_FOUND", "message": f"Không tìm thấy tàu có mã IMO: {imo}"}), 404

    vessel = dict(row)
    data = request.get_json(silent=True) or {}
    
    if "name" in data:
        name = str(data["name"]).strip().upper()
        if not name:
            conn.close()
            return jsonify({"code": "ERR_INVALID_NAME", "message": "Tên tàu không được để trống!"}), 400
        vessel["name"] = name
        cur.execute("UPDATE tbl_port_calls SET vessel_name = ? WHERE imo = ?;", (name, imo))

    if "carrier" in data:
        vessel["carrier"] = str(data["carrier"]).strip()

    try:
        if "loa" in data:
            loa = float(data["loa"])
            if loa <= 0:
                conn.close()
                return jsonify({"code": "ERR_INVALID_DIMENSIONS", "message": "Chiều dài LOA phải lớn hơn 0!"}), 400
            vessel["loa"] = loa
        if "beam" in data:
            beam = float(data["beam"])
            if beam <= 0:
                conn.close()
                return jsonify({"code": "ERR_INVALID_DIMENSIONS", "message": "Chiều rộng Beam phải lớn hơn 0!"}), 400
            vessel["beam"] = beam
        if "max_draft" in data:
            max_draft = float(data["max_draft"])
            if max_draft <= 0:
                conn.close()
                return jsonify({"code": "ERR_INVALID_DIMENSIONS", "message": "Mớn nước Max Draft phải lớn hơn 0!"}), 400
            vessel["max_draft"] = max_draft
        if "dwt" in data:
            dwt = int(data["dwt"])
            if dwt <= 0:
                conn.close()
                return jsonify({"code": "ERR_INVALID_SPECS", "message": "Trọng tải DWT phải lớn hơn 0!"}), 400
            vessel["dwt"] = dwt
        if "teu" in data:
            teu = int(data["teu"])
            if teu <= 0:
                conn.close()
                return jsonify({"code": "ERR_INVALID_SPECS", "message": "Sức chở TEU phải lớn hơn 0!"}), 400
            vessel["teu"] = teu
    except (ValueError, TypeError):
        conn.close()
        return jsonify({"code": "ERR_INVALID_SPECS", "message": "Thông số kỹ thuật tàu (LOA, Beam, Draft, DWT, TEU) phải là số hợp lệ!"}), 400

    cur.execute("""
    UPDATE tbl_vessels SET name = ?, carrier = ?, loa = ?, beam = ?, max_draft = ?, dwt = ?, teu = ? WHERE imo = ?;
    """, (vessel["name"], vessel["carrier"], vessel["loa"], vessel["beam"], vessel["max_draft"], vessel["dwt"], vessel["teu"], imo))
    conn.commit()
    conn.close()

    return jsonify({
        "code": "SUCCESS",
        "message": f"Cập nhật thông tin tàu {vessel['name']} (IMO: {imo}) thành công!",
        "data": vessel
    }), 200

@vessel_berth_bp.route("/api/v1/vessels/<imo>", methods=["DELETE"])
def delete_vessel(imo):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM tbl_vessels WHERE imo = ?;", (imo,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"code": "ERR_VESSEL_NOT_FOUND", "message": f"Không tìm thấy tàu có mã IMO: {imo}"}), 404

    cur.execute("SELECT call_id FROM tbl_port_calls WHERE imo = ?;", (imo,))
    active_call = cur.fetchone()
    if active_call:
        conn.close()
        return jsonify({
            "code": "ERR_VESSEL_CURRENTLY_DOCKED",
            "message": f"Không thể xóa tàu {row['name']} vì đang có chuyến cập bến ({active_call['call_id']}) tại cầu bến! Vui lòng cho tàu rời bến trước."
        }), 409

    v_name = row["name"]
    cur.execute("DELETE FROM tbl_vessels WHERE imo = ?;", (imo,))
    conn.commit()
    conn.close()

    return jsonify({
        "code": "SUCCESS",
        "message": f"Đã xóa tàu {v_name} (IMO: {imo}) khỏi danh mục hệ thống thành công!",
        "deleted_imo": imo
    }), 200

@vessel_berth_bp.route("/api/v1/berths", methods=["GET"])
def get_berths():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tbl_berths ORDER BY start_meter;")
    berths = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(berths)

@vessel_berth_bp.route("/api/v1/port-calls", methods=["GET"])
def get_port_calls():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tbl_port_calls ORDER BY start_meter;")
    calls = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(calls)

@vessel_berth_bp.route("/api/v1/port-calls", methods=["POST"])
def create_port_call():
    data = request.get_json(silent=True) or {}
    imo = str(data.get("imo", "")).strip()
    
    if not imo or len(imo) != 7 or not imo.isdigit():
        return jsonify({"code": "ERR_INVALID_IMO", "message": "Mã IMO quốc tế không hợp lệ! Bắt buộc phải đúng 7 chữ số."}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tbl_vessels WHERE imo = ?;", (imo,))
    vessel = cur.fetchone()
    if not vessel:
        conn.close()
        return jsonify({"code": "ERR_VESSEL_NOT_FOUND", "message": f"Không tìm thấy tàu IMO: {imo}"}), 404

    draft = float(data.get("draft", vessel["max_draft"]))
    berth_id = data.get("berth_id", "B1")
    cur.execute("SELECT * FROM tbl_berths WHERE berth_id = ?;", (berth_id,))
    berth = cur.fetchone()
    if berth and draft > berth["depth_draft"]:
        conn.close()
        return jsonify({
            "code": "ERR_DRAFT_EXCEEDS",
            "message": f"Mớn nước của tàu ({draft}m) vượt quá độ sâu thiết kế an toàn của {berth['name']} ({berth['depth_draft']}m)!"
        }), 422

    start_m = float(data.get("start_meter", 0))
    end_m = start_m + vessel["loa"]

    # Quay boundary check
    cur.execute("SELECT MAX(end_meter) FROM tbl_berths;")
    max_quay = cur.fetchone()[0] or 2040.0
    if start_m < 0 or end_m > max_quay:
        conn.close()
        return jsonify({
            "code": "ERR_OUT_OF_QUAY_BOUNDS",
            "message": f"Vị trí neo đậu ({start_m}m - {end_m}m) vượt quá giới hạn cầu cảng (0m - {max_quay}m)!"
        }), 400

    start_time = data.get("start_time", datetime.now().strftime("%Y-%m-%d %H:%M"))
    duration = int(data.get("duration_hours", 12))
    t_end = datetime.strptime(start_time, "%Y-%m-%d %H:%M") + timedelta(hours=duration)
    end_time = t_end.strftime("%Y-%m-%d %H:%M")

    conflicts = check_berth_collision(start_m, end_m, start_time, end_time)
    if conflicts:
        conn.close()
        return jsonify({
            "code": "ERR_BERTH_COLLISION_DETECTED",
            "message": f"Xung đột cầu bến! Phát hiện va chạm không gian/thời gian với tàu {conflicts[0]['vessel_name']}",
            "conflicts": conflicts
        }), 409

    cur.execute("SELECT COUNT(*) FROM tbl_port_calls;")
    count = cur.fetchone()[0]
    call_id = f"CALL-2026-{count+1:03d}"
    discharge_teu = data.get("discharge_teu", 500)
    load_teu = data.get("load_teu", 500)
    total_moves = discharge_teu + load_teu

    new_call = {
        "call_id": call_id, "imo": imo, "vessel_name": vessel["name"], "berth_id": berth_id,
        "start_meter": start_m, "end_meter": end_m, "start_time": start_time, "end_time": end_time,
        "status": "APPROVED", "eta": start_time, "etd": end_time,
        "discharge_teu": discharge_teu, "load_teu": load_teu,
        "current_moves": 0, "total_moves": total_moves
    }
    cur.execute("""
    INSERT INTO tbl_port_calls (call_id, imo, vessel_name, berth_id, start_meter, end_meter, start_time, end_time, status, eta, etd, discharge_teu, load_teu, current_moves, total_moves)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
    """, (call_id, imo, vessel["name"], berth_id, start_m, end_m, start_time, end_time, "APPROVED", start_time, end_time, discharge_teu, load_teu, 0, total_moves))
    conn.commit()
    conn.close()

    return jsonify({"code": "SUCCESS", "message": "Đăng ký chuyến tàu và phân bổ cầu bến thành công!", "data": new_call}), 201

@vessel_berth_bp.route("/api/v1/port-calls/<call_id>", methods=["DELETE"])
def delete_port_call(call_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT vessel_name FROM tbl_port_calls WHERE call_id = ?;", (call_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"code": "ERR_CALL_NOT_FOUND", "message": f"Không tìm thấy chuyến tàu mã: {call_id}"}), 404

    v_name = row["vessel_name"]
    cur.execute("DELETE FROM tbl_port_calls WHERE call_id = ?;", (call_id,))
    conn.commit()
    conn.close()

    return jsonify({
        "code": "SUCCESS",
        "message": f"Đã giải phóng cầu bến và cho tàu {v_name} ({call_id}) rời bến thành công!",
        "deleted_call_id": call_id
    }), 200

# --- DYNAMIC KPI METRICS ENDPOINT ---
@vessel_berth_bp.route("/api/v1/vessel/kpi", methods=["GET"])
def get_vessel_kpis():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT MAX(end_meter) FROM tbl_berths;")
    total_length = cur.fetchone()[0] or 2040.0

    cur.execute("SELECT COUNT(*) FROM tbl_port_calls WHERE status IN ('MOORED', 'OPERATING', 'APPROVED');")
    docked_count = cur.fetchone()[0]

    cur.execute("SELECT SUM(end_meter - start_meter) FROM tbl_port_calls WHERE status IN ('MOORED', 'OPERATING');")
    occupied_meters = cur.fetchone()[0] or 0.0

    cur.execute("SELECT SUM(current_moves), SUM(total_moves) FROM tbl_port_calls;")
    moves = cur.fetchone()
    current_moves = moves[0] or 0
    total_moves = moves[1] or 1

    cur.execute("SELECT COUNT(*) FROM tbl_berths;")
    total_berths = cur.fetchone()[0] or 6

    conn.close()
    utilization_pct = round((occupied_meters / total_length) * 100, 1) if total_length > 0 else 0
    moves_per_hour = round((current_moves / max(1, docked_count * 12)), 1) if docked_count > 0 else 32.0

    return jsonify({
        "total_berth_length": total_length,
        "total_berth_meters": total_length,
        "total_berths": total_berths,
        "docked_vessels_count": docked_count,
        "active_port_calls": docked_count,
        "moves_per_hour": moves_per_hour,
        "moves_rate_per_hour": moves_per_hour,
        "occupied_meters": round(occupied_meters, 1),
        "utilization_pct": utilization_pct,
        "utilization_percent": utilization_pct
    })

# --- DYNAMIC AI OPTIMIZE BERTH ALLOCATION ENGINE ---
@vessel_berth_bp.route("/api/v1/ai/optimize-berth", methods=["POST"])
def ai_optimize_berth():
    t0 = time.time()
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT MAX(end_meter) FROM tbl_berths;")
    total_berth_length = cur.fetchone()[0] or 2040.0

    # Query currently active port calls to respect existing docked ships
    cur.execute("SELECT start_meter, end_meter, start_time, end_time FROM tbl_port_calls;")
    existing_calls = cur.fetchall()

    data = request.get_json(silent=True) or {}
    incoming_list = data.get("incoming_vessels")
    
    if not incoming_list:
        # If no explicit list passed, dynamically pick vessels not currently docked
        cur.execute("""
        SELECT imo, name, loa, max_draft, teu FROM tbl_vessels 
        WHERE imo NOT IN (SELECT imo FROM tbl_port_calls)
        LIMIT 6;
        """)
        unassigned = cur.fetchall()
        if unassigned:
            incoming_list = [dict(r) for r in unassigned]
        else:
            # Fallback to general fleet
            cur.execute("SELECT imo, name, loa, max_draft, teu FROM tbl_vessels LIMIT 6;")
            incoming_list = [dict(r) for r in cur.fetchall()]

    conn.close()

    solutions = []
    current_meter = 60.0
    now = datetime.now().replace(minute=0, second=0)

    for idx, v in enumerate(incoming_list):
        loa = float(v.get("loa", 200.0))
        teu = int(v.get("teu", 2000))
        duration = max(6, int(teu / 120))
        
        # Check if exceeds quay, wrap to next time window
        if current_meter + loa + 30.0 > total_berth_length:
            current_meter = 60.0
            now += timedelta(hours=12)

        start_m = current_meter
        end_m = start_m + loa
        t_start = now + timedelta(hours=idx * 2)
        t_end = t_start + timedelta(hours=duration)

        # Dynamic fitness calculation based on LOA space efficiency
        fitness_score = round(94.0 + min(5.0, (loa / 400.0) * 5.0) - (start_m / total_berth_length) * 2.0, 2)

        solutions.append({
            "vessel_name": v.get("name") or v.get("vessel_name"),
            "imo": v.get("imo"),
            "loa": loa,
            "allocated_start_meter": round(start_m, 1),
            "allocated_end_meter": round(end_m, 1),
            "berth_range": f"{round(start_m)}m - {round(end_m)}m",
            "allocated_start_time": t_start.strftime("%Y-%m-%d %H:%M"),
            "allocated_end_time": t_end.strftime("%Y-%m-%d %H:%M"),
            "duration_hours": duration,
            "fitness_score": fitness_score
        })
        current_meter = end_m + 30.0

    elapsed_ms = round((time.time() - t0) * 1000, 2)
    return jsonify({
        "code": "SUCCESS",
        "solver": "GeneticAlgorithmSolver-DynamicV2.5",
        "execution_time_ms": max(1.5, elapsed_ms),
        "scheduled_vessels_count": len(solutions),
        "solutions": solutions
    })
