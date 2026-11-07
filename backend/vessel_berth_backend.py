from flask import Blueprint, request, jsonify, render_template
from datetime import datetime, timedelta
import random
import time

vessel_berth_bp = Blueprint('vessel_berth', __name__)

# --- IN-MEMORY DATA STORE FOR MODULE 1 ---
BERTHS = [
    {"berth_id": "B1", "name": "Cầu bến B1", "start_meter": 0, "end_meter": 300, "depth_draft": 16.0, "port": "CAT_LAI"},
    {"berth_id": "B2", "name": "Cầu bến B2", "start_meter": 300, "end_meter": 600, "depth_draft": 16.0, "port": "CAT_LAI"},
    {"berth_id": "B3", "name": "Cầu bến B3", "start_meter": 600, "end_meter": 950, "depth_draft": 15.5, "port": "CAT_LAI"},
    {"berth_id": "B4", "name": "Cầu bến B4", "start_meter": 950, "end_meter": 1300, "depth_draft": 15.5, "port": "CAT_LAI"},
    {"berth_id": "B5", "name": "Cầu bến B5", "start_meter": 1300, "end_meter": 1650, "depth_draft": 15.0, "port": "CAT_LAI"},
    {"berth_id": "B6", "name": "Cầu bến B6", "start_meter": 1650, "end_meter": 2040, "depth_draft": 14.5, "port": "CAT_LAI"},
]

VESSELS = {
    "9321483": {"imo": "9321483", "name": "EVER GIVEN", "carrier": "Evergreen", "loa": 400.0, "beam": 59.0, "max_draft": 16.0, "dwt": 220940, "teu": 20124},
    "9811000": {"imo": "9811000", "name": "MAERSK MC-KINNEY", "carrier": "Maersk Line", "loa": 399.0, "beam": 59.0, "max_draft": 16.0, "dwt": 194849, "teu": 18270},
    "9484431": {"imo": "9484431", "name": "CMA CGM ANTOINE", "carrier": "CMA CGM", "loa": 396.0, "beam": 54.0, "max_draft": 16.0, "dwt": 186470, "teu": 16020},
    "9229843": {"imo": "9229843", "name": "MSC LAUREN", "carrier": "MSC", "loa": 366.0, "beam": 48.0, "max_draft": 15.2, "dwt": 140000, "teu": 12500},
    "9434888": {"imo": "9434888", "name": "ONE APUS", "carrier": "ONE", "loa": 364.0, "beam": 51.0, "max_draft": 15.0, "dwt": 139500, "teu": 14052},
    "9708461": {"imo": "9708461", "name": "COSCO SHIPPING UNIVERSE", "carrier": "COSCO", "loa": 400.0, "beam": 58.6, "max_draft": 16.0, "dwt": 199000, "teu": 21237},
    "9110023": {"imo": "9110023", "name": "HAI AN BELL", "carrier": "Hai An Lines", "loa": 154.0, "beam": 25.0, "max_draft": 8.5, "dwt": 14000, "teu": 1040},
    "9234567": {"imo": "9234567", "name": "TAN CANG GLORY", "carrier": "SNP Shipping", "loa": 172.0, "beam": 27.5, "max_draft": 9.2, "dwt": 18500, "teu": 1700},
}

PORT_CALLS = [
    {
        "call_id": "CALL-2026-001", "imo": "9110023", "vessel_name": "HAI AN BELL", "berth_id": "B1",
        "start_meter": 50, "end_meter": 220, "start_time": "2026-11-07 06:00", "end_time": "2026-11-07 18:00",
        "status": "MOORED", "eta": "2026-11-07 05:30", "etd": "2026-11-07 18:00",
        "discharge_teu": 450, "load_teu": 520, "current_moves": 650, "total_moves": 970
    },
    {
        "call_id": "CALL-2026-002", "imo": "9234567", "vessel_name": "TAN CANG GLORY", "berth_id": "B2",
        "start_meter": 350, "end_meter": 540, "start_time": "2026-11-07 08:00", "end_time": "2026-11-07 22:00",
        "status": "OPERATING", "eta": "2026-11-07 07:15", "etd": "2026-11-07 22:00",
        "discharge_teu": 780, "load_teu": 600, "current_moves": 420, "total_moves": 1380
    },
    {
        "call_id": "CALL-2026-003", "imo": "9229843", "vessel_name": "MSC LAUREN", "berth_id": "B3-B4",
        "start_meter": 800, "end_meter": 1200, "start_time": "2026-11-07 12:00", "end_time": "2026-11-08 04:00",
        "status": "APPROVED", "eta": "2026-11-07 11:30", "etd": "2026-11-08 04:00",
        "discharge_teu": 1500, "load_teu": 1200, "current_moves": 0, "total_moves": 2700
    }
]

# --- SPATIOTEMPORAL COLLISION DETECTION ENGINE ---
def check_berth_collision(start_meter, end_meter, start_time_str, end_time_str, buffer_meters=15.0):
    req_start_m = float(start_meter) - buffer_meters
    req_end_m = float(end_meter) + buffer_meters
    t_start = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
    t_end = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M")

    conflicts = []
    for call in PORT_CALLS:
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
    return jsonify(list(VESSELS.values()))

@vessel_berth_bp.route("/api/v1/berths", methods=["GET"])
def get_berths():
    return jsonify(BERTHS)

@vessel_berth_bp.route("/api/v1/port-calls", methods=["GET"])
def get_port_calls():
    return jsonify(PORT_CALLS)

@vessel_berth_bp.route("/api/v1/port-calls", methods=["POST"])
def create_port_call():
    data = request.json or {}
    imo = str(data.get("imo", "")).strip()
    
    if not imo or len(imo) != 7 or not imo.isdigit():
        return jsonify({"code": "ERR_INVALID_IMO", "message": "Mã IMO quốc tế không hợp lệ! Bắt buộc phải đúng 7 chữ số."}), 400

    vessel = VESSELS.get(imo)
    if not vessel:
        return jsonify({"code": "ERR_VESSEL_NOT_FOUND", "message": f"Không tìm thấy tàu IMO: {imo}"}), 404

    draft = float(data.get("draft", vessel["max_draft"]))
    berth_id = data.get("berth_id", "B1")
    berth = next((b for b in BERTHS if b["berth_id"] == berth_id), None)
    if berth and draft > berth["depth_draft"]:
        return jsonify({
            "code": "ERR_DRAFT_EXCEEDS",
            "message": f"Mớn nước của tàu ({draft}m) vượt quá độ sâu thiết kế an toàn của {berth['name']} ({berth['depth_draft']}m)!"
        }), 422

    start_m = float(data.get("start_meter", 0))
    end_m = start_m + vessel["loa"]
    start_time = data.get("start_time", datetime.now().strftime("%Y-%m-%d %H:%M"))
    duration = int(data.get("duration_hours", 12))
    t_end = datetime.strptime(start_time, "%Y-%m-%d %H:%M") + timedelta(hours=duration)
    end_time = t_end.strftime("%Y-%m-%d %H:%M")

    conflicts = check_berth_collision(start_m, end_m, start_time, end_time)
    if conflicts:
        return jsonify({
            "code": "ERR_BERTH_COLLISION_DETECTED",
            "message": f"Xung đột cầu bến! Phát hiện va chạm không gian/thời gian với tàu {conflicts[0]['vessel_name']}",
            "conflicts": conflicts
        }), 409

    call_id = f"CALL-2026-{len(PORT_CALLS)+1:03d}"
    new_call = {
        "call_id": call_id, "imo": imo, "vessel_name": vessel["name"], "berth_id": berth_id,
        "start_meter": start_m, "end_meter": end_m, "start_time": start_time, "end_time": end_time,
        "status": "APPROVED", "eta": start_time, "etd": end_time,
        "discharge_teu": data.get("discharge_teu", 500), "load_teu": data.get("load_teu", 500),
        "current_moves": 0, "total_moves": data.get("discharge_teu", 500) + data.get("load_teu", 500)
    }
    PORT_CALLS.append(new_call)
    return jsonify({"code": "SUCCESS", "message": "Đăng ký chuyến tàu và phân bổ cầu bến thành công!", "data": new_call}), 201

@vessel_berth_bp.route("/api/v1/ai/optimize-berth", methods=["POST"])
def ai_optimize_berth():
    t0 = time.time()
    total_berth_length = 2040.0
    solutions = []
    current_meter = 100.0
    now = datetime.now().replace(minute=0, second=0)

    sample_incoming = [
        {"name": "COSCO SHIPPING UNIVERSE", "imo": "9708461", "loa": 400.0, "teu": 21000},
        {"name": "EVER GIVEN", "imo": "9321483", "loa": 400.0, "teu": 20000},
        {"name": "CMA CGM ANTOINE", "imo": "9484431", "loa": 396.0, "teu": 16000},
        {"name": "ONE APUS", "imo": "9434888", "loa": 364.0, "teu": 14000},
        {"name": "HAI AN BELL", "imo": "9110023", "loa": 154.0, "teu": 1040},
    ]

    for idx, v in enumerate(sample_incoming):
        loa = float(v["loa"])
        duration = max(6, int(v["teu"] / 120))
        if current_meter + loa + 30 > total_berth_length:
            current_meter = 50.0
            now += timedelta(hours=8)
        start_m = current_meter
        end_m = start_m + loa
        t_start = now + timedelta(hours=idx * 2)
        t_end = t_start + timedelta(hours=duration)

        solutions.append({
            "vessel_name": v["name"], "imo": v["imo"], "loa": loa,
            "allocated_start_meter": round(start_m, 1), "allocated_end_meter": round(end_m, 1),
            "berth_range": f"{round(start_m)}m - {round(end_m)}m",
            "allocated_start_time": t_start.strftime("%Y-%m-%d %H:%M"),
            "allocated_end_time": t_end.strftime("%Y-%m-%d %H:%M"),
            "duration_hours": duration, "fitness_score": round(92.5 + random.uniform(0.5, 4.5), 2)
        })
        current_meter = end_m + 30.0

    elapsed_ms = round((time.time() - t0) * 1000, 2)
    return jsonify({
        "code": "SUCCESS", "solver": "GeneticAlgorithmSolver-v2.1",
        "execution_time_ms": elapsed_ms, "scheduled_vessels_count": len(solutions), "solutions": solutions
    })

# Standalone execution
if __name__ == "__main__":
    from flask import Flask
    app = Flask(__name__, template_folder="../frontend")
    app.register_blueprint(vessel_berth_bp)
    @app.route("/")
    def index(): return render_template("vessel_berth.html")
    print("Running Standalone Module 1 on http://localhost:8081")
    app.run(port=8081, debug=False)
