"""领域层共享的持久化相对路径校验；不含宿主平台调用。"""

from pathlib import PurePosixPath, PureWindowsPath

WINDOWS_ILLEGAL_CHARS = frozenset('<>:"\\|?*')
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def validate_managed_relative_path(path: PurePosixPath, field_name: str) -> None:
    """校验项目内相对路径：POSIX 分隔、不逃逸、Windows 安全（contract §1）。

    绝对路径、`..` 段、Windows 保留名/非法字符一律在构造边界拒绝；
    错误消息携带字段名以便定位。
    """

    windows_path = PureWindowsPath(path.as_posix())
    if (
        not path.parts
        or ".." in path.parts
        or windows_path.drive
        or windows_path.root
    ):
        raise ValueError(f"{field_name} must stay inside the project using POSIX separators")
    for component in path.parts:
        reserved_stem = component.split(".", maxsplit=1)[0].upper()
        if (
            any(character in WINDOWS_ILLEGAL_CHARS for character in component)
            or component.endswith((" ", "."))
            or reserved_stem in WINDOWS_RESERVED_NAMES
        ):
            raise ValueError(f"{field_name} is not Windows-safe: {component}")
