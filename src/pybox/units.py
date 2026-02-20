"""Unit conversion utilities for Blackbox data.

Mirrors blackbox-tools/src/units.c and the conversion routines in parser.c.
"""

from __future__ import annotations

import math
from enum import Enum, auto

from pybox.decoder.headers import SysConfig

ADCVREF = 33  # ADC voltage reference (3.3V scaled)


def vbat_adc_to_millivolts(sys_config: SysConfig, vbat_adc: int) -> int:
    """Convert raw vbat ADC value to millivolts."""
    return (vbat_adc * ADCVREF * 10 * sys_config.vbatscale) // 0xFFF


def amperage_adc_to_milliamps(sys_config: SysConfig, amperage_adc: int) -> int:
    """Convert raw amperage ADC value to milliamps."""
    millivolts = (amperage_adc * ADCVREF * 100) // 4095
    millivolts -= sys_config.current_meter_offset
    return (millivolts * 10000) // sys_config.current_meter_scale


def estimate_num_cells(sys_config: SysConfig) -> int:
    """Estimate the number of battery cells from reference voltage."""
    ref_mv = vbat_adc_to_millivolts(sys_config, sys_config.vbatref) // 100
    for i in range(1, 8):
        if ref_mv < i * sys_config.vbatmaxcellvoltage:
            return i
    return 8


def gyro_raw_to_degrees_per_second(sys_config: SysConfig, gyro_raw: int) -> float:
    """Convert raw gyro value to degrees per second.

    gyro_scale is in radians per microsecond, so:
        deg/s = gyro_scale * 1e6 * gyro_raw * (180 / pi)
    """
    rad_per_sec = sys_config.gyro_scale * 1_000_000 * gyro_raw
    return rad_per_sec * (180.0 / math.pi)


def gyro_raw_to_radians_per_second(sys_config: SysConfig, gyro_raw: int) -> float:
    """Convert raw gyro value to radians per second."""
    return sys_config.gyro_scale * 1_000_000 * gyro_raw


def acceleration_raw_to_g(sys_config: SysConfig, acc_raw: int) -> float:
    """Convert raw accelerometer value to g's."""
    if sys_config.acc_1g == 0:
        return 0.0
    return acc_raw / sys_config.acc_1g


def vbat_to_volts(sys_config: SysConfig, vbat_adc: int) -> float:
    """Convert raw vbat ADC to volts."""
    return vbat_adc_to_millivolts(sys_config, vbat_adc) / 1000.0


def amperage_to_amps(sys_config: SysConfig, amperage_adc: int) -> float:
    """Convert raw amperage ADC to amps."""
    return amperage_adc_to_milliamps(sys_config, amperage_adc) / 1000.0


def motor_to_percent(motor_value: int, motor_output_low: int = 0, motor_output_high: int = 2000) -> float:
    """Convert motor output value to percentage (0-100%).

    For Betaflight digital protocols (motor_output_low=0, motor_output_high=2000):
        percent = motor_value / 2000 * 100
    For older PWM (motor_output_low=1000):
        percent = (motor_value - 1000) / 1000 * 100
    """
    range_ = motor_output_high - motor_output_low
    if range_ == 0:
        return 0.0
    return ((motor_value - motor_output_low) / range_) * 100.0


def time_us_to_seconds(time_us: int) -> float:
    """Convert microseconds to seconds."""
    return time_us / 1_000_000.0


def phase_shift_degrees(delay_ms: float, freq_hz: float) -> float:
    """Convert filter delay in ms to phase shift in degrees at a given frequency.

    Mirrors PTphaseShiftDeg.m.
    """
    if freq_hz == 0:
        return 0.0
    period_ms = 1000.0 / freq_hz
    return delay_ms / period_ms * 360.0
