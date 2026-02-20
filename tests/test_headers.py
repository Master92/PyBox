"""Tests for pybox.decoder.headers – header line parsing."""

import pytest

from pybox.decoder.headers import (
    LogHeader,
    parse_header_line,
    parse_headers,
    FrameDef,
)
from pybox.decoder.defs import FirmwareType
from pybox.decoder.stream import BinaryStream


class TestParseHeaderLine:
    def test_field_i_name(self):
        header = LogHeader()
        parse_header_line(header, "Field I name:loopIteration,time,axisP[0],axisP[1],axisP[2]")
        frame_def = header.frame_defs[ord("I")]
        assert frame_def.field_count == 5
        assert frame_def.field_names[0] == "loopIteration"
        assert frame_def.field_names[1] == "time"
        assert header.main_field_indexes.loop_iteration == 0
        assert header.main_field_indexes.time == 1
        assert header.main_field_indexes.pid[0][0] == 2  # axisP[0]

    def test_field_i_signed(self):
        header = LogHeader()
        parse_header_line(header, "Field I name:a,b,c")
        parse_header_line(header, "Field I signed:0,1,0")
        frame_def = header.frame_defs[ord("I")]
        assert frame_def.field_signed[0] == 0
        assert frame_def.field_signed[1] == 1
        assert frame_def.field_signed[2] == 0

    def test_field_i_predictor(self):
        header = LogHeader()
        parse_header_line(header, "Field I predictor:0,0,6")
        frame_def = header.frame_defs[ord("I")]
        assert frame_def.predictor[2] == 6

    def test_field_i_encoding(self):
        header = LogHeader()
        parse_header_line(header, "Field I encoding:1,1,0")
        frame_def = header.frame_defs[ord("I")]
        assert frame_def.encoding[0] == 1

    def test_p_frame_inherits_from_i(self):
        header = LogHeader()
        parse_header_line(header, "Field I name:loopIteration,time")
        parse_header_line(header, "Field I signed:0,0")
        p_def = header.frame_defs[ord("P")]
        assert p_def.field_count == 2
        assert p_def.field_names[0] == "loopIteration"
        assert p_def.field_signed[0] == 0

    def test_sys_config_minthrottle(self):
        header = LogHeader()
        parse_header_line(header, "minthrottle:1070")
        assert header.sys_config.minthrottle == 1070
        assert header.sys_config.motor_output_low == 1070

    def test_sys_config_maxthrottle(self):
        header = LogHeader()
        parse_header_line(header, "maxthrottle:1860")
        assert header.sys_config.maxthrottle == 1860

    def test_firmware_betaflight(self):
        header = LogHeader()
        parse_header_line(header, "Firmware revision:Betaflight 4.3.1")
        assert header.sys_config.firmware_type == FirmwareType.BETAFLIGHT
        assert header.fc_version == "4.3.1"

    def test_firmware_cleanflight(self):
        header = LogHeader()
        parse_header_line(header, "Firmware type:Cleanflight")
        assert header.sys_config.firmware_type == FirmwareType.CLEANFLIGHT

    def test_i_interval(self):
        header = LogHeader()
        parse_header_line(header, "I interval:32")
        assert header.frame_interval_i == 32

    def test_p_interval(self):
        header = LogHeader()
        parse_header_line(header, "P interval:1/2")
        assert header.frame_interval_p_num == 1
        assert header.frame_interval_p_denom == 2

    def test_data_version(self):
        header = LogHeader()
        parse_header_line(header, "Data version:2")
        assert header.data_version == 2

    def test_vbatcellvoltage(self):
        header = LogHeader()
        parse_header_line(header, "vbatcellvoltage:33,35,43")
        assert header.sys_config.vbatmincellvoltage == 33
        assert header.sys_config.vbatwarningcellvoltage == 35
        assert header.sys_config.vbatmaxcellvoltage == 43

    def test_motor_output(self):
        header = LogHeader()
        parse_header_line(header, "motorOutput:0,2047")
        assert header.sys_config.motor_output_low == 0
        assert header.sys_config.motor_output_high == 2047

    def test_motor_fields(self):
        header = LogHeader()
        parse_header_line(header, "Field I name:loopIteration,time,motor[0],motor[1],motor[2],motor[3]")
        idx = header.main_field_indexes
        assert idx.motor[0] == 2
        assert idx.motor[1] == 3
        assert idx.motor[2] == 4
        assert idx.motor[3] == 5

    def test_gyro_fields(self):
        header = LogHeader()
        parse_header_line(header, "Field I name:loopIteration,time,gyroADC[0],gyroADC[1],gyroADC[2]")
        idx = header.main_field_indexes
        assert idx.gyro_adc[0] == 2
        assert idx.gyro_adc[1] == 3
        assert idx.gyro_adc[2] == 4

    def test_rc_command_fields(self):
        header = LogHeader()
        parse_header_line(header, "Field I name:loopIteration,time,rcCommand[0],rcCommand[1],rcCommand[2],rcCommand[3]")
        idx = header.main_field_indexes
        assert idx.rc_command[0] == 2
        assert idx.rc_command[3] == 5

    def test_raw_headers_stored(self):
        header = LogHeader()
        parse_header_line(header, "debug_mode:0")
        assert header.raw_headers["debug_mode"] == "0"

    def test_gps_fields(self):
        header = LogHeader()
        parse_header_line(header, "Field G name:time,GPS_numSat,GPS_coord[0],GPS_coord[1],GPS_altitude,GPS_speed,GPS_ground_course")
        idx = header.gps_field_indexes
        assert idx.time == 0
        assert idx.gps_num_sat == 1
        assert idx.gps_coord[0] == 2
        assert idx.gps_coord[1] == 3

    def test_slow_fields(self):
        header = LogHeader()
        parse_header_line(header, "Field S name:flightModeFlags,stateFlags,failsafePhase")
        idx = header.slow_field_indexes
        assert idx.flight_mode_flags == 0
        assert idx.state_flags == 1
        assert idx.failsafe_phase == 2


class TestParseHeaders:
    def test_parse_from_stream(self):
        lines = [
            b"H Product:Blackbox flight data recorder by Nicholas Sherlock\n",
            b"H Data version:2\n",
            b"H Field I name:loopIteration,time\n",
            b"H Field I signed:0,0\n",
            b"H Field I predictor:0,0\n",
            b"H Field I encoding:1,1\n",
            b"H minthrottle:1070\n",
        ]
        data = b"".join(lines) + b"I"  # I-frame marker follows headers
        stream = BinaryStream(data)
        header = parse_headers(stream)

        assert header.data_version == 2
        assert header.sys_config.minthrottle == 1070
        i_def = header.frame_defs[ord("I")]
        assert i_def.field_count == 2
        assert i_def.field_names[0] == "loopIteration"
        # Stream should now be positioned at the 'I' marker
        assert stream.peek_char() == ord("I")
