"""Tests for pybox.analysis – PID error, spectral, step response, statistics, filters."""

import numpy as np
import pandas as pd
import pytest

from pybox.analysis.pid_error import (
    compute_pid_error,
    compute_pid_sum,
    pid_error_distribution,
    pid_error_vs_stick,
)
from pybox.analysis.spectral import (
    compute_spectrum_2d,
    compute_throttle_spectrogram,
    compute_spectrogram,
)
from pybox.analysis.step_response import estimate_step_response
from pybox.analysis.statistics import (
    rc_command_to_percent,
    compute_stick_distribution,
    compute_motor_stats,
    compute_rate_curve,
)
from pybox.analysis.filters import (
    estimate_delay_cross_correlation,
    estimate_delay_phase,
    phase_shift_degrees,
    estimate_filter_delays,
)


# ── PID Error ─────────────────────────────────────────────────────────

class TestPIDError:
    def test_compute_pid_error(self):
        gyro = np.array([100, 200, 300], dtype=np.float64)
        setpoint = np.array([100, 190, 310], dtype=np.float64)
        err = compute_pid_error(gyro, setpoint)
        np.testing.assert_array_almost_equal(err, [0, 10, -10])

    def test_compute_pid_sum(self):
        p = np.array([10, 20])
        i = np.array([1, 2])
        d = np.array([0.5, 1.0])
        f = np.array([0.1, 0.2])
        result = compute_pid_sum(p, i, d, f)
        np.testing.assert_array_almost_equal(result, [11.6, 23.2])

    def test_compute_pid_sum_no_d_no_f(self):
        p = np.array([10, 20])
        i = np.array([1, 2])
        result = compute_pid_sum(p, i)
        np.testing.assert_array_almost_equal(result, [11, 22])

    def test_pid_error_distribution(self):
        rng = np.random.default_rng(42)
        data = rng.normal(0, 5, size=10000)
        bins, counts = pid_error_distribution(data)
        assert len(bins) == len(counts)
        assert counts.max() == pytest.approx(1.0)
        # Peak should be near zero
        peak_idx = np.argmax(counts)
        assert abs(bins[peak_idx]) < 5

    def test_pid_error_vs_stick(self):
        rng = np.random.default_rng(42)
        n = 5000
        rc_rate = rng.uniform(-500, 500, n)
        pid_err = rng.normal(0, 3, n)
        mean_abs, se = pid_error_vs_stick(pid_err, rc_rate)
        assert len(mean_abs) == 10
        assert len(se) == 10
        assert all(m >= 0 for m in mean_abs)


# ── Spectral ──────────────────────────────────────────────────────────

class TestSpectral:
    def test_spectrum_2d_basic(self):
        sr = 4000.0
        t = np.arange(0, 1, 1 / sr)
        # 200 Hz sine
        data = np.sin(2 * np.pi * 200 * t)
        result = compute_spectrum_2d(data, sr)
        assert len(result.frequencies) > 0
        assert len(result.amplitudes) > 0
        # Peak should be near 200 Hz
        peak_idx = np.argmax(result.amplitudes)
        assert abs(result.frequencies[peak_idx] - 200) < 20

    def test_spectrum_2d_psd(self):
        sr = 4000.0
        t = np.arange(0, 1, 1 / sr)
        data = np.sin(2 * np.pi * 100 * t)
        result = compute_spectrum_2d(data, sr, use_psd=True)
        assert len(result.frequencies) > 0
        # PSD should have dB values (can be negative)
        assert result.amplitudes.max() > result.amplitudes.min()

    def test_spectrum_2d_short_data(self):
        result = compute_spectrum_2d(np.array([1, 2]), 4000.0)
        assert len(result.frequencies) == 0

    def test_throttle_spectrogram(self):
        sr = 4000.0
        n = 8000
        t = np.arange(n) / sr
        data = np.sin(2 * np.pi * 200 * t)
        throttle = np.linspace(20, 80, n)
        result = compute_throttle_spectrogram(data, throttle, sr)
        assert result.power_matrix.shape[0] > 0
        assert result.power_matrix.shape[1] > 0
        assert len(result.throttle_bins) > 0
        assert len(result.frequency_bins) > 0

    def test_spectrogram(self):
        sr = 4000.0
        t = np.arange(0, 1, 1 / sr)
        data = np.sin(2 * np.pi * 200 * t)
        freqs, times, Sxx = compute_spectrogram(data, sr)
        assert len(freqs) > 0
        assert len(times) > 0
        assert Sxx.shape[0] == len(freqs)
        assert Sxx.shape[1] == len(times)


# ── Step Response ─────────────────────────────────────────────────────

class TestStepResponse:
    def test_basic_step_response(self):
        # Simulate a first-order system response
        sr_khz = 4.0
        sr_hz = sr_khz * 1000
        n = int(sr_hz * 5)  # 5 seconds
        t = np.arange(n) / sr_hz

        # Square wave setpoint
        setpoint = np.zeros(n)
        for i in range(0, n, int(sr_hz * 0.5)):
            setpoint[i:i + int(sr_hz * 0.25)] = 300

        # Simulate gyro as low-pass filtered setpoint (first-order)
        tau = 0.02  # 20ms time constant
        alpha = 1 / (tau * sr_hz + 1)
        gyro = np.zeros(n)
        for i in range(1, n):
            gyro[i] = gyro[i - 1] + alpha * (setpoint[i] - gyro[i - 1])

        result = estimate_step_response(setpoint, gyro, sr_khz, min_input=10)
        assert len(result.time_ms) > 0
        assert len(result.mean_response) > 0

    def test_empty_input(self):
        result = estimate_step_response(
            np.zeros(100), np.zeros(100), 4.0, min_input=20
        )
        assert len(result.mean_response) > 0
        # With zero input, all segments should be skipped
        # mean_response should be zeros
        np.testing.assert_array_almost_equal(result.mean_response, np.zeros_like(result.mean_response))


# ── Statistics ────────────────────────────────────────────────────────

class TestStatistics:
    def test_rc_command_to_percent(self):
        rc = np.array([0, 250, -500, 500])
        pct = rc_command_to_percent(rc)
        np.testing.assert_array_almost_equal(pct, [0, 50, 100, 100])

    def test_stick_distribution(self):
        rng = np.random.default_rng(42)
        pct = rng.uniform(0, 100, 5000)
        dist = compute_stick_distribution(pct, "roll")
        assert dist.axis == "roll"
        assert len(dist.histogram) > 0
        assert 0 < dist.mean_percent < 100

    def test_motor_stats(self):
        motors = np.array([[1000, 1200, 1100, 1300],
                           [1050, 1250, 1150, 1350],
                           [1100, 1300, 1200, 1400]], dtype=np.float64)
        stats = compute_motor_stats(motors, motor_output_low=0, motor_output_high=2000)
        assert len(stats.mean_percent) == 4
        assert all(0 <= m <= 100 for m in stats.mean_percent)
        assert all(stats.min_percent[i] <= stats.mean_percent[i] <= stats.max_percent[i] for i in range(4))

    def test_rate_curve_betaflight(self):
        # Typical Betaflight rates
        curve = compute_rate_curve(rc_rate=1.0, rc_expo=0.0, super_rate=0.7)
        assert len(curve) == 501  # 0..500
        assert curve[0] == pytest.approx(0.0)
        assert curve[-1] > 0  # max rate should be positive
        # With super_rate > 0, curve should be exponential-ish
        assert curve[250] < curve[500] / 2  # mid-stick < half of max rate

    def test_rate_curve_no_expo_no_super(self):
        curve = compute_rate_curve(rc_rate=1.0, rc_expo=0.0, super_rate=0.0)
        # Should be linear
        assert curve[0] == pytest.approx(0.0)
        # Linear: rate = 200 * 1.0 * (i/500) = 0.4 * i
        expected_at_250 = 200.0 * 1.0 * 0.5
        assert curve[250] == pytest.approx(expected_at_250, rel=0.01)


# ── Filters ───────────────────────────────────────────────────────────

class TestFilters:
    def test_phase_shift_degrees(self):
        assert phase_shift_degrees(1.0, 1000.0) == pytest.approx(360.0)
        assert phase_shift_degrees(0.5, 100.0) == pytest.approx(18.0)
        assert phase_shift_degrees(1.0, 0.0) == 0.0

    def test_cross_correlation_known_delay(self):
        sr = 4000.0
        delay_ms = 2.0
        delay_samples = int(delay_ms * sr / 1000)
        n = 4000

        rng = np.random.default_rng(42)
        raw = rng.normal(0, 1, n)
        # Filtered = raw shifted by delay_samples
        filtered = np.zeros(n)
        filtered[delay_samples:] = raw[:-delay_samples]

        est_delay = estimate_delay_cross_correlation(raw, filtered, sr, max_delay_ms=10.0)
        assert abs(est_delay - delay_ms) < 0.5  # within 0.5ms

    def test_cross_correlation_no_delay(self):
        sr = 4000.0
        data = np.sin(2 * np.pi * 100 * np.arange(4000) / sr)
        est_delay = estimate_delay_cross_correlation(data, data, sr)
        assert est_delay < 0.5  # essentially zero delay

    def test_estimate_delay_phase_known(self):
        sr = 4000.0
        n = 8000
        t = np.arange(n) / sr

        # Create a signal with known group delay using a simple FIR filter
        raw = np.random.default_rng(42).normal(0, 1, n)
        # Simple moving average with ~1ms delay at sr=4000
        kernel_len = 9  # ~1ms at 4kHz
        kernel = np.ones(kernel_len) / kernel_len
        filtered = np.convolve(raw, kernel, mode="same")

        est_delay = estimate_delay_phase(raw, filtered, sr, freq_range_hz=(50, 500))
        # Moving average of length 9 at 4kHz has group delay ~1ms
        assert 0.5 < est_delay < 3.0

    def test_estimate_filter_delays(self):
        sr = 4000.0
        n = 4000
        rng = np.random.default_rng(42)
        gyro_raw = rng.normal(0, 10, n)
        # Simple smoothing
        kernel = np.ones(5) / 5
        gyro_filtered = np.convolve(gyro_raw, kernel, mode="same")

        result = estimate_filter_delays(
            gyro_raw, gyro_filtered, None, None, sr, reference_freq_hz=100.0
        )
        assert result.gyro_delay_ms >= 0
        assert result.dterm_delay_ms == 0.0  # no dterm provided
        assert result.reference_freq_hz == 100.0
