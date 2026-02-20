"""PID error analysis – distributions and error vs stick deflection.

Mirrors PTplotPIDerror.m from PIDtoolbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class PIDErrorResult:
    """Result of PID error analysis for one axis."""
    axis: str  # "roll", "pitch", or "yaw"
    histogram_bins: np.ndarray
    histogram_counts: np.ndarray  # normalized 0..1
    std_dev: float
    mean_abs_error_vs_stick: np.ndarray  # shape (10,) for 10%-100% stick
    se_error_vs_stick: np.ndarray  # standard errors


def compute_pid_error(
    gyro: np.ndarray,
    setpoint: np.ndarray,
) -> np.ndarray:
    """Compute PID error = gyro - setpoint (deg/s)."""
    return gyro - setpoint


def compute_pid_sum(
    axis_p: np.ndarray,
    axis_i: np.ndarray,
    axis_d: Optional[np.ndarray] = None,
    axis_f: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Compute PID sum = P + I + D + F."""
    result = axis_p + axis_i
    if axis_d is not None:
        result = result + axis_d
    if axis_f is not None:
        result = result + axis_f
    return result


def pid_error_distribution(
    pid_error: np.ndarray,
    bin_range: tuple[int, int] = (-1000, 1000),
    bin_width: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute normalized PID error histogram.

    Returns (bins, normalized_counts) where counts are normalized to peak=1.
    """
    bins = np.arange(bin_range[0], bin_range[1] + bin_width, bin_width)
    counts, bin_edges = np.histogram(pid_error, bins=bins)
    counts = counts.astype(np.float64)
    max_count = counts.max()
    if max_count > 0:
        counts /= max_count
    centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    return centers, counts


def pid_error_vs_stick(
    pid_error: np.ndarray,
    rc_rate: np.ndarray,
    num_bins: int = 10,
    max_degsec: float = 1000.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute mean |PID error| as a function of stick deflection.

    Args:
        pid_error: PID error for one axis, shape (N,)
        rc_rate: Setpoint/rate for the same axis, shape (N,)
        num_bins: Number of stick deflection bins (default 10 for 10%..100%)
        max_degsec: Threshold for filtering extreme values

    Returns:
        (mean_abs_errors, standard_errors) each of shape (num_bins,)
    """
    max_rate = np.max(np.abs(rc_rate))
    if max_rate == 0:
        return np.zeros(num_bins), np.zeros(num_bins)

    thresholds = np.linspace(0.1, 1.0, num_bins)
    mean_errors = np.zeros(num_bins)
    se_errors = np.zeros(num_bins)

    for i, t in enumerate(thresholds):
        limit = max_rate * t
        mask = (np.abs(rc_rate) < limit) & (np.abs(pid_error) < max_degsec)
        subset = np.abs(pid_error[mask])
        if len(subset) > 0:
            mean_errors[i] = np.nanmean(subset)
            se_errors[i] = np.nanstd(subset) / np.sqrt(len(subset))

    return mean_errors, se_errors


def analyze_pid_errors(
    df: pd.DataFrame,
    axes: list[str] = None,
) -> list[PIDErrorResult]:
    """Run full PID error analysis on a decoded DataFrame.

    Expects columns like gyroADC[0], setpoint[0], etc.
    Automatically detects column naming conventions.

    Args:
        df: Decoded flight log DataFrame
        axes: List of axis names, default ["roll", "pitch", "yaw"]

    Returns:
        List of PIDErrorResult, one per axis.
    """
    if axes is None:
        axes = ["roll", "pitch", "yaw"]

    results = []
    for i, axis_name in enumerate(axes):
        # Try to find gyro and setpoint columns
        gyro_col = _find_column(df, [f"gyroADC[{i}]", f"gyroData[{i}]", f"gyroADC_{i}_"])
        sp_col = _find_column(df, [f"setpoint[{i}]", f"setpoint_{i}_"])

        if gyro_col is None or sp_col is None:
            continue

        gyro = df[gyro_col].values.astype(np.float64)
        setpoint = df[sp_col].values.astype(np.float64)
        pid_err = compute_pid_error(gyro, setpoint)

        bins, counts = pid_error_distribution(pid_err)
        mean_abs, se = pid_error_vs_stick(pid_err, setpoint)

        results.append(PIDErrorResult(
            axis=axis_name,
            histogram_bins=bins,
            histogram_counts=counts,
            std_dev=float(np.std(pid_err)),
            mean_abs_error_vs_stick=mean_abs,
            se_error_vs_stick=se,
        ))

    return results


def _find_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Return the first column name from candidates that exists in df."""
    for c in candidates:
        if c in df.columns:
            return c
    return None
