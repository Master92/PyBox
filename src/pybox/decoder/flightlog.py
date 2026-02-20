"""High-level API for loading and decoding Blackbox flight logs.

Usage:
    from pybox.decoder import FlightLog

    log = FlightLog("path/to/log.bbl")
    print(f"Found {log.log_count} logs in file")

    df = log.to_dataframe(log_index=0)
    print(df.head())
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

from pybox.decoder.defs import (
    FLIGHT_LOG_FIELD_INDEX_ITERATION,
    FLIGHT_LOG_FIELD_INDEX_TIME,
    LOG_START_MARKER,
    FieldPredictor,
)
from pybox.decoder.frames import FrameParser
from pybox.decoder.headers import LogHeader, parse_headers
from pybox.decoder.stream import BinaryStream


@dataclass
class LogIndex:
    """Start/end offsets for one log within the file."""
    start: int
    end: int


class FlightLog:
    """Represents a Blackbox log file that may contain multiple flight logs.

    Each arm-disarm cycle creates a new log within the same file.
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        self._data = self.path.read_bytes()
        self._logs: list[LogIndex] = []
        self._discover_logs()

    @property
    def log_count(self) -> int:
        return len(self._logs)

    def _discover_logs(self) -> None:
        """Find all log start markers in the file."""
        marker = LOG_START_MARKER
        search_start = 0
        while True:
            pos = self._data.find(marker, search_start)
            if pos == -1:
                break
            self._logs.append(LogIndex(start=pos, end=0))
            search_start = pos + len(marker)

        # Set end offsets
        for i in range(len(self._logs)):
            if i + 1 < len(self._logs):
                self._logs[i].end = self._logs[i + 1].start
            else:
                self._logs[i].end = len(self._data)

    def get_header(self, log_index: int = 0) -> LogHeader:
        """Parse and return the header for the given log index."""
        if log_index < 0 or log_index >= self.log_count:
            raise IndexError(f"Log index {log_index} out of range (0..{self.log_count - 1})")

        log_info = self._logs[log_index]
        stream = BinaryStream(self._data, start=log_info.start, end=log_info.end)
        return parse_headers(stream)

    def decode(self, log_index: int = 0, raw: bool = False) -> DecodedLog:
        """Decode the given log index and return structured data.

        Args:
            log_index: Which log in the file to decode (0-based).
            raw: If True, don't apply field predictions (show raw deltas).

        Returns:
            A DecodedLog with header info and decoded frames.
        """
        if log_index < 0 or log_index >= self.log_count:
            raise IndexError(f"Log index {log_index} out of range (0..{self.log_count - 1})")

        log_info = self._logs[log_index]
        stream = BinaryStream(self._data, start=log_info.start, end=log_info.end)

        # Parse headers
        header = parse_headers(stream)

        # Rewrite duplicate HOME_COORD predictors for GPS
        g_def = header.frame_defs.get(ord("G"))
        if g_def is not None:
            for i in range(1, g_def.field_count):
                if (g_def.predictor[i - 1] == FieldPredictor.HOME_COORD
                        and g_def.predictor[i] == FieldPredictor.HOME_COORD):
                    g_def.predictor[i] = FieldPredictor.HOME_COORD_1

        i_def = header.frame_defs.get(ord("I"))
        if i_def is None or i_def.field_count == 0:
            raise ValueError("Log is missing I-frame field definitions")

        parser = FrameParser(header)
        field_count = i_def.field_count
        field_names = i_def.field_names[:field_count]

        # Collect frames
        main_frames: list[list[int]] = []
        slow_frames: list[list[int]] = []
        gps_frames: list[list[int]] = []
        events: list[dict] = []
        valid_count = 0
        corrupt_count = 0

        while not stream.eof:
            command = stream.peek_char()
            if command == -1:
                break

            if command == ord("I"):
                stream.read_byte()
                pos_before = stream.pos
                valid = parser.parse_intraframe(stream, raw)
                if valid and parser.main_history[1] is not None:
                    main_frames.append(list(parser.main_history[1][:field_count]))
                    valid_count += 1
                else:
                    corrupt_count += 1

            elif command == ord("P"):
                stream.read_byte()
                valid = parser.parse_interframe(stream, raw)
                if valid and parser.main_history[1] is not None:
                    main_frames.append(list(parser.main_history[1][:field_count]))
                    valid_count += 1
                else:
                    corrupt_count += 1

            elif command == ord("E"):
                stream.read_byte()
                event = parser.parse_event_frame(stream)
                if event.event_type >= 0:
                    events.append({
                        "type": event.event_type,
                        "sync_beep_time": event.sync_beep_time,
                        "log_iteration": event.log_iteration,
                        "current_time": event.current_time,
                    })

            elif command == ord("G"):
                stream.read_byte()
                parser.parse_gps_frame(stream, raw)
                g_def = header.frame_defs.get(ord("G"))
                if g_def:
                    gps_frames.append(list(parser.last_gps[:g_def.field_count]))

            elif command == ord("H") and stream.pos < stream.end:
                # Could be GPS Home frame or leftover header – try GPS home
                stream.read_byte()
                parser.parse_gps_home_frame(stream, raw)

            elif command == ord("S"):
                stream.read_byte()
                parser.parse_slow_frame(stream, raw)
                s_def = header.frame_defs.get(ord("S"))
                if s_def:
                    slow_frames.append(list(parser.last_slow[:s_def.field_count]))

            else:
                # Unknown/corrupt byte – skip
                stream.read_byte()
                parser._invalidate_stream()

        return DecodedLog(
            header=header,
            field_names=field_names,
            main_frames=main_frames,
            slow_frames=slow_frames,
            gps_frames=gps_frames,
            events=events,
            valid_frame_count=valid_count,
            corrupt_frame_count=corrupt_count,
        )

    def to_dataframe(self, log_index: int = 0, raw: bool = False) -> pd.DataFrame:
        """Convenience: decode + convert to pandas DataFrame."""
        decoded = self.decode(log_index, raw)
        return decoded.to_dataframe()


@dataclass
class DecodedLog:
    """Container for a fully decoded flight log."""
    header: LogHeader
    field_names: list[str]
    main_frames: list[list[int]]
    slow_frames: list[list[int]]
    gps_frames: list[list[int]]
    events: list[dict]
    valid_frame_count: int = 0
    corrupt_frame_count: int = 0

    def to_dataframe(self) -> pd.DataFrame:
        """Convert main frames to a pandas DataFrame."""
        if not self.main_frames:
            return pd.DataFrame()

        arr = np.array(self.main_frames, dtype=np.int64)
        df = pd.DataFrame(arr, columns=self.field_names[:arr.shape[1]])
        return df

    @property
    def duration_us(self) -> int:
        """Total duration of the log in microseconds."""
        if not self.main_frames:
            return 0
        return self.main_frames[-1][FLIGHT_LOG_FIELD_INDEX_TIME] - self.main_frames[0][FLIGHT_LOG_FIELD_INDEX_TIME]

    @property
    def duration_s(self) -> float:
        """Total duration in seconds."""
        return self.duration_us / 1_000_000.0

    @property
    def sample_rate_hz(self) -> float:
        """Estimated sample rate in Hz."""
        if len(self.main_frames) < 2:
            return 0.0
        dt_us = self.duration_us
        if dt_us == 0:
            return 0.0
        return (len(self.main_frames) - 1) / (dt_us / 1_000_000.0)

    @property
    def setup_info(self) -> dict[str, str]:
        """Return the raw header key-value pairs (like PIDtoolbox's SetupInfo)."""
        return dict(self.header.raw_headers)
