"""Tests for pybox.gui.models – GUI data model."""

import os
import pytest
import numpy as np

from pybox.gui.models import (
    LogEntry,
    PIDFFConfig,
    LOG_COLORS,
    load_log_entry,
)
from pybox.decoder.headers import LogHeader

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")
SAMPLE_BBL = os.path.join(SAMPLES_DIR, "btfl_001.bbl")


def _skip_if_missing(path):
    if not os.path.isfile(path):
        pytest.skip(f"Sample file not found: {path}")


class TestPIDFFConfig:
    def test_from_header(self):
        header = LogHeader()
        header.raw_headers["rollPID"] = "45,80,40"
        header.raw_headers["pitchPID"] = "47,84,46"
        header.raw_headers["yawPID"] = "45,80,0"
        header.raw_headers["ff_weight"] = "120,125,120"

        cfg = PIDFFConfig.from_header(header)
        assert cfg.roll_p == 45
        assert cfg.roll_i == 80
        assert cfg.roll_d == 40
        assert cfg.roll_ff == 120
        assert cfg.pitch_p == 47
        assert cfg.pitch_i == 84
        assert cfg.pitch_d == 46
        assert cfg.pitch_ff == 125
        assert cfg.yaw_p == 45
        assert cfg.yaw_d == 0
        assert cfg.yaw_ff == 120

    def test_axis_str(self):
        cfg = PIDFFConfig(roll_p=45, roll_i=80, roll_d=40, roll_ff=120)
        s = cfg.axis_str(0)
        assert "P45" in s
        assert "I80" in s
        assert "D40" in s
        assert "FF120" in s

    def test_from_empty_header(self):
        header = LogHeader()
        cfg = PIDFFConfig.from_header(header)
        assert cfg.roll_p == 0
        assert cfg.roll_ff == 0


class TestLoadLogEntry:
    def test_load_entry(self):
        _skip_if_missing(SAMPLE_BBL)
        entry = load_log_entry(SAMPLE_BBL, 0, 0)
        assert isinstance(entry, LogEntry)
        assert entry.log_index == 0
        assert entry.color == LOG_COLORS[0]
        assert entry.duration_s > 0
        assert entry.visible is True
        assert entry.time_start_s == 0.0
        assert entry.time_end_s > 0.0

    def test_gyro_arrays(self):
        _skip_if_missing(SAMPLE_BBL)
        entry = load_log_entry(SAMPLE_BBL, 0, 0)
        time_s, gyro_r, gyro_p, gyro_y = entry.gyro_arrays()
        assert len(time_s) > 100
        assert len(gyro_r) == len(time_s)
        assert len(gyro_p) == len(time_s)
        assert len(gyro_y) == len(time_s)
        # Time should start near 0
        assert time_s[0] == pytest.approx(0.0)
        # Time should be generally increasing
        assert time_s[-1] > time_s[0]

    def test_setpoint_arrays(self):
        _skip_if_missing(SAMPLE_BBL)
        entry = load_log_entry(SAMPLE_BBL, 0, 0)
        sp_r, sp_p, sp_y = entry.setpoint_arrays()
        assert len(sp_r) > 100

    def test_time_mask(self):
        _skip_if_missing(SAMPLE_BBL)
        entry = load_log_entry(SAMPLE_BBL, 0, 0)
        # Set range to first 10 seconds
        entry.time_start_s = 0.0
        entry.time_end_s = 10.0
        mask = entry.time_mask()
        assert np.sum(mask) > 0
        assert np.sum(mask) < len(mask)

    def test_pidff_from_real_log(self):
        _skip_if_missing(SAMPLE_BBL)
        entry = load_log_entry(SAMPLE_BBL, 0, 0)
        # btfl_001.bbl has rollPID:45,80,40 etc
        assert entry.pidff.roll_p > 0
        assert entry.pidff.pitch_p > 0

    def test_color_palette_coverage(self):
        assert len(LOG_COLORS) >= 12
        # All should be valid hex colors
        for c in LOG_COLORS:
            assert c.startswith("#")
            assert len(c) == 7

    def test_label_format(self):
        _skip_if_missing(SAMPLE_BBL)
        entry = load_log_entry(SAMPLE_BBL, 0, 2)
        assert "#1" in entry.label  # log index 0 -> "#1"
        assert entry.color == LOG_COLORS[2]
