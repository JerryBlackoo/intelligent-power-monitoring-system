from datetime import datetime
import re
from typing import Optional


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def timestamp_slug(value: Optional[str] = None) -> str:
    return re.sub(r"[^0-9]", "", value or now_text())[:14]
