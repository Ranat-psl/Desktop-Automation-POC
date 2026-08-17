"""Day 8 — Workspace & Test-Case Folder targeted smoke tests.

All tests use temporary directories (pytest's tmp_path fixture) and do NOT
launch any Windows UI or external processes.  Temporary directories are
cleaned up automatically by pytest after each test.

Coverage:
    - workspace creation
    - workspace loading
    - required directory creation
    - existing workspace preservation
    - smoke folder creation
    - regression folder creation
    - custom folder creation
    - invalid folder/path handling
    - duplicate folder handling
    - recording placement / association
    - workspace.json metadata round-trip
    - WorkspaceInfo path accessors
    - validate_name safety checks
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.workspace.models import (
    DEFAULT_TEST_CASE_CATEGORIES,
    WORKSPACE_DIRS,
    TestCaseFolder,
    WorkspaceInfo,
    validate_name,
)
from framework.workspace.workspace_service import (
    DuplicateTestCaseFolderError,
    WorkspaceError,
    WorkspaceNotFoundError,
    WorkspaceService,
)


# ===========================================================================
# validate_name
# ===========================================================================


class TestValidateName:
    def test_valid_simple(self) -> None:
        validate_name("smoke")  # must not raise

    def test_valid_with_dash(self) -> None:
        validate_name("login-flow")

    def test_valid_with_underscore(self) -> None:
        validate_name("login_flow")

    def test_valid_alphanumeric(self) -> None:
        validate_name("Flow01")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            validate_name("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_name("   ")

    def test_path_traversal_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_name("../evil")

    def test_slash_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_name("foo/bar")

    def test_backslash_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_name("foo\\bar")

    def test_space_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_name("has space")

    def test_too_long_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_name("a" * 65)

    def test_reserved_con_raises(self) -> None:
        with pytest.raises(ValueError, match="reserved"):
            validate_name("CON")

    def test_reserved_nul_raises(self) -> None:
        with pytest.raises(ValueError, match="reserved"):
            validate_name("NUL")


# ===========================================================================
# Workspace creation
# ===========================================================================


class TestWorkspaceCreation:
    def test_creates_root_directory(self, tmp_path) -> None:
        root = tmp_path / "ws"
        WorkspaceService.create(root=root, name="MyProject")
        assert root.is_dir()

    def test_creates_all_required_dirs(self, tmp_path) -> None:
        root = tmp_path / "ws"
        WorkspaceService.create(root=root, name="MyProject")
        for dirname in WORKSPACE_DIRS:
            assert (root / dirname).is_dir(), f"Missing: {dirname}"

    def test_creates_workspace_json(self, tmp_path) -> None:
        root = tmp_path / "ws"
        WorkspaceService.create(root=root, name="MyProject")
        meta_file = root / "workspace.json"
        assert meta_file.exists()

    def test_workspace_json_contains_name(self, tmp_path) -> None:
        root = tmp_path / "ws"
        WorkspaceService.create(root=root, name="MyProject")
        data = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
        assert data["name"] == "MyProject"

    def test_workspace_json_contains_version(self, tmp_path) -> None:
        root = tmp_path / "ws"
        WorkspaceService.create(root=root, name="MyProject")
        data = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
        assert "version" in data

    def test_creates_smoke_test_case_by_default(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        assert "smoke" in svc.list_test_cases()

    def test_creates_regression_test_case_by_default(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        assert "regression" in svc.list_test_cases()

    def test_invalid_name_raises(self, tmp_path) -> None:
        with pytest.raises(ValueError):
            WorkspaceService.create(root=tmp_path / "ws", name="bad name!")

    def test_root_is_file_raises(self, tmp_path) -> None:
        blocker = tmp_path / "ws"
        blocker.write_text("I am a file")
        with pytest.raises(WorkspaceError):
            WorkspaceService.create(root=blocker, name="P")

    def test_nested_root_created_automatically(self, tmp_path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "ws"
        WorkspaceService.create(root=deep, name="Deep")
        assert deep.is_dir()

    def test_create_is_idempotent(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc1 = WorkspaceService.create(root=root, name="P")
        svc2 = WorkspaceService.create(root=root, name="P")
        assert svc1.name == svc2.name


# ===========================================================================
# Workspace loading
# ===========================================================================


class TestWorkspaceLoading:
    def test_load_returns_correct_name(self, tmp_path) -> None:
        root = tmp_path / "ws"
        WorkspaceService.create(root=root, name="LoadTest")
        loaded = WorkspaceService.load(root)
        assert loaded.name == "LoadTest"

    def test_load_discovers_existing_test_cases(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        svc.add_test_case("integration")
        loaded = WorkspaceService.load(root)
        assert "integration" in loaded.list_test_cases()

    def test_load_preserves_default_categories(self, tmp_path) -> None:
        root = tmp_path / "ws"
        WorkspaceService.create(root=root, name="P")
        loaded = WorkspaceService.load(root)
        for cat in DEFAULT_TEST_CASE_CATEGORIES:
            assert cat in loaded.list_test_cases()

    def test_load_missing_dir_raises(self, tmp_path) -> None:
        with pytest.raises(WorkspaceNotFoundError):
            WorkspaceService.load(tmp_path / "no_such_dir")

    def test_load_dir_without_metadata_raises(self, tmp_path) -> None:
        orphan = tmp_path / "orphan"
        orphan.mkdir()
        with pytest.raises(WorkspaceNotFoundError, match="workspace.json"):
            WorkspaceService.load(orphan)

    def test_load_does_not_delete_existing_files(self, tmp_path) -> None:
        root = tmp_path / "ws"
        WorkspaceService.create(root=root, name="P")
        sentinel = root / "recordings" / "existing.json"
        sentinel.write_text('[]', encoding="utf-8")
        WorkspaceService.load(root)
        assert sentinel.exists()


# ===========================================================================
# Test-case folder management
# ===========================================================================


class TestTestCaseFolderManagement:
    def test_add_smoke_folder(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P", default_categories=[])
        folder = svc.add_test_case("smoke")
        assert folder.path.is_dir()
        assert svc.test_case_exists("smoke")

    def test_add_regression_folder(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P", default_categories=[])
        folder = svc.add_test_case("regression")
        assert folder.path.is_dir()
        assert svc.test_case_exists("regression")

    def test_add_custom_folder(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P", default_categories=[])
        folder = svc.add_test_case("login-flow")
        assert folder.path.is_dir()

    def test_add_folder_creates_recordings_subdir(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P", default_categories=[])
        folder = svc.add_test_case("smoke")
        assert folder.recordings_path.is_dir()

    def test_duplicate_folder_raises(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P", default_categories=[])
        svc.add_test_case("smoke")
        with pytest.raises(DuplicateTestCaseFolderError):
            svc.add_test_case("smoke")

    def test_invalid_folder_name_raises(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P", default_categories=[])
        with pytest.raises(ValueError):
            svc.add_test_case("has space")

    def test_path_traversal_in_folder_name_raises(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P", default_categories=[])
        with pytest.raises(ValueError):
            svc.add_test_case("../../evil")

    def test_list_test_cases_returns_sorted(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P", default_categories=[])
        svc.add_test_case("zebra")
        svc.add_test_case("alpha")
        assert svc.list_test_cases() == ["alpha", "zebra"]

    def test_get_test_case_returns_folder(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P", default_categories=[])
        svc.add_test_case("smoke")
        folder = svc.get_test_case("smoke")
        assert isinstance(folder, TestCaseFolder)
        assert folder.name == "smoke"

    def test_get_missing_test_case_raises(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P", default_categories=[])
        with pytest.raises(KeyError):
            svc.get_test_case("nonexistent")


# ===========================================================================
# Recording organization
# ===========================================================================


class TestRecordingOrganization:
    def test_workspace_level_recordings_dir(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        rec_dir = svc.recordings_dir_for()
        assert rec_dir == root / "recordings"
        assert rec_dir.is_dir()

    def test_test_case_recordings_dir(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        rec_dir = svc.recordings_dir_for("smoke")
        assert rec_dir == root / "test-cases" / "smoke" / "recordings"
        assert rec_dir.is_dir()

    def test_recordings_dir_for_unknown_case_raises(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        with pytest.raises(KeyError):
            svc.recordings_dir_for("nonexistent")

    def test_recording_store_compat_workspace_level(self, tmp_path) -> None:
        """RecordingStore can be pointed at workspace-level recordings dir."""
        from framework.recorder.recording_store import RecordingStore
        from framework.core.models import Action, ActionType

        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        rec_dir = svc.recordings_dir_for()

        store = RecordingStore(base_dir=rec_dir)
        actions = [Action(action_type=ActionType.LAUNCH, value="notepad.exe")]
        path = store.save("test_recording", actions)
        assert path.exists()
        assert path.suffix == ".json"

    def test_recording_store_compat_test_case_level(self, tmp_path) -> None:
        """RecordingStore can be pointed at per-test-case recordings dir."""
        from framework.recorder.recording_store import RecordingStore
        from framework.core.models import Action, ActionType

        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        rec_dir = svc.recordings_dir_for("regression")

        store = RecordingStore(base_dir=rec_dir)
        actions = [Action(action_type=ActionType.TYPE, value="hello")]
        path = store.save("reg_flow", actions)
        loaded = store.load("reg_flow")
        assert loaded[0].value == "hello"

    def test_existing_recordings_not_deleted_on_create(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        sentinel = svc.recordings_dir_for() / "old_flow.json"
        sentinel.write_text("[]", encoding="utf-8")
        # Re-create / ensure_dirs must not remove existing files
        svc.ensure_dirs()
        assert sentinel.exists()


# ===========================================================================
# WorkspaceInfo path accessors
# ===========================================================================


class TestWorkspaceInfoPaths:
    def test_recordings_path_accessor(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        assert svc.info.recordings_path == root / "recordings"

    def test_generated_path_accessor(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        assert svc.info.generated_path == root / "generated"

    def test_reports_path_accessor(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        assert svc.info.reports_path == root / "reports"

    def test_metadata_path_accessor(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        assert svc.info.metadata_path == root / "metadata"

    def test_test_cases_path_accessor(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        assert svc.info.test_cases_path == root / "test-cases"


# ===========================================================================
# ensure_dirs repair helper
# ===========================================================================


class TestEnsureDirs:
    def test_ensure_dirs_recreates_missing_dir(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        import shutil
        shutil.rmtree(root / "reports")
        svc.ensure_dirs()
        assert (root / "reports").is_dir()

    def test_ensure_dirs_preserves_existing_files(self, tmp_path) -> None:
        root = tmp_path / "ws"
        svc = WorkspaceService.create(root=root, name="P")
        sentinel = root / "metadata" / "notes.txt"
        sentinel.write_text("keep me", encoding="utf-8")
        svc.ensure_dirs()
        assert sentinel.read_text(encoding="utf-8") == "keep me"
