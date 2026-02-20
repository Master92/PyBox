"""Blackbox field definitions, enums, and constants.

Mirrors blackbox-tools/src/blackbox_fielddefs.h and parser.h constants.
"""

from __future__ import annotations

from enum import IntEnum

# ── max limits ────────────────────────────────────────────────────────

FLIGHT_LOG_MAX_LOGS_IN_FILE = 1000
FLIGHT_LOG_MAX_FIELDS = 128
FLIGHT_LOG_MAX_FRAME_LENGTH = 256
FLIGHT_LOG_MAX_MOTORS = 8
FLIGHT_LOG_MAX_SERVOS = 8

FLIGHT_LOG_FIELD_INDEX_ITERATION = 0
FLIGHT_LOG_FIELD_INDEX_TIME = 1

LOG_START_MARKER = b"H Product:Blackbox flight data recorder by Nicholas Sherlock\n"

MAXIMUM_TIME_JUMP_BETWEEN_FRAMES = 10 * 1_000_000  # 10 seconds in µs
MAXIMUM_ITERATION_JUMP_BETWEEN_FRAMES = 500 * 10


# ── firmware types ────────────────────────────────────────────────────

class FirmwareType(IntEnum):
    UNKNOWN = 0
    BASEFLIGHT = 1
    CLEANFLIGHT = 2
    BETAFLIGHT = 3


# ── predictors ────────────────────────────────────────────────────────

class FieldPredictor(IntEnum):
    ZERO = 0
    PREVIOUS = 1
    STRAIGHT_LINE = 2
    AVERAGE_2 = 3
    MINTHROTTLE = 4
    MOTOR_0 = 5
    INC = 6
    HOME_COORD = 7
    FIFTEEN_HUNDRED = 8
    VBATREF = 9
    LAST_MAIN_FRAME_TIME = 10
    MINMOTOR = 11
    # internal: rewritten second coord of a home-coord pair
    HOME_COORD_1 = 256


# ── encodings ─────────────────────────────────────────────────────────

class FieldEncoding(IntEnum):
    SIGNED_VB = 0
    UNSIGNED_VB = 1
    NEG_14BIT = 3
    ELIAS_DELTA_U32 = 4
    ELIAS_DELTA_S32 = 5
    TAG8_8SVB = 6
    TAG2_3S32 = 7
    TAG8_4S16 = 8
    NULL = 9
    ELIAS_GAMMA_U32 = 10
    ELIAS_GAMMA_S32 = 11


# ── events ────────────────────────────────────────────────────────────

class FlightLogEvent(IntEnum):
    SYNC_BEEP = 0
    INFLIGHT_ADJUSTMENT = 13
    LOGGING_RESUME = 14
    FLIGHTMODE = 30
    LOG_END = 255


# ── flight modes ──────────────────────────────────────────────────────

FLIGHT_MODE_NAMES = [
    "ANGLE", "HORIZON", "MAG", "BARO", "GPS_HOME",
    "GPS_HOLD", "HEADFREE", "UNUSED", "PASSTHRU",
    "RANGEFINDER", "FAILSAFE",
]

FLIGHT_STATE_NAMES = [
    "GPS_FIX_HOME", "GPS_FIX", "CALIBRATE_MAG", "SMALL_ANGLE", "FIXED_WING",
]

FAILSAFE_PHASE_NAMES = [
    "IDLE", "RX_LOSS_DETECTED", "LANDING", "LANDED",
    "RX_LOSS_MONITORING", "RX_LOSS_RECOVERED",
]
