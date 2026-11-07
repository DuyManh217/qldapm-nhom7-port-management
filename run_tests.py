import os
import sys
import unittest

sys.stdout.reconfigure(encoding='utf-8')

# Add backend directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(current_dir, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

print("=" * 70)
print("  SPMS - BỘ KIỂM THỬ TỰ ĐỘNG HỆ THỐNG QUẢN LÝ CẢNG BIỂN THÔNG MINH")
print("  Tân Cảng Sài Gòn (SNP) · Cát Lái & Cái Mép · Test Suite Runner")
print("=" * 70)

suite = unittest.defaultTestLoader.discover(os.path.join(current_dir, "tests"), pattern="test_*.py")
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

if result.wasSuccessful():
    print("\n✓ TOÀN BỘ CÁC BÀI KIỂM THỬ ĐỀU ĐẠT CHUẨN (PASS 100%)!\n")
    sys.exit(0)
else:
    print("\n✗ CÓ BÀI KIỂM THỬ THẤT BẠI!\n")
    sys.exit(1)
