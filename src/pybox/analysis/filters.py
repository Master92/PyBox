"""Filter delay and phase-shift estimation.

Mirrors PTfiltDelay.m and PTphaseShiftDeg.m from PIDtoolbox.
Estimates the group delay introduced by gyro and D-term filters by
cross-correlating raw vs filtered signals, or by computing phase
from the transfer function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import signal as sig


@dataclass
class FilterDelayResult:
    """Result of filter delay estimation."""
    gyro_delay_ms: float
    dterm_delay_ms: float
    gyro_phase_shift_deg: float  # at a reference frequency
    dterm_phase_shift_deg: float
    reference_freq_hz: float


def estimate_delay_cross_correlation(
    raw_signal: np.ndarray,
    filtered_signal: np.ndarray,
    sample_rate_hz: float,
    max_delay_ms: float = 10.0,
) -> float:
    """Estimate filter delay via cross-correlation.

    Finds the lag at which the cross-correlation between raw and
    filtered signals is maximized.

    Args:
        raw_signal: Unfiltered signal (e.g. raw gyro derivative for D-term)
        filtered_signal: Filtered signal (e.g. filtered D-term)
        sample_rate_hz: Sampling rate in Hz
        max_delay_ms: Maximum expected delay in ms

    Returns:
        Estimated delay in milliseconds
    """
    if len(raw_signal) < 10 or len(filtered_signal) < 10:
        return 0.0

    # Normalize
    raw_norm = raw_signal - np.mean(raw_signal)
    filt_norm = filtered_signal - np.mean(filtered_signal)

    std_raw = np.std(raw_norm)
    std_filt = np.std(filt_norm)
    if std_raw < 1e-10 or std_filt < 1e-10:
        return 0.0

    raw_norm = raw_norm / std_raw
    filt_norm = filt_norm / std_filt

    max_lag_samples = int(max_delay_ms * sample_rate_hz / 1000.0)
    max_lag_samples = min(max_lag_samples, len(raw_norm) // 2)

    correlation = sig.correlate(filt_norm, raw_norm, mode="full")
    mid = len(correlation) // 2

    # Only look at positive lags (filter introduces delay, not advance)
    search_region = correlation[mid : mid + max_lag_samples + 1]

    if len(search_region) == 0:
        return 0.0

    peak_lag = np.argmax(search_region)
    delay_ms = peak_lag / sample_rate_hz * 1000.0

    return delay_ms


def estimate_delay_phase(
    input_signal: np.ndarray,
    output_signal: np.ndarray,
    sample_rate_hz: float,
    freq_range_hz: tuple[float, float] = (50.0, 200.0),
) -> float:
    """Estimate filter delay from the average phase slope.

    Computes the transfer function H(f) = FFT(output) / FFT(input),
    then fits the phase slope in the given frequency range.
    Group delay = -dφ/dω.

    Args:
        input_signal: Input (unfiltered) signal
        output_signal: Output (filtered) signal
        sample_rate_hz: Sampling rate in Hz
        freq_range_hz: Frequency range for phase slope fitting

    Returns:
        Estimated delay in milliseconds
    """
    n = len(input_signal)
    if n < 64:
        return 0.0

    X = np.fft.rfft(input_signal)
    Y = np.fft.rfft(output_signal)
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate_hz)

    # Avoid division by zero
    magnitude_X = np.abs(X)
    valid = magnitude_X > np.max(magnitude_X) * 1e-6
    freq_mask = (freqs >= freq_range_hz[0]) & (freqs <= freq_range_hz[1]) & valid

    if np.sum(freq_mask) < 3:
        return 0.0

    H = Y[freq_mask] / X[freq_mask]
    phase = np.unwrap(np.angle(H))
    f = freqs[freq_mask]

    # Linear fit: phase = -2*pi*delay*f + offset
    # delay = -slope / (2*pi)
    coeffs = np.polyfit(f, phase, 1)
    slope = coeffs[0]
    delay_s = -slope / (2 * np.pi)
    delay_ms = delay_s * 1000.0

    return max(0.0, delay_ms)


def phase_shift_degrees(delay_ms: float, freq_hz: float) -> float:
    """Convert filter delay to phase shift in degrees at a given frequency.

    Mirrors PTphaseShiftDeg.m:
        phase_shift = delay_ms / period_ms * 360
    """
    if freq_hz <= 0:
        return 0.0
    period_ms = 1000.0 / freq_hz
    return delay_ms / period_ms * 360.0


def estimate_filter_delays(
    gyro_raw: np.ndarray,
    gyro_filtered: np.ndarray,
    dterm_raw: Optional[np.ndarray],
    dterm_filtered: Optional[np.ndarray],
    sample_rate_hz: float,
    reference_freq_hz: float = 100.0,
) -> FilterDelayResult:
    """Estimate both gyro and D-term filter delays.

    Args:
        gyro_raw: Raw (unfiltered) gyro signal
        gyro_filtered: Filtered gyro signal
        dterm_raw: Raw D-term (negative derivative of gyro), or None
        dterm_filtered: Filtered D-term output, or None
        sample_rate_hz: Sampling rate in Hz
        reference_freq_hz: Frequency at which to report phase shift

    Returns:
        FilterDelayResult with delay and phase shift for both filters
    """
    gyro_delay = estimate_delay_cross_correlation(
        gyro_raw, gyro_filtered, sample_rate_hz
    )

    dterm_delay = 0.0
    if dterm_raw is not None and dterm_filtered is not None:
        dterm_delay = estimate_delay_cross_correlation(
            dterm_raw, dterm_filtered, sample_rate_hz
        )

    return FilterDelayResult(
        gyro_delay_ms=gyro_delay,
        dterm_delay_ms=dterm_delay,
        gyro_phase_shift_deg=phase_shift_degrees(gyro_delay, reference_freq_hz),
        dterm_phase_shift_deg=phase_shift_degrees(dterm_delay, reference_freq_hz),
        reference_freq_hz=reference_freq_hz,
    )
