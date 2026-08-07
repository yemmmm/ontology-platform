# R2.3-005 Background Outer Input Design

## Status and scope

- Status: proposed design; not implemented
- Requirement: `docs/requirements/requirements-v2.3.md`, R2.3-005 cooperative pause
- Problem: a background `modeling_team run` keeps pumping after stdin EOF, but a non-interactive
  Host cannot send `issue_resolution`, grounded answers, supplements, or corrections back to the
  live Runner.

## Decision

Add an optional local named pipe:

```text
stdin ----\
           -> existing decode/admission gates -> runner.receive_outer()
FIFO  -----/
```

The CLI accepts `--outer-input-fifo PATH`. A background Host writes one UTF-8 JSON object per line:

```bash
printf '%s\n' '{"action":"issue_resolution", ...}' > "$FIFO_PATH"
```

FIFO is preferred because it is selectable, needs no port or supervisor, preserves the existing
NDJSON contract, and is naturally scoped to one live run. An append-only regular file would require
offset, truncation, partial-write, replay, and consumption semantics. Separate request/resolution
files duplicate foreground output and do not cover all outer actions. Unix sockets and HTTP are
reserved for future productization.

## Current minimal scope

### Files and symbols

- `modeling_team/__main__.py`
  - add the CLI option;
  - extract shared `_handle_foreground_message(...)` admission logic;
  - extend `_foreground_event_loop(...)` to select stdin and FIFO;
  - create the FIFO after `prepare()` and before `start()`, then close it in `finally`.
- New `modeling_team/outer_input.py`
  - `OuterInputFifo.open()`, `fileno()`, `read_ready()`, `pop_line()`, and `close()`;
  - own only OS-level framing and lifecycle, never Runner routing.
- Update `modeling_team/tests/test_runner.py` and
  `modeling_team/tests/test_runner_r23005_owner_answer.py`.
- Do not change `TeamRunner.receive_outer`, `_decode_foreground_message`,
  `_KNOWN_OUTER_ACTIONS`, or `_foreground_issue_resolution_is_ready`.

Expected impact is LOW for the new FIFO helper and MEDIUM for the CLI/event loop. Runner protocol
risk remains unchanged because every admitted message still passes through `receive_outer`.
GitNexus must be rerun before implementation: its current index refresh failed with an inconsistent
FTS index, so the present `UNKNOWN`/unrelated `CRITICAL` output is not reliable impact evidence.

### Foreground compatibility

- Without the option, behavior is unchanged.
- Drain and emit Runner output before reading outer input.
- When stdin and FIFO are both ready, process stdin first.
- Process at most one outer message per loop iteration so Runner pumping is not starved.
- stdin EOF retires only stdin; FIFO remains active.
- FIFO writer disconnect does not retire the FIFO or cause a busy loop; the CLI holds a keeper
  writer descriptor.
- Terminal-report completion wins over late input.
- Both sources use the same decode, known-action check, issue-readiness gate, `receive_outer`, emit,
  and foreground-observation sequence.

### Security and lifecycle

- Create a new FIFO with mode `0600` under a mode-`0700` control directory.
- Reject an existing file, directory, FIFO, or symlink instead of reusing it.
- Open nonblocking descriptors with close-on-exec and no-follow protections where supported.
- Buffer partial lines, reject invalid UTF-8 and lines over a fixed limit, and preserve duplicate-key
  rejection through `_decode_foreground_message`.
- On cleanup, unlink only the FIFO inode created by this process.
- The channel accepts structured outer JSON only; it exposes no command or code execution surface.

## Test contract

1. Existing stdin messages and immediate-EOF pumping remain unchanged.
2. With stdin at EOF, a FIFO message reaches `runner.receive_outer` and the run continues.
3. Multiple short-lived FIFO writers work; partial lines are not decoded before newline.
4. Simultaneously readable stdin and FIFO process stdin first.
5. Malformed JSON, duplicate keys, unknown actions, invalid UTF-8, and oversized lines emit
   `outer-input-rejected` without calling Runner.
6. Premature `issue_resolution` is rejected; a resolution in `WAITING_OWNER` or `WAITING_REPAIR`
   uses the existing strict Runner validation and binding.
7. Grounded answers still require a successfully emitted and observed question.
8. Existing nodes/symlinks fail closed, permissions are `0600`, and cleanup does not delete a
   replacement inode.

## Implementation sketch

```python
class OuterInputFifo:
    def __init__(self, path: Path, *, max_line_bytes: int = 65_536): ...
    def open(self) -> None: ...
    def fileno(self) -> int: ...
    def read_ready(self) -> None: ...
    def pop_line(self) -> str | None: ...
    def close(self) -> None: ...


def _handle_foreground_message(runner, line, emit_and_observe, emit_rejection):
    message = _decode_foreground_message(line)
    # Apply _KNOWN_OUTER_ACTIONS and issue-readiness checks unchanged.
    output = runner.receive_outer(message)
    if output:
        emit_and_observe(output)


def _foreground_event_loop(
    runner, stream, emit, *, outer_input=None, select_fn=select.select
):
    # drain -> terminal check -> select(stdin, FIFO)
    # stdin first -> one buffered FIFO line -> repeat
    ...
```

For the narrowest final interface, prefer a fixed path below the run root, such as
`<run-root>/control/outer-input.fifo`, over an unrestricted caller-supplied path. A boolean
`--enable-outer-input-fifo` can then replace the path option while keeping the Host-visible location
deterministic from `run-id`.

## Future productization

Unix-socket acknowledgements, peer credential inspection, durable inbox/replay, cross-process or
cross-run recovery, multiple issue queues, HTTP control APIs, and a supervisor are not part of this
change.
