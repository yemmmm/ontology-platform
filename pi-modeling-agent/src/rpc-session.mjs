// Pi RPC Session: one headless Pi child process driven over NDJSON on stdin/stdout.
//
// LIFECYCLE CONTRACT (R2.0-002 frozen constraint #1):
//   `agent_end` is ONLY a low-level run boundary. An auto-retry, a compaction retry, or a queued
//   follow-up may still continue the same role. A disposable role's artifact is accepted and its
//   child is reclaimed ONLY when all three hold simultaneously:
//     1. Pi emitted `agent_settled` for the current run;
//     2. the modeling Extension reports idle with no pending message;
//     3. the latest observed `queue_update` reports an empty queue.
//   The R2.0-001 integrated-rpc-probe closed stdin on `agent_end`; this module MUST NOT do that.

import { spawn } from "node:child_process";
import { once } from "node:events";

/** Events that reset the settled/idle state because the role is still running. */
const RESET_EVENTS = new Set([
  "agent_end",
  "turn_start",
  "auto_retry",
  "compaction_start",
  "compaction_end",
]);

/** Idle markers the modeling Extension emits through `extension_ui_request` notify. */
const IDLE_MARKER = "modeling_idle";

/**
 * @typedef {Object} RpcSessionOptions
 * @property {string} command       Absolute path to the `pi` executable (real or fake).
 * @property {string[]} args        Arguments after the command.
 * @property {string} cwd           Working directory for the child.
 * @property {Object<string,string>} [env]
 * @property {string} role          Stable role name for correlation.
 * @property {(record: any) => void} [onEvent]  Observer for every parsed record.
 * @property {number} [timeoutMs]   External per-role timeout. On fire the child is force-killed.
 */

export class RpcSession {
  /** @param {RpcSessionOptions} options */
  constructor(options) {
    this.command = options.command;
    this.args = options.args;
    this.cwd = options.cwd;
    this.env = options.env;
    this.role = options.role;
    this.onEvent = options.onEvent ?? (() => {});
    this.timeoutMs = options.timeoutMs ?? null;

    this.child = null;
    this.buffer = "";
    /** Parsed records kept for bounded summarizer input; capped to avoid unbounded growth. */
    this.records = [];
    this.recordsCap = 5000;
    this.exited = false;
    this.exitCode = null;
    this.exitError = null;

    // Lifecycle booleans tracked from the event stream.
    this.settled = false;
    this.extensionIdle = false;
    this.queueEmpty = false;
    /** Set of open `extension_ui_request` input ids awaiting a coordinator answer. */
    this.pendingInputs = new Set();
    /** Resolved when the child process exits. */
    this._exitPromise = null;

    this._timeoutHandle = null;
    this._settleResolvers = [];
  }

  /** Spawn the child and begin framing stdout. Returns once the process is launched. */
  start() {
    if (this.child) throw new Error("RpcSession already started");
    this.child = spawn(this.command, this.args, {
      cwd: this.cwd,
      env: { ...process.env, ...(this.env ?? {}) },
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.child.stdout.setEncoding("utf-8");
    this.child.stdout.on("data", (chunk) => this._onStdout(chunk));
    this.child.stderr.on("data", (chunk) => {
      // stderr is observability only; never parsed as protocol.
      this.onEvent({ type: "stderr", role: this.role, text: chunk.toString() });
    });
    this.child.once("error", (error) => {
      this.exitError = error;
      this._resolveSettlement(new Error(`pi spawn error: ${error.message}`));
    });
    this._exitPromise = once(this.child, "exit").then(([code]) => {
      this.exited = true;
      this.exitCode = code;
      // A process exit without settlement is a failure for disposable roles.
      this._resolveSettlement(
        this.isCompleteEligible()
          ? null
          : new Error(`pi exited (code ${code}) before role settlement`),
      );
    });
    if (this.timeoutMs && this.timeoutMs > 0) {
      this._timeoutHandle = setTimeout(() => {
        this.forceKill(new Error(`role ${this.role} timed out after ${this.timeoutMs}ms`));
      }, this.timeoutMs);
    }
    return this;
  }

  /** Send one prompt record. */
  sendPrompt(id, message) {
    this._write({ id, type: "prompt", message });
  }

  /** Answer one open clarification `extension_ui_request` input. */
  respondUi(requestId, value) {
    if (!this.pendingInputs.has(requestId)) {
      throw new Error(`no pending input ${requestId} for role ${this.role}`);
    }
    this._write({ type: "extension_ui_response", id: requestId, value });
    this.pendingInputs.delete(requestId);
    // Answering a clarification means the Extension is doing work again; not idle until it says so.
    this.extensionIdle = false;
  }

  /**
   * The three-way completion gate. A role is complete-eligible only when settled, the Extension is
   * idle with no pending clarification, and the observed queue is empty.
   */
  isCompleteEligible() {
    return (
      this.settled &&
      this.extensionIdle &&
      this.queueEmpty &&
      this.pendingInputs.size === 0 &&
      !this.exited
    );
  }

  /**
   * Resolve when the role becomes complete-eligible. Rejects on timeout, error, or non-settling
   * exit. Crucially this does NOT resolve on a bare `agent_end`.
   */
  async awaitSettlement() {
    if (this.isCompleteEligible()) return;
    await new Promise((resolve, reject) => {
      this._settleResolvers.push({ resolve, reject });
    });
  }

  /** Graceful shutdown: end stdin (no more prompts) and await exit. */
  async gracefulShutdown() {
    this._clearTimeout();
    if (this.child && this.child.stdin && !this.child.stdin.destroyed) {
      this.child.stdin.end();
    }
    await this._exitPromise;
  }

  /** Forceful reclamation: SIGTERM, escalate to SIGKILL, always await exit. Never orphans. */
  async forceKill(reason) {
    this._clearTimeout();
    if (this.exited || !this.child) return;
    const term = this.child.kill("SIGTERM");
    if (!term) return;
    const killTimer = setTimeout(() => {
      if (!this.exited) this.child.kill("SIGKILL");
    }, 5000);
    try {
      await this._exitPromise;
    } finally {
      clearTimeout(killTimer);
    }
    if (reason) {
      this._resolveSettlement(reason instanceof Error ? reason : new Error(String(reason)));
    }
  }

  _clearTimeout() {
    if (this._timeoutHandle) {
      clearTimeout(this._timeoutHandle);
      this._timeoutHandle = null;
    }
  }

  _write(record) {
    if (!this.child || !this.child.stdin || this.child.stdin.destroyed) {
      throw new Error(`cannot write to role ${this.role}: stdin closed`);
    }
    this.child.stdin.write(`${JSON.stringify(record)}\n`);
  }

  _onStdout(chunk) {
    this.buffer += chunk;
    for (;;) {
      const newline = this.buffer.indexOf("\n");
      if (newline < 0) break;
      const line = this.buffer.slice(0, newline);
      this.buffer = this.buffer.slice(newline + 1);
      if (!line) continue;
      let record;
      try {
        record = JSON.parse(line);
      } catch (error) {
        this.onEvent({ type: "stderr", role: this.role, text: `unparseable line: ${line}` });
        continue;
      }
      this._ingest(record);
    }
  }

  _ingest(record) {
    record.role = record.role ?? this.role;
    if (this.records.length < this.recordsCap) this.records.push(record);
    this.onEvent(record);
    switch (record.type) {
      case "agent_settled":
        this.settled = true;
        break;
      case "queue_update":
        this.queueEmpty = Number(record.length ?? (Array.isArray(record.queue) ? record.queue.length : 1)) === 0;
        break;
      case "extension_ui_request":
        if (record.method === "input") {
          this.pendingInputs.add(record.id);
          this.extensionIdle = false;
        } else if (record.method === "notify" && record.message === IDLE_MARKER) {
          this.extensionIdle = true;
        }
        break;
      default:
        if (RESET_EVENTS.has(record.type)) {
          // The role is still running; an earlier settled/idle state no longer counts.
          this.settled = false;
          this.extensionIdle = false;
        }
    }
    if (this.isCompleteEligible()) this._resolveSettlement(null);
  }

  _resolveSettlement(error) {
    if (this._settleResolvers.length === 0) return;
    const pending = this._settleResolvers;
    this._settleResolvers = [];
    for (const { resolve, reject } of pending) {
      if (error) reject(error);
      else resolve();
    }
  }
}

/**
 * Default headless RPC arguments for a modeling role. `--approve` trusts the project Extension load
 * (R2.0-001 P2); `--no-session` keeps each role an isolated process; `--mode rpc` is the NDJSON mode.
 */
export function defaultRoleArgs({ provider, model, tools, piAgentDir }) {
  if (!Array.isArray(tools) || tools.length === 0) {
    throw new Error("a modeling role must declare a non-empty tool inventory");
  }
  const args = [
    "--mode",
    "rpc",
    "--no-session",
    "--approve",
    "--no-builtin-tools",
    "--tools",
    tools.join(","),
  ];
  if (provider && model) {
    args.push("--provider", provider, "--model", model);
  }
  if (piAgentDir) {
    // The Pi agent/resource directory is conveyed through env in start(); kept here for clarity.
  }
  return args;
}
