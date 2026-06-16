from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def next_id(db: Session, model: type, field_name: str, prefix: str) -> str:
    field = getattr(model, field_name)
    count = db.scalar(select(func.count()).select_from(model)) or 0
    while True:
        candidate = f"{prefix}_{count + 1:03d}"
        exists = db.scalar(select(model).where(field == candidate))
        if exists is None:
            return candidate
        count += 1


def highest_status(statuses: list[str]) -> str:
    rank = {"failed": 4, "critical": 3, "warning": 2, "pending_review": 1, "normal": 0}
    if not statuses:
        return "normal"
    return max(statuses, key=lambda item: rank.get(item, 0))
