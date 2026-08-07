from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from modeling_team.outer_input import (
    OuterInputFifo,
    OuterInputFramingError,
    OuterInputInvalidUtf8,
    OuterInputLineTooLong,
)


def _write_line(fifo_path: Path, payload: bytes) -> None:
    # A short-lived writer: open, write, close.  The keeper descriptor held by
    # OuterInputFifo must keep the channel alive across this disconnect.
    fd = os.open(str(fifo_path), os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)


class OuterInputFifoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.fifo_path = self.root / "control" / "outer-input.fifo"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _open(self, **kwargs) -> OuterInputFifo:
        fifo = OuterInputFifo(self.fifo_path, **kwargs)
        fifo.open()
        self.addCleanup(fifo.close)
        return fifo

    def test_open_creates_fifo_with_tight_permissions_under_private_dir(self) -> None:
        fifo = self._open()
        info = os.stat(self.fifo_path, follow_symlinks=False)
        self.assertTrue(stat.S_ISFIFO(info.st_mode))
        self.assertEqual(info.st_mode & 0o777, 0o600)
        parent_info = os.stat(self.fifo_path.parent, follow_symlinks=False)
        self.assertEqual(parent_info.st_mode & 0o777, 0o700)

    def test_open_fail_closed_on_existing_file_dir_fifo_or_symlink(self) -> None:
        cases = (
            ("regular file", lambda: self.fifo_path.write_text("x")),
            ("directory", lambda: self.fifo_path.mkdir()),
            ("fifo", lambda: os.mkfifo(self.fifo_path)),
        )
        for label, create in cases:
            with self.subTest(label=label):
                self.fifo_path.parent.mkdir(parents=True, exist_ok=True)
                if self.fifo_path.exists() or self.fifo_path.is_symlink():
                    if self.fifo_path.is_symlink() or self.fifo_path.is_file():
                        self.fifo_path.unlink()
                    else:
                        self.fifo_path.rmdir()
                create()
                fifo = OuterInputFifo(self.fifo_path)
                with self.assertRaises(FileExistsError):
                    fifo.open()
                # The pre-existing entry is left in place (fail closed, no
                # mutation of caller-owned state).
                self.assertTrue(self.fifo_path.exists())

        # A symlink pointing at a non-existent target also fails closed.
        self.fifo_path.parent.mkdir(parents=True, exist_ok=True)
        if self.fifo_path.exists() or self.fifo_path.is_symlink():
            self.fifo_path.unlink()
        link = self.fifo_path.parent / "link.fifo"
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(self.root / "missing", link)
        fifo = OuterInputFifo(link)
        with self.assertRaises(FileExistsError):
            fifo.open()

    def test_short_lived_writers_deliver_lines_and_partial_line_waits(self) -> None:
        fifo = self._open()
        # A partial line with no newline is buffered but never decoded.
        _write_line(self.fifo_path, b"partial-without-newline")
        fifo.read_ready()
        self.assertIsNone(fifo.pop_line())
        # A second short-lived writer completes the line.
        _write_line(self.fifo_path, b"-suffix\n")
        fifo.read_ready()
        self.assertEqual(fifo.pop_line(), "partial-without-newline-suffix")
        self.assertIsNone(fifo.pop_line())

    def test_multiple_complete_lines_in_one_read_are_popped_separately(self) -> None:
        fifo = self._open()
        _write_line(self.fifo_path, b'{"a":1}\n{"a":2}\n{"a":3}\n')
        fifo.read_ready()
        self.assertEqual(fifo.pop_line(), '{"a":1}')
        # No new data arrives between pops; buffered lines still drain.
        self.assertEqual(fifo.pop_line(), '{"a":2}')
        self.assertEqual(fifo.pop_line(), '{"a":3}')
        self.assertIsNone(fifo.pop_line())

    def test_oversized_complete_line_raises_and_resyncs_past_newline(self) -> None:
        fifo = self._open(max_line_bytes=16)
        big = b"x" * 32 + b"\n"
        _write_line(self.fifo_path, big)
        with self.assertRaises(OuterInputLineTooLong):
            fifo.read_ready()
        # The oversized line was resynced past its newline; a later valid line
        # is still decoded normally.
        _write_line(self.fifo_path, b'{"ok":true}\n')
        fifo.read_ready()
        self.assertEqual(fifo.pop_line(), '{"ok":true}')

    def test_oversized_accumulating_partial_raises_and_resyncs(self) -> None:
        fifo = self._open(max_line_bytes=16)
        # First chunk: a valid line, then the start of an oversized partial.
        _write_line(self.fifo_path, b'{"ok":1}\n' + b"y" * 8)
        fifo.read_ready()
        self.assertEqual(fifo.pop_line(), '{"ok":1}')
        # Grow the partial past the limit without a newline.
        _write_line(self.fifo_path, b"z" * 16)
        with self.assertRaises(OuterInputLineTooLong):
            fifo.read_ready()
        # Resync drops everything up to the next newline; a following valid
        # line is decoded.
        _write_line(self.fifo_path, b"tail-junk\n" + b'{"after":true}\n')
        fifo.read_ready()
        self.assertEqual(fifo.pop_line(), '{"after":true}')

    def test_invalid_utf8_complete_line_raises_and_drops_line(self) -> None:
        fifo = self._open()
        _write_line(self.fifo_path, b"\xff\xfe\xfd\n")
        fifo.read_ready()
        with self.assertRaises(OuterInputInvalidUtf8):
            fifo.pop_line()
        # Subsequent valid UTF-8 line still decodes.
        _write_line(self.fifo_path, b'{"ok":"utf8"}\n')
        fifo.read_ready()
        self.assertEqual(fifo.pop_line(), '{"ok":"utf8"}')

    def test_close_unlinks_only_the_inode_this_process_created(self) -> None:
        fifo = OuterInputFifo(self.fifo_path)
        fifo.open()
        original_stat = os.stat(self.fifo_path, follow_symlinks=False)
        # Replace the FIFO at the same path with a different inode after open.
        os.unlink(self.fifo_path)
        os.mkfifo(self.fifo_path, 0o600)
        replacement_stat = os.stat(self.fifo_path, follow_symlinks=False)
        self.assertNotEqual(
            (original_stat.st_dev, original_stat.st_ino),
            (replacement_stat.st_dev, replacement_stat.st_ino),
        )
        fifo.close()
        # The replacement inode survives cleanup.
        current = os.stat(self.fifo_path, follow_symlinks=False)
        self.assertEqual(
            (current.st_dev, current.st_ino),
            (replacement_stat.st_dev, replacement_stat.st_ino),
        )
        self.assertTrue(stat.S_ISFIFO(current.st_mode))
        os.unlink(self.fifo_path)

    def test_close_is_idempotent_and_clears_recorded_inode(self) -> None:
        fifo = self._open()
        fifo.close()
        fifo.close()  # second close must be a no-op
        self.assertFalse(self.fifo_path.exists())

    def test_writer_disconnect_does_not_retire_channel_or_busy_loop(self) -> None:
        # With the keeper descriptor held, a writer disconnect surfaces as
        # BlockingIOError (no data) rather than EOF, so read_ready returns
        # without retiring and pop_line reports no complete line.
        fifo = self._open()
        _write_line(self.fifo_path, b'{"first":true}\n')
        fifo.read_ready()
        self.assertEqual(fifo.pop_line(), '{"first":true}')
        # Writer has now disconnected; reading again must not raise and must
        # not consume the channel.
        fifo.read_ready()
        self.assertIsNone(fifo.pop_line())
        # A later writer can still deliver a line through the same FIFO.
        _write_line(self.fifo_path, b'{"second":true}\n')
        fifo.read_ready()
        self.assertEqual(fifo.pop_line(), '{"second":true}')


if __name__ == "__main__":
    unittest.main()
