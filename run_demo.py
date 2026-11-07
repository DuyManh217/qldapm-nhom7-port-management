import os
import sys

# Set directory to backend
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(current_dir, "backend")
sys.path.insert(0, backend_dir)

import app

if __name__ == "__main__":
    port = 8088
    print("=" * 65)
    print(f"  SPMS FULL STACK SERVER RUNNING: http://localhost:{port}")
    print("  - Module 1 (Vessel & Berth)  : http://localhost:8088/vessel")
    print("  - Module 2 (Yard & Container): http://localhost:8088/yard")
    print("  - Portal Hợp Nhất           : http://localhost:8088/")
    print("=" * 65)
    app.app.run(host="0.0.0.0", port=port, debug=False)
