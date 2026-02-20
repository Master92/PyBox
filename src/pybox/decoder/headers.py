"""Blackbox log header parser.

Parses the 'H ...' header lines at the start of each log to extract:
- Frame field definitions (names, predictors, encodings, signedness)
- System configuration (rates, battery, gyro scale, etc.)
- Frame intervals, data version, firmware info
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pybox.decoder.defs import (
    FLIGHT_LOG_MAX_FIELDS,
    FirmwareType,
)
from pybox.decoder.stream import BinaryStream, EOF


# ── data structures ───────────────────────────────────────────────────

@dataclass
class FrameDef:
    """Definition of fields for one frame type (I, P, G, H, S)."""
    field_names: list[str] = field(default_factory=list)
    field_count: int = 0
    field_signed: list[int] = field(default_factory=lambda: [0] * FLIGHT_LOG_MAX_FIELDS)
    field_width: list[int] = field(default_factory=lambda: [4] * FLIGHT_LOG_MAX_FIELDS)
    predictor: list[int] = field(default_factory=lambda: [0] * FLIGHT_LOG_MAX_FIELDS)
    encoding: list[int] = field(default_factory=lambda: [0] * FLIGHT_LOG_MAX_FIELDS)


@dataclass
class SysConfig:
    """Flight controller system configuration extracted from headers."""
    minthrottle: int = 1150
    maxthrottle: int = 1850
    motor_output_low: int = 1150
    motor_output_high: int = 1850

    rc_rate: int = 90
    yaw_rate: int = 0

    acc_1g: int = 1
    gyro_scale: float = 1.0

    vbatscale: int = 110
    vbatmaxcellvoltage: int = 43
    vbatmincellvoltage: int = 33
    vbatwarningcellvoltage: int = 35

    current_meter_offset: int = 0
    current_meter_scale: int = 400

    vbatref: int = 4095

    firmware_type: FirmwareType = FirmwareType.UNKNOWN


@dataclass
class MainFieldIndexes:
    """Well-known field indexes in the main (I/P) frame."""
    loop_iteration: int = -1
    time: int = -1
    pid: list[list[int]] = field(default_factory=lambda: [[-1, -1, -1] for _ in range(3)])
    rc_command: list[int] = field(default_factory=lambda: [-1, -1, -1, -1])
    vbat_latest: int = -1
    amperage_latest: int = -1
    mag_adc: list[int] = field(default_factory=lambda: [-1, -1, -1])
    baro_alt: int = -1
    sonar_raw: int = -1
    rssi: int = -1
    gyro_adc: list[int] = field(default_factory=lambda: [-1, -1, -1])
    acc_smooth: list[int] = field(default_factory=lambda: [-1, -1, -1])
    motor: list[int] = field(default_factory=lambda: [-1] * 8)
    servo: list[int] = field(default_factory=lambda: [-1] * 8)


@dataclass
class GPSFieldIndexes:
    time: int = -1
    gps_num_sat: int = -1
    gps_coord: list[int] = field(default_factory=lambda: [-1, -1])
    gps_altitude: int = -1
    gps_speed: int = -1
    gps_ground_course: int = -1


@dataclass
class GPSHomeFieldIndexes:
    gps_home: list[int] = field(default_factory=lambda: [-1, -1])


@dataclass
class SlowFieldIndexes:
    flight_mode_flags: int = -1
    state_flags: int = -1
    failsafe_phase: int = -1


@dataclass
class LogHeader:
    """All metadata parsed from the header section of one log."""
    frame_defs: dict[int, FrameDef] = field(default_factory=dict)
    sys_config: SysConfig = field(default_factory=SysConfig)
    main_field_indexes: MainFieldIndexes = field(default_factory=MainFieldIndexes)
    gps_field_indexes: GPSFieldIndexes = field(default_factory=GPSFieldIndexes)
    gps_home_field_indexes: GPSHomeFieldIndexes = field(default_factory=GPSHomeFieldIndexes)
    slow_field_indexes: SlowFieldIndexes = field(default_factory=SlowFieldIndexes)

    data_version: int = 0
    fc_version: str = ""
    firmware_revision: str = ""

    frame_interval_i: int = 32
    frame_interval_p_num: int = 1
    frame_interval_p_denom: int = 1

    datetime: Optional[datetime] = None

    # Raw header key-value pairs for setup info extraction
    raw_headers: dict[str, str] = field(default_factory=dict)


# ── parsing ───────────────────────────────────────────────────────────

def _parse_field_names(value: str) -> list[str]:
    """Split a comma-separated list of field names."""
    return [n.strip() for n in value.split(",") if n.strip()]


def _parse_csv_ints(value: str) -> list[int]:
    """Parse a comma-separated list of integers."""
    result = []
    for part in value.split(","):
        part = part.strip()
        if part:
            try:
                result.append(int(part))
            except ValueError:
                result.append(0)
    return result


def _identify_main_fields(header: LogHeader, frame_def: FrameDef) -> None:
    idx = header.main_field_indexes
    for i, name in enumerate(frame_def.field_names):
        if name.startswith("motor["):
            mi = int(name[len("motor["):].rstrip("]"))
            if 0 <= mi < 8:
                idx.motor[mi] = i
        elif name.startswith("rcCommand["):
            ri = int(name[len("rcCommand["):].rstrip("]"))
            if 0 <= ri < 4:
                idx.rc_command[ri] = i
        elif name.startswith("axis"):
            # axisP[0], axisI[1], axisD[2], etc.
            axis_letter = name[4]  # P, I, or D
            bracket_pos = name.find("[")
            if bracket_pos != -1:
                ai = int(name[bracket_pos + 1:].rstrip("]"))
                if axis_letter == "P":
                    idx.pid[0][ai] = i
                elif axis_letter == "I":
                    idx.pid[1][ai] = i
                elif axis_letter == "D":
                    idx.pid[2][ai] = i
                elif axis_letter == "F":
                    pass  # feedforward – store if needed
        elif name.startswith("gyroData[") or name.startswith("gyroADC["):
            prefix = "gyroData[" if name.startswith("gyroData[") else "gyroADC["
            ai = int(name[len(prefix):].rstrip("]"))
            idx.gyro_adc[ai] = i
        elif name.startswith("magADC["):
            ai = int(name[len("magADC["):].rstrip("]"))
            idx.mag_adc[ai] = i
        elif name.startswith("accSmooth["):
            ai = int(name[len("accSmooth["):].rstrip("]"))
            idx.acc_smooth[ai] = i
        elif name.startswith("servo["):
            si = int(name[len("servo["):].rstrip("]"))
            idx.servo[si] = i
        elif name == "vbatLatest":
            idx.vbat_latest = i
        elif name == "amperageLatest":
            idx.amperage_latest = i
        elif name == "BaroAlt":
            idx.baro_alt = i
        elif name == "sonarRaw":
            idx.sonar_raw = i
        elif name == "rssi":
            idx.rssi = i
        elif name == "loopIteration":
            idx.loop_iteration = i
        elif name == "time":
            idx.time = i


def _identify_gps_fields(header: LogHeader, frame_def: FrameDef) -> None:
    idx = header.gps_field_indexes
    for i, name in enumerate(frame_def.field_names):
        if name == "time":
            idx.time = i
        elif name == "GPS_numSat":
            idx.gps_num_sat = i
        elif name == "GPS_altitude":
            idx.gps_altitude = i
        elif name == "GPS_speed":
            idx.gps_speed = i
        elif name == "GPS_ground_course":
            idx.gps_ground_course = i
        elif name.startswith("GPS_coord["):
            ci = int(name[len("GPS_coord["):].rstrip("]"))
            idx.gps_coord[ci] = i


def _identify_gps_home_fields(header: LogHeader, frame_def: FrameDef) -> None:
    idx = header.gps_home_field_indexes
    for i, name in enumerate(frame_def.field_names):
        if name == "GPS_home[0]":
            idx.gps_home[0] = i
        elif name == "GPS_home[1]":
            idx.gps_home[1] = i


def _identify_slow_fields(header: LogHeader, frame_def: FrameDef) -> None:
    idx = header.slow_field_indexes
    for i, name in enumerate(frame_def.field_names):
        if name == "flightModeFlags":
            idx.flight_mode_flags = i
        elif name == "stateFlags":
            idx.state_flags = i
        elif name == "failsafePhase":
            idx.failsafe_phase = i


def _get_or_create_frame_def(header: LogHeader, frame_type: int) -> FrameDef:
    if frame_type not in header.frame_defs:
        header.frame_defs[frame_type] = FrameDef()
    return header.frame_defs[frame_type]


def parse_header_line(header: LogHeader, line: str) -> None:
    """Parse a single header line (without the leading 'H ') into *header*."""
    colon_pos = line.find(":")
    if colon_pos == -1:
        return

    field_name = line[:colon_pos].strip()
    field_value = line[colon_pos + 1:].strip()

    # Store raw header
    header.raw_headers[field_name] = field_value

    if field_name.startswith("Field "):
        # e.g. "Field I name", "Field P predictor", etc.
        frame_char = field_name[len("Field ")]
        frame_type = ord(frame_char)
        frame_def = _get_or_create_frame_def(header, frame_type)

        if field_name.endswith(" name"):
            names = _parse_field_names(field_value)
            frame_def.field_names = names
            frame_def.field_count = len(names)

            # Identify well-known field indexes
            if frame_char == "I":
                _identify_main_fields(header, frame_def)
                # P frames derive from I frames
                p_def = _get_or_create_frame_def(header, ord("P"))
                p_def.field_names = list(frame_def.field_names)
                p_def.field_count = frame_def.field_count
            elif frame_char == "G":
                _identify_gps_fields(header, frame_def)
            elif frame_char == "H":
                _identify_gps_home_fields(header, frame_def)
            elif frame_char == "S":
                _identify_slow_fields(header, frame_def)

        elif field_name.endswith(" signed"):
            ints = _parse_csv_ints(field_value)
            for j, v in enumerate(ints):
                frame_def.field_signed[j] = v
            if frame_char == "I":
                p_def = _get_or_create_frame_def(header, ord("P"))
                for j, v in enumerate(ints):
                    p_def.field_signed[j] = v

        elif field_name.endswith(" predictor"):
            ints = _parse_csv_ints(field_value)
            for j, v in enumerate(ints):
                frame_def.predictor[j] = v

        elif field_name.endswith(" encoding"):
            ints = _parse_csv_ints(field_value)
            for j, v in enumerate(ints):
                frame_def.encoding[j] = v

        elif field_name.endswith(" width"):
            ints = _parse_csv_ints(field_value)
            for j, v in enumerate(ints):
                frame_def.field_width[j] = v

    elif field_name == "I interval":
        header.frame_interval_i = max(1, int(field_value))

    elif field_name == "P interval":
        if "/" in field_value:
            parts = field_value.split("/")
            header.frame_interval_p_num = int(parts[0])
            header.frame_interval_p_denom = int(parts[1])

    elif field_name == "Data version":
        header.data_version = int(field_value)

    elif field_name == "Firmware type":
        if field_value == "Cleanflight":
            header.sys_config.firmware_type = FirmwareType.CLEANFLIGHT
        else:
            header.sys_config.firmware_type = FirmwareType.BASEFLIGHT

    elif field_name == "Firmware revision":
        header.firmware_revision = field_value
        parts = field_value.split(" ")
        if len(parts) >= 2 and parts[0] == "Betaflight":
            header.fc_version = parts[1]
            header.sys_config.firmware_type = FirmwareType.BETAFLIGHT

    elif field_name == "minthrottle":
        header.sys_config.minthrottle = int(field_value)
        header.sys_config.motor_output_low = int(field_value)

    elif field_name == "maxthrottle":
        header.sys_config.maxthrottle = int(field_value)
        header.sys_config.motor_output_high = int(field_value)

    elif field_name == "rcRate":
        header.sys_config.rc_rate = int(field_value)

    elif field_name == "vbatscale":
        header.sys_config.vbatscale = int(field_value)

    elif field_name == "vbatref":
        header.sys_config.vbatref = int(field_value)

    elif field_name == "vbatcellvoltage":
        vals = _parse_csv_ints(field_value)
        if len(vals) >= 3:
            header.sys_config.vbatmincellvoltage = vals[0]
            header.sys_config.vbatwarningcellvoltage = vals[1]
            header.sys_config.vbatmaxcellvoltage = vals[2]

    elif field_name == "currentMeter":
        vals = _parse_csv_ints(field_value)
        if len(vals) >= 2:
            header.sys_config.current_meter_offset = vals[0]
            header.sys_config.current_meter_scale = vals[1]

    elif field_name in ("gyro.scale", "gyro_scale"):
        try:
            raw_uint = int(field_value, 16)
            gyro_scale = struct.unpack("<f", struct.pack("<I", raw_uint))[0]
        except (ValueError, struct.error):
            gyro_scale = 1.0

        if header.sys_config.firmware_type != FirmwareType.BASEFLIGHT:
            gyro_scale = gyro_scale * (math.pi / 180.0) * 0.000001

        header.sys_config.gyro_scale = gyro_scale

    elif field_name == "acc_1G":
        header.sys_config.acc_1g = int(field_value)

    elif field_name == "motorOutput":
        vals = _parse_csv_ints(field_value)
        if len(vals) >= 2:
            header.sys_config.motor_output_low = vals[0]
            header.sys_config.motor_output_high = vals[1]

    elif field_name.startswith("Log start datetime"):
        try:
            header.datetime = datetime.fromisoformat(field_value)
        except (ValueError, TypeError):
            pass


def parse_headers(stream: BinaryStream) -> LogHeader:
    """Read all header lines from the stream at its current position.

    Returns a populated LogHeader. The stream is left positioned at the
    first non-header byte (i.e. the first data frame marker).
    """
    header = LogHeader()

    while not stream.eof:
        c = stream.peek_char()
        if c != ord("H"):
            break

        # Read 'H'
        stream.read_byte()
        # Read ' '
        space = stream.read_byte()
        if space != ord(" "):
            break

        # Read until newline
        line_chars: list[str] = []
        while True:
            ch = stream.read_byte()
            if ch == EOF or ch == ord("\n") or ch == 0:
                break
            line_chars.append(chr(ch))

        line = "".join(line_chars)
        parse_header_line(header, line)

    return header
