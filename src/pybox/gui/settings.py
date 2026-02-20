"""Persistent application settings backed by QSettings.

Stores user preferences (theme, language, window geometry, etc.) across
sessions.  On Windows this uses the registry; on Linux/macOS a config file.
"""

from __future__ import annotations

from PyQt6.QtCore import QSettings


_ORG = "PyBox"
_APP = "PyBox"


def _qs() -> QSettings:
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _ORG, _APP)


def get(key: str, default=None):
    """Read a setting value."""
    return _qs().value(key, default)


def set(key: str, value) -> None:
    """Write a setting value."""
    s = _qs()
    s.setValue(key, value)
    s.sync()


# ── Convenience helpers for common settings ──────────────────────────

def theme() -> str:
    return str(get("appearance/theme", "dark"))


def set_theme(name: str) -> None:
    set("appearance/theme", name)


def language() -> str:
    return str(get("appearance/language", ""))


def set_language(code: str) -> None:
    set("appearance/language", code)


def window_geometry() -> bytes | None:
    val = get("window/geometry")
    if isinstance(val, bytes):
        return val
    return None


def set_window_geometry(data: bytes) -> None:
    set("window/geometry", data)


def window_state() -> bytes | None:
    val = get("window/state")
    if isinstance(val, bytes):
        return val
    return None


def set_window_state(data: bytes) -> None:
    set("window/state", data)
