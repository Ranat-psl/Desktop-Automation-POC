"""Focused tests for click/mouse action validation and click reliability.

Covers:
  A. screen_info.scale_coords — coordinate scaling math
  B. RecordingStore — new envelope format + backward compat with legacy flat list
  C. ActionNormalizer — CLICK records screen_width/screen_height in metadata
  D. PlaybackExecutor — coordinate scaling applied at execution time
  E. Mixed keyboard + mouse end-to-end recording scenario
  F. CLICK failure handling — FAILED result, screenshot, cleanup
  G. HTML report — CLICK actions render correctly
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from framework.core.models import Action, ActionType, Locator
from framework.playback.executor import PlaybackExecutor


# ===========================================================================
# A. scale_coords — resolution scaling math
# ===========================================================================

class TestScaleCoords:
    def test_same_resolution_returns_unchanged(self):
        from framework.driver.screen_info import scale_coords
        with patch("framework.driver.screen_info.get_screen_size", return_value=(1920, 1080)):
            result = scale_coords(960, 540, 1920, 1080)
        assert result == (960, 540)

    def test_scale_up_doubles_resolution(self):
        from framework.driver.screen_info import scale_coords
        with patch("framework.driver.screen_info.get_screen_size", return_value=(3840, 2160)):
            result = scale_coords(100, 200, 1920, 1080)
        assert result == (200, 400)

    def test_scale_down_halves_resolution(self):
        from framework.driver.screen_info import scale_coords
        with patch("framework.driver.screen_info.get_screen_size", return_value=(1920, 1080)):
            result = scale_coords(200, 400, 3840, 2160)
        assert result == (100, 200)

    def test_zero_recorded_resolution_returns_unchanged(self):
        from framework.driver.screen_info import scale_coords
        with patch("framework.driver.screen_info.get_screen_size", return_value=(1920, 1080)):
            result = scale_coords(100, 200, 0, 0)
        assert result == (100, 200)

    def test_zero_current_resolution_returns_unchanged(self):
        from framework.driver.screen_info import scale_coords
        with patch("framework.driver.screen_info.get_screen_size", return_value=(0, 0)):
            result = scale_coords(100, 200, 1920, 1080)
        assert result == (100, 200)

    def test_partial_scale_rounds_correctly(self):
        from framework.driver.screen_info import scale_coords
        with patch("framework.driver.screen_info.get_screen_size", return_value=(2560, 1440)):
            sx, sy = scale_coords(100, 50, 1920, 1080)
        assert sx == round(100 * 2560 / 1920)
        assert sy == round(50 * 1440 / 1080)

    def test_get_screen_size_returns_tuple_of_ints(self):
        from framework.driver.screen_info import get_screen_size
        w, h = get_screen_size()
        assert isinstance(w, int)
        assert isinstance(h, int)
        # On a real Windows machine both are > 0; in CI they may be 0.
        assert w >= 0 and h >= 0


# ===========================================================================
# B. RecordingStore — new envelope format + backward compat
# ===========================================================================

class TestRecordingStoreEnvelope:
    def test_save_produces_envelope_with_meta(self, tmp_path):
        from framework.recorder.recording_store import RecordingStore

        store = RecordingStore(base_dir=tmp_path)
        actions = [
            Action(action_type=ActionType.KEY, value="enter"),
        ]
        with patch("framework.recorder.recording_store.get_screen_size", return_value=(1920, 1080)):
            store.save("rec_a", actions)

        raw = json.loads((tmp_path / "rec_a.json").read_text())
        assert isinstance(raw, dict), "New format must be a dict, not a list"
        assert "meta" in raw
        assert "actions" in raw
        assert raw["meta"]["screen_width"] == 1920
        assert raw["meta"]["screen_height"] == 1080
        assert raw["meta"]["version"] == 1
        assert len(raw["actions"]) == 1

    def test_load_new_envelope_format(self, tmp_path):
        from framework.recorder.recording_store import RecordingStore

        store = RecordingStore(base_dir=tmp_path)
        payload = {
            "meta": {"version": 1, "screen_width": 1920, "screen_height": 1080},
            "actions": [
                {
                    "action_type": "click",
                    "locator": {"by": "auto_id", "value": "Btn1"},
                    "value": None,
                    "timeout_seconds": None,
                    "metadata": {"recorded_x": 100, "recorded_y": 200,
                                 "screen_width": 1920, "screen_height": 1080},
                }
            ],
        }
        (tmp_path / "rec_b.json").write_text(json.dumps(payload))
        actions = store.load("rec_b")
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.CLICK
        assert actions[0].metadata["recorded_x"] == 100

    def test_load_legacy_flat_list_still_works(self, tmp_path):
        """Existing recordings saved as flat lists must load without error."""
        from framework.recorder.recording_store import RecordingStore

        store = RecordingStore(base_dir=tmp_path)
        payload = [
            {
                "action_type": "hotkey",
                "locator": None,
                "value": "ctrl+c",
                "timeout_seconds": None,
                "metadata": {},
            }
        ]
        (tmp_path / "legacy.json").write_text(json.dumps(payload))
        actions = store.load("legacy")
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.HOTKEY
        assert actions[0].value == "ctrl+c"

    def test_load_meta_returns_dict_for_new_format(self, tmp_path):
        from framework.recorder.recording_store import RecordingStore

        store = RecordingStore(base_dir=tmp_path)
        payload = {"meta": {"version": 1, "screen_width": 2560, "screen_height": 1440}, "actions": []}
        (tmp_path / "r.json").write_text(json.dumps(payload))
        meta = store.load_meta("r")
        assert meta["screen_width"] == 2560

    def test_load_meta_returns_empty_for_legacy(self, tmp_path):
        from framework.recorder.recording_store import RecordingStore

        store = RecordingStore(base_dir=tmp_path)
        (tmp_path / "old.json").write_text(json.dumps([]))
        meta = store.load_meta("old")
        assert meta == {}

    def test_roundtrip_click_action_preserves_coordinates(self, tmp_path):
        from framework.recorder.recording_store import RecordingStore

        store = RecordingStore(base_dir=tmp_path)
        original = [
            Action(
                action_type=ActionType.CLICK,
                locator=Locator(by="auto_id", value="OKButton"),
                metadata={"recorded_x": 300, "recorded_y": 450,
                          "screen_width": 1920, "screen_height": 1080},
            )
        ]
        with patch("framework.recorder.recording_store.get_screen_size", return_value=(1920, 1080)):
            store.save("click_rec", original)
        loaded = store.load("click_rec")
        assert loaded[0].metadata["recorded_x"] == 300
        assert loaded[0].metadata["recorded_y"] == 450
        assert loaded[0].metadata["screen_width"] == 1920


# ===========================================================================
# C. ActionNormalizer — CLICK stores screen dimensions in metadata
# ===========================================================================

class TestNormalizerClickMetadata:
    def _make_click_event(self, x=100, y=200):
        return {"type": "click", "x": x, "y": y, "button": "left"}

    def test_click_stores_screen_width_and_height(self):
        from framework.recorder.action_normalizer import ActionNormalizer

        normalizer = ActionNormalizer()
        with patch("framework.recorder.action_normalizer.get_screen_size", return_value=(2560, 1440)), \
             patch("framework.recorder.action_normalizer._resolve_locator_at", return_value=None):
            normalizer.push(self._make_click_event(100, 200))
            actions = normalizer.flush()

        assert len(actions) == 1
        meta = actions[0].metadata
        assert meta["recorded_x"] == 100
        assert meta["recorded_y"] == 200
        assert meta["screen_width"] == 2560
        assert meta["screen_height"] == 1440

    def test_click_screen_dims_are_ints(self):
        from framework.recorder.action_normalizer import ActionNormalizer

        normalizer = ActionNormalizer()
        with patch("framework.recorder.action_normalizer.get_screen_size", return_value=(1920, 1080)), \
             patch("framework.recorder.action_normalizer._resolve_locator_at", return_value=None):
            normalizer.push(self._make_click_event())
            actions = normalizer.flush()

        assert isinstance(actions[0].metadata["screen_width"], int)
        assert isinstance(actions[0].metadata["screen_height"], int)


# ===========================================================================
# D. PlaybackExecutor — coordinate scaling applied for CLICK actions
# ===========================================================================

class TestExecutorClickScaling:
    def _make_click_action(self, rx, ry, sw=1920, sh=1080, locator=None):
        return Action(
            action_type=ActionType.CLICK,
            locator=locator or Locator(by="auto_id", value="Btn"),
            metadata={"recorded_x": rx, "recorded_y": ry,
                      "screen_width": sw, "screen_height": sh},
        )

    def test_same_resolution_no_scaling(self):
        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)
        action = self._make_click_action(400, 300, 1920, 1080)
        with patch("framework.playback.executor.scale_coords",
                   wraps=lambda x, y, sw, sh: (x, y)) as mock_scale, \
             patch("time.sleep"):
            executor._execute(action)
        mock_scale.assert_called_once_with(400, 300, 1920, 1080)
        mock_driver.click.assert_called_once_with(action.locator, coords=(400, 300))

    def test_different_resolution_scales_coords(self):
        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)
        action = self._make_click_action(100, 100, 1920, 1080)

        with patch("framework.playback.executor.scale_coords", return_value=(200, 200)) as mock_scale, \
             patch("time.sleep"):
            executor._execute(action)
        mock_scale.assert_called_once_with(100, 100, 1920, 1080)
        mock_driver.click.assert_called_once_with(action.locator, coords=(200, 200))

    def test_missing_screen_dims_in_metadata_uses_zero(self):
        """Legacy recordings without screen_width/height pass 0,0 — scale_coords returns unchanged."""
        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)
        action = Action(
            action_type=ActionType.CLICK,
            locator=Locator(by="auto_id", value="X"),
            metadata={"recorded_x": 50, "recorded_y": 75},  # no screen dims
        )
        with patch("framework.playback.executor.scale_coords", wraps=lambda x, y, sw, sh: (x, y)) as mock_scale, \
             patch("time.sleep"):
            executor._execute(action)
        mock_scale.assert_called_once_with(50, 75, 0, 0)
        mock_driver.click.assert_called_once_with(action.locator, coords=(50, 75))

    def test_no_locator_no_coords_raises(self):
        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)
        action = Action(action_type=ActionType.CLICK, locator=None, metadata={})
        from framework.core.exceptions import PlaybackExecutionError
        with pytest.raises(PlaybackExecutionError):
            executor._execute(action)

    def test_no_locator_with_coords_uses_coordinate_click(self):
        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)
        action = Action(
            action_type=ActionType.CLICK,
            locator=None,
            metadata={"recorded_x": 300, "recorded_y": 400, "screen_width": 1920, "screen_height": 1080},
        )
        with patch("framework.playback.executor.scale_coords", return_value=(300, 400)), \
             patch("time.sleep"):
            executor._execute(action)
        mock_driver.click.assert_called_once_with(None, coords=(300, 400))


# ===========================================================================
# E. Mixed keyboard + mouse end-to-end scenario (unit level)
# ===========================================================================

class TestMixedKeyboardMousePlayback:
    """End-to-end scenario with launch, click, type, hotkey — all mocked."""

    def _make_actions(self):
        return [
            Action(action_type=ActionType.LAUNCH, value="notepad.exe"),
            Action(
                action_type=ActionType.CLICK,
                locator=Locator(by="auto_id", value="TextArea"),
                metadata={"recorded_x": 400, "recorded_y": 300,
                          "screen_width": 1920, "screen_height": 1080},
            ),
            Action(action_type=ActionType.TYPE, locator=None, value="Hello automation"),
            Action(action_type=ActionType.KEY, value="enter"),
            Action(action_type=ActionType.HOTKEY, value="ctrl+a"),
            Action(action_type=ActionType.HOTKEY, value="alt+f4"),
        ]

    def test_all_actions_pass(self):
        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver, recording_name="mixed_test")
        actions = self._make_actions()

        with patch("time.sleep"), \
             patch("framework.playback.executor.scale_coords", side_effect=lambda x, y, w, h: (x, y)):
            result = executor.run(actions, inter_action_delay_seconds=0)

        assert result.status == "passed"
        assert len(result.action_results) == len(actions)
        assert all(r.status == "passed" for r in result.action_results)

    def test_action_types_recorded_correctly(self):
        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)
        actions = self._make_actions()

        with patch("time.sleep"), \
             patch("framework.playback.executor.scale_coords", side_effect=lambda x, y, w, h: (x, y)):
            result = executor.run(actions, inter_action_delay_seconds=0)

        types = [r.action_type for r in result.action_results]
        assert types == ["launch", "click", "type", "key", "hotkey", "hotkey"]

    def test_click_invokes_driver_click_with_coords(self):
        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)
        actions = self._make_actions()

        with patch("time.sleep"), \
             patch("framework.playback.executor.scale_coords", return_value=(400, 300)):
            executor.run(actions, inter_action_delay_seconds=0)

        click_calls = [c for c in mock_driver.click.call_args_list]
        assert len(click_calls) == 1
        # coords kwarg must be passed
        assert click_calls[0].kwargs.get("coords") == (400, 300) or click_calls[0].args[1] == (400, 300)

    def test_hotkey_alt_f4_invokes_driver_hotkey(self):
        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)
        actions = self._make_actions()

        with patch("time.sleep"), \
             patch("framework.playback.executor.scale_coords", side_effect=lambda x, y, w, h: (x, y)):
            executor.run(actions, inter_action_delay_seconds=0)

        hotkey_values = [c.args[0] for c in mock_driver.hotkey.call_args_list]
        assert "alt+f4" in hotkey_values

    def test_recording_name_in_result(self):
        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver, recording_name="my_recording")
        with patch("time.sleep"), \
             patch("framework.playback.executor.scale_coords", side_effect=lambda x, y, w, h: (x, y)):
            result = executor.run([Action(action_type=ActionType.KEY, value="enter")],
                                  inter_action_delay_seconds=0)
        assert result.recording_name == "my_recording"


# ===========================================================================
# F. CLICK failure — FAILED result, screenshot attempted, cleanup
# ===========================================================================

class TestClickFailureHandling:
    def test_failed_click_result_is_failed(self):
        mock_driver = MagicMock()
        mock_driver.click.side_effect = RuntimeError("control not found")
        executor = PlaybackExecutor(driver=mock_driver, recording_name="fail_test")

        action = Action(
            action_type=ActionType.CLICK,
            locator=Locator(by="auto_id", value="Missing"),
            metadata={"recorded_x": 100, "recorded_y": 100,
                      "screen_width": 1920, "screen_height": 1080},
        )
        from framework.core.exceptions import PlaybackExecutionError
        with patch("time.sleep"), \
             patch("framework.playback.executor.scale_coords", return_value=(100, 100)), \
             patch.object(executor, "_try_capture_screenshot", return_value=None), \
             pytest.raises(PlaybackExecutionError):
            executor.run([action], inter_action_delay_seconds=0)

        assert executor.result is not None
        assert executor.result.status == "failed"
        assert executor.result.action_results[0].status == "failed"
        assert executor.result.action_results[0].action_type == "click"

    def test_failed_click_error_message_preserved(self):
        mock_driver = MagicMock()
        mock_driver.click.side_effect = RuntimeError("element not visible")
        executor = PlaybackExecutor(driver=mock_driver)

        action = Action(
            action_type=ActionType.CLICK,
            locator=Locator(by="title", value="Btn"),
            metadata={"recorded_x": 50, "recorded_y": 50,
                      "screen_width": 1920, "screen_height": 1080},
        )
        from framework.core.exceptions import PlaybackExecutionError
        with patch("time.sleep"), \
             patch("framework.playback.executor.scale_coords", return_value=(50, 50)), \
             patch.object(executor, "_try_capture_screenshot", return_value="/tmp/shot.png"), \
             pytest.raises(PlaybackExecutionError):
            executor.run([action], inter_action_delay_seconds=0)

        ar = executor.result.action_results[0]
        assert "element not visible" in ar.error_message

    def test_failed_click_does_not_block_result_generation(self):
        """Even after click failure, self.result is populated for HTML report."""
        mock_driver = MagicMock()
        mock_driver.click.side_effect = RuntimeError("timeout")
        executor = PlaybackExecutor(driver=mock_driver)

        action = Action(
            action_type=ActionType.CLICK,
            locator=Locator(by="auto_id", value="X"),
            metadata={"recorded_x": 10, "recorded_y": 10,
                      "screen_width": 1920, "screen_height": 1080},
        )
        from framework.core.exceptions import PlaybackExecutionError
        with patch("time.sleep"), \
             patch("framework.playback.executor.scale_coords", return_value=(10, 10)), \
             patch.object(executor, "_try_capture_screenshot", return_value=None), \
             pytest.raises(PlaybackExecutionError):
            executor.run([action], inter_action_delay_seconds=0)

        assert executor.result is not None  # Must be set for HTML report generation


# ===========================================================================
# G. HTML report — CLICK actions render correctly
# ===========================================================================

class TestHTMLReportClickActions:
    def _make_result(self, status="passed", click_value=None, locator_str=None):
        from datetime import datetime, timezone
        from framework.playback.executor import ActionResult, PlaybackResult

        now = datetime.now(timezone.utc)
        ar = ActionResult(
            action_index=0,
            action_type="click",
            value=click_value,
            locator_str=locator_str,
            status=status,
            duration_seconds=0.3,
            error_message="control not found" if status == "failed" else None,
        )
        return PlaybackResult(
            recording_name="test_recording",
            status=status,
            started_at=now,
            finished_at=now,
            duration_seconds=0.3,
            action_results=[ar],
            error_message="control not found" if status == "failed" else None,
        )

    def test_passed_click_shows_pass_badge(self, tmp_path):
        from framework.reporting.recording_report import generate_recording_report

        result = self._make_result("passed", locator_str="auto_id:OKButton")
        path = generate_recording_report(result, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "click" in content.lower()
        assert "PASS" in content

    def test_failed_click_shows_fail_badge(self, tmp_path):
        from framework.reporting.recording_report import generate_recording_report

        result = self._make_result("failed", locator_str="auto_id:Missing")
        path = generate_recording_report(result, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "FAIL" in content
        assert "control not found" in content

    def test_click_locator_shown_in_report(self, tmp_path):
        from framework.reporting.recording_report import generate_recording_report

        result = self._make_result("passed", locator_str="auto_id:SubmitButton")
        path = generate_recording_report(result, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "SubmitButton" in content

    def test_report_has_action_count_one(self, tmp_path):
        from framework.reporting.recording_report import generate_recording_report

        result = self._make_result("passed")
        path = generate_recording_report(result, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "1" in content   # Total actions = 1
