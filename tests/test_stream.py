"""Tests for pybox.decoder.stream – binary stream reader."""

import pytest

from pybox.decoder.stream import (
    BinaryStream,
    EOF,
    zigzag_decode,
    zigzag_encode,
    sign_extend,
    sign_extend_2bit,
    sign_extend_4bit,
    sign_extend_6bit,
    sign_extend_14bit,
    sign_extend_24bit,
)


class TestZigZag:
    def test_encode_zero(self):
        assert zigzag_encode(0) == 0

    def test_encode_positive(self):
        assert zigzag_encode(1) == 2
        assert zigzag_encode(2) == 4

    def test_encode_negative(self):
        assert zigzag_encode(-1) == 1
        assert zigzag_encode(-2) == 3

    def test_decode_zero(self):
        assert zigzag_decode(0) == 0

    def test_decode_roundtrip(self):
        for v in [-1000, -1, 0, 1, 1000, 2**30]:
            assert zigzag_decode(zigzag_encode(v)) == v


class TestSignExtend:
    def test_2bit(self):
        assert sign_extend_2bit(0b00) == 0
        assert sign_extend_2bit(0b01) == 1
        assert sign_extend_2bit(0b10) == -2
        assert sign_extend_2bit(0b11) == -1

    def test_4bit(self):
        assert sign_extend_4bit(0b0111) == 7
        assert sign_extend_4bit(0b1000) == -8
        assert sign_extend_4bit(0b1111) == -1

    def test_6bit(self):
        assert sign_extend_6bit(0b011111) == 31
        assert sign_extend_6bit(0b100000) == -32

    def test_14bit(self):
        assert sign_extend_14bit(0) == 0
        assert sign_extend_14bit(0x1FFF) == 8191
        assert sign_extend_14bit(0x2000) == -8192

    def test_24bit(self):
        assert sign_extend_24bit(0) == 0
        assert sign_extend_24bit(0x7FFFFF) == 8388607
        assert sign_extend_24bit(0x800000) == -8388608

    def test_generic(self):
        assert sign_extend(0b10, 2) == -2
        assert sign_extend(0b01, 2) == 1


class TestBinaryStream:
    def test_read_byte(self):
        s = BinaryStream(bytes([0x42, 0xFF, 0x00]))
        assert s.read_byte() == 0x42
        assert s.read_byte() == 0xFF
        assert s.read_byte() == 0x00
        assert s.read_byte() == EOF
        assert s.eof is True

    def test_peek_char(self):
        s = BinaryStream(bytes([0x48]))
        assert s.peek_char() == 0x48
        assert s.pos == 0  # didn't advance
        s.read_byte()
        assert s.peek_char() == EOF

    def test_unread_char(self):
        s = BinaryStream(bytes([0x01, 0x02]))
        s.read_byte()
        s.unread_char()
        assert s.read_byte() == 0x01

    def test_read_bytes(self):
        s = BinaryStream(b"Hello")
        assert s.read(3) == b"Hel"
        assert s.read(10) == b"lo"  # reads only what's available
        assert s.eof is True

    def test_read_bit(self):
        # 0b10110000 = 0xB0
        s = BinaryStream(bytes([0xB0]))
        assert s.read_bit() == 1  # bit 7
        assert s.read_bit() == 0  # bit 6
        assert s.read_bit() == 1  # bit 5
        assert s.read_bit() == 1  # bit 4
        assert s.read_bit() == 0  # bit 3
        assert s.read_bit() == 0  # bit 2
        assert s.read_bit() == 0  # bit 1
        assert s.read_bit() == 0  # bit 0

    def test_read_bits(self):
        # 0b11001010 = 0xCA
        s = BinaryStream(bytes([0xCA]))
        assert s.read_bits(4) == 0b1100  # top 4 bits
        assert s.read_bits(4) == 0b1010  # bottom 4 bits

    def test_byte_align(self):
        s = BinaryStream(bytes([0xFF, 0x42]))
        s.read_bit()  # read 1 bit
        s.byte_align()  # skip remaining 7 bits
        assert s.read_byte() == 0x42

    def test_read_unsigned_vb_single_byte(self):
        # Value 0 -> byte 0x00
        s = BinaryStream(bytes([0x00]))
        assert s.read_unsigned_vb() == 0

    def test_read_unsigned_vb_multi_byte(self):
        # Value 300: 300 = 0b100101100
        # VB: 0b10101100, 0b00000010 -> 0xAC, 0x02
        s = BinaryStream(bytes([0xAC, 0x02]))
        assert s.read_unsigned_vb() == 300

    def test_read_signed_vb(self):
        # zigzag(1) = 2, VB(2) = 0x02
        s = BinaryStream(bytes([0x02]))
        assert s.read_signed_vb() == 1

        # zigzag(-1) = 1, VB(1) = 0x01
        s = BinaryStream(bytes([0x01]))
        assert s.read_signed_vb() == -1

    def test_read_s16(self):
        # Little-endian: 0x0100 = 256
        s = BinaryStream(bytes([0x00, 0x01]))
        assert s.read_s16() == 256

        # 0xFFFF = -1 (signed)
        s = BinaryStream(bytes([0xFF, 0xFF]))
        assert s.read_s16() == -1

    def test_read_raw_float(self):
        import struct
        val = 3.14
        data = struct.pack("<f", val)
        s = BinaryStream(data)
        result = s.read_raw_float()
        assert abs(result - val) < 0.001

    def test_subrange(self):
        data = b"XXXHelloXXX"
        s = BinaryStream(data, start=3, end=8)
        assert s.read(5) == b"Hello"
        assert s.read_byte() == EOF
