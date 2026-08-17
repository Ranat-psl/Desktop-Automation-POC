"""WorkspaceService — create, load, and manage workspaces (Day 8).

Usage::

    from framework.workspace.workspace_service import WorkspaceService

    # Create a new workspace
    ws = WorkspaceService.create(root="~/my_project/workspace", name="MyProject")

    # Load an existing workspace
    ws = WorkspaceService.load(root="~/my_project/workspace")

    # Add a test-case folder
    folder = ws.add_test_case("login_flow")

    # Recordings for that folder live at:
    #   <workspace>/test-cases/login_flow/recordings/

This module does NOT touch the existing RecordingStore; it only provides
the folder structure.  RecordingStore consumers can point their
``recordings_dir`` at any path returned by this API.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

from framework.workspace.models import (
    DEFAULT_TEST_CASE_CATEGORIES,
    WORKSPACE_DIRS,
    TestCaseFolder,
    WorkspaceInfo,
    validate_name,
)

_log = logging.getLogger(__name__)

# Name of the lightweight metadata file stored at the workspace root.
_WORKSPACE_META_FILE = "workspace.json"


class WorkspaceError(Exception):
    """Base exception for workspace-related errors."""


class WorkspaceNotFoundError(WorkspaceError):
    """Raised when trying to load a workspace that does not exist."""


class DuplicateTestCaseFolderError(WorkspaceError):
    """Raised when a test-case folder with the same name already exists."""


class WorkspaceService:
    """Service for creating, loading, and managing workspaces.

    A workspace is a filesystem directory with a fixed layout::

        <root>/
        ├── workspace.json          ← lightweight metadata (name, version)
        ├── test-cases/
        │   ├── smoke/
        │   │   └── recordings/
        │   └── regression/
        │       └── recordings/
        ├── recordings/             ← workspace-level (legacy-compatible)
        ├── generated/
        ├── reports/
        └── metadata/               ← reserved for Day 17 metadata

    The ``recordings/`` directory at the workspace root is kept for backward
    compatibility with existing Day 6/7 RecordingStore usage.
    """

    def __init__(self, info: WorkspaceInfo) -> None:
        self._info = info

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def info(self) -> WorkspaceInfo:
        return self._info

    @property
    def root(self) -> Path:
        return self._info.root

    @property
    def name(self) -> str:
        return self._info.name

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        root: str | Path,
        name: str,
        default_categories: Sequence[str] = DEFAULT_TEST_CASE_CATEGORIES,
    ) -> "WorkspaceService":
        """Create a new workspace at *root*.

        If the directory already exists and contains a ``workspace.json``, it
        is loaded instead of being overwritten (idempotent).

        Args:
            root:               Filesystem path for the workspace root.
            name:               Human-readable workspace name.
            default_categories: Test-case category folders to pre-create.

        Returns:
            Initialised :class:`WorkspaceService`.

        Raises:
            ValueError:      If *name* is invalid.
            WorkspaceError:  If *root* exists as a file (not a directory).
            OSError:         For other filesystem errors.
        """
        validate_name(name)
        root_path = Path(root).expanduser().resolve()

        if root_path.is_file():
            raise WorkspaceError(
                f"Cannot create workspace: {root_path} exists as a file."
            )

        # Idempotent: if workspace already exists, load it.
        meta_file = root_path / _WORKSPACE_META_FILE
        if meta_file.exists():
            _log.info("Workspace already exists at %s — loading.", root_path)
            return cls.load(root_path)

        _log.info("Creating workspace %r at %s", name, root_path)

        # Create required directories.
        for dirname in WORKSPACE_DIRS:
            (root_path / dirname).mkdir(parents=True, exist_ok=True)

        # Write minimal metadata.
        meta = {"name": name, "version": 1}
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # Build WorkspaceInfo and create default test-case categories.
        info = WorkspaceInfo(name=name, root=root_path)
        svc = cls(info)
        for category in default_categories:
            svc.add_test_case(category)

        return svc

    @classmethod
    def load(cls, root: str | Path) -> "WorkspaceService":
        """Load an existing workspace from *root*.

        Does NOT delete or modify existing data.

        Raises:
            WorkspaceNotFoundError: If *root* is not a valid workspace.
            OSError:                For filesystem errors.
        """
        root_path = Path(root).expanduser().resolve()
        meta_file = root_path / _WORKSPACE_META_FILE

        if not root_path.is_dir():
            raise WorkspaceNotFoundError(
                f"Workspace directory not found: {root_path}"
            )
        if not meta_file.exists():
            raise WorkspaceNotFoundError(
                f"No workspace.json found at {root_path}. "
                "This does not appear to be a valid workspace."
            )

        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        name = meta.get("name", root_path.name)

        # Discover existing test-case folders.
        test_cases_root = root_path / "test-cases"
        test_cases: dict[str, TestCaseFolder] = {}
        if test_cases_root.is_dir():
            for child in sorted(test_cases_root.iterdir()):
                if child.is_dir():
                    test_cases[child.name] = TestCaseFolder(
                        name=child.name, path=child
                    )

        info = WorkspaceInfo(name=name, root=root_path, test_cases=test_cases)
        _log.info("Loaded workspace %r from %s", name, root_path)
        return cls(info)

    # ------------------------------------------------------------------
    # Test-case folder management
    # ------------------------------------------------------------------

    def add_test_case(self, name: str) -> TestCaseFolder:
        """Create a test-case category folder.

        Args:
            name: Category name — must match ``[A-Za-z0-9_\\-]{1,64}``.

        Returns:
            The new :class:`TestCaseFolder`.

        Raises:
            ValueError:                  If *name* is invalid.
            DuplicateTestCaseFolderError: If the category already exists.
        """
        validate_name(name)
        if name in self._info.test_cases:
            raise DuplicateTestCaseFolderError(
                f"Test-case folder {name!r} already exists in this workspace."
            )

        folder = TestCaseFolder(
            name=name,
            path=self._info.test_cases_path / name,
        )
        folder.create()
        self._info.test_cases[name] = folder
        _log.info("Created test-case folder %r at %s", name, folder.path)
        return folder

    def get_test_case(self, name: str) -> TestCaseFolder:
        """Return the :class:`TestCaseFolder` for *name*.

        Raises:
            KeyError: If the category does not exist.
        """
        try:
            return self._info.test_cases[name]
        except KeyError:
            raise KeyError(
                f"Test-case folder {name!r} not found. "
                f"Available: {sorted(self._info.test_cases)}"
            ) from None

    def list_test_cases(self) -> list[str]:
        """Return sorted list of test-case category names."""
        return sorted(self._info.test_cases)

    def test_case_exists(self, name: str) -> bool:
        return name in self._info.test_cases

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------

    def recordings_dir_for(self, test_case: str | None = None) -> Path:
        """Return the appropriate recordings directory.

        If *test_case* is given, returns the per-category recordings folder.
        If *test_case* is ``None``, returns the workspace-level ``recordings/``
        directory (backward-compatible with Day 6/7).

        Args:
            test_case: Category name, or ``None`` for the shared location.

        Returns:
            A :class:`~pathlib.Path` that is guaranteed to exist on return.
        """
        if test_case is None:
            target = self._info.recordings_path
        else:
            folder = self.get_test_case(test_case)
            target = folder.recordings_path

        target.mkdir(parents=True, exist_ok=True)
        return target

    # ------------------------------------------------------------------
    # Ensure required dirs (repair/migration helper)
    # ------------------------------------------------------------------

    def ensure_dirs(self) -> None:
        """Create any missing workspace directories without touching data."""
        for dirname in WORKSPACE_DIRS:
            (self._info.root / dirname).mkdir(parents=True, exist_ok=True)
        for folder in self._info.test_cases.values():
            folder.create()
