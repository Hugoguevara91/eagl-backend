import os
import sys

import requests


def check(endpoint: str) -> bool:
    url = f"{BASE_URL}{endpoint}"
    try:
        res = requests.get(url, timeout=10)
    except Exception:
        print(f"FAIL {endpoint}: request error")
        return False
    if res.status_code != 200:
        print(f"FAIL {endpoint}: HTTP {res.status_code}")
        return False
    status = res.json().get("status")
    if status not in {"OK", "WARN"}:
        print(f"FAIL {endpoint}: status={status}")
        return False
    print(f"OK   {endpoint}: status={status}")
    return True


BASE_URL = os.getenv("EAGL_API_BASE_URL", "http://127.0.0.1:8000/api")

ok = True
ok = check("/doctor") and ok
ok = check("/doctor/maps") and ok

sys.exit(0 if ok else 1)
