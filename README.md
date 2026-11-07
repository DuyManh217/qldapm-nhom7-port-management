# SPMS - Smart Port Management System (Hệ Thống Quản Lý Cảng Biển Thông Minh)
> **Học phần Quản lý Dự án Phần mềm (QLDAPM) - Nhóm 07**  
> Mô phỏng & Điều hành Cảng Biển Thông minh (Tân Cảng Sài Gòn - SNP / Cát Lái & Cái Mép)

---

## 📌 Tổng quan dự án

Hệ thống SPMS cung cấp giải pháp chuyển đổi số toàn diện cho khai thác cảng biển container với 2 phân hệ cốt lõi:
1. **Module 1: Kế hoạch Cầu bến & Lịch trình Tàu (Vessel & Berth Planning)**
   - Quản lý cầu bến liên tục 2.040m với biểu đồ Gantt tương tác.
   - Thuật toán Spatiotemporal Collision Detection kiểm tra xung đột không gian - thời gian theo mớn nước, chiều dài tàu (LOA) và khoảng cách đệm an toàn mũi/lái (15m).
   - Tối ưu hóa xếp lịch bến bằng thuật toán di truyền (Genetic Algorithm) và Heuristic fallback.
2. **Module 2: Quản lý Bãi & Container (Yard & Container Management)**
   - Quản lý quy hoạch ô bãi 3D (Block, Bay, Row, Tier).
   - Kiểm soát nghiêm ngặt các quy tắc xếp bãi: Giới hạn trọng lực (nặng không đè nhẹ), cấp nguồn điện 3 pha cho container lạnh (Reefer), cách ly an toàn hóa chất nguy hiểm (IMDG Code).
   - Điều phối tác nghiệp di chuyển container nguyên tử (Atomic Movement).

---

## 📁 Cấu trúc thư mục

```
spms_app/
├── backend/
│   ├── app.py                      # Flask Server chính gộp 2 Blueprint
│   ├── vessel_berth_backend.py     # API & Thuật toán Module 1 (Cầu bến & Tàu)
│   └── yard_container_backend.py   # API & Quy tắc xếp bãi Module 2 (Bãi & Container)
├── frontend/
│   ├── index.html                  # Cổng điều hành hợp nhất (SPMS Unified Portal)
│   ├── vessel_berth.html           # Giao diện Gantt Chart Cầu bến 2.040m
│   └── yard_container.html         # Giao diện trực quan hóa Lưới bãi Container 3D
├── tests/
│   └── test_spms.py                # 15 bài kiểm thử Unit & Integration tự động
├── schema.sql                      # Lược đồ cơ sở dữ liệu PostGIS hợp nhất
├── run_demo.py                     # Kịch bản khởi chạy nhanh server
├── run_tests.py                    # Kịch bản thực thi bộ kiểm thử
└── README.md                       # Tài liệu hướng dẫn sử dụng
```

---

## 🚀 Hướng dẫn khởi chạy ứng dụng

### 1. Cài đặt thư viện phụ thuộc:
```bash
pip install flask
```

### 2. Chạy Server:
Bạn có thể khởi động server bằng một trong hai cách:
```powershell
python run_demo.py
```
*hoặc*
```powershell
python backend/app.py
```

Sau khi server khởi động thành công, truy cập các địa chỉ trên trình duyệt:
- **Cổng điều hành hợp nhất**: [http://localhost:8088/](http://localhost:8088/)
- **Module 1 - Cầu bến & Lịch tàu**: [http://localhost:8088/vessel](http://localhost:8088/vessel)
- **Module 2 - Bãi & Container**: [http://localhost:8088/yard](http://localhost:8088/yard)

---

## 🧪 Chạy kiểm thử tự động (15 Test Cases)

Bộ kiểm thử bao quát toàn bộ chức năng kiểm tra hợp lệ IMO, độ sâu mớn nước, xung đột cầu bến, quy tắc an toàn container lạnh, trọng lực tầng bãi và endpoint tích hợp:

```powershell
python run_tests.py
```
*hoặc qua unittest module*:
```powershell
python -m unittest discover tests
```

---

## 📄 Bản quyền & Tác giả
- Nhóm 07 - Bộ môn Quản lý Dự án Phần mềm.
- Được cấp phép theo giấy phép [MIT](LICENSE).
