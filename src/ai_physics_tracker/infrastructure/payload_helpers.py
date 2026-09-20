"""serializer 共享的 JSON 类型强制校验助手；任何类型不符抛 ValueError。"""

from datetime import datetime
from typing import cast


def format_datetime(value: datetime) -> str:
    return value.isoformat()


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def string(payload: dict[str, object], key: str) -> str:
    return expect_string(payload[key], key)


def integer(payload: dict[str, object], key: str) -> int:
    return expect_integer(payload[key], key)


def number(payload: dict[str, object], key: str) -> float:
    return expect_number(payload[key], key)


def expect_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def optional_string(value: object) -> str | None:
    if value is None:
        return None
    return expect_string(value, "optional string")


def expect_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def optional_integer(value: object) -> int | None:
    if value is None:
        return None
    return expect_integer(value, "optional integer")


def expect_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def sequence(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def object_(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return cast(dict[str, object], value)


def json_object(value: object, name: str) -> dict:
    return object_(value, name)


def object_sequence(value: object, name: str) -> list[dict[str, object]]:
    return [object_(item, f"{name} item") for item in sequence(value, name)]


def sequence_of_sequences(value: object, name: str) -> list[list[object]]:
    return [sequence(item, f"{name} row") for item in sequence(value, name)]


def string_tuple(value: object, name: str) -> tuple[str, ...]:
    return tuple(expect_string(item, f"{name} item") for item in sequence(value, name))


def point(value: object, name: str) -> tuple[float, float]:
    coordinates = sequence(value, name)
    if len(coordinates) != 2:
        raise ValueError(f"{name} must contain two coordinates")
    return (
        expect_number(coordinates[0], f"{name}[0]"),
        expect_number(coordinates[1], f"{name}[1]"),
    )
