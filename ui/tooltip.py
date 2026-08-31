"""Lightweight reusable hover tooltip for Tkinter widgets."""
from __future__ import annotations

import tkinter as tk


class HoverTooltip:
    """Attach a simple tooltip to any Tk widget."""

    def __init__(self, widget: tk.Widget, text: str, *, wraplength: int = 320) -> None:
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self._tip_window: tk.Toplevel | None = None

        self.widget.bind("<Enter>", self._show, add="+")
        self.widget.bind("<Leave>", self._hide, add="+")
        self.widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self._tip_window is not None or not self.text.strip():
            return

        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8

        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)

        label = tk.Label(
            tip,
            text=self.text,
            justify="left",
            bg="#1f2d3a",
            fg="#ffffff",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
            wraplength=self.wraplength,
            font=("Segoe UI", 9),
        )
        label.pack()

        tip.update_idletasks()
        pos_x, pos_y = self.compute_position(
            anchor_x=x,
            anchor_y=y,
            tooltip_width=tip.winfo_reqwidth(),
            tooltip_height=tip.winfo_reqheight(),
            screen_width=tip.winfo_screenwidth(),
            screen_height=tip.winfo_screenheight(),
            margin=8,
        )
        tip.wm_geometry(f"+{pos_x}+{pos_y}")
        self._tip_window = tip

    @staticmethod
    def compute_position(
        *,
        anchor_x: int,
        anchor_y: int,
        tooltip_width: int,
        tooltip_height: int,
        screen_width: int,
        screen_height: int,
        margin: int = 8,
    ) -> tuple[int, int]:
        """Return an on-screen position for the tooltip window."""
        x = anchor_x
        y = anchor_y

        if x + tooltip_width > screen_width - margin:
            x = max(margin, screen_width - tooltip_width - margin)

        if y + tooltip_height > screen_height - margin:
            y = max(margin, screen_height - tooltip_height - margin)

        x = max(margin, x)
        y = max(margin, y)
        return x, y

    def _hide(self, _event=None) -> None:
        if self._tip_window is not None:
            self._tip_window.destroy()
            self._tip_window = None
