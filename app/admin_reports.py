# app/admin_reports.py
"""
A simple bridge to re-export the admin reports router:
- Keeps main.py unchanged (no need to modify it)
- Reuses the same router defined inside app/reports.py
"""

from .reports import router  # Same router that serves /admin/reports
