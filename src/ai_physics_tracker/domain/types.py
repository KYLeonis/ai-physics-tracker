"""领域层共享标量类型；不含任何框架依赖。"""

from datetime import UTC, datetime
from typing import TypeAlias

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonObject: TypeAlias = dict[str, JsonValue]


def utc_now() -> datetime:
    """返回带时区的 UTC 当前时间。"""

    return datetime.now(UTC)


def require_aware_datetime(value: datetime, field_name: str) -> None:
    """在领域构造边界拒绝无时区信息的 naive 时间戳。"""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
