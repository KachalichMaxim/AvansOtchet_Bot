"""Utility functions for the bot."""
import re
from datetime import datetime
from pytz import timezone
from bot.config import TIMEZONE

TZ = timezone(TIMEZONE)


def validate_date(date_str: str) -> tuple[bool, str]:
    """
    Validate date format dd.mm.yyyy.
    
    Returns:
        (is_valid, error_message)
    """
    pattern = r'^\d{2}\.\d{2}\.\d{4}$'
    if not re.match(pattern, date_str):
        return False, "Неверный формат даты. Используйте формат: dd.mm.yyyy (например, 02.01.2026)"
    
    try:
        day, month, year = map(int, date_str.split('.'))
        datetime(year, month, day)
        return True, ""
    except ValueError:
        return False, "Неверная дата. Проверьте день, месяц и год."


def validate_amount(amount_str: str) -> tuple[bool, float | None, str]:
    """
    Validate amount - must be positive number.
    
    Returns:
        (is_valid, amount_value, error_message)
    """
    try:
        # Remove spaces and replace comma with dot
        cleaned = amount_str.replace(" ", "").replace(",", ".")
        amount = float(cleaned)
        
        if amount <= 0:
            return False, None, "Сумма должна быть положительным числом."
        
        return True, amount, ""
    except ValueError:
        return False, None, "Неверный формат суммы. Введите положительное число."


def format_balance(balance: float) -> str:
    """Format balance with currency symbol."""
    return f"{balance:,.0f} ₽".replace(",", " ")


def get_current_month() -> str:
    """Get current month in MM.YYYY format."""
    now = datetime.now(TZ)
    return f"{now.month:02d}.{now.year}"


def parse_month(month_str: str) -> tuple[bool, str | None, str]:
    """
    Parse month string (MM.YYYY or similar formats).
    
    Returns:
        (is_valid, month_string, error_message)
    """
    # Try MM.YYYY format
    pattern = r'^(\d{1,2})\.(\d{4})$'
    match = re.match(pattern, month_str)
    
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            return True, f"{month:02d}.{year}", ""
        else:
            return False, None, "Месяц должен быть от 1 до 12."
    
    return False, None, "Неверный формат месяца. Используйте MM.YYYY (например, 01.2026)"


def get_current_timestamp() -> str:
    """Get current timestamp in UTC+3 timezone formatted for audit log."""
    now = datetime.now(TZ)
    return now.strftime("%Y-%m-%d %H:%M:%S")


def format_date_for_sheets(date_str: str) -> str:
    """Ensure date is in dd.mm.yyyy format for sheets."""
    return date_str


