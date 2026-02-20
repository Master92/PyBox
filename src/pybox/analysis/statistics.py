"""Flight statistics – stick distributions, rate curves, motor stats.

Mirrors PTplotStats.m from PIDtoolbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class StickDistribution:
    """Stick input distribution for one axis."""
    axis: str
    bin_edges: np.ndarray      # 0..100 %
    histogram: np.ndarray      # normalized probability
    mean_percent: float
    std_percent: float


@dataclass
class MotorStats:
    """Motor output statistics."""
    mean_percent: np.ndarray   # per motor, shape (n_motors,)
    std_percent: np.ndarray
    min_percent: np.ndarray
    max_percent: np.ndarray


@dataclass
class FlightStatistics:
    """Aggregated flight statistics."""
    duration_s: float
    sample_rate_hz: float
    stick_distributions: list[StickDistribution]
    motor_stats: Optional[MotorStats]
    throttle_distribution: Optional[StickDistribution]


def rc_command_to_percent(rc_command: np.ndarray) -> np.ndarray:
    """Convert rcCommand values (-500..500) to percentage of deflection (0..100)."""
    return np.abs(rc_command) / 500.0 * 100.0


def compute_stick_distribution(
    rc_percent: np.ndarray,
    axis_name: str,
    bin_width: float = 1.0,
) -> StickDistribution:
    """Compute stick deflection distribution.

    Args:
        rc_percent: Stick deflection in percent (0..100)
        axis_name: "roll", "pitch", "yaw", or "throttle"
        bin_width: Histogram bin width in percent

    Returns:
        StickDistribution
    """
    bins = np.arange(0, 100 + bin_width, bin_width)
    counts, edges = np.histogram(rc_percent, bins=bins, density=True)

    return StickDistribution(
        axis=axis_name,
        bin_edges=edges,
        histogram=counts * bin_width,  # normalize so sum ≈ 1
        mean_percent=float(np.nanmean(rc_percent)),
        std_percent=float(np.nanstd(rc_percent)),
    )


def compute_motor_stats(
    motors: np.ndarray,
    motor_output_low: int = 0,
    motor_output_high: int = 2000,
) -> MotorStats:
    """Compute motor output statistics.

    Args:
        motors: Motor values, shape (n_samples, n_motors)
        motor_output_low: Minimum motor output value
        motor_output_high: Maximum motor output value

    Returns:
        MotorStats with per-motor statistics in percent (0..100)
    """
    range_ = motor_output_high - motor_output_low
    if range_ == 0:
        range_ = 1

    motors_pct = (motors.astype(np.float64) - motor_output_low) / range_ * 100.0

    return MotorStats(
        mean_percent=np.nanmean(motors_pct, axis=0),
        std_percent=np.nanstd(motors_pct, axis=0),
        min_percent=np.nanmin(motors_pct, axis=0),
        max_percent=np.nanmax(motors_pct, axis=0),
    )


def compute_rate_curve(
    rc_rate: float,
    rc_expo: float,
    super_rate: float,
    max_rc: int = 500,
    rate_constant: float = 200.0,
) -> np.ndarray:
    """Compute Betaflight rate curve (degrees/second vs stick position).

    Implements the Betaflight rate calculation:
        rcCommandf = rcCommand / 500
        expo_applied = rcCommandf * |rcCommandf|^expoPower * rcExpo + rcCommandf * (1 - rcExpo)
        angleRate = rateConstant * rcRate * expo_applied / (1 - |expo_applied| * superRate)

    Args:
        rc_rate: RC rate value (e.g. 1.0)
        rc_expo: RC expo value (0..1)
        super_rate: Super rate value (0..1)
        max_rc: Maximum RC command value (typically 500)
        rate_constant: Rate constant (200 for newer BF, 205.85 for older)

    Returns:
        Array of deg/s values for stick positions 0..max_rc
    """
    positions = np.arange(0, max_rc + 1, dtype=np.float64)
    rc_commandf = positions / 500.0
    rc_commandf_abs = np.abs(rc_commandf)

    expo_power = 3  # Betaflight ≥ API 1.20

    if rc_expo > 0:
        rc_commandf = (
            rc_commandf * np.power(rc_commandf_abs, expo_power) * rc_expo
            + rc_commandf * (1 - rc_expo)
        )

    adjusted_rate = rc_rate
    if rc_rate > 2.0:
        adjusted_rate = rc_rate + (rc_rate - 2.0) * 14.54

    angle_rate = rate_constant * adjusted_rate * rc_commandf

    if super_rate > 0:
        rc_factor = 1.0 / np.maximum(1.0 - rc_commandf_abs * super_rate, 0.01)
        angle_rate = angle_rate * rc_factor

    return angle_rate


def compute_flight_statistics(
    df,
    motor_output_low: int = 0,
    motor_output_high: int = 2000,
) -> FlightStatistics:
    """Compute comprehensive flight statistics from a decoded DataFrame.

    Args:
        df: pandas DataFrame from FlightLog.to_dataframe()
        motor_output_low: Min motor output value
        motor_output_high: Max motor output value

    Returns:
        FlightStatistics
    """
    import pandas as pd

    n = len(df)
    if n < 2:
        return FlightStatistics(
            duration_s=0.0,
            sample_rate_hz=0.0,
            stick_distributions=[],
            motor_stats=None,
            throttle_distribution=None,
        )

    # Duration and sample rate
    if "time" in df.columns:
        time_col = df["time"].values
        duration_us = int(time_col[-1] - time_col[0])
        duration_s = duration_us / 1_000_000.0
        sample_rate_hz = (n - 1) / duration_s if duration_s > 0 else 0.0
    else:
        duration_s = 0.0
        sample_rate_hz = 0.0

    # Stick distributions
    axis_names = ["roll", "pitch", "yaw"]
    stick_dists = []
    for i, name in enumerate(axis_names):
        col = _find_col(df, [f"rcCommand[{i}]", f"rcCommand_{i}_"])
        if col is not None:
            pct = rc_command_to_percent(df[col].values.astype(np.float64))
            stick_dists.append(compute_stick_distribution(pct, name))

    # Throttle distribution
    throttle_dist = None
    thr_col = _find_col(df, ["rcCommand[3]", "rcCommand_3_", "setpoint[3]", "setpoint_3_"])
    if thr_col is not None:
        thr = df[thr_col].values.astype(np.float64)
        # Normalize throttle to 0..100%
        thr_pct = thr / 10.0 if np.max(thr) > 100 else thr
        thr_pct = np.clip(thr_pct, 0, 100)
        throttle_dist = compute_stick_distribution(thr_pct, "throttle")

    # Motor stats
    motor_cols = []
    for i in range(4):
        col = _find_col(df, [f"motor[{i}]", f"motor_{i}_"])
        if col is not None:
            motor_cols.append(col)

    motor_stats = None
    if motor_cols:
        motors = np.column_stack([df[c].values for c in motor_cols])
        motor_stats = compute_motor_stats(motors, motor_output_low, motor_output_high)

    return FlightStatistics(
        duration_s=duration_s,
        sample_rate_hz=sample_rate_hz,
        stick_distributions=stick_dists,
        motor_stats=motor_stats,
        throttle_distribution=throttle_dist,
    )


def _find_col(df, candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None
