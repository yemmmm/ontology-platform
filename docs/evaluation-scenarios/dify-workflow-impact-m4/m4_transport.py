"""Strict file-spool transport normalization shared by M4 host endpoints."""

from __future__ import annotations


def strip_one_final_line_ending(raw: bytes) -> bytes:
    """Remove one transport-only LF or CRLF terminator; preserve every other byte."""
    if raw.endswith(b"\r\n"):
        return raw[:-2]
    if raw.endswith(b"\n"):
        return raw[:-1]
    return raw
