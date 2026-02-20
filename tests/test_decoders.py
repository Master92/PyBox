"""Tests for pybox.decoder.decoders – advanced encoding decoders."""

import pytest

from pybox.decoder.stream import BinaryStream
from pybox.decoder.decoders import (
    read_tag2_3s32,
    read_tag8_4s16_v1,
    read_tag8_4s16_v2,
    read_tag8_8svb,
    read_elias_delta_u32,
    read_elias_delta_s32,
    read_elias_gamma_u32,
    read_elias_gamma_s32,
    _to_signed8,
    _to_signed16,
    _to_signed32,
)


class TestSignedHelpers:
    def test_to_signed8(self):
        assert _to_signed8(0) == 0
        assert _to_signed8(127) == 127
        assert _to_signed8(128) == -128
        assert _to_signed8(255) == -1

    def test_to_signed16(self):
        assert _to_signed16(0) == 0
        assert _to_signed16(32767) == 32767
        assert _to_signed16(32768) == -32768
        assert _to_signed16(65535) == -1

    def test_to_signed32(self):
        assert _to_signed32(0) == 0
        assert _to_signed32(0x7FFFFFFF) == 2147483647
        assert _to_signed32(0x80000000) == -2147483648
        assert _to_signed32(0xFFFFFFFF) == -1


class TestTag2_3S32:
    def test_selector_0_2bit_fields(self):
        # selector=0b00, values: 01, 10, 11 -> 1, -2, -1
        # lead byte: 0b00_01_10_11 = 0x1B
        s = BinaryStream(bytes([0x1B]))
        result = read_tag2_3s32(s)
        assert result[0] == 1
        assert result[1] == -2
        assert result[2] == -1

    def test_selector_0_all_zeros(self):
        # lead byte: 0b00_00_00_00 = 0x00
        s = BinaryStream(bytes([0x00]))
        result = read_tag2_3s32(s)
        assert result == [0, 0, 0]

    def test_selector_1_4bit_fields(self):
        # selector=0b01, first value in low 4 bits of lead byte
        # lead=0b01_0011 = 0x43 -> values[0] = sign_extend_4bit(0x3) = 3
        # next byte: 0b0010_0101 = 0x25 -> values[1]=sign_extend_4bit(2)=2, values[2]=sign_extend_4bit(5)=5
        s = BinaryStream(bytes([0x43, 0x25]))
        result = read_tag2_3s32(s)
        assert result[0] == 3
        assert result[1] == 2
        assert result[2] == 5


class TestTag8_4S16:
    def test_v1_all_zeros(self):
        # selector=0x00 -> all FIELD_ZERO
        s = BinaryStream(bytes([0x00]))
        result = read_tag8_4s16_v1(s)
        assert result == [0, 0, 0, 0]

    def test_v2_all_zeros(self):
        s = BinaryStream(bytes([0x00]))
        result = read_tag8_4s16_v2(s)
        assert result == [0, 0, 0, 0]

    def test_v1_8bit_fields(self):
        # selector byte: all 8-bit = 0b10_10_10_10 = 0xAA
        # 4 bytes of 8-bit signed data
        s = BinaryStream(bytes([0xAA, 0x01, 0xFF, 0x80, 0x7F]))
        result = read_tag8_4s16_v1(s)
        assert result[0] == 1
        assert result[1] == -1  # 0xFF signed
        assert result[2] == -128  # 0x80 signed
        assert result[3] == 127  # 0x7F signed


class TestTag8_8SVB:
    def test_single_value(self):
        # value_count=1, read one signed VB
        # zigzag(5) = 10, VB(10) = 0x0A
        s = BinaryStream(bytes([0x0A]))
        result = read_tag8_8svb(s, 1)
        assert result[0] == 5

    def test_multi_value_all_present(self):
        # header=0xFF (all bits set), 8 values, each zigzag(0)=0 -> VB 0x00
        data = bytes([0xFF] + [0x00] * 8)
        s = BinaryStream(data)
        result = read_tag8_8svb(s, 8)
        assert result == [0] * 8

    def test_multi_value_some_present(self):
        # header=0b00000101 -> bit 0 and bit 2 are set
        # value[0] = zigzag(3) = 6, VB=0x06
        # value[2] = zigzag(-2) = 3, VB=0x03
        data = bytes([0x05, 0x06, 0x03])
        s = BinaryStream(data)
        result = read_tag8_8svb(s, 8)
        assert result[0] == 3
        assert result[1] == 0
        assert result[2] == -2
        assert result[3] == 0


class TestEliasDelta:
    def test_u32_value_0(self):
        # Elias Delta of 0+1=1: 1 bit for length=1 (unary 1), 0 bits for length_low, 0 bits for value
        # Binary: 1 -> but actually the encoding of value 0 is just "1" (single 1 bit)
        # Let's test with known encoded bytes
        # Value 0: encoded as binary 1 (the leading 1 bit)
        s = BinaryStream(bytes([0x80]))  # 1000 0000
        result = read_elias_delta_u32(s)
        assert result == 0

    def test_s32_zero(self):
        # zigzag(0) = 0
        s = BinaryStream(bytes([0x80]))
        result = read_elias_delta_s32(s)
        assert result == 0


class TestEliasGamma:
    def test_u32_value_0(self):
        # Elias Gamma for 0+1=1: binary "1", so first bit is 1
        s = BinaryStream(bytes([0x80]))  # 1000 0000
        result = read_elias_gamma_u32(s)
        assert result == 0

    def test_s32_zero(self):
        s = BinaryStream(bytes([0x80]))
        result = read_elias_gamma_s32(s)
        assert result == 0
