#!/usr/bin/env python3
"""Compile Qt .ts translation files to .qm binary format.

Pure-Python implementation – no external ``lrelease`` binary needed.

Usage:
    python scripts/compile_translations.py

Reads all ``*.ts`` files from ``src/pybox/gui/translations/`` and writes
corresponding ``*.qm`` files into the same directory.
"""

from __future__ import annotations

import struct
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET


# ── .qm binary format constants ──────────────────────────────────────
QM_MAGIC = b"\x3C\xB8\x64\x18\xCA\xEF\x9C\x95\xCD\x21\x1C\xBF\x60\xA1\xBD\xDD"

# Section tags
TAG_END = 1
TAG_SOURCE_TEXT16 = 2    # obsolete, not used
TAG_TRANSLATION = 3
TAG_CONTEXT16 = 4        # obsolete, not used
TAG_HASH = 5             # obsolete, not used
TAG_SOURCE_TEXT = 6
TAG_CONTEXT = 7
TAG_COMMENT = 8

# Top-level block tags
BLOCK_HASHES = 0x42
BLOCK_MESSAGES = 0x69
BLOCK_CONTEXTS = 0x2F
BLOCK_NUMERUS = 0x88
BLOCK_DEPENDENCIES = 0x96


def _utf8(s: str) -> bytes:
    return s.encode("utf-8")


def _utf16(s: str) -> bytes:
    return s.encode("utf-16-be")


def _qm_hash(source: str, comment: str = "") -> int:
    """Compute the ELF hash Qt uses to look up messages.

    Qt hashes the UTF-8 bytes of ``source + comment`` (context is NOT
    part of the hash — it is matched separately after the hash lookup).
    """
    data = source.encode("utf-8") + comment.encode("utf-8")
    h = 0
    for byte in data:
        h = ((h << 4) + byte) & 0xFFFFFFFF
        g = h & 0xF0000000
        if g:
            h ^= g >> 24
        h &= ~g & 0xFFFFFFFF
    return h if h != 0 else 1


def _pack_message(context: str, source: str, translation: str) -> bytes:
    """Pack a single translated message into the .qm message format."""
    buf = b""

    # Translation (UTF-16BE)
    trans_bytes = _utf16(translation)
    buf += struct.pack(">BI", TAG_TRANSLATION, len(trans_bytes))
    buf += trans_bytes

    # Context (UTF-8)
    ctx_bytes = _utf8(context)
    buf += struct.pack(">BI", TAG_CONTEXT, len(ctx_bytes))
    buf += ctx_bytes

    # Source text (UTF-8)
    src_bytes = _utf8(source)
    buf += struct.pack(">BI", TAG_SOURCE_TEXT, len(src_bytes))
    buf += src_bytes

    # End tag
    buf += struct.pack(">B", TAG_END)

    return buf


def compile_ts(ts_path: Path) -> bytes:
    """Parse a .ts file and return the compiled .qm binary."""
    tree = ET.parse(ts_path)
    root = tree.getroot()

    messages: list[tuple[int, bytes]] = []  # (hash, packed_message)

    for ctx_elem in root.iter("context"):
        context_name = ""
        name_elem = ctx_elem.find("name")
        if name_elem is not None and name_elem.text:
            context_name = name_elem.text

        for msg in ctx_elem.iter("message"):
            src_elem = msg.find("source")
            trans_elem = msg.find("translation")

            if src_elem is None or src_elem.text is None:
                continue
            if trans_elem is None or trans_elem.text is None:
                continue
            # Skip unfinished translations
            if trans_elem.get("type") == "unfinished":
                continue

            source = src_elem.text
            translation = trans_elem.text

            h = _qm_hash(source)
            packed = _pack_message(context_name, source, translation)
            messages.append((h, packed))

    # Sort by hash for binary search at runtime
    messages.sort(key=lambda x: x[0])

    # Build hash offset table
    hash_table = b""
    msg_block = b""
    for h, packed in messages:
        offset = len(msg_block)
        hash_table += struct.pack(">II", h, offset)
        msg_block += packed

    # Assemble final .qm file
    out = QM_MAGIC

    # Hashes block
    out += struct.pack(">BI", BLOCK_HASHES, len(hash_table))
    out += hash_table

    # Messages block
    out += struct.pack(">BI", BLOCK_MESSAGES, len(msg_block))
    out += msg_block

    return out


def main():
    ts_dir = Path(__file__).resolve().parent.parent / "src" / "pybox" / "gui" / "translations"
    if not ts_dir.is_dir():
        print(f"Translations directory not found: {ts_dir}")
        return

    ts_files = list(ts_dir.glob("*.ts"))
    if not ts_files:
        print("No .ts files found")
        return

    for ts_path in ts_files:
        qm_path = ts_path.with_suffix(".qm")
        print(f"Compiling {ts_path.name} -> {qm_path.name}...")
        qm_data = compile_ts(ts_path)
        qm_path.write_bytes(qm_data)
        print(f"  {len(qm_data)} bytes written")

    print("Done.")


if __name__ == "__main__":
    main()
