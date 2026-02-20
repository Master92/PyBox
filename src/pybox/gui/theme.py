"""Theme definitions for the PyBox GUI – dark and light modes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """Color and style tokens for one theme variant."""

    name: str

    # Base colors
    bg: str              # main background
    bg_alt: str          # secondary background (panels, headers)
    bg_input: str        # input/table background
    fg: str              # primary text
    fg_dim: str          # secondary/muted text
    border: str          # borders and grid lines
    border_light: str    # lighter border / hover
    accent: str          # accent for selection highlight
    accent_bg: str       # selection background

    # Plot-specific
    plot_bg: str         # pyqtgraph background
    plot_axis: str       # axis pen color
    plot_grid_alpha: float
    plot_title_color: str
    plot_ref_line: str   # y=1 reference line

    # Buttons
    btn_primary_bg: str
    btn_danger_bg: str
    btn_compute_bg: str
    btn_compute_hover: str
    btn_compute_pressed: str
    btn_disabled_bg: str
    btn_disabled_fg: str


DARK = Theme(
    name="dark",
    bg="#252525",
    bg_alt="#2d2d2d",
    bg_input="#1e1e1e",
    fg="#ddd",
    fg_dim="#888",
    border="#444",
    border_light="#666",
    accent="#7777bb",
    accent_bg="#3a3a5a",
    plot_bg="#1e1e1e",
    plot_axis="#888",
    plot_grid_alpha=0.15,
    plot_title_color="#ddd",
    plot_ref_line="#555555",
    btn_primary_bg="#4a6fa5",
    btn_danger_bg="#884444",
    btn_compute_bg="#4a8a4a",
    btn_compute_hover="#5a9a5a",
    btn_compute_pressed="#3a7a3a",
    btn_disabled_bg="#444",
    btn_disabled_fg="#888",
)

LIGHT = Theme(
    name="light",
    bg="#f5f5f5",
    bg_alt="#e8e8e8",
    bg_input="#ffffff",
    fg="#222",
    fg_dim="#666",
    border="#ccc",
    border_light="#aaa",
    accent="#4466aa",
    accent_bg="#d0d8ee",
    plot_bg="#ffffff",
    plot_axis="#444",
    plot_grid_alpha=0.2,
    plot_title_color="#222",
    plot_ref_line="#bbbbbb",
    btn_primary_bg="#4a6fa5",
    btn_danger_bg="#c05050",
    btn_compute_bg="#4a8a4a",
    btn_compute_hover="#5a9a5a",
    btn_compute_pressed="#3a7a3a",
    btn_disabled_bg="#ccc",
    btn_disabled_fg="#999",
)

THEMES: dict[str, Theme] = {"dark": DARK, "light": LIGHT}

# Module-level current theme
_current: Theme = DARK


def current() -> Theme:
    """Return the active theme."""
    return _current


def set_theme(name: str) -> Theme:
    """Switch to the named theme and return it."""
    global _current
    _current = THEMES[name]
    return _current
