"""Integration tests for pybox.decoder.flightlog – end-to-end decoding."""

import os
import pytest

from pybox.decoder.flightlog import FlightLog, DecodedLog

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")
SAMPLE_BBL = os.path.join(SAMPLES_DIR, "btfl_001.bbl")
TUNING_DIR = os.path.join(SAMPLES_DIR, "tuning")


def _skip_if_missing(path):
    if not os.path.isfile(path):
        pytest.skip(f"Sample file not found: {path}")


class TestFlightLogDiscovery:
    def test_discover_logs(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        assert log.log_count >= 1

    def test_log_count_matches_arms(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        # Each arm cycle creates a new log; just verify it's reasonable
        assert 1 <= log.log_count <= 100


class TestFlightLogHeader:
    def test_get_header(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        header = log.get_header(0)
        assert header.data_version >= 1
        # Should have I-frame definition
        i_def = header.frame_defs.get(ord("I"))
        assert i_def is not None
        assert i_def.field_count > 0
        # Should have at least time and loopIteration
        assert "time" in i_def.field_names or "time" in [n.strip() for n in i_def.field_names]

    def test_header_has_field_indexes(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        header = log.get_header(0)
        assert header.main_field_indexes.time >= 0
        assert header.main_field_indexes.loop_iteration >= 0

    def test_invalid_log_index(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        with pytest.raises(IndexError):
            log.get_header(9999)


class TestFlightLogDecode:
    def test_decode_first_log(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        decoded = log.decode(0)
        assert isinstance(decoded, DecodedLog)
        assert decoded.valid_frame_count > 0
        assert len(decoded.main_frames) > 0
        assert len(decoded.field_names) > 0

    def test_duration_positive(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        decoded = log.decode(0)
        assert decoded.duration_us > 0
        assert decoded.duration_s > 0.0

    def test_sample_rate_reasonable(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        decoded = log.decode(0)
        sr = decoded.sample_rate_hz
        # Betaflight typically logs at 1-8 kHz
        assert 100 < sr < 50000, f"Sample rate {sr} Hz seems unreasonable"

    def test_time_monotonic(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        decoded = log.decode(0)
        times = [f[1] for f in decoded.main_frames]  # field index 1 = time
        # Time should be generally increasing (some small hiccups are ok)
        increasing_count = sum(1 for i in range(1, len(times)) if times[i] >= times[i-1])
        ratio = increasing_count / max(1, len(times) - 1)
        assert ratio > 0.95, f"Only {ratio*100:.1f}% of timestamps are increasing"


class TestFlightLogDataFrame:
    def test_to_dataframe(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        df = log.to_dataframe(0)
        assert len(df) > 0
        assert "time" in df.columns or "time(us)" in df.columns
        assert "loopIteration" in df.columns

    def test_dataframe_columns_match_field_names(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        decoded = log.decode(0)
        df = decoded.to_dataframe()
        assert list(df.columns) == decoded.field_names[:len(df.columns)]

    def test_setup_info(self):
        _skip_if_missing(SAMPLE_BBL)
        log = FlightLog(SAMPLE_BBL)
        decoded = log.decode(0)
        info = decoded.setup_info
        assert isinstance(info, dict)
        assert len(info) > 0


class TestTuningSamples:
    """Test against the tuning sample files if available."""

    @pytest.fixture(params=[
        "4s.bbl", "ff_0.bbl", "pd_08.bbl", "m_1.bbl", "i_09.bbl",
    ])
    def tuning_file(self, request):
        path = os.path.join(TUNING_DIR, request.param)
        _skip_if_missing(path)
        return path

    def test_decode_tuning_sample(self, tuning_file):
        log = FlightLog(tuning_file)
        assert log.log_count >= 1
        decoded = log.decode(0)
        assert decoded.valid_frame_count > 0
        assert decoded.duration_s > 0.0
        df = decoded.to_dataframe()
        assert len(df) > 100  # should have substantial data
