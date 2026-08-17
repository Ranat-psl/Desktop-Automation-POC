"""Workspace models — lightweight dataclasses for Day 8.

Kept intentionally minimal to leave room for the Day 17 metadata feature.
No third-party dependencies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Directories always present in a valid workspace.
WORKSPACE_DIRS = (
    "test-cases",
    "recordings",
    "generated",
    "reports",
    "metadata",
)

#: Sub-directories created inside test-cases/ by default.
DEFAULT_TEST_CASE_CATEGORIES = ("smoke", "regression")

#: Pattern for a valid test-case or workspace name segment:
#: alphanumeric, dash, underscore; 1–64 characters.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_name(name: str) -> None:
    """Raise :class:`ValueError` if *name* is not a safe identifier.

    Prevents directory traversal, whitespace-only names, reserved OS names,
    and excessively long segments.
    """
    if not name or not name.strip():
        raise ValueError("Name must not be empty or blank.")
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid name {name!r}. Only letters, digits, hyphens, and "
            "underscores are allowed (1–64 characters)."
        )
    # Block Windows reserved names (CON, NUL, COM1…COM9, LPT1…LPT9, etc.)
    reserved = {"CON", "NUL", "AUX", "PRN", "COM1", "COM2", "COM3", "COM4",
                "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2",
                "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}
    if name.upper() in reserved:
        raise ValueError(f"Name {name!r} is a reserved OS name.")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TestCaseFolder:
    """Represents a single test-case category folder inside a workspace.

    Attributes:
        name:       Category name (e.g. ``"smoke"``, ``"regression"``).
        path:       Absolute path to the folder on disk.
        recordings_path: Sub-folder where recordings for this category live.
    """

    # Prevent pytest from trying to collect this dataclass as a test class.
    __test__ = False

    name: str
    path: Path

    @property
    def recordings_path(self) -> Path:
        """Path where recordings for this test-case category are stored."""
        return self.path / "recordings"

    def create(self) -> None:
        """Create the folder and its recordings sub-directory on disk."""
        self.path.mkdir(parents=True, exist_ok=True)
        self.recordings_path.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.path.is_dir()


@dataclass
class WorkspaceInfo:
    """Lightweight descriptor for an open workspace.

    This is intentionally minimal for Day 8.  Day 17 will extend it with
    full test-case metadata (tags, status, linked recordings, etc.).

    Attributes:
        name:        Human-readable workspace name.
        root:        Absolute path to the workspace root directory.
        test_cases:  Mapping of category name → :class:`TestCaseFolder`.
    """

    name: str
    root: Path
    test_cases: dict[str, TestCaseFolder] = field(default_factory=dict)

    # Convenience path accessors ------------------------------------------

    @property
    def recordings_path(self) -> Path:
        return self.root / "recordings"

    @property
    def generated_path(self) -> Path:
        return self.root / "generated"

    @property
    def reports_path(self) -> Path:
        return self.root / "reports"

    @property
    def metadata_path(self) -> Path:
        return self.root / "metadata"

    @property
    def test_cases_path(self) -> Path:
        return self.root / "test-cases"
