# RentAll MVP (Anything Rental) — Free, Simple, No JWT

This is a minimal **FastAPI + SQLite + SQLAlchemy + Jinja2** scaffold with **session-based auth** (no JWT) to kickstart your school project.
It includes:
- Register/Login with document upload for identity verification (admin review).
- Admin dashboard to approve/reject users.
- Basic home page and profile page.
- Ready to extend (items, bookings, messaging, ratings).

## 🚀 Run locally
```bash
python -m venv venv
source venv/bin/activate  # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # (or copy manually)
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000

## 🔐 Default Admin
- Email: `chachouamohamed57@gmail.com`
- Password: `Blida0909`

## 📁 Structure
```
rentall_mvp/
  app/
    main.py
    database.py
    models.py
    utils.py
    auth.py
    admin.py
    templates/
      base.html, home.html, auth_login.html, auth_register.html, admin_dashboard.html, profile.html
    static/
      style.css
  uploads/
    ids/
  requirements.txt
  .env.example
  README.md
```

## ➕ Next steps (suggested)
- Add Items & Bookings routes and templates.
- Add Inbox & Chat (Threads/Messages tables).
- Add User Public Profile & Ratings.
- Add Owner/Admin dashboards in more detail.
