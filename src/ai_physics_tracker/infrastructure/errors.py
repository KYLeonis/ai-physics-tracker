"""Persistence error hierarchy with user-recoverable context."""


class ProjectFormatError(Exception):
    """Base error for unreadable or unsupported project data."""


class UnsupportedSchemaVersionError(ProjectFormatError):
    """Raised when a project was created by a newer application version."""
