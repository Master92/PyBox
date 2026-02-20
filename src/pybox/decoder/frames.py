"""Blackbox frame parser – I, P, G, H, S, E frames.

Mirrors the core parsing loop from blackbox-tools/src/parser.c.
Handles field prediction, encoding dispatch, history ring buffer rotation,
and frame validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from pybox.decoder.defs import (
    FLIGHT_LOG_FIELD_INDEX_ITERATION,
    FLIGHT_LOG_FIELD_INDEX_TIME,
    FLIGHT_LOG_MAX_FIELDS,
    MAXIMUM_ITERATION_JUMP_BETWEEN_FRAMES,
    MAXIMUM_TIME_JUMP_BETWEEN_FRAMES,
    FieldEncoding,
    FieldPredictor,
    FlightLogEvent,
)
from pybox.decoder.decoders import (
    read_elias_delta_s32,
    read_elias_delta_u32,
    read_elias_gamma_s32,
    read_elias_gamma_u32,
    read_tag2_3s32,
    read_tag8_4s16_v1,
    read_tag8_4s16_v2,
    read_tag8_8svb,
)
from pybox.decoder.headers import LogHeader
from pybox.decoder.stream import BinaryStream, EOF, sign_extend_14bit


# ── event data ────────────────────────────────────────────────────────

@dataclass
class EventData:
    event_type: int = -1
    # sync beep
    sync_beep_time: int = 0
    # inflight adjustment
    adjustment_function: int = 0
    new_value: int = 0
    new_float_value: float = 0.0
    # logging resume
    log_iteration: int = 0
    current_time: int = 0


# ── callbacks ─────────────────────────────────────────────────────────

FrameReadyCallback = Callable[[bool, list[int], int, int], None]
EventReadyCallback = Callable[[EventData], None]


# ── frame parser state ────────────────────────────────────────────────

class FrameParser:
    """Stateful parser that decodes data frames from a binary stream.

    The parser maintains a history ring buffer (3 slots) for the main
    (I/P) frames, plus last-known state for GPS, GPS Home, Slow, and
    Event frames.
    """

    def __init__(self, header: LogHeader) -> None:
        self.header = header

        # History ring: 3 frame buffers of FLIGHT_LOG_MAX_FIELDS each
        self._ring = [[0] * FLIGHT_LOG_MAX_FIELDS for _ in range(3)]
        # main_history[0] = current, [1] = previous, [2] = previous-previous
        self.main_history: list[Optional[list[int]]] = [self._ring[0], None, None]
        self.main_stream_valid = False

        # GPS / Slow / Event state
        self.last_gps = [0] * FLIGHT_LOG_MAX_FIELDS
        self.gps_home_history = [[0] * FLIGHT_LOG_MAX_FIELDS, [0] * FLIGHT_LOG_MAX_FIELDS]
        self.gps_home_valid = False
        self.last_slow = [0] * FLIGHT_LOG_MAX_FIELDS
        self.last_event = EventData()

        # Time tracking
        self.time_rollover_accumulator = 0
        self.last_main_frame_iteration: int = -1  # use -1 as sentinel (like (uint32_t)-1)
        self.last_main_frame_time: int = -1
        self.last_skipped_frames = 0

        # Ring rotation index
        self._ring_idx = 0

    def reset(self) -> None:
        """Reset all parser state for a fresh log parse."""
        for buf in self._ring:
            for i in range(len(buf)):
                buf[i] = 0

        self.main_history = [self._ring[0], None, None]
        self.main_stream_valid = False
        self._ring_idx = 0

        self.last_gps = [0] * FLIGHT_LOG_MAX_FIELDS
        self.gps_home_history = [[0] * FLIGHT_LOG_MAX_FIELDS, [0] * FLIGHT_LOG_MAX_FIELDS]
        self.gps_home_valid = False
        self.last_slow = [0] * FLIGHT_LOG_MAX_FIELDS
        self.last_event = EventData()

        self.time_rollover_accumulator = 0
        self.last_main_frame_iteration = -1
        self.last_main_frame_time = -1
        self.last_skipped_frames = 0

    # ── prediction ────────────────────────────────────────────────────

    def _apply_prediction(
        self,
        field_index: int,
        predictor: int,
        value: int,
        current: list[int],
        previous: Optional[list[int]],
        previous2: Optional[list[int]],
    ) -> int:
        h = self.header

        if predictor == FieldPredictor.ZERO:
            pass
        elif predictor == FieldPredictor.MINTHROTTLE:
            value += h.sys_config.minthrottle
        elif predictor == FieldPredictor.FIFTEEN_HUNDRED:
            value += 1500
        elif predictor == FieldPredictor.MOTOR_0:
            motor0_idx = h.main_field_indexes.motor[0]
            if motor0_idx >= 0:
                value += current[motor0_idx]
        elif predictor == FieldPredictor.VBATREF:
            value += h.sys_config.vbatref
        elif predictor == FieldPredictor.MINMOTOR:
            value += h.sys_config.motor_output_low
        elif predictor == FieldPredictor.PREVIOUS:
            if previous is not None:
                value += previous[field_index]
        elif predictor == FieldPredictor.STRAIGHT_LINE:
            if previous is not None and previous2 is not None:
                value += 2 * previous[field_index] - previous2[field_index]
        elif predictor == FieldPredictor.AVERAGE_2:
            if previous is not None and previous2 is not None:
                value += (previous[field_index] + previous2[field_index]) // 2
        elif predictor == FieldPredictor.HOME_COORD:
            gps_home_idx = h.gps_home_field_indexes.gps_home[0]
            if gps_home_idx >= 0:
                value += self.gps_home_history[1][gps_home_idx]
        elif predictor == FieldPredictor.HOME_COORD_1:
            gps_home_idx = h.gps_home_field_indexes.gps_home[1]
            if gps_home_idx >= 0:
                value += self.gps_home_history[1][gps_home_idx]
        elif predictor == FieldPredictor.LAST_MAIN_FRAME_TIME:
            if self.main_history[1] is not None:
                value += self.main_history[1][FLIGHT_LOG_FIELD_INDEX_TIME]

        return value

    # ── generic frame decode ──────────────────────────────────────────

    def _parse_frame(
        self,
        stream: BinaryStream,
        frame_type: int,
        frame: list[int],
        previous: Optional[list[int]],
        previous2: Optional[list[int]],
        skipped_frames: int,
        raw: bool,
    ) -> None:
        frame_def = self.header.frame_defs.get(frame_type)
        if frame_def is None:
            return

        predictor = frame_def.predictor
        encoding = frame_def.encoding
        field_signed = frame_def.field_signed
        field_width = frame_def.field_width
        field_count = frame_def.field_count

        i = 0
        while i < field_count:
            if predictor[i] == FieldPredictor.INC:
                frame[i] = skipped_frames + 1
                if previous is not None:
                    frame[i] += previous[i]
                i += 1
                continue

            enc = encoding[i]
            pred = FieldPredictor.ZERO if raw else predictor[i]

            if enc == FieldEncoding.SIGNED_VB:
                stream.byte_align()
                value = stream.read_signed_vb()
                frame[i] = self._apply_prediction(i, pred, value, frame, previous, previous2)
                if field_width[i] != 8:
                    frame[i] = _truncate(frame[i], field_signed[i])
                i += 1

            elif enc == FieldEncoding.UNSIGNED_VB:
                stream.byte_align()
                value = stream.read_unsigned_vb()
                frame[i] = self._apply_prediction(i, pred, value, frame, previous, previous2)
                if field_width[i] != 8:
                    frame[i] = _truncate(frame[i], field_signed[i])
                i += 1

            elif enc == FieldEncoding.NEG_14BIT:
                stream.byte_align()
                value = -sign_extend_14bit(stream.read_unsigned_vb())
                frame[i] = self._apply_prediction(i, pred, value, frame, previous, previous2)
                if field_width[i] != 8:
                    frame[i] = _truncate(frame[i], field_signed[i])
                i += 1

            elif enc == FieldEncoding.TAG8_4S16:
                stream.byte_align()
                if self.header.data_version < 2:
                    values = read_tag8_4s16_v1(stream)
                else:
                    values = read_tag8_4s16_v2(stream)
                for j in range(4):
                    if i < field_count:
                        p = FieldPredictor.ZERO if raw else predictor[i]
                        frame[i] = self._apply_prediction(i, p, values[j], frame, previous, previous2)
                        i += 1

            elif enc == FieldEncoding.TAG2_3S32:
                stream.byte_align()
                values = read_tag2_3s32(stream)
                for j in range(3):
                    if i < field_count:
                        p = FieldPredictor.ZERO if raw else predictor[i]
                        frame[i] = self._apply_prediction(i, p, values[j], frame, previous, previous2)
                        i += 1

            elif enc == FieldEncoding.TAG8_8SVB:
                stream.byte_align()
                # Count consecutive TAG8_8SVB fields
                group_count = 1
                for j in range(i + 1, min(i + 8, field_count)):
                    if encoding[j] != FieldEncoding.TAG8_8SVB:
                        break
                    group_count += 1
                values = read_tag8_8svb(stream, group_count)
                for j in range(group_count):
                    if i < field_count:
                        p = FieldPredictor.ZERO if raw else predictor[i]
                        frame[i] = self._apply_prediction(i, p, values[j], frame, previous, previous2)
                        i += 1

            elif enc == FieldEncoding.ELIAS_DELTA_U32:
                value = read_elias_delta_u32(stream)
                frame[i] = self._apply_prediction(i, pred, value, frame, previous, previous2)
                if field_width[i] != 8:
                    frame[i] = _truncate(frame[i], field_signed[i])
                i += 1

            elif enc == FieldEncoding.ELIAS_DELTA_S32:
                value = read_elias_delta_s32(stream)
                frame[i] = self._apply_prediction(i, pred, value, frame, previous, previous2)
                if field_width[i] != 8:
                    frame[i] = _truncate(frame[i], field_signed[i])
                i += 1

            elif enc == FieldEncoding.ELIAS_GAMMA_U32:
                value = read_elias_gamma_u32(stream)
                frame[i] = self._apply_prediction(i, pred, value, frame, previous, previous2)
                if field_width[i] != 8:
                    frame[i] = _truncate(frame[i], field_signed[i])
                i += 1

            elif enc == FieldEncoding.ELIAS_GAMMA_S32:
                value = read_elias_gamma_s32(stream)
                frame[i] = self._apply_prediction(i, pred, value, frame, previous, previous2)
                if field_width[i] != 8:
                    frame[i] = _truncate(frame[i], field_signed[i])
                i += 1

            elif enc == FieldEncoding.NULL:
                value = 0
                frame[i] = self._apply_prediction(i, pred, value, frame, previous, previous2)
                i += 1

            else:
                # Unknown encoding – skip field
                i += 1

        stream.byte_align()

    # ── frame-type specific parsers ───────────────────────────────────

    def _count_skipped_frames(self) -> int:
        """Count intentionally skipped frames based on sampling rate."""
        if self.last_main_frame_iteration == -1:
            return 0
        h = self.header
        count = 0
        frame_index = self.last_main_frame_iteration + 1
        while not _should_have_frame(h, frame_index):
            count += 1
            frame_index += 1
            if count > 10000:  # safety
                break
        return count

    def _count_skipped_frames_to(self, target_iteration: int) -> int:
        if self.last_main_frame_iteration == -1:
            return 0
        h = self.header
        count = 0
        for fi in range(self.last_main_frame_iteration + 1, target_iteration):
            if not _should_have_frame(h, fi):
                count += 1
        return count

    def _detect_time_rollover(self, timestamp: int) -> int:
        """Detect 32-bit time rollover and return 64-bit timestamp."""
        if self.last_main_frame_time != -1:
            ts32 = timestamp & 0xFFFFFFFF
            last32 = self.last_main_frame_time & 0xFFFFFFFF
            if ts32 < last32 and ((ts32 - last32) & 0xFFFFFFFF) < MAXIMUM_TIME_JUMP_BETWEEN_FRAMES:
                self.time_rollover_accumulator += 0x100000000

        return (timestamp & 0xFFFFFFFF) + self.time_rollover_accumulator

    def _validate_main_frame(self) -> bool:
        """Check that iteration/time didn't jump unreasonably."""
        current = self.main_history[0]
        if current is None:
            return False
        iteration = current[FLIGHT_LOG_FIELD_INDEX_ITERATION] & 0xFFFFFFFF
        time_val = current[FLIGHT_LOG_FIELD_INDEX_TIME]

        if self.last_main_frame_iteration == -1:
            return True

        last_iter = self.last_main_frame_iteration & 0xFFFFFFFF
        return (
            iteration >= last_iter
            and iteration < last_iter + MAXIMUM_ITERATION_JUMP_BETWEEN_FRAMES
            and time_val >= self.last_main_frame_time
            and time_val < self.last_main_frame_time + MAXIMUM_TIME_JUMP_BETWEEN_FRAMES
        )

    def _invalidate_stream(self) -> None:
        self.main_stream_valid = False
        self.main_history[1] = None
        self.main_history[2] = None

    def _rotate_history(self, is_intraframe: bool) -> None:
        """Rotate the history ring buffer after a successful frame."""
        if is_intraframe:
            self.main_history[1] = self.main_history[0]
            self.main_history[2] = self.main_history[0]
        else:
            self.main_history[2] = self.main_history[1]
            self.main_history[1] = self.main_history[0]

        # Advance to next ring slot
        self._ring_idx = (self._ring_idx + 1) % 3
        self.main_history[0] = self._ring[self._ring_idx]

    def parse_intraframe(self, stream: BinaryStream, raw: bool = False) -> bool:
        """Parse an I-frame. Returns True if the frame was valid."""
        current = self.main_history[0]
        previous = self.main_history[1]
        self._parse_frame(stream, ord("I"), current, previous, None, 0, raw)

        # Apply time rollover
        current[FLIGHT_LOG_FIELD_INDEX_TIME] = self._detect_time_rollover(
            current[FLIGHT_LOG_FIELD_INDEX_TIME]
        )

        if not raw and self.last_main_frame_iteration != -1 and not self._validate_main_frame():
            self._invalidate_stream()
        else:
            self.main_stream_valid = True

        if self.main_stream_valid:
            self.last_main_frame_iteration = current[FLIGHT_LOG_FIELD_INDEX_ITERATION] & 0xFFFFFFFF
            self.last_main_frame_time = current[FLIGHT_LOG_FIELD_INDEX_TIME]
            self._rotate_history(is_intraframe=True)

        return self.main_stream_valid

    def parse_interframe(self, stream: BinaryStream, raw: bool = False) -> bool:
        """Parse a P-frame. Returns True if the frame was valid."""
        current = self.main_history[0]
        previous = self.main_history[1]
        previous2 = self.main_history[2]

        self.last_skipped_frames = self._count_skipped_frames()
        self._parse_frame(stream, ord("P"), current, previous, previous2, self.last_skipped_frames, raw)

        current[FLIGHT_LOG_FIELD_INDEX_TIME] = self._detect_time_rollover(
            current[FLIGHT_LOG_FIELD_INDEX_TIME]
        )

        if self.main_stream_valid and not raw and not self._validate_main_frame():
            self._invalidate_stream()

        if self.main_stream_valid:
            self.last_main_frame_iteration = current[FLIGHT_LOG_FIELD_INDEX_ITERATION] & 0xFFFFFFFF
            self.last_main_frame_time = current[FLIGHT_LOG_FIELD_INDEX_TIME]
            self._rotate_history(is_intraframe=False)

        return self.main_stream_valid

    def parse_gps_frame(self, stream: BinaryStream, raw: bool = False) -> None:
        self._parse_frame(stream, ord("G"), self.last_gps, None, None, 0, raw)
        # Apply GPS time rollover
        time_idx = self.header.gps_field_indexes.time
        if time_idx >= 0:
            self.last_gps[time_idx] = self._detect_time_rollover(self.last_gps[time_idx])

    def parse_gps_home_frame(self, stream: BinaryStream, raw: bool = False) -> None:
        self._parse_frame(stream, ord("H"), self.gps_home_history[0], None, None, 0, raw)
        # Publish: copy slot 0 → slot 1
        self.gps_home_history[1] = list(self.gps_home_history[0])
        self.gps_home_valid = True

    def parse_slow_frame(self, stream: BinaryStream, raw: bool = False) -> None:
        self._parse_frame(stream, ord("S"), self.last_slow, None, None, 0, raw)

    def parse_event_frame(self, stream: BinaryStream) -> EventData:
        """Parse an event frame. Returns the decoded event."""
        event_type = stream.read_byte()
        event = EventData(event_type=event_type)

        if event_type == FlightLogEvent.SYNC_BEEP:
            event.sync_beep_time = stream.read_unsigned_vb() + self.time_rollover_accumulator

        elif event_type == FlightLogEvent.INFLIGHT_ADJUSTMENT:
            event.adjustment_function = stream.read_byte()
            if event.adjustment_function > 127:
                event.new_float_value = stream.read_raw_float()
            else:
                event.new_value = stream.read_signed_vb()

        elif event_type == FlightLogEvent.LOGGING_RESUME:
            event.log_iteration = stream.read_unsigned_vb()
            event.current_time = stream.read_unsigned_vb() + self.time_rollover_accumulator
            # Update tracking so we accept the jump
            self.last_main_frame_iteration = event.log_iteration
            self.last_main_frame_time = event.current_time

        elif event_type == FlightLogEvent.LOG_END:
            end_msg = stream.read(11)
            if end_msg == b"End of log\x00":
                # Signal end of log by setting stream end
                stream.end = stream.pos
            else:
                event.event_type = -1

        else:
            event.event_type = -1

        self.last_event = event
        return event


# ── helpers ───────────────────────────────────────────────────────────

def _should_have_frame(header: LogHeader, frame_index: int) -> bool:
    return (
        (frame_index % header.frame_interval_i + header.frame_interval_p_num - 1)
        % header.frame_interval_p_denom
        < header.frame_interval_p_num
    )


def _truncate(value: int, signed: int) -> int:
    """Truncate to 32-bit signed or unsigned."""
    if signed:
        value &= 0xFFFFFFFF
        if value >= 0x80000000:
            value -= 0x100000000
    else:
        value &= 0xFFFFFFFF
    return value
