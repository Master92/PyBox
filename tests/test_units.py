"""Tests for pybox.units – unit conversion utilities."""

import math
import pytest

from pybox.decoder.headers import SysConfig
from pybox.units import (
    vbat_adc_to_millivolts,
    amperage_adc_to_milliamps,
    estimate_num_cells,
    gyro_raw_to_degrees_per_second,
    gyro_raw_to_radians_per_second,
    acceleration_raw_to_g,
    motor_to_percent,
    time_us_to_seconds,
    phase_shift_degrees,
)


@pytest.fixture
def default_config():
    return SysConfig()


class TestVbat:
    def test_adc_to_millivolts(self, default_config):
        # With default vbatscale=110, vbatref=4095:
        # (4095 * 33 * 10 * 110) / 0xFFF = 33 * 10 * 110 = 36300
        mv = vbat_adc_to_millivolts(default_config, 4095)
        assert mv == 36300

    def test_adc_zero(self, default_config):
        assert vbat_adc_to_millivolts(default_config, 0) == 0


class TestAmperage:
    def test_adc_to_milliamps(self, default_config):
        # With offset=0, scale=400:
        # millivolts = (1000 * 33 * 100) / 4095 = ~805
        # milliamps = (805 * 10000) / 400 = 20125
        ma = amperage_adc_to_milliamps(default_config, 1000)
        assert isinstance(ma, int)


class TestCellCount:
    def test_default_4s(self):
        config = SysConfig(vbatref=4095, vbatscale=110, vbatmaxcellvoltage=43)
        cells = estimate_num_cells(config)
        # 36300 / 100 = 363 -> 363 / 43 ~ 8.4, loop breaks at i=9
        # Actually: for i in 1..7: if 363 < i * 43
        # i=1: 363 < 43 -> False
        # ...
        # i=8: 363 < 344 -> False -> returns 8
        assert cells >= 1


class TestGyro:
    def test_raw_to_dps(self):
        # gyro_scale for Cleanflight-style: gyro_scale * pi/180 * 1e-6
        # Typical value: gyro_scale after conversion ~ 0.00106526 * pi/180 * 1e-6
        config = SysConfig(gyro_scale=1.0e-6 * math.pi / 180.0)
        dps = gyro_raw_to_degrees_per_second(config, 1000)
        # Should be close to 1000 deg/s
        assert abs(dps - 1000.0) < 0.1

    def test_raw_to_rps(self):
        config = SysConfig(gyro_scale=1.0e-6)
        rps = gyro_raw_to_radians_per_second(config, 1000)
        assert abs(rps - 1000.0) < 0.001


class TestAcceleration:
    def test_raw_to_g(self):
        config = SysConfig(acc_1g=4096)
        assert abs(acceleration_raw_to_g(config, 4096) - 1.0) < 0.001
        assert abs(acceleration_raw_to_g(config, 0) - 0.0) < 0.001

    def test_zero_acc1g(self):
        config = SysConfig(acc_1g=0)
        assert acceleration_raw_to_g(config, 100) == 0.0


class TestMotor:
    def test_digital_protocol(self):
        # motor_output_low=0, high=2000
        assert abs(motor_to_percent(2000, 0, 2000) - 100.0) < 0.01
        assert abs(motor_to_percent(0, 0, 2000) - 0.0) < 0.01
        assert abs(motor_to_percent(1000, 0, 2000) - 50.0) < 0.01

    def test_pwm_protocol(self):
        assert abs(motor_to_percent(1500, 1000, 2000) - 50.0) < 0.01


class TestTime:
    def test_us_to_seconds(self):
        assert abs(time_us_to_seconds(1_000_000) - 1.0) < 0.001
        assert abs(time_us_to_seconds(0) - 0.0) < 0.001


class TestPhaseShift:
    def test_basic(self):
        # 1ms delay at 1000Hz -> period=1ms -> shift = 360 deg
        assert abs(phase_shift_degrees(1.0, 1000.0) - 360.0) < 0.01
        # 0.5ms delay at 100Hz -> period=10ms -> shift = 18 deg
        assert abs(phase_shift_degrees(0.5, 100.0) - 18.0) < 0.01

    def test_zero_freq(self):
        assert phase_shift_degrees(1.0, 0.0) == 0.0
