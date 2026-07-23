// Append-only JSONL event recorder for one run. Records the minimum event classes required by the
// R2.0-002 test plan (section E): run/role/Session and stage start/end, model call start/end/error,
// queue/auto-retry/compaction/agent_end/agent_settled/terminal-idle, tool start/end/error,
// clarification lifecycle, artifact accepted/rejected, and terminal state.
//
// The stream never contains hidden reasoning, full prompts/transcripts, source bodies, raw tool
// responses, credentials, or lease tokens.

import { open } from "node:fs/promises";

export class EventRecorder {
  /**
   * @param {string} path    Absolute path to the JSONL event file.
   * @param {string} runId   Stable run id correlation key.
   */
  constructor(path, runId) {
    this.path = path;
    this.runId = runId;
    this.handle = null;
    this.counter = 0;
  }

  async open() {
    this.handle = await open(this.path, "a");
  }

  /** Append one event. Secret-like fields are stripped by the caller. */
  async record(eventClass, payload = {}) {
    if (!this.handle) throw new Error("EventRecorder not opened");
    const entry = {
      seq: this.counter++,
      run_id: this.runId,
      class: eventClass,
      ts: new Date().toISOString(),
      ...payload,
    };
    await this.handle.writeFile(`${JSON.stringify(entry)}\n`);
    return entry;
  }

  async close() {
    if (this.handle) {
      await this.handle.close();
      this.handle = null;
    }
  }
}

/** Names of the event classes the Runner emits, kept in one place for tests and summaries. */
export const EVENT_CLASSES = Object.freeze({
  RUN_START: "run_start",
  RUN_END: "run_end",
  ROLE_START: "role_start",
  ROLE_END: "role_end",
  STAGE_START: "stage_start",
  STAGE_END: "stage_end",
  MODEL_CALL_START: "model_call_start",
  MODEL_CALL_END: "model_call_end",
  MODEL_CALL_ERROR: "model_call_error",
  QUEUE_UPDATE: "queue_update",
  AUTO_RETRY: "auto_retry",
  COMPACTION_START: "compaction_start",
  COMPACTION_END: "compaction_end",
  AGENT_END: "agent_end",
  AGENT_SETTLED: "agent_settled",
  TERMINAL_IDLE: "terminal_idle",
  TOOL_START: "tool_start",
  TOOL_END: "tool_end",
  TOOL_ERROR: "tool_error",
  CLARIFICATION_REQUESTED: "clarification_requested",
  CLARIFICATION_PAUSED: "clarification_paused",
  CLARIFICATION_ANSWERED: "clarification_answered",
  CLARIFICATION_RESUMED: "clarification_resumed",
  ARTIFACT_ACCEPTED: "artifact_accepted",
  ARTIFACT_REJECTED: "artifact_rejected",
  CANCELLED: "cancelled",
  TIMEOUT: "timeout",
  FAILURE: "failure",
  STDERR: "stderr",
});

/**
 * Map a raw Pi RPC record type to a recorder event class, or null when not recordable.
 *
 * `stderr` is surfaced as its own STDERR class so Pi diagnostics are visible in events.jsonl when a
 * role exits abnormally (e.g. code 143). stderr is observability only and is never parsed as protocol.
 */
export function recordableClass(recordType) {
  const map = {
    queue_update: EVENT_CLASSES.QUEUE_UPDATE,
    auto_retry: EVENT_CLASSES.AUTO_RETRY,
    compaction_start: EVENT_CLASSES.COMPACTION_START,
    compaction_end: EVENT_CLASSES.COMPACTION_END,
    agent_end: EVENT_CLASSES.AGENT_END,
    agent_settled: EVENT_CLASSES.AGENT_SETTLED,
    model_call_start: EVENT_CLASSES.MODEL_CALL_START,
    model_call_end: EVENT_CLASSES.MODEL_CALL_END,
    stderr: EVENT_CLASSES.STDERR,
  };
  return map[recordType] ?? null;
}
