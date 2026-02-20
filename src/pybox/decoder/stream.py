"""Bit-level binary stream reader for Blackbox log data.

Mirrors the C implementation in blackbox-tools/src/stream.c.
Operates on a bytes buffer with byte and bit cursors.
"""

from __future__ import annotations

import struct
from typing import Optional

EOF = -1
CHAR_BIT = 8


class BinaryStream:
    """Random-access bit-level reader over an in-memory bytes buffer."""

    __slots__ = ("_data", "_size", "_start", "_end", "_pos", "_bit_pos", "eof")

    def __init__(self, data: bytes, start: int = 0, end: Optional[int] = None) -> None:
        self._data = data
        self._size = len(data)
        self._start = start
        self._end = end if end is not None else self._size
        self._pos = start
        self._bit_pos = CHAR_BIT - 1
        self.eof = False

    # ── properties ────────────────────────────────────────────────────

    @property
    def pos(self) -> int:
        return self._pos

    @pos.setter
    def pos(self, value: int) -> None:
        self._pos = value

    @property
    def start(self) -> int:
        return self._start

    @start.setter
    def start(self, value: int) -> None:
        self._start = value

    @property
    def end(self) -> int:
        return self._end

    @end.setter
    def end(self, value: int) -> None:
        self._end = value

    @property
    def data(self) -> bytes:
        return self._data

    @property
    def size(self) -> int:
        return self._size

    # ── byte-level reads ──────────────────────────────────────────────

    def peek_char(self) -> int:
        """Return the next byte without advancing, or EOF."""
        if self._pos < self._end:
            return self._data[self._pos]
        self.eof = True
        return EOF

    def read_byte(self) -> int:
        """Read one unsigned byte, or return EOF."""
        if self._pos < self._end:
            result = self._data[self._pos]
            self._pos += 1
            return result
        self.eof = True
        return EOF

    def read_char(self) -> int:
        """Read one signed byte, or return EOF."""
        if self._pos < self._end:
            result = self._data[self._pos]
            self._pos += 1
            # interpret as signed
            return result if result < 128 else result - 256
        self.eof = True
        return EOF

    def unread_char(self) -> None:
        """Push back one byte (move cursor back by 1)."""
        if self._pos > self._start:
            self._pos -= 1

    def read(self, length: int) -> bytes:
        """Read *length* bytes from the stream."""
        avail = self._end - self._pos
        if length > avail:
            length = avail
            self.eof = True
        result = self._data[self._pos : self._pos + length]
        self._pos += length
        return result

    # ── bit-level reads ───────────────────────────────────────────────

    def read_bit(self) -> int:
        """Read a single bit (MSB-first within each byte). Returns 0 or 1, or EOF."""
        return self.read_bits(1)

    def read_bits(self, num_bits: int) -> int:
        """Read *num_bits* bits (MSB-first). Returns an unsigned int, or EOF on underflow."""
        # rough byte count needed
        num_bytes = (num_bits + CHAR_BIT - 1) // CHAR_BIT

        if self._pos + num_bytes > self._end:
            self._pos = self._end
            self.eof = True
            self._bit_pos = CHAR_BIT - 1
            return EOF

        result = 0
        while num_bits > 0:
            byte_val = self._data[self._pos]
            result |= ((byte_val >> self._bit_pos) & 0x01) << (num_bits - 1)

            if self._bit_pos == 0:
                self._pos += 1
                self._bit_pos = CHAR_BIT - 1
            else:
                self._bit_pos -= 1
            num_bits -= 1

        return result

    def byte_align(self) -> None:
        """Advance the bit pointer to the next byte boundary."""
        if self._bit_pos != CHAR_BIT - 1:
            self._bit_pos = CHAR_BIT - 1
            self._pos += 1

    # ── variable-byte reads ───────────────────────────────────────────

    def read_unsigned_vb(self) -> int:
        """Read a variable-byte encoded unsigned 32-bit integer."""
        result = 0
        shift = 0

        for _ in range(5):  # max 5 bytes for 32-bit
            c = self.read_byte()
            if c == EOF:
                return 0
            result |= (c & 0x7F) << shift
            if c < 128:
                return result
            shift += 7

        return 0  # VB too long

    def read_signed_vb(self) -> int:
        """Read a variable-byte encoded signed 32-bit integer (zigzag decoded)."""
        return zigzag_decode(self.read_unsigned_vb())

    # ── S16 read ──────────────────────────────────────────────────────

    def read_s16(self) -> int:
        """Read a little-endian signed 16-bit integer."""
        lo = self.read_byte()
        hi = self.read_byte()
        if lo == EOF or hi == EOF:
            return 0
        value = lo | (hi << 8)
        return value if value < 0x8000 else value - 0x10000

    def read_raw_float(self) -> float:
        """Read a 4-byte little-endian IEEE 754 float."""
        raw = self.read(4)
        if len(raw) < 4:
            return 0.0
        return struct.unpack("<f", raw)[0]


# ── utility functions ─────────────────────────────────────────────────

def zigzag_encode(value: int) -> int:
    """ZigZag-encode a signed int32 to unsigned."""
    return ((value << 1) ^ (value >> 31)) & 0xFFFFFFFF


def zigzag_decode(value: int) -> int:
    """ZigZag-decode an unsigned int32 to signed."""
    result = (value >> 1) ^ -(value & 1)
    # ensure 32-bit signed range
    if result > 0x7FFFFFFF:
        result -= 0x100000000
    return result


def sign_extend(value: int, bits: int) -> int:
    """Sign-extend *value* from *bits*-wide to Python int."""
    sign_bit = 1 << (bits - 1)
    mask = (1 << bits) - 1
    value &= mask
    if value & sign_bit:
        value -= 1 << bits
    return value


def sign_extend_2bit(value: int) -> int:
    return sign_extend(value, 2)


def sign_extend_4bit(value: int) -> int:
    return sign_extend(value, 4)


def sign_extend_6bit(value: int) -> int:
    return sign_extend(value, 6)


def sign_extend_14bit(value: int) -> int:
    return sign_extend(value, 14)


def sign_extend_24bit(value: int) -> int:
    return sign_extend(value, 24)
