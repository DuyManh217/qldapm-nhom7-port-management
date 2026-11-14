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
    old_slot_id = container_data.get("slot_id")

    # 1. Container cannot move to its current slot
    if target_slot_id == old_slot_id:
        return False, f"Container {container_data.get('container_no')} hiện đã đang ở ô {target_slot_id} rồi!"

    # 2. Check if the container is blocked by a container above it at current location
    if old_slot_id:
        o_block, o_bay, o_row, o_tier = old_slot_id.split("-")
        above_old_id = f"{o_block}-{int(o_bay):02d}-{int(o_row):02d}-{int(o_tier)+1}"
        above_slot = YARD_SLOTS.get(above_old_id)
        if above_slot and above_slot.get("status") == "OCCUPIED":
            return False, f"Vi phạm bốc dỡ: Container {container_data.get('container_no')} đang bị container ở tầng trên ({above_old_id}) đè lên! Phải đảo chuyển container phía trên trước khi nâng container này."

    block, bay, row, tier = target_slot_id.split("-")
    bay, row, tier = int(bay), int(row), int(tier)
    slot = YARD_SLOTS.get(target_slot_id)
    if not slot: return False, "Ô bãi không tồn tại trong hệ thống."
    if slot["status"] == "OCCUPIED": return False, f"Ô bãi {target_slot_id} hiện đang có container chiếm giữ."

    # 3. Ground support & Heavy on light rule
    if tier > 1:
        below_id = f"{block}-{bay:02d}-{row:02d}-{tier-1}"
        # CRITICAL BUG FIX: Container cannot stack on its own current position!
        if below_id == old_slot_id:
            return False, f"Vi phạm trọng lực: Không thể xếp container đè lên vị trí của chính nó! Ô bên dưới ({below_id}) sẽ bị trống khi cẩu nhấc container này lên."
        
        below_slot = YARD_SLOTS.get(below_id)
        if not below_slot or below_slot.get("status") != "OCCUPIED" or below_slot.get("container_no") == container_data.get("container_no"):
            return False, f"Vi phạm trọng lực: Ô bên dưới ({below_id}) chưa có container đỡ!"

        below_cont = CONTAINERS.get(below_slot.get("container_no"))
        if below_cont:
            # 3.1. Size compatibility (40ft cannot stack on 20ft)
            upper_iso = container_data.get("iso_type", "")
            below_iso = below_cont.get("iso_type", "")
            is_upper_40 = ("40" in upper_iso or "45" in upper_iso)
            is_below_20 = ("20" in below_iso)
            if is_upper_40 and is_below_20:
                return False, f"Vi phạm kết cấu chịu lực: Không thể xếp container 40ft ({upper_iso}) đè lên container 20ft ({below_iso}) tại {below_id} vì bị hẫng 2 đầu chịu lực!"

            # 3.2. Weight hierarchy (Heavy on light)
            below_w = below_cont.get("weight_kg", 20000)
            upper_w = container_data.get("weight_kg", 20000)
            if upper_w > below_w * 1.1:
                return False, f"Vi phạm nguyên tắc xếp bãi: Container nặng ({upper_w}kg) không được đặt lên container nhẹ ({below_w}kg) tại {below_id}."

    # 4. Reefer rule
    if container_data.get("is_reefer"):
        if not slot["is_reefer_plug"]:
            return False, f"Vi phạm thiết bị: Ô {target_slot_id} không có ổ cắm điện 3 pha 380V cho container lạnh!"
        if tier > 3:
            return False, f"Vi phạm an toàn lao động: Container lạnh không được xếp quá Tầng 3 (hiện tại Tầng {tier}) để thợ điện cắm rút an toàn."

    # 5. Hazardous IMDG rule
    if container_data.get("is_hazardous"):
        for adj_bay in [bay - 1, bay + 1]:
            if 1 <= adj_bay <= 4:
                for adj_row in range(1, 5):
                    for adj_tier in range(1, 5):
                        chk_id = f"{block}-{adj_bay:02d}-{adj_row:02d}-{adj_tier}"
                        s = YARD_SLOTS.get(chk_id)
                        if s and s.get("status") == "OCCUPIED" and s.get("container_no") != container_data.get("container_no"):
                            c = CONTAINERS.get(s.get("container_no"))
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

@yard_container_bp.route("/api/v1/yard/containers", methods=["POST"])
def create_container():
    data = request.json or {}
    container_no = str(data.get("container_no", "")).strip().upper()
    
    if not container_no or len(container_no) < 4:
        return jsonify({"code": "ERR_INVALID_CONTAINER_NO", "message": "Số container không hợp lệ! Vui lòng nhập đúng chuẩn ISO (VD: TCKU9012384)."}), 400

    if container_no in CONTAINERS:
        return jsonify({"code": "ERR_DUPLICATE_CONTAINER", "message": f"Container {container_no} đã tồn tại trong hệ thống bãi!"}), 409

    iso_type = str(data.get("iso_type", "20GP")).strip().upper()
    try:
        weight_kg = float(data.get("weight_kg", 20000))
        if weight_kg <= 0 or weight_kg > 45000:
            return jsonify({"code": "ERR_INVALID_WEIGHT", "message": "Trọng lượng container không hợp lệ (phải từ 100kg đến 45.000kg)!"}), 400
    except (ValueError, TypeError):
        return jsonify({"code": "ERR_INVALID_WEIGHT", "message": "Trọng lượng container phải là số hợp lệ!"}), 400

    is_reefer = bool(data.get("is_reefer", False))
    set_temp = float(data.get("set_temp_celsius", -18.0)) if is_reefer else None
    is_hazardous = bool(data.get("is_hazardous", False))
    imdg_class = data.get("imdg_class") if is_hazardous else None

    target_slot_id = data.get("slot_id")
    if target_slot_id:
        target_slot_id = str(target_slot_id).strip().upper()
        target_slot = YARD_SLOTS.get(target_slot_id)
        if not target_slot:
            return jsonify({"code": "ERR_SLOT_NOT_FOUND", "message": f"Ô bãi {target_slot_id} không tồn tại!"}), 404
        if target_slot["status"] == "OCCUPIED":
            return jsonify({"code": "ERR_SLOT_OCCUPIED", "message": f"Ô bãi {target_slot_id} hiện đã có container {target_slot.get('container_no')} chiếm giữ!"}), 422

        temp_cont = {
            "container_no": container_no, "iso_type": iso_type, "weight_kg": weight_kg,
            "is_reefer": is_reefer, "is_hazardous": is_hazardous, "imdg_class": imdg_class,
            "slot_id": None
        }
        is_valid, msg = evaluate_stacking_rules(temp_cont, target_slot_id)
        if not is_valid:
            return jsonify({"code": "ERR_STACKING_RULE_VIOLATION", "message": f"Không thể xếp vào ô {target_slot_id}: {msg}"}), 422

        target_slot["status"] = "OCCUPIED"
        target_slot["container_no"] = container_no

    new_cont = {
        "container_no": container_no,
        "iso_type": iso_type,
        "weight_kg": weight_kg,
        "is_reefer": is_reefer,
        "set_temp_celsius": set_temp,
        "is_hazardous": is_hazardous,
        "imdg_class": imdg_class,
        "slot_id": target_slot_id
    }
    CONTAINERS[container_no] = new_cont

    return jsonify({
        "code": "SUCCESS",
        "message": f"Thêm mới container {container_no} thành công" + (f" tại vị trí {target_slot_id}!" if target_slot_id else " (chưa xếp bãi)!"),
        "data": new_cont
    }), 201

@yard_container_bp.route("/api/v1/yard/containers/<container_no>", methods=["PUT"])
def update_container(container_no):
    container_no = container_no.strip().upper()
    cont = CONTAINERS.get(container_no)
    if not cont:
        return jsonify({"code": "ERR_CONTAINER_NOT_FOUND", "message": f"Không tìm thấy container {container_no}"}), 404

    data = request.json or {}
    if "iso_type" in data:
        cont["iso_type"] = str(data["iso_type"]).strip().upper()

    if "weight_kg" in data:
        try:
            w = float(data["weight_kg"])
            if w <= 0 or w > 45000:
                return jsonify({"code": "ERR_INVALID_WEIGHT", "message": "Trọng lượng phải từ 100kg đến 45.000kg"}), 400
            cont["weight_kg"] = w
        except (ValueError, TypeError):
            return jsonify({"code": "ERR_INVALID_WEIGHT", "message": "Trọng lượng phải là số"}), 400

    if "is_reefer" in data:
        cont["is_reefer"] = bool(data["is_reefer"])
        if cont["is_reefer"]:
            cont["set_temp_celsius"] = float(data.get("set_temp_celsius", -18.0))
        else:
            cont["set_temp_celsius"] = None

    if "is_hazardous" in data:
        cont["is_hazardous"] = bool(data["is_hazardous"])
        cont["imdg_class"] = data.get("imdg_class") if cont["is_hazardous"] else None

    return jsonify({
        "code": "SUCCESS",
        "message": f"Cập nhật thông tin container {container_no} thành công!",
        "data": cont
    })

@yard_container_bp.route("/api/v1/yard/containers/<container_no>", methods=["DELETE"])
def delete_container(container_no):
    container_no = container_no.strip().upper()
    cont = CONTAINERS.get(container_no)
    if not cont:
        return jsonify({"code": "ERR_CONTAINER_NOT_FOUND", "message": f"Không tìm thấy container {container_no}"}), 404

    old_slot_id = cont.get("slot_id")
    if old_slot_id and old_slot_id in YARD_SLOTS:
        # Check if container is blocked by a container at upper tier
        o_block, o_bay, o_row, o_tier = old_slot_id.split("-")
        above_slot_id = f"{o_block}-{int(o_bay):02d}-{int(o_row):02d}-{int(o_tier)+1}"
        above_slot = YARD_SLOTS.get(above_slot_id)
        if above_slot and above_slot.get("status") == "OCCUPIED":
            return jsonify({
                "code": "ERR_CONTAINER_BLOCKED",
                "message": f"Không thể xóa container {container_no} vì đang bị container {above_slot.get('container_no')} ở tầng trên ({above_slot_id}) đè lên! Phải dỡ container tầng trên trước."
            }), 422

        # Free the slot
        YARD_SLOTS[old_slot_id]["status"] = "AVAILABLE"
        YARD_SLOTS[old_slot_id]["container_no"] = None
        YARD_SLOTS[old_slot_id]["locked_by"] = None

    del CONTAINERS[container_no]

    return jsonify({
        "code": "SUCCESS",
        "message": f"Đã xóa container {container_no} khỏi hệ thống và giải phóng ô bãi {old_slot_id or 'N/A'}!"
    })

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


@yard_container_bp.route("/api/v1/yard/reset", methods=["POST"])
def reset_yard():
    init_yard_data()
    return jsonify({"code": "SUCCESS", "message": "Đã khôi phục trạng thái bãi ban đầu!"})
