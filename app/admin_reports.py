# app/admin_reports.py
"""
جسر بسيط لإعادة تصدير راوتر البلاغات الإداري:
- يبقي main.py كما هو (لا حاجة لتغييره)
- يعيد استخدام نفس الراوتر الموجود داخل app/reports.py
"""

from .reports import router  # نفس الراوتر الذي يقدّم /admin/reports
