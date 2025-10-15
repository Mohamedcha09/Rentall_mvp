from app.email_service import send_email

ok = send_email(
    to_email="بريدك_الحقيقي@gmail.com",
    subject="🚀 Test Email - Sevor",
    html_body="<h2>Hello from Sevor App!</h2><p>This is a test email.</p>"
)
print("✅ Sent!" if ok else "❌ Failed.")