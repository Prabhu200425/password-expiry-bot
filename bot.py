import csv
import smtplib
import schedule
import time
import os
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

EMAIL_SENDER   = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER    = "smtp.gmail.com"
SMTP_PORT      = 587
DAYS_WARNING   = 7  # warn users this many days before expiry


def get_expiring_users():
    """Read CSV and return users whose passwords expire within 7 days."""
    expiring = []
    today = datetime.today().date()

    with open("users.csv", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            expiry_date = datetime.strptime(row["PasswordExpiryDate"], "%Y-%m-%d").date()
            days_left = (expiry_date - today).days

            if 0 <= days_left <= DAYS_WARNING:
                expiring.append({
                    "name":      row["Name"],
                    "email":     row["Email"],
                    "days_left": days_left,
                    "expiry":    expiry_date.strftime("%B %d, %Y")
                })

    return expiring


def send_email(user):
    """Send a personalized HTML reminder email."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⚠️ Your password expires in {user['days_left']} day(s)"
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = user["email"]

    body = f"""
    <html><body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #e74c3c;">🔐 Password Expiry Reminder</h2>
        <p>Hi <strong>{user['name']}</strong>,</p>
        <p>Your network password will expire on
           <strong style="color: #e74c3c;">{user['expiry']}</strong>
           — that's in <strong>{user['days_left']} day(s)</strong>.</p>

        <h3>👉 How to change your password:</h3>
        <ol>
            <li>Press <code>Ctrl + Alt + Delete</code></li>
            <li>Click <strong>"Change a password"</strong></li>
            <li>Enter your old password, then your new one twice</li>
        </ol>

        <p style="color: #888;">Need help? Contact IT Support at
           <a href="mailto:it@yourcompany.com">it@yourcompany.com</a></p>

        <p>— IT Support Team 🔐</p>
    </body></html>
    """

    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, user["email"], msg.as_string())

    print(f"  ✅ Email sent → {user['name']} ({user['email']})")


def run_bot():
    print(f"\n🔍 Checking users... [{datetime.now().strftime('%Y-%m-%d %H:%M')}]")
    users = get_expiring_users()

    if not users:
        print("  ✅ No passwords expiring in the next 7 days.")
        return

    print(f"  ⚠️  {len(users)} user(s) with expiring passwords:")
    for user in users:
        print(f"     → {user['name']} | Expires: {user['expiry']} | {user['days_left']} days left")
        send_email(user)


# Runs every day at 8:00 AM
schedule.every().day.at("08:00").do(run_bot)

if __name__ == "__main__":
    print("🤖 Password Expiry Bot is running...")
    run_bot()  # run once immediately
    while True:
        schedule.run_pending()
        time.sleep(60)