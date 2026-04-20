from __future__ import annotations


class IntegrityError(RuntimeError):
    """Raised when template checksum verification fails."""


class DeprecatedTemplateError(RuntimeError):
    """Raised when a deprecated template version is requested."""


class LayoutOverflowError(RuntimeError):
    """Raised when layout simulation detects non-recoverable overflow."""


class VisualValidationError(RuntimeError):
    """Raised when visual validation fails."""

    def __init__(self, message: str, failures: list[dict] | None = None):
        super().__init__(message)
        self.failures = failures or []
