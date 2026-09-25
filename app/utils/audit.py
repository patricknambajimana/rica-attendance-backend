from datetime import datetime, timezone

from prisma import Json

from ..extensions import db


def log_action(
    action: str,
    *,
    user_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    delta: dict | None = None,
) -> None:
    data = {
        "action": action,
        "entityType": entity_type,
        "entityId": entity_id,
    }
    if user_id is not None:
        data["user"] = {"connect": {"id": user_id}}
    if delta is not None:
        data["delta"] = Json(delta)

    db.auditlog.create(data=data)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def date_only(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day)