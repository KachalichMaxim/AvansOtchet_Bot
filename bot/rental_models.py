"""Data models for rental management."""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta
from bot.config import TIMEZONE
from pytz import timezone

TZ = timezone(TIMEZONE)


@dataclass
class RentalObject:
    """Rental object data model."""
    legal_entity: str  # Юр.лицо
    address: str  # Адрес
    mm_number: str  # М/М
    next_payment_date: Optional[str]  # Дата следующего платежа (DD.MM.YYYY или пусто)
    payment_amount: Optional[float]  # Платеж по аренде
    responsible: Optional[str]  # Ответственный
    paid_this_month: Optional[bool]  # Оплачено в текущем месяце (TRUE/FALSE)
    row_index: Optional[int] = None  # Индекс строки в таблице для обновления


def parse_rental_date(date_str: str) -> Optional[datetime]:
    """
    Parse rental date from DD.MM.YYYY format.
    
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str or not date_str.strip():
        return None
    
    try:
        # Try DD.MM.YYYY format
        day, month, year = map(int, date_str.strip().split('.'))
        # Handle 2-digit years (assume 20XX for years < 100)
        if year < 100:
            year += 2000
        return datetime(year, month, day, tzinfo=TZ)
    except (ValueError, AttributeError):
        return None


def format_rental_date(date: datetime) -> str:
    """
    Format datetime to DD.MM.YYYY format.
    
    Args:
        date: datetime object
        
    Returns:
        Formatted date string (DD.MM.YYYY)
    """
    return date.strftime("%d.%m.%Y")


def add_days_to_date(date_str: str, days: int) -> str:
    """
    Add days to a date string and return formatted result.
    
    Args:
        date_str: Date in DD.MM.YYYY format
        days: Number of days to add
        
    Returns:
        New date in DD.MM.YYYY format
    """
    date_obj = parse_rental_date(date_str)
    if date_obj is None:
        # If parsing fails, use current date
        date_obj = datetime.now(TZ)
    
    new_date = date_obj + timedelta(days=days)
    return format_rental_date(new_date)

