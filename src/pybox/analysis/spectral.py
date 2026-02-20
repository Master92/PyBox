"""Spectral analysis – FFT, PSD, and throttle-vs-frequency spectrograms.

Mirrors PTplotSpec.m / PTthrSpec.m / PTSpec2d.m from PIDtoolbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import signal as sig


@dataclass
class Spectrum2D:
    """Result of a 2D amplitude/PSD spectrum."""
    frequencies: np.ndarray  # Hz
    amplitudes: np.ndarray   # amplitude or dB


@dataclass
class ThrottleSpectrogram:
    """Result of a throttle-vs-frequency spectrogram."""
    throttle_bins: np.ndarray   # 0..100 %
    frequency_bins: np.ndarray  # Hz
    power_matrix: np.ndarray    # shape (n_throttle, n_freq)


def compute_spectrum_2d(
    data: np.ndarray,
    sample_rate_hz: float,
    use_psd: bool = False,
    nperseg: int = 0,
    window: str = "hann",
) -> Spectrum2D:
    """Compute a 2D amplitude or PSD spectrum using Welch's method.

    Args:
        data: 1D time series
        sample_rate_hz: Sampling rate in Hz
        use_psd: If True, return power spectral density in dB; else amplitude
        nperseg: Segment length for Welch; 0 = auto (1/4 of data length)
        window: Window function name

    Returns:
        Spectrum2D with frequencies and amplitudes
    """
    if len(data) < 4:
        return Spectrum2D(frequencies=np.array([]), amplitudes=np.array([]))

    if nperseg <= 0:
        nperseg = min(len(data), max(256, len(data) // 4))

    freqs, pxx = sig.welch(
        data,
        fs=sample_rate_hz,
        window=window,
        nperseg=nperseg,
        noverlap=nperseg // 2,
        scaling="density" if use_psd else "spectrum",
    )

    if use_psd:
        # Convert to dB, avoid log(0)
        pxx = 10 * np.log10(np.maximum(pxx, 1e-20))
    else:
        pxx = np.sqrt(pxx)  # amplitude spectrum

    return Spectrum2D(frequencies=freqs, amplitudes=pxx)


def compute_throttle_spectrogram(
    data: np.ndarray,
    throttle: np.ndarray,
    sample_rate_hz: float,
    use_psd: bool = False,
    n_throttle_bins: int = 100,
    nperseg: int = 0,
    window: str = "hann",
    freq_limit_hz: float = 0,
) -> ThrottleSpectrogram:
    """Compute a throttle-vs-frequency spectrogram.

    Splits the signal into segments grouped by throttle position, computes
    the spectrum for each throttle bin.

    Args:
        data: 1D time series (e.g. gyro for one axis)
        throttle: 1D throttle values (0..100 %)
        sample_rate_hz: Sampling rate in Hz
        use_psd: If True, compute PSD in dB
        n_throttle_bins: Number of throttle bins (default 100 for 1% resolution)
        nperseg: Segment length; 0 = auto
        window: Window function
        freq_limit_hz: If > 0, limit output to this frequency

    Returns:
        ThrottleSpectrogram
    """
    if len(data) < 4:
        return ThrottleSpectrogram(
            throttle_bins=np.array([]),
            frequency_bins=np.array([]),
            power_matrix=np.array([[]]),
        )

    if nperseg <= 0:
        nperseg = min(len(data), max(128, len(data) // 8))

    # Compute STFT
    freqs, times, Zxx = sig.stft(
        data,
        fs=sample_rate_hz,
        window=window,
        nperseg=nperseg,
        noverlap=nperseg * 3 // 4,
    )

    if freq_limit_hz > 0:
        freq_mask = freqs <= freq_limit_hz
        freqs = freqs[freq_mask]
        Zxx = Zxx[freq_mask, :]

    power = np.abs(Zxx) ** 2

    # Map each STFT time slice to a throttle bin
    throttle_interp = np.interp(
        times,
        np.linspace(0, len(data) / sample_rate_hz, len(throttle)),
        throttle.astype(np.float64),
    )

    throttle_edges = np.linspace(0, 100, n_throttle_bins + 1)
    throttle_centers = (throttle_edges[:-1] + throttle_edges[1:]) / 2

    result_matrix = np.zeros((n_throttle_bins, len(freqs)))

    for i in range(n_throttle_bins):
        mask = (throttle_interp >= throttle_edges[i]) & (throttle_interp < throttle_edges[i + 1])
        if np.any(mask):
            result_matrix[i, :] = np.mean(power[:, mask], axis=1)

    if use_psd:
        result_matrix = 10 * np.log10(np.maximum(result_matrix, 1e-20))
    else:
        result_matrix = np.sqrt(result_matrix)

    return ThrottleSpectrogram(
        throttle_bins=throttle_centers,
        frequency_bins=freqs,
        power_matrix=result_matrix,
    )


def compute_spectrogram(
    data: np.ndarray,
    sample_rate_hz: float,
    use_psd: bool = False,
    nperseg: int = 0,
    window: str = "hann",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute a time-frequency spectrogram.

    Returns:
        (frequencies, times, power_matrix)
    """
    if len(data) < 4:
        return np.array([]), np.array([]), np.array([[]])

    if nperseg <= 0:
        nperseg = min(len(data), max(256, len(data) // 8))

    freqs, times, Sxx = sig.spectrogram(
        data,
        fs=sample_rate_hz,
        window=window,
        nperseg=nperseg,
        noverlap=nperseg * 3 // 4,
    )

    if use_psd:
        Sxx = 10 * np.log10(np.maximum(Sxx, 1e-20))
    else:
        Sxx = np.sqrt(Sxx)

    return freqs, times, Sxx
