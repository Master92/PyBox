"""Data model for the GUI – LogEntry, color palette, shared state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from pybox.decoder.flightlog import FlightLog, DecodedLog
from pybox.decoder.headers import LogHeader


# Distinguishable color palette (hex) for up to 12 logs
LOG_COLORS = [
    "#e6194b",  # red
    "#3cb44b",  # green
    "#4363d8",  # blue
    "#f58231",  # orange
    "#911eb4",  # purple
    "#42d4f4",  # cyan
    "#f032e6",  # magenta
    "#bfef45",  # lime
    "#fabed4",  # pink
    "#dcbeff",  # lavender
    "#ffe119",  # yellow
    "#a9a9a9",  # grey
]


@dataclass
class PIDFFConfig:
    """PID and Feedforward configuration for one log."""
    roll_p: int = 0
    roll_i: int = 0
    roll_d: int = 0
    roll_ff: int = 0
    pitch_p: int = 0
    pitch_i: int = 0
    pitch_d: int = 0
    pitch_ff: int = 0
    yaw_p: int = 0
    yaw_i: int = 0
    yaw_d: int = 0
    yaw_ff: int = 0

    @classmethod
    def from_header(cls, header: LogHeader) -> PIDFFConfig:
        """Extract PIDFF values from a parsed log header."""
        raw = header.raw_headers
        cfg = cls()

        # Parse rollPID, pitchPID, yawPID (format: "P,I,D")
        for axis, prefix in [("roll", "roll"), ("pitch", "pitch"), ("yaw", "yaw")]:
            pid_str = raw.get(f"{prefix}PID", "")
            if pid_str:
                parts = [int(x.strip()) for x in pid_str.split(",") if x.strip()]
                if len(parts) >= 1:
                    setattr(cfg, f"{axis}_p", parts[0])
                if len(parts) >= 2:
                    setattr(cfg, f"{axis}_i", parts[1])
                if len(parts) >= 3:
                    setattr(cfg, f"{axis}_d", parts[2])

        # Parse ff_weight (format: "roll,pitch,yaw")
        ff_str = raw.get("ff_weight", "")
        if ff_str:
            parts = [int(x.strip()) for x in ff_str.split(",") if x.strip()]
            if len(parts) >= 1:
                cfg.roll_ff = parts[0]
            if len(parts) >= 2:
                cfg.pitch_ff = parts[1]
            if len(parts) >= 3:
                cfg.yaw_ff = parts[2]

        return cfg

    def axis_str(self, axis_index: int) -> str:
        """Return 'P/I/D/FF' string for axis 0=roll, 1=pitch, 2=yaw."""
        names = ["roll", "pitch", "yaw"]
        name = names[axis_index]
        p = getattr(self, f"{name}_p")
        i = getattr(self, f"{name}_i")
        d = getattr(self, f"{name}_d")
        ff = getattr(self, f"{name}_ff")
        return f"P{p} I{i} D{d} FF{ff}"


@dataclass
class LogEntry:
    """A single loaded log with its decoded data and display state."""
    file_path: str
    log_index: int
    label: str              # display name
    color: str              # hex color from palette
    header: LogHeader
    decoded: DecodedLog
    df: pd.DataFrame
    pidff: PIDFFConfig

    # Time range for analysis (in seconds, relative to log start)
    time_start_s: float = 0.0
    time_end_s: float = 0.0

    # Visibility
    visible: bool = True

    # Cached gyro arrays (time_s, gyro_roll, gyro_pitch, gyro_yaw)
    _gyro_cache: Optional[tuple] = field(default=None, repr=False)

    @property
    def duration_s(self) -> float:
        return self.decoded.duration_s

    def gyro_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return (time_s, gyro_roll, gyro_pitch, gyro_yaw) arrays."""
        if self._gyro_cache is not None:
            return self._gyro_cache

        df = self.df
        # Find time column
        time_col = _find_col(df, ["time"])
        if time_col is None:
            empty = np.array([])
            return empty, empty, empty, empty

        time_us = df[time_col].values.astype(np.float64)
        time_s = (time_us - time_us[0]) / 1_000_000.0

        gyro = []
        for i in range(3):
            col = _find_col(df, [f"gyroADC[{i}]", f"gyroData[{i}]"])
            if col is not None:
                gyro.append(df[col].values.astype(np.float64))
            else:
                gyro.append(np.zeros(len(time_s)))

        self._gyro_cache = (time_s, gyro[0], gyro[1], gyro[2])
        return self._gyro_cache

    def setpoint_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (sp_roll, sp_pitch, sp_yaw) arrays."""
        df = self.df
        sp = []
        for i in range(3):
            col = _find_col(df, [f"setpoint[{i}]"])
            if col is not None:
                sp.append(df[col].values.astype(np.float64))
            else:
                sp.append(np.zeros(len(df)))
        return sp[0], sp[1], sp[2]

    def time_mask(self) -> np.ndarray:
        """Boolean mask for the selected time range."""
        time_s = self.gyro_arrays()[0]
        return (time_s >= self.time_start_s) & (time_s <= self.time_end_s)


def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def detect_active_range(
    time_s: np.ndarray,
    setpoints: list[np.ndarray],
    threshold_frac: float = 0.15,
    window_s: float = 0.5,
    margin_s: float = 0.5,
) -> tuple[float, float]:
    """Detect the time range with meaningful stick input.

    Computes a rolling RMS of the combined setpoint channels and returns
    the first and last times the signal exceeds *threshold_frac* of the
    peak RMS, with a small *margin_s* padding.

    Falls back to full range if detection fails.
    """
    if len(time_s) < 100:
        return float(time_s[0]), float(time_s[-1])

    # Combined absolute setpoint magnitude
    combined = np.zeros(len(time_s), dtype=np.float64)
    for sp in setpoints:
        combined += np.abs(sp)

    # Rolling RMS (boxcar)
    dt = np.median(np.diff(time_s))
    if dt <= 0:
        return float(time_s[0]), float(time_s[-1])
    win = max(1, int(window_s / dt))
    kernel = np.ones(win) / win
    rms = np.sqrt(np.convolve(combined ** 2, kernel, mode="same"))

    peak = np.max(rms)
    if peak < 1.0:
        return float(time_s[0]), float(time_s[-1])

    threshold = threshold_frac * peak
    active = rms >= threshold
    indices = np.nonzero(active)[0]

    if len(indices) == 0:
        return float(time_s[0]), float(time_s[-1])

    t_start = max(float(time_s[0]), float(time_s[indices[0]]) - margin_s)
    t_end = min(float(time_s[-1]), float(time_s[indices[-1]]) + margin_s)
    return t_start, t_end


def load_log_entry(
    file_path: str,
    log_index: int,
    color_index: int,
) -> LogEntry:
    """Load and decode a single log from a .bbl file."""
    fl = FlightLog(file_path)
    decoded = fl.decode(log_index)
    header = fl.get_header(log_index)
    df = decoded.to_dataframe()
    pidff = PIDFFConfig.from_header(header)

    # Build label
    from pathlib import Path
    fname = Path(file_path).stem
    label = f"{fname} #{log_index + 1}"

    color = LOG_COLORS[color_index % len(LOG_COLORS)]

    entry = LogEntry(
        file_path=str(file_path),
        log_index=log_index,
        label=label,
        color=color,
        header=header,
        decoded=decoded,
        df=df,
        pidff=pidff,
        time_start_s=0.0,
        time_end_s=decoded.duration_s,
    )

    # Auto-detect a meaningful analysis range
    time_s, _, _, _ = entry.gyro_arrays()
    sp_r, sp_p, sp_y = entry.setpoint_arrays()
    if len(time_s) > 0:
        t0, t1 = detect_active_range(time_s, [sp_r, sp_p, sp_y])
        entry.time_start_s = t0
        entry.time_end_s = t1

    return entry
