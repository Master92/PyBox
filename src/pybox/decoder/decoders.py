"""Advanced data-format decoders for Blackbox streams.

Mirrors blackbox-tools/src/decoders.c – Tag2_3S32, Tag8_4S16 (v1/v2),
Tag8_8SVB, Elias Delta/Gamma encodings.
"""

from __future__ import annotations

from pybox.decoder.stream import (
    BinaryStream,
    EOF,
    sign_extend_2bit,
    sign_extend_4bit,
    sign_extend_6bit,
    sign_extend_24bit,
    zigzag_decode,
)


def read_tag2_3s32(stream: BinaryStream) -> list[int]:
    """Decode three signed 32-bit values packed with a 2-bit selector."""
    lead = stream.read_byte()
    if lead == EOF:
        return [0, 0, 0]

    selector = lead >> 6
    values = [0, 0, 0]

    if selector == 0:
        # 2-bit fields
        values[0] = sign_extend_2bit((lead >> 4) & 0x03)
        values[1] = sign_extend_2bit((lead >> 2) & 0x03)
        values[2] = sign_extend_2bit(lead & 0x03)

    elif selector == 1:
        # 4-bit fields
        values[0] = sign_extend_4bit(lead & 0x0F)
        lead = stream.read_byte()
        values[1] = sign_extend_4bit(lead >> 4)
        values[2] = sign_extend_4bit(lead & 0x0F)

    elif selector == 2:
        # 6-bit fields
        values[0] = sign_extend_6bit(lead & 0x3F)
        lead = stream.read_byte()
        values[1] = sign_extend_6bit(lead & 0x3F)
        lead = stream.read_byte()
        values[2] = sign_extend_6bit(lead & 0x3F)

    elif selector == 3:
        # 8/16/24/32-bit fields, with per-field size selector in low 6 bits
        for i in range(3):
            field_size = lead & 0x03
            if field_size == 0:  # 8-bit
                b1 = stream.read_byte()
                values[i] = _to_signed8(b1)
            elif field_size == 1:  # 16-bit
                b1 = stream.read_byte()
                b2 = stream.read_byte()
                values[i] = _to_signed16(b1 | (b2 << 8))
            elif field_size == 2:  # 24-bit
                b1 = stream.read_byte()
                b2 = stream.read_byte()
                b3 = stream.read_byte()
                values[i] = sign_extend_24bit(b1 | (b2 << 8) | (b3 << 16))
            elif field_size == 3:  # 32-bit
                b1 = stream.read_byte()
                b2 = stream.read_byte()
                b3 = stream.read_byte()
                b4 = stream.read_byte()
                values[i] = _to_signed32(b1 | (b2 << 8) | (b3 << 16) | (b4 << 24))
            lead >>= 2

    return values


def read_tag8_4s16_v1(stream: BinaryStream) -> list[int]:
    """Decode four signed 16-bit values (data version < 2)."""
    FIELD_ZERO = 0
    FIELD_4BIT = 1
    FIELD_8BIT = 2
    FIELD_16BIT = 3

    selector = stream.read_byte()
    values = [0, 0, 0, 0]
    i = 0

    while i < 4:
        field_type = selector & 0x03
        if field_type == FIELD_ZERO:
            values[i] = 0
        elif field_type == FIELD_4BIT:
            combined = stream.read_byte()
            values[i] = sign_extend_4bit(combined & 0x0F)
            i += 1
            selector >>= 2
            if i < 4:
                values[i] = sign_extend_4bit(combined >> 4)
        elif field_type == FIELD_8BIT:
            values[i] = _to_signed8(stream.read_byte())
        elif field_type == FIELD_16BIT:
            c1 = stream.read_byte()
            c2 = stream.read_byte()
            values[i] = _to_signed16(c1 | (c2 << 8))

        selector >>= 2
        i += 1

    return values


def read_tag8_4s16_v2(stream: BinaryStream) -> list[int]:
    """Decode four signed 16-bit values (data version >= 2)."""
    FIELD_ZERO = 0
    FIELD_4BIT = 1
    FIELD_8BIT = 2
    FIELD_16BIT = 3

    selector = stream.read_byte()
    values = [0, 0, 0, 0]
    nibble_index = 0
    buffer = 0

    for i in range(4):
        field_type = selector & 0x03
        if field_type == FIELD_ZERO:
            values[i] = 0
        elif field_type == FIELD_4BIT:
            if nibble_index == 0:
                buffer = stream.read_byte()
                values[i] = sign_extend_4bit(buffer >> 4)
                nibble_index = 1
            else:
                values[i] = sign_extend_4bit(buffer & 0x0F)
                nibble_index = 0
        elif field_type == FIELD_8BIT:
            if nibble_index == 0:
                values[i] = _to_signed8(stream.read_byte())
            else:
                c1 = (buffer << 4) & 0xFF
                buffer = stream.read_byte()
                c1 |= buffer >> 4
                values[i] = _to_signed8(c1)
        elif field_type == FIELD_16BIT:
            if nibble_index == 0:
                c1 = stream.read_byte()
                c2 = stream.read_byte()
                values[i] = _to_signed16((c1 << 8) | c2)
            else:
                c1 = stream.read_byte()
                c2 = stream.read_byte()
                values[i] = _to_signed16(
                    ((buffer & 0x0F) << 12) | (c1 << 4) | (c2 >> 4)
                )
                buffer = c2

        selector >>= 2

    return values


def read_tag8_8svb(stream: BinaryStream, value_count: int) -> list[int]:
    """Decode up to 8 signed VB values with a presence header byte."""
    values = [0] * 8

    if value_count == 1:
        values[0] = stream.read_signed_vb()
    else:
        header = stream.read_byte()
        for i in range(8):
            if header & 0x01:
                values[i] = stream.read_signed_vb()
            else:
                values[i] = 0
            header >>= 1

    return values


def read_elias_delta_u32(stream: BinaryStream) -> int:
    """Read an Elias-Delta encoded unsigned 32-bit integer."""
    MAX_BIT_READ = 32
    length_val_bits = 0

    while length_val_bits <= MAX_BIT_READ:
        bit = stream.read_bit()
        if bit == EOF:
            return 0
        if bit != 0:
            break
        length_val_bits += 1

    if stream.eof or length_val_bits > MAX_BIT_READ:
        return 0

    length_low_bits = stream.read_bits(length_val_bits) if length_val_bits > 0 else 0
    if stream.eof:
        return 0

    length = ((1 << length_val_bits) | length_low_bits) - 1
    if length > MAX_BIT_READ:
        return 0

    result_low_bits = stream.read_bits(length) if length > 0 else 0
    if stream.eof:
        return 0

    result = (1 << length) | result_low_bits

    if result == 0xFFFFFFFF:
        escape = stream.read_bit()
        if escape == 0:
            return 0xFFFFFFFE
        elif escape == 1:
            return 0xFFFFFFFF
        else:
            return 0

    return result - 1


def read_elias_delta_s32(stream: BinaryStream) -> int:
    """Read an Elias-Delta encoded signed 32-bit integer."""
    return zigzag_decode(read_elias_delta_u32(stream))


def read_elias_gamma_u32(stream: BinaryStream) -> int:
    """Read an Elias-Gamma encoded unsigned 32-bit integer."""
    MAX_BIT_READ = 32
    val_bits = 0

    while val_bits <= MAX_BIT_READ:
        bit = stream.read_bit()
        if bit == EOF:
            return 0
        if bit != 0:
            break
        val_bits += 1

    if stream.eof or val_bits > MAX_BIT_READ:
        return 0

    value_low_bits = stream.read_bits(val_bits - 1) if val_bits > 1 else 0
    if stream.eof and val_bits > 1:
        return 0

    result = (1 << (val_bits - 1)) | value_low_bits if val_bits > 0 else 1

    if result == 0xFFFFFFFF:
        escape = stream.read_bit()
        if escape == 0:
            return 0xFFFFFFFE
        elif escape == 1:
            return 0xFFFFFFFF
        else:
            return 0

    return result - 1


def read_elias_gamma_s32(stream: BinaryStream) -> int:
    """Read an Elias-Gamma encoded signed 32-bit integer."""
    return zigzag_decode(read_elias_gamma_u32(stream))


# ── helpers ───────────────────────────────────────────────────────────

def _to_signed8(v: int) -> int:
    v &= 0xFF
    return v if v < 0x80 else v - 0x100


def _to_signed16(v: int) -> int:
    v &= 0xFFFF
    return v if v < 0x8000 else v - 0x10000


def _to_signed32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v if v < 0x80000000 else v - 0x100000000
