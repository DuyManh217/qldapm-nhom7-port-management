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
pip install -r requirements.txt
```

### 2. Kết nối Cơ sở dữ liệu (PostgreSQL Local + SQLite Fallback):
Hệ thống mặc định ưu tiên kết nối **PostgreSQL** chạy tại máy cá nhân (local). Nếu máy chưa bật PostgreSQL, hệ thống sẽ tự động chuyển về dùng **SQLite** (`backend/spms.db`).

Để chạy với **PostgreSQL Local**:
1. Cài đặt PostgreSQL và tạo một database rỗng tên `spms_db` (ví dụ: `createdb -U postgres spms_db` hoặc tạo trong pgAdmin 4).
2. Nếu tài khoản `postgres` trên máy có đặt mật khẩu (hoặc khác cấu hình mặc định `127.0.0.1:5432`, user `postgres`, db `spms_db`), thiết lập biến môi trường trước khi chạy:
   ```powershell
   $env:SPMS_PG_HOST="127.0.0.1"
   $env:SPMS_PG_PORT="5432"
   $env:SPMS_PG_USER="postgres"
   $env:SPMS_PG_PASSWORD="mat_khau_cua_ban"
   $env:SPMS_PG_DBNAME="spms_db"
   ```
   *(Nếu muốn ép chạy bằng SQLite: `$env:SPMS_FORCE_SQLITE="1"`)*
3. Khi khởi chạy server lần đầu, hệ thống tự động tạo đầy đủ các bảng và nạp dữ liệu mẫu vào PostgreSQL.

### 3. Chạy Server:
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

## 🔁 CI bằng GitHub Actions

Workflow CI nằm tại `.github/workflows/ci.yml` và được chạy tự động khi:

- push lên nhánh `main` hoặc `develop`;
- tạo Pull Request vào nhánh `main`.

CI thực hiện các bước: cài dependency, kiểm tra cú pháp Python, chạy lint cơ bản và chạy toàn bộ test. Có thể xem kết quả tại tab **Actions** của repository. Nếu một bước thất bại, Pull Request cần được sửa trước khi hợp nhất vào `main`.

CI hiện chỉ kiểm tra mã nguồn và test; chưa tự động deploy lên Staging/Production. CD là hướng phát triển tương lai khi nhóm có hạ tầng triển khai phù hợp.

---

## 📄 Bản quyền & Tác giả
- Nhóm 07 - Bộ môn Quản lý Dự án Phần mềm.
- Được cấp phép theo giấy phép [MIT](LICENSE).
