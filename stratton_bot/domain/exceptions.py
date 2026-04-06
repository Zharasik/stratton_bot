class StrattonError(Exception):
    """Base application error."""


class ConfigurationError(StrattonError):
    """Raised when application configuration is invalid."""


class ValidationError(StrattonError):
    """Raised when user input is invalid."""


class ConflictError(StrattonError):
    """Raised when operation cannot be completed because of current state."""


class NotFoundError(StrattonError):
    """Raised when entity was not found."""


class AccessDeniedError(StrattonError):
    """Raised when user has no permission for operation."""


class OCRProviderError(StrattonError):
    """Raised when OCR provider request failed."""


class OCRResponseError(StrattonError):
    """Raised when OCR provider returned invalid payload."""
