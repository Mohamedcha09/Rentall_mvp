# init_db.py
from app.database import engine, Base
import app.models  # تأكد أن ملف models.py فيه تعريف جدول Message وغيره

print("⏳ إنشاء الجداول...")
Base.metadata.create_all(bind=engine)
print("✔ تم إنشاء/تأكيد الجداول.")
