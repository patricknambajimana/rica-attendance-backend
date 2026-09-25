from datetime import datetime, timedelta

from .errors import AppError


def parse_iso_date(value: str, field_name: str = "date") -> datetime:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise AppError(f"{field_name} must be YYYY-MM-DD", 400) from exc


def date_range_filter(date_from: str | None, date_to: str | None) -> dict:
    filt: dict = {}
    if date_from:
        filt["gte"] = parse_iso_date(date_from, "from")
    if date_to:
        filt["lt"] = parse_iso_date(date_to, "to") + timedelta(days=1)
    return filt


def iter_dates(start: datetime, end: datetime):
    current = datetime(start.year, start.month, start.day)
    last = datetime(end.year, end.month, end.day)
    while current <= last:
        yield current
        current += timedelta(days=1)
