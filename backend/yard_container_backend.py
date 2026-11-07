from flask import Blueprint, request, jsonify, render_template
from datetime import datetime
import time

yard_container_bp = Blueprint('yard_container', __name__)

# --- IN-MEMORY DATA STORE FOR MODULE 2 ---
YARD_SLOTS = {}
CONTAINERS = {}
YARD_ALERTS = []

def init_yard_data():
    YARD_SLOTS.clear()
    CONTAINERS.clear()
    blocks = ["A", "B", "C"]
    sample_containers = [
        {"container_no": "EMCU8921470", "iso_type": "40HC", "weight_kg": 28400, "is_hazardous": False, "imdg_class": None, "is_reefer": False},
        {"container_no": "MSCU1294801", "iso_type": "20GP", "weight_kg": 14200, "is_hazardous": False, "imdg_class": None, "is_reefer": False},
        {"container_no": "TCKU9012384", "iso_type": "40RH", "weight_kg": 22500, "is_hazardous": False, "imdg_class": None, "is_reefer": True, "set_temp_celsius": -18.0},
        {"container_no": "CMAU7483920", "iso_type": "20GP", "weight_kg": 26800, "is_hazardous": True, "imdg_class": "Class 3 - Flammable", "is_reefer": False},
        {"container_no": "ONEU3391024", "iso_type": "40HC", "weight_kg": 11200, "is_hazardous": False, "imdg_class": None, "is_reefer": False},
    ]

    for b in blocks:
        for bay in range(1, 5):
            for row in range(1, 5):
                for tier in range(1, 5):
                    slot_id = f"{b}-{bay:02d}-{row:02d}-{tier}"
                    is_reefer_plug = (row == 4 and tier <= 3)
                    YARD_SLOTS[slot_id] = {
                        "slot_id": slot_id, "block": b, "bay": bay, "row": row, "tier": tier,
                        "is_reefer_plug": is_reefer_plug, "status": "AVAILABLE",
                        "container_no": None, "locked_by": None
                    }

    placements = [
        ("A-01-01-1", sample_containers[0]),
        ("A-01-01-2", sample_containers[1]),
        ("A-01-04-1", sample_containers[2]),
        ("B-02-02-1", sample_containers[3]),
        ("C-03-03-1", sample_containers[4]),
    ]
    for slot_id, cont in placements:
        YARD_SLOTS[slot_id]["status"] = "OCCUPIED"
        YARD_SLOTS[slot_id]["container_no"] = cont["container_no"]
        cont["slot_id"] = slot_id
        CONTAINERS[cont["container_no"]] = cont

    YARD_ALERTS.clear()
    YARD_ALERTS.append({
        "alert_id": "ALT-001", "severity": "WARNING", "code": "WARN_REEFER_POWER_CHECK",
        "container_no": "TCKU9012384", "slot_id": "A-01-04-1",
        "message": "Container lạnh TCKU9012384 kết nối lưới 3 pha 380V. Nhiệt độ: -18.2°C (Bình thường)",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

init_yard_data()

# --- AI STACKING RULE EVALUATION ENGINE ---
def evaluate_stacking_rules(container_data, target_slot_id):
    block, bay, row, tier = target_slot_id.split("-")
    bay, row, tier = int(bay), int(row), int(tier)
    slot = YARD_SLOTS.get(target_slot_id)
    if not slot: return False, "Ô bãi không tồn tại trong hệ thống."
    if slot["status"] == "OCCUPIED": return False, f"Ô bãi {target_slot_id} hiện đang có container chiếm giữ."

    # Ground support & Heavy on light rule
    if tier > 1:
        below_id = f"{block}-{bay:02d}-{row:02d}-{tier-1}"
        below_slot = YARD_SLOTS.get(below_id)
        if not below_slot or below_slot["status"] != "OCCUPIED":
            return False, f"Vi phạm trọng lực: Ô bên dưới ({below_id}) chưa có container đỡ!"
        below_cont = CONTAINERS.get(below_slot["container_no"])
        if below_cont:
            below_w = below_cont.get("weight_kg", 20000)
            upper_w = container_data.get("weight_kg", 20000)
            if upper_w > below_w * 1.1:
                return False, f"Vi phạm nguyên tắc xếp bãi: Container nặng ({upper_w}kg) không được đặt lên container nhẹ ({below_w}kg) tại {below_id}."

    # Reefer rule
    if container_data.get("is_reefer"):
        if not slot["is_reefer_plug"]:
            return False, f"Vi phạm thiết bị: Ô {target_slot_id} không có ổ cắm điện 3 pha 380V cho container lạnh!"
        if tier > 3:
            return False, f"Vi phạm an toàn lao động: Container lạnh không được xếp quá Tầng 3 (hiện tại Tầng {tier}) để thợ điện cắm rút an toàn."

    # Hazardous IMDG rule
    if container_data.get("is_hazardous"):
        for adj_bay in [bay - 1, bay + 1]:
            if 1 <= adj_bay <= 4:
                for adj_row in range(1, 5):
                    for adj_tier in range(1, 5):
                        chk_id = f"{block}-{adj_bay:02d}-{adj_row:02d}-{adj_tier}"
                        s = YARD_SLOTS.get(chk_id)
                        if s and s["status"] == "OCCUPIED":
                            c = CONTAINERS.get(s["container_no"])
                            if c and c.get("is_reefer"):
                                return False, f"Vi phạm hàng nguy hiểm: Hàng IMDG tại {target_slot_id} cách ly dưới 2 Bay so với container lạnh/dễ cháy tại {chk_id}."

    return True, "Hợp lệ, thỏa mãn toàn bộ quy chuẩn xếp bãi."

# --- REST APIS FOR YARD & CONTAINER ---
@yard_container_bp.route("/api/v1/yard/slots", methods=["GET"])
def get_yard_slots():
    block = request.args.get("block", "A")
    return jsonify([s for s in YARD_SLOTS.values() if s["block"] == block])

@yard_container_bp.route("/api/v1/yard/containers", methods=["GET"])
def get_containers():
    return jsonify(list(CONTAINERS.values()))

@yard_container_bp.route("/api/v1/yard/alerts", methods=["GET"])
def get_yard_alerts():
    return jsonify(YARD_ALERTS)

@yard_container_bp.route("/api/v1/yard/atomic-move", methods=["POST"])
def atomic_yard_movement():
    data = request.json or {}
    container_no = data.get("container_no")
    target_slot_id = data.get("target_slot_id")
    operator = data.get("operator", "RTG-01")

    cont = CONTAINERS.get(container_no)
    if not cont: return jsonify({"code": "ERR_CONTAINER_NOT_FOUND", "message": f"Không tìm thấy container {container_no}"}), 404
    target_slot = YARD_SLOTS.get(target_slot_id)
    if not target_slot: return jsonify({"code": "ERR_SLOT_NOT_FOUND", "message": f"Không tìm thấy ô bãi {target_slot_id}"}), 404

    # Distributed Lock Check
    if target_slot["locked_by"] and target_slot["locked_by"] != operator:
        return jsonify({
            "code": "ERR_SLOT_LOCK_CONFLICT",
            "message": f"Xung đột tranh chấp (409 Conflict): Ô {target_slot_id} đang bị khóa bởi {target_slot['locked_by']}!"
        }), 409

    is_valid, rule_msg = evaluate_stacking_rules(cont, target_slot_id)
    if not is_valid:
        alert = {
            "alert_id": f"ALT-{len(YARD_ALERTS)+1:03d}", "severity": "CRITICAL",
            "code": "ALERT_STACKING_RULE_VIOLATION", "container_no": container_no,
            "slot_id": target_slot_id, "message": rule_msg,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        YARD_ALERTS.insert(0, alert)
        return jsonify({"code": "ERR_STACKING_RULE_VIOLATION", "message": rule_msg}), 422

    # Perform Atomic Move
    target_slot["locked_by"] = operator
    old_slot_id = cont.get("slot_id")
    if old_slot_id and old_slot_id in YARD_SLOTS:
        YARD_SLOTS[old_slot_id]["status"] = "AVAILABLE"
        YARD_SLOTS[old_slot_id]["container_no"] = None
        YARD_SLOTS[old_slot_id]["locked_by"] = None

    target_slot["status"] = "OCCUPIED"
    target_slot["container_no"] = container_no
    target_slot["locked_by"] = None
    cont["slot_id"] = target_slot_id

    return jsonify({
        "code": "SUCCESS", "message": f"Đảo chuyển container {container_no} thành công sang ô {target_slot_id} (Atomic Commit)",
        "old_slot_id": old_slot_id, "new_slot_id": target_slot_id
    })

# Standalone execution
if __name__ == "__main__":
    from flask import Flask
    app = Flask(__name__, template_folder="../frontend")
    app.register_blueprint(yard_container_bp)
    @app.route("/")
    def index(): return render_template("yard_container.html")
    print("Running Standalone Module 2 on http://localhost:8082")
    app.run(port=8082, debug=False)
