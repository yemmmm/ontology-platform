"""Local FIFO outer-input channel for the foreground ``modeling_team`` CLI.

A non-interactive background Host (for example a Claude Code session whose
stdin is ``/dev/null``) cannot otherwise send ``issue_resolution``, grounded
owner answers, or corrections to a live ``modeling_team run``.  This module
owns only the OS-level framing and lifecycle of an optional named pipe:

* create a fresh FIFO (mode ``0600``) under a mode-``0700`` control directory;
* fail closed if anything already exists at the target path;
* hold a keeper writer descriptor so short-lived writers disconnecting does
  not look like EOF and does not retire the channel;
* buffer partial lines, reject oversized lines or invalid UTF-8 by raising a
  dedicated :class:`OuterInputFramingError` (the foreground loop emits
  ``outer-input-rejected`` for these without calling ``receive_outer``);
* on cleanup, unlink only the FIFO inode created by this process.

Routing, decoding, and Runner admission stay in the foreground CLI.  The
channel carries only the existing NDJSON outer-action contract; it exposes no
command or code execution surface.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path


class OuterInputFramingError(Exception):
    """Base class for FIFO framing errors.

    A framing error is distinct from a Runner admission error: the foreground
    loop emits ``outer-input-rejected`` for it WITHOUT calling
    ``receive_outer``, then resynchronizes at the next newline.
    """


class OuterInputLineTooLong(OuterInputFramingError):
    """A single FIFO line exceeded ``max_line_bytes`` before its newline."""


class OuterInputInvalidUtf8(OuterInputFramingError):
    """A complete FIFO line could not be decoded as UTF-8."""


class OuterInputFifo:
    """A selectable local FIFO that feeds the foreground admission path.

    The reader descriptor is what ``select`` watches; the keeper writer
    descriptor is held open for the lifetime of this object so that a writer
    disconnecting does not produce EOF (``os.read`` raising ``BlockingIOError``
    instead of returning ``b""``) and does not cause a busy loop.
    """

    def __init__(self, path: Path, *, max_line_bytes: int = 65_536) -> None:
        self.path = Path(path)
        if max_line_bytes <= 0:
            raise ValueError("max_line_bytes must be positive")
        self.max_line_bytes = int(max_line_bytes)
        self._reader_fd: int | None = None
        self._keeper_fd: int | None = None
        self._buffer = bytearray()
        self._created_dev: int | None = None
        self._created_ino: int | None = None
        self._discard_until_newline = False

    def open(self) -> None:
        """Create and open the FIFO.

        Fail closed if the target path already exists as anything (file,
        directory, FIFO, or symlink).  Record the created inode so cleanup can
        unlink only what this process created.
        """

        if self._reader_fd is not None:
            raise OSError("outer-input FIFO is already open")
        # Fail closed on any pre-existing entry, following no symlinks so a
        # attacker-placed symlink cannot redirect the mkfifo target.
        try:
            os.stat(self.path, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(
                f"outer-input FIFO target already exists: {self.path}"
            )
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        # Guarantee the control-directory and FIFO permissions regardless of
        # the process umask: mkfifo/mkdir apply umask to the requested mode.
        try:
            os.chmod(parent, 0o700)
        except OSError:
            pass
        try:
            os.mkfifo(self.path, mode=0o600)
        except FileExistsError as exc:  # race between stat and mkfifo
            raise FileExistsError(
                f"outer-input FIFO target already exists: {self.path}"
            ) from exc
        os.chmod(self.path, 0o600)
        created = os.stat(self.path, follow_symlinks=False)
        if not stat.S_ISFIFO(created.st_mode):
            # Defensive: another type should not appear after mkfifo, but do
            # not trust it blindly before recording the inode.
            raise OSError(f"outer-input target is not a FIFO: {self.path}")
        self._created_dev = created.st_dev
        self._created_ino = created.st_ino
        reader_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC
        keeper_flags = os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC
        # Open the reader first.  O_RDONLY | O_NONBLOCK on a FIFO returns
        # immediately without waiting for a writer, which lets the keeper
        # O_WRONLY | O_NONBLOCK open succeed (it would otherwise raise ENXIO).
        self._reader_fd = os.open(self.path, reader_flags)
        try:
            self._keeper_fd = os.open(self.path, keeper_flags)
        except OSError as exc:
            os.close(self._reader_fd)
            self._reader_fd = None
            if exc.errno == errno.ENXIO:
                raise OSError(
                    f"outer-input FIFO keeper writer could not open: {self.path}"
                ) from exc
            raise

    def fileno(self) -> int:
        if self._reader_fd is None:
            raise OSError("outer-input FIFO is not open")
        return self._reader_fd

    def read_ready(self) -> None:
        """Drain available bytes into the line buffer and check framing.

        Called when ``select`` reports the reader readable.  Oversized lines
        raise :class:`OuterInputLineTooLong` after resyncing past the next
        newline; the caller emits one ``outer-input-rejected`` and the next
        call resumes normal framing.
        """

        if self._reader_fd is None:
            return
        while True:
            try:
                chunk = os.read(self._reader_fd, 65536)
            except BlockingIOError:
                break
            except InterruptedError:
                continue
            if not chunk:
                # The keeper descriptor holds the FIFO open, so a writer
                # disconnect surfaces as BlockingIOError rather than EOF.
                # Treat an unexpected empty read as "no more data for now".
                break
            self._buffer.extend(chunk)
        self._process_buffer()

    def _process_buffer(self) -> None:
        # Finish resyncing past a previously-reported oversized line first.
        if self._discard_until_newline:
            idx = self._buffer.find(b"\n")
            if idx == -1:
                del self._buffer[:]
                return
            del self._buffer[: idx + 1]
            self._discard_until_newline = False
        # Scan every complete line and the trailing partial for an oversized
        # segment.  A complete oversized line is resynced past its newline; an
        # oversized accumulating partial enters discard mode until the next
        # newline arrives.
        start = 0
        while True:
            idx = self._buffer.find(b"\n", start)
            if idx == -1:
                partial_len = len(self._buffer) - start
                if partial_len > self.max_line_bytes:
                    self._discard_until_newline = True
                    del self._buffer[:]
                    raise OuterInputLineTooLong(
                        f"outer-input line exceeds {self.max_line_bytes} bytes "
                        "without a newline"
                    )
                return
            line_len = idx - start
            if line_len > self.max_line_bytes:
                del self._buffer[: idx + 1]
                raise OuterInputLineTooLong(
                    f"outer-input line exceeds {self.max_line_bytes} bytes"
                )
            start = idx + 1

    def pop_line(self) -> str | None:
        """Return the next complete newline-terminated line decoded as UTF-8.

        Returns ``None`` when no complete line is buffered.  Invalid UTF-8 on a
        complete line raises :class:`OuterInputInvalidUtf8`; the caller emits
        ``outer-input-rejected`` and the line is dropped.
        """

        newline_idx = self._buffer.find(b"\n")
        if newline_idx == -1:
            return None
        line_bytes = bytes(self._buffer[:newline_idx])
        del self._buffer[: newline_idx + 1]
        try:
            return line_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise OuterInputInvalidUtf8(
                "outer-input line is not valid UTF-8"
            ) from exc

    def close(self) -> None:
        """Close descriptors and unlink only the FIFO inode this process made.

        If the path was replaced with a different inode after ``open`` (by any
        process), cleanup leaves the replacement in place.
        """

        for attr in ("_keeper_fd", "_reader_fd"):
            fd = getattr(self, attr)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
                setattr(self, attr, None)
        if self._created_dev is None or self._created_ino is None:
            return
        try:
            current = os.stat(self.path, follow_symlinks=False)
        except FileNotFoundError:
            return
        if (
            current.st_dev == self._created_dev
            and current.st_ino == self._created_ino
            and stat.S_ISFIFO(current.st_mode)
        ):
            try:
                os.unlink(self.path)
            except OSError:
                pass
        # The recorded inode is single-use: never unlink a later replacement
        # even if close() is called again.
        self._created_dev = None
        self._created_ino = None
