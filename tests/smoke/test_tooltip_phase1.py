"""Focused tests for tooltip behavior used by workspace help icons."""
from __future__ import annotations

from ui.tooltip import HoverTooltip


class _FakeWidget:
    def __init__(self) -> None:
        self.bind_calls: list[tuple[str, str]] = []

    def bind(self, event: str, handler, add=None):
        self.bind_calls.append((event, add))
        return "bound"


def test_tooltip_stores_wraplength_and_binds_events() -> None:
    widget = _FakeWidget()
    tooltip = HoverTooltip(widget, "help text", wraplength=280)

    assert tooltip.wraplength == 280
    events = {event for event, _ in widget.bind_calls}
    assert "<Enter>" in events
    assert "<Leave>" in events
    assert "<ButtonPress>" in events


def test_compute_position_keeps_tooltip_inside_screen_bounds() -> None:
    x, y = HoverTooltip.compute_position(
        anchor_x=780,
        anchor_y=580,
        tooltip_width=220,
        tooltip_height=140,
        screen_width=800,
        screen_height=600,
        margin=8,
    )

    assert x <= 800 - 220 - 8
    assert y <= 600 - 140 - 8
    assert x >= 8
    assert y >= 8


def test_compute_position_preserves_anchor_when_space_is_available() -> None:
    x, y = HoverTooltip.compute_position(
        anchor_x=120,
        anchor_y=160,
        tooltip_width=180,
        tooltip_height=80,
        screen_width=1400,
        screen_height=900,
        margin=8,
    )

    assert x == 120
    assert y == 160
