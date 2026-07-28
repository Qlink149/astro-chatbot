"""Static lint: UsersPage.jsx polling intervals must be 30000ms, not 5000ms.

User reported the 5s cadence caused visible refresh jitter. This lint asserts:
  - both setInterval(...) calls in UsersPage.jsx pass 30000
  - no 5000ms setInterval appears in the file
"""
import re
from pathlib import Path

USERS_PAGE = Path("/app/frontend/src/pages/users/UsersPage.jsx")


def test_users_page_polling_intervals_are_30s():
    src = USERS_PAGE.read_text()
    # Match setInterval(...) closing paren followed by comma + digits + close paren.
    # Handles inline arrow functions/blocks by anchoring on ", 30000)" pattern.
    intervals = re.findall(r"setInterval\(", src)
    trailing = re.findall(r",\s*(\d{2,6})\s*\)\s*(?://[^\n]*)?\s*\n\s*return\s*\(\s*\)\s*=>\s*clearInterval", src)
    assert len(intervals) == 2, f"Expected exactly 2 setInterval calls, got {len(intervals)}"
    assert len(trailing) == 2, f"Expected 2 interval durations, found {trailing}"
    for iv in trailing:
        assert int(iv) == 30000, f"setInterval must be 30000ms, got {iv}"


def test_users_page_no_5s_polling():
    src = USERS_PAGE.read_text()
    assert "setInterval(fetchUsers, 5000)" not in src
    assert re.search(r"setInterval\([^,]+,\s*5000\s*\)", src) is None, \
        "No setInterval should still be 5000ms"
