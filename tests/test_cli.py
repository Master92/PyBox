"""Tests for pybox.cli – command-line interface."""

import os
import json
import pytest
from click.testing import CliRunner

from pybox.cli import main

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")
SAMPLE_BBL = os.path.join(SAMPLES_DIR, "btfl_001.bbl")


def _skip_if_missing(path):
    if not os.path.isfile(path):
        pytest.skip(f"Sample file not found: {path}")


class TestCLIVersion:
    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestCLIInfo:
    def test_info(self):
        _skip_if_missing(SAMPLE_BBL)
        runner = CliRunner()
        result = runner.invoke(main, ["info", SAMPLE_BBL])
        assert result.exit_code == 0
        assert "Logs:" in result.output
        assert "Firmware" in result.output

    def test_info_with_index(self):
        _skip_if_missing(SAMPLE_BBL)
        runner = CliRunner()
        result = runner.invoke(main, ["info", "-i", "0", SAMPLE_BBL])
        assert result.exit_code == 0


class TestCLIDecode:
    def test_decode(self, tmp_path):
        _skip_if_missing(SAMPLE_BBL)
        runner = CliRunner()
        out_csv = str(tmp_path / "test_output.csv")
        result = runner.invoke(main, ["decode", "-i", "0", "-o", out_csv, SAMPLE_BBL])
        assert result.exit_code == 0
        assert os.path.isfile(out_csv)
        # Check the CSV has content
        with open(out_csv) as f:
            lines = f.readlines()
        assert len(lines) > 100  # header + many data rows


class TestCLIAnalyze:
    def test_analyze(self):
        _skip_if_missing(SAMPLE_BBL)
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", SAMPLE_BBL])
        assert result.exit_code == 0
        assert "Flight Statistics" in result.output
        assert "PID Error" in result.output

    def test_analyze_json_output(self, tmp_path):
        _skip_if_missing(SAMPLE_BBL)
        runner = CliRunner()
        out_json = str(tmp_path / "analysis.json")
        result = runner.invoke(main, ["analyze", "-o", out_json, SAMPLE_BBL])
        assert result.exit_code == 0
        assert os.path.isfile(out_json)
        data = json.loads(open(out_json).read())
        assert "duration_s" in data
        assert "sample_rate_hz" in data
        assert "pid_error" in data
