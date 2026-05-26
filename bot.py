import csv
import smtplib
import os
import sqlite3
import logging
import uuid
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Configuration ────────────────────────────────────────
EMAIL_SENDER   = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
TRACKER_URL    = os.environ.get("TRACKER_URL", "http://localhost:5000/track")

SMTP_SERVER  = "smtp.gmail.com"
SMTP_PORT    = 587
DAYS_WARNING = 7
LOG_FILE     = "bot.log"
DB_FILE      = "password_expiry.db"

# ── Validate Secrets ─────────────────────────────────────
if not EMAIL_SENDER or not EMAIL_PASSWORD:
    raise EnvironmentError(
        "❌ Missing Secrets! Set EMAIL_SENDER and EMAIL_PASSWORD "
        "in GitHub → Settings → Secrets → Actions."
    )

# ── Logging Setup ────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"✅ Secrets loaded — Sender: {EMAIL_SENDER}")


# ── Database Setup ───────────────────────────────────────
def init_database():
    """Initialize SQLite database with users and email_logs tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            email           TEXT NOT NULL UNIQUE,
            department      TEXT,
            password_expiry DATE NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email   TEXT NOT NULL,
            user_name    TEXT NOT NULL,
            days_left    INTEGER,
            status       TEXT NOT NULL,
            tracking_id  TEXT UNIQUE,
            opened       BOOLEAN DEFAULT 0,
            opened_at    TIMESTAMP,
            sent_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            error        TEXT
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")


def import_users_from_csv(csv_file="users.csv"):
    """Import users from CSV into SQLite database."""
    if not os.path.exists(csv_file):
        logger.warning(f"CSV file '{csv_file}' not found. Skipping import.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    imported = 0

    with open(csv_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO users (name, email, department, password_expiry)
                    VALUES (?, ?, ?, ?)
                """, (
                    row["Name"],
                    row["Email"],
                    row.get("Department", "General"),
                    row["PasswordExpiryDate"]
                ))
                imported += 1
            except Exception as e:
                logger.error(f"Failed to import user {row.get('Email')}: {e}")

    conn.commit()
    conn.close()
    logger.info(f"Imported {imported} user(s) from CSV into database.")


# ── Fetch Expiring Users ──────────────────────────────────
def get_expiring_users():
    """Query database for users whose passwords expire within warning period."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today = datetime.today().date()
    expiring = []

    cursor.execute("SELECT name, email, department, password_expiry FROM users")
    rows = cursor.fetchall()
    conn.close()

    for name, email, department, expiry_str in rows:
        try:
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            days_left = (expiry_date - today).days

            if 0 <= days_left <= DAYS_WARNING:
                expiring.append({
                    "name":        name,
                    "email":       email,
                    "department":  department,
                    "days_left":   days_left,
                    "expiry":      expiry_date.strftime("%B %d, %Y"),
                    "tracking_id": str(uuid.uuid4())
                })
        except Exception as e:
            logger.error(f"Error processing user {email}: {e}")

    return expiring


# ── Email Logger ──────────────────────────────────────────
def log_email(user, status, error=None):
    """Log every email attempt to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO email_logs (user_email, user_name, days_left, status, tracking_id, error)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user["email"],
        user["name"],
        user["days_left"],
        status,
        user.get("tracking_id"),
        error
    ))
    conn.commit()
    conn.close()


# ── Send Email ────────────────────────────────────────────
def send_email(user):
    """Send a professional HTML reminder email."""
    tracking_pixel = f'<img src="{TRACKER_URL}/{user["tracking_id"]}" width="1" height="1" style="display:none"/>'

    if user["days_left"] <= 1:
        urgency_color = "#e74c3c"
        urgency_text  = "URGENT: "
    elif user["days_left"] <= 3:
        urgency_color = "#e67e22"
        urgency_text  = "Warning: "
    else:
        urgency_color = "#2980b9"
        urgency_text  = ""

    msg = MIMEMultipart("alternative")
    msg["Subject"]    = f"⚠️ {urgency_text}Your password expires in {user['days_left']} day(s)"
    msg["From"]       = f"IT Support <{EMAIL_SENDER}>"
    msg["To"]         = user["email"]
    msg["X-Priority"] = "1" if user["days_left"] <= 1 else "3"

    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">

            <div style="border-left: 5px solid {urgency_color}; padding-left: 15px; margin-bottom: 25px;">
                <h2 style="color: {urgency_color}; margin: 0;">🔐 Password Expiry Reminder</h2>
                <p style="color: #666; margin: 5px 0;">IT Security Notification</p>
            </div>

            <p>Dear <strong>{user['name']}</strong>,</p>
            <p>This is an automated security notification from the IT Support Team.</p>

            <div style="background: #fff3cd; border: 1px solid {urgency_color}; border-radius: 6px; padding: 15px; margin: 20px 0;">
                <p style="margin: 0; font-size: 16px;">
                    Your network password will expire on
                    <strong style="color: {urgency_color};">{user['expiry']}</strong>
                    — <strong>{user['days_left']} day(s) remaining</strong>
                </p>
            </div>

            <h3 style="color: #2c3e50;">👉 How to Change Your Password:</h3>
            <ol style="line-height: 2;">
                <li>Press <code style="background:#eee; padding: 2px 6px; border-radius:3px;">Ctrl + Alt + Delete</code></li>
                <li>Select <strong>"Change a password"</strong></li>
                <li>Enter your current password</li>
                <li>Enter and confirm your new password</li>
                <li>Press <strong>Enter</strong> or click the arrow</li>
            </ol>

            <div style="background: #eaf4fb; border-radius: 6px; padding: 15px; margin: 20px 0;">
                <p style="margin: 0; color: #2980b9;">
                    💡 <strong>Password Requirements:</strong>
                    Minimum 8 characters, include uppercase, lowercase,
                    number and special character.
                </p>
            </div>

            <p style="color: #666;">
                If you need assistance, please contact IT Support:<br>
                📧 <a href="mailto:it@yourcompany.com">it@yourcompany.com</a><br>
                📞 Extension: 1234
            </p>

            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="color: #999; font-size: 12px;">
                This is an automated message from the IT Password Management System.<br>
                Department: {user['department']} | Notification ID: {user['tracking_id'][:8].upper()}
            </p>
        </div>
        {tracking_pixel}
    </body>
    </html>
    """

    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, user["email"], msg.as_string())

        log_email(user, "SUCCESS")
        logger.info(f"✅ Email sent → {user['name']} ({user['email']}) | {user['days_left']} days left")

    except smtplib.SMTPAuthenticationError:
        error = "Authentication failed — check EMAIL_SENDER and EMAIL_PASSWORD in GitHub Secrets"
        log_email(user, "FAILED", error)
        logger.error(f"❌ {error}")

    except smtplib.SMTPRecipientsRefused:
        error = f"Recipient refused: {user['email']}"
        log_email(user, "FAILED", error)
        logger.error(f"❌ {error}")

    except Exception as e:
        log_email(user, "FAILED", str(e))
        logger.error(f"❌ Failed to send to {user['email']}: {e}")


# ── Daily Report ──────────────────────────────────────────
def generate_report():
    """Print a summary report of today's email activity."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today = datetime.today().date()

    cursor.execute("""
        SELECT status, COUNT(*) FROM email_logs
        WHERE DATE(sent_at) = ?
        GROUP BY status
    """, (str(today),))

    results = cursor.fetchall()
    conn.close()

    logger.info("=" * 50)
    logger.info(f"📊 DAILY REPORT — {today}")
    for status, count in results:
        logger.info(f"   {status}: {count} email(s)")
    logger.info("=" * 50)


# ── Main ──────────────────────────────────────────────────
def run_bot():
    logger.info("=" * 50)
    logger.info(f"🔍 Bot started at {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    users = get_expiring_users()

    if not users:
        logger.info("✅ No passwords expiring in the next 7 days.")
    else:
        logger.info(f"⚠️  {len(users)} user(s) with expiring passwords found.")
        for user in users:
            send_email(user)

    generate_report()
    logger.info("✅ Bot run complete.")
    logger.info("=" * 50)


if __name__ == "__main__":
    logger.info("🤖 Password Expiry Bot initializing...")
    init_database()
    import_users_from_csv("users.csv")
    run_bot()
    logger.info("✅ GitHub Actions run complete.")