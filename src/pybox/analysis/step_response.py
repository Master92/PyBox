"""Step response estimation via deconvolution.

Mirrors PTstepcalc.m from PIDtoolbox – estimates the closed-loop step
response by deconvolving the setpoint (input) from the gyro (output).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal as sig


@dataclass
class StepResponseResult:
    """Result of step response estimation."""
    time_ms: np.ndarray          # time axis in milliseconds
    step_responses: np.ndarray   # shape (n_segments, n_time), stack of segment responses
    mean_response: np.ndarray    # mean across all segments
    std_response: np.ndarray     # std across all segments


def estimate_step_response(
    setpoint: np.ndarray,
    gyro: np.ndarray,
    sample_rate_khz: float,
    min_input: float = 20.0,
    duration_ms: float = 500.0,
    segment_duration_ms: float = 2000.0,
    smooth_window: int = 1,
) -> StepResponseResult:
    """Estimate the step response using Wiener deconvolution.

    Splits the data into overlapping segments, deconvolves each segment,
    and returns the stack + mean response.

    Args:
        setpoint: Setpoint signal (input), 1D array
        gyro: Filtered gyro signal (output), 1D array
        sample_rate_khz: Sample rate in kHz (e.g. 4.0 for 4kHz)
        min_input: Minimum setpoint amplitude to consider a segment valid
        duration_ms: Duration of the step response window in ms
        segment_duration_ms: Length of each analysis segment in ms
        smooth_window: Smoothing window size for gyro (1 = no smoothing)

    Returns:
        StepResponseResult with time axis and step response estimates
    """
    sample_rate_hz = sample_rate_khz * 1000.0
    n_samples = len(setpoint)

    # Optionally smooth gyro
    if smooth_window > 1:
        kernel = np.ones(smooth_window) / smooth_window
        gyro = np.convolve(gyro, kernel, mode="same")

    # Step response length in samples
    response_len = int(duration_ms * sample_rate_khz)  # samples = ms * kHz
    segment_len = int(segment_duration_ms * sample_rate_khz)

    if response_len < 2 or segment_len < response_len * 2:
        return StepResponseResult(
            time_ms=np.array([]),
            step_responses=np.array([[]]),
            mean_response=np.array([]),
            std_response=np.array([]),
        )

    time_ms = np.linspace(0, duration_ms, response_len)
    step_responses = []

    # Slide through the data in segments
    step = max(1, segment_len // 2)
    for start in range(0, n_samples - segment_len, step):
        seg_sp = setpoint[start : start + segment_len].astype(np.float64)
        seg_gy = gyro[start : start + segment_len].astype(np.float64)

        # Skip segments with low input activity
        if np.max(np.abs(seg_sp)) < min_input:
            continue

        # Wiener deconvolution in frequency domain
        resp = _deconvolve_segment(seg_sp, seg_gy, response_len)
        if resp is not None:
            step_responses.append(resp)

    if not step_responses:
        return StepResponseResult(
            time_ms=time_ms,
            step_responses=np.array([[]]),
            mean_response=np.zeros(response_len),
            std_response=np.zeros(response_len),
        )

    stack = np.array(step_responses)
    mean_resp = np.mean(stack, axis=0)
    std_resp = np.std(stack, axis=0)

    return StepResponseResult(
        time_ms=time_ms,
        step_responses=stack,
        mean_response=mean_resp,
        std_response=std_resp,
    )


def _deconvolve_segment(
    input_sig: np.ndarray,
    output_sig: np.ndarray,
    response_len: int,
    noise_floor: float = 1e-3,
) -> np.ndarray | None:
    """Estimate impulse response via Wiener deconvolution, then integrate to step response.

    Uses the frequency-domain relationship: H(f) = Y(f) / X(f), with
    Wiener regularization to avoid noise amplification.
    """
    n = len(input_sig)
    if n < response_len:
        return None

    X = np.fft.rfft(input_sig, n=n)
    Y = np.fft.rfft(output_sig, n=n)

    # Wiener filter: H = (Y * conj(X)) / (|X|^2 + noise)
    power_x = np.abs(X) ** 2
    max_power = np.max(power_x)
    if max_power == 0:
        return None

    noise_level = noise_floor * max_power
    H = (Y * np.conj(X)) / (power_x + noise_level)

    # Inverse FFT to get impulse response
    impulse_response = np.fft.irfft(H, n=n)

    # Take first response_len samples and integrate to get step response
    ir = impulse_response[:response_len]
    step_response = np.cumsum(ir)

    # Normalize so steady-state ≈ 1
    if len(step_response) > 0:
        tail = step_response[-response_len // 4:]
        steady_state = np.mean(tail) if len(tail) > 0 else 1.0
        if abs(steady_state) > 1e-6:
            step_response = step_response / steady_state

    return step_response
