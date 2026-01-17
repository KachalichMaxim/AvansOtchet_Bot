"""Configuration management for the bot."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8538778789:AAEyEwR3h7HkVKHshli7eafd3Fchg9rRd_k")

# Google Sheets Configuration
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "1TfF8PFjJ0cBOWLtod6OpNhRtOSGZDbOKCG7NIdudzoY")
GOOGLE_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    str(Path(__file__).parent.parent / "tonal-concord-464913-u3-2024741e839c.json")
)

# Timezone
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

# Sheet Names
SHEET_REFERENCE = "Справочник"
SHEET_TEMPLATE = "Шаблон_Сотрудника"
SHEET_AUDIT_LOG = "Audit_Log"
SHEET_MONTHLY_SUMMARY = "Итоги_Месяц"
SHEET_USERS = "Users"
SHEET_RENTAL = "Справочник М/М"

