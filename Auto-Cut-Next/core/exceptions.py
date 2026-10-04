"""Custom exception hierarchy for Auto-Cut-Next."""


class AutoCutError(Exception):
    """Base exception for all Auto-Cut-Next errors."""
    pass


class IngestError(AutoCutError):
    """Raised when source image ingestion fails."""
    pass


class CorruptImageError(IngestError):
    """Raised when an image cannot be read, decoded or has invalid dimensions."""
    pass


class PathTraversalError(IngestError):
    """Raised when a file path escapes the permitted directory."""
    pass


class SessionError(AutoCutError):
    """Base exception for session operations."""
    pass


class SessionCorruptError(SessionError):
    """Raised when session manifest JSON cannot be parsed or lacks required fields."""
    pass


class SessionIncompatibleError(SessionError):
    """Raised when session schema version is newer than supported."""
    pass


class CacheError(AutoCutError):
    """Raised on cache reading or writing failure."""
    pass


class ConfigurationError(AutoCutError):
    """Raised when settings or configuration validation fails."""
    pass
