class FrameworkError(Exception):
    """Base exception for framework-level failures."""


class LocatorResolutionError(FrameworkError):
    """Raised when a locator cannot be translated or applied."""


class ApprovalRequiredError(FrameworkError):
    """Raised when a sensitive action is blocked by approval policy."""


class PlaybackExecutionError(FrameworkError):
    """Raised when playback action execution fails."""
