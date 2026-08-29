"""持久化错误层级，携带用户可恢复的上下文信息。"""


class ProjectFormatError(Exception):
    """项目数据无法读取或不受支持时的基础错误。"""


class UnsupportedSchemaVersionError(ProjectFormatError):
    """项目由更新版本的应用创建时抛出。"""
