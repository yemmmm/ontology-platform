// Pi modeling Runner: orchestrates isolated role RPC sessions, enforces the lifecycle contract,
// accepts schema-valid artifacts only after settlement, records ordered events, drives stage
// summaries, and wraps protected platform writes around the deterministic adapter.
//
// The Runner owns Runtime lifecycle and observable orchestration. Modeling judgment lives in the
// Workflow Package; deterministic files/hashes/Batch planning/platform requests live in the Python
// library. The platform remains the sole authority for applied semantic facts.

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { RpcSession, defaultRoleArgs } from "./rpc-session.mjs";
import { EventRecorder, EVENT_CLASSES, recordableClass } from "./event-recorder.mjs";
import { validateSummary, summarizeVisibleEvents, SUMMARY_FIELDS } from "./stage-summary.mjs";

/**
 * Role tool inventories. The organizer never receives modeling-item or apply tools.
 *
 * `read` and `grep` are read-only Pi built-ins, re-enabled per role through `--tools` even though
 * `--no-builtin-tools` keeps the dangerous built-ins (bash/edit/write) disabled. Roles whose prompts
 * require reading real source locators or shared-directory artifacts (business organizer, Work Unit
 * modeler, reviewer) get them; the coordinator's introduce prompt does not read files, and the
 * stage summarizer only consumes bounded events already injected through its prompt.
 */
export const ROLE_TOOLS = Object.freeze({
  coordinator: [
    "request_modeling_clarification",
    "complete_stage",
    "submit_platform_action",
  ],
  "business-organizer": [
    "read",
    "grep",
    "request_modeling_clarification",
    "write_modeling_artifact",
    "complete_stage",
  ],
  "work-unit-modeler": ["read", "grep", "write_modeling_artifact", "complete_stage"],
  "model-reviewer": ["read", "grep", "write_modeling_artifact", "complete_stage"],
  "stage-summarizer": ["write_modeling_artifact"],
});

export const ROLE_PROMPTS = Object.freeze({
  coordinator: "workflow/coordinator.md",
  "business-organizer": "workflow/business-organizer.md",
  "work-unit-modeler": "workflow/work-unit-modeler.md",
  "model-reviewer": "workflow/model-reviewer.md",
  "stage-summarizer": "workflow/stage-summarizer.md",
});

/** Hard upper bound on a single accepted artifact to reject oversized/hidden payloads. */
const MAX_ARTIFACT_BYTES = 256 * 1024;

export class RunnerError extends Error {}

/** Compute the stable canonical hash of a parsed artifact for candidate binding. */
export function artifactHash(artifact) {
  const canonical = JSON.stringify(sortDeep(artifact));
  return createHash("sha256").update(canonical).digest("hex");
}

function sortDeep(value) {
  if (Array.isArray(value)) return value.map(sortDeep);
  if (value && typeof value === "object" && !(value instanceof Date)) {
    return Object.keys(value)
      .sort()
      .reduce((acc, key) => {
        acc[key] = sortDeep(value[key]);
        return acc;
      }, {});
  }
  return value;
}

const ARTIFACT_GRACE_ATTEMPTS = 10;
const ARTIFACT_GRACE_DELAY_MS = 25;

/**
 * Read an artifact file, retrying briefly when it is not yet present. Real Pi writes artifacts
 * before settlement; this only absorbs the fake-Pi harness write/read race and never changes the
 * accept/reject contract.
 */
async function readArtifactWithGrace(absolute) {
  let lastError;
  for (let attempt = 0; attempt < ARTIFACT_GRACE_ATTEMPTS; attempt += 1) {
    try {
      return await readFile(absolute);
    } catch (error) {
      lastError = error;
      if (error.code !== "ENOENT") throw error;
      await new Promise((resolve) => setTimeout(resolve, ARTIFACT_GRACE_DELAY_MS));
    }
  }
  throw lastError;
}

/**
 * One modeling run. Owns the event recorder and the set of live role sessions.
 */
export class ModelingRun {
  /**
   * @param {Object} init
   * @param {string} init.runId
   * @param {string} init.eventFile   Absolute path to the JSONL event file.
   * @param {string} init.workDir     Shared run working directory (artifact root).
   */
  constructor({ runId, eventFile, workDir }) {
    this.runId = runId;
    this.workDir = workDir;
    this.recorder = new EventRecorder(eventFile, runId);
    /** @type {Map<string, RpcSession>} role -> session */
    this.sessions = new Map();
    this.coordinator = null;
    this.terminal = false;
    /** @type {Map<string, (record: any) => Promise<string>>} role -> clarify handler */
    this.clarifyHandlers = new Map();
  }

  async start() {
    await this.recorder.open();
    await this.recorder.record(EVENT_CLASSES.RUN_START, { run_id: this.runId });
  }

  /**
   * Start one role session. The command is injectable so tests drive a fake Pi subprocess while the
   * real Runner uses the pinned `pi` binary.
   *
   * @param {Object} options
   * @param {string} options.role
   * @param {string} options.command
   * @param {string[]} options.args
   * @param {string} options.cwd
   * @param {Object<string,string>} [options.env]
   * @param {number} [options.timeoutMs]
   * @param {boolean} [options.persistent]  Coordinator stays alive across per-turn settlement.
   */
  async startRole({ role, command, args, cwd, env, timeoutMs, persistent = false }) {
    if (this.sessions.has(role)) {
      throw new RunnerError(`role ${role} already started`);
    }
    const session = new RpcSession({
      command,
      args,
      cwd,
      env,
      role,
      timeoutMs,
      onEvent: (record) => this._observe(role, record),
    });
    session.persistent = persistent;
    session.start();
    this.sessions.set(role, session);
    await this.recorder.record(EVENT_CLASSES.ROLE_START, {
      role,
      session_pid: session.child?.pid ?? null,
      persistent,
    });
    if (role === "coordinator") this.coordinator = session;
    return session;
  }

  /** Observe a raw Pi record: record the mapped event class with role correlation. */
  async _observe(role, record) {
    if (record.type === "extension_ui_request" && record.method === "input") {
      await this.recorder.record(EVENT_CLASSES.CLARIFICATION_REQUESTED, {
        role,
        request_id: record.id,
        title: record.title ?? null,
      });
      const handler = this.clarifyHandlers.get(role);
      if (handler) {
        await this.recorder.record(EVENT_CLASSES.CLARIFICATION_PAUSED, { role, request_id: record.id });
        const session = this.sessions.get(role);
        try {
          const answer = await handler(record);
          session?.respondUi(record.id, answer);
          await this.recorder.record(EVENT_CLASSES.CLARIFICATION_ANSWERED, {
            role,
            request_id: record.id,
          });
        } catch (error) {
          await this.recorder.record(EVENT_CLASSES.FAILURE, {
            role,
            request_id: record.id,
            error: error.message,
          });
          throw error;
        }
      }
    }
    const cls = recordableClass(record.type);
    if (cls) {
      const payload = {
        role,
        tool: record.toolName ?? null,
        isError: record.isError ?? null,
        queue_length: record.length ?? (Array.isArray(record.queue) ? record.queue.length : null),
      };
      // Bound stderr text so Pi diagnostics are visible in events.jsonl without unbounded dumps.
      // stderr is observability only; it is never parsed as protocol or treated as a tool result.
      if (cls === EVENT_CLASSES.STDERR && typeof record.text === "string") {
        payload.text = record.text.slice(0, 1000);
      }
      await this.recorder.record(cls, payload);
    }
  }

  /**
   * Send a prompt to a role and drive it to settlement. Clarification inputs are routed to the
   * provided handler (the coordinator/user). Resolves only when the role is complete-eligible.
   */
  async driveRole(role, prompt, { promptId, clarify } = {}) {
    const session = this.sessions.get(role);
    if (!session) throw new RunnerError(`unknown role ${role}`);
    const id = promptId ?? `${role}-${Date.now()}`;
    if (clarify) this.clarifyHandlers.set(role, clarify);
    await this.recorder.record(EVENT_CLASSES.STAGE_START, { role, prompt_id: id });
    session.sendPrompt(id, prompt);
    try {
      await session.awaitSettlement();
      await this.recorder.record(EVENT_CLASSES.TERMINAL_IDLE, { role });
    } finally {
      this.clarifyHandlers.delete(role);
    }
    await this.recorder.record(EVENT_CLASSES.STAGE_END, { role, prompt_id: id });
    return session;
  }

  /**
   * Read and validate a role artifact after settlement. Rejects missing, malformed, oversized, or   * schema-mismatched output. The artifact is accepted (recorded) only when it validates.
   */
  async acceptArtifact(role, relativePath, { requiredKeys = [], forbiddenKeys = [] } = {}) {
    const session = this.sessions.get(role);
    if (!session || !session.isCompleteEligible()) {
      throw new RunnerError(`cannot accept artifact from unsettled role ${role}`);
    }
    const absolute = path.isAbsolute(relativePath)
      ? relativePath
      : path.join(this.workDir, relativePath);
    let raw;
    try {
      // Real Pi writes an artifact during its tool call, before settlement; the brief grace below only
      // absorbs the fake-Pi test harness write/read race when a script writes the file just after the
      // settle signals. It never changes what is accepted or rejected and never triggers for real runs.
      raw = await readArtifactWithGrace(absolute);
    } catch (error) {
      await this.recorder.record(EVENT_CLASSES.ARTIFACT_REJECTED, { role, locator: relativePath, reason: "missing" });
      throw new RunnerError(`artifact missing for ${role}: ${relativePath}`);
    }
    if (raw.byteLength > MAX_ARTIFACT_BYTES) {
      await this.recorder.record(EVENT_CLASSES.ARTIFACT_REJECTED, { role, locator: relativePath, reason: "oversized" });
      throw new RunnerError(`artifact oversized for ${role}`);
    }
    let parsed;
    try {
      parsed = JSON.parse(raw.toString("utf-8"));
    } catch (error) {
      await this.recorder.record(EVENT_CLASSES.ARTIFACT_REJECTED, { role, locator: relativePath, reason: "malformed" });
      throw new RunnerError(`artifact malformed for ${role}`);
    }
    const keys = new Set(Object.keys(parsed ?? {}));
    for (const key of requiredKeys) {
      if (!keys.has(key)) {
        await this.recorder.record(EVENT_CLASSES.ARTIFACT_REJECTED, { role, locator: relativePath, reason: `missing_key:${key}` });
        throw new RunnerError(`artifact missing key ${key} for ${role}`);
      }
    }
    for (const key of forbiddenKeys) {
      if (keys.has(key)) {
        await this.recorder.record(EVENT_CLASSES.ARTIFACT_REJECTED, { role, locator: relativePath, reason: `forbidden_key:${key}` });
        throw new RunnerError(`artifact forbidden key ${key} for ${role}`);
      }
    }
    const hash = artifactHash(parsed);
    await this.recorder.record(EVENT_CLASSES.ARTIFACT_ACCEPTED, { role, locator: relativePath, hash });
    return { artifact: parsed, hash, locator: relativePath };
  }

  /**
   * Drive an already-started summarizer role over one stage's visible events and validate its
   * summary. The caller starts the role session (real or fake) so the lifecycle path is identical.
   */
  async summarizeStage(role, { stage, stageRecords, artifactRefs }) {
    const visible = summarizeVisibleEvents(stageRecords);
    const prompt =
      `Summarize stage "${stage}" using ONLY these bounded visible events and artifact references. ` +
      `Emit a JSON object with EXACTLY these keys: ${SUMMARY_FIELDS.join(", ")}. ` +
      `Field types: stage/goal/result/next_step are non-empty strings; ` +
      `roles/actions/issues_decisions/unresolved are arrays (use [] when empty, NEVER null); ` +
      `inputs_outputs is an object of bounded reference key/values (no transcript/reasoning/raw). ` +
      `Then persist it by calling write_modeling_artifact(name: "summary-${stage}", json: <that JSON object as a single JSON string>). ` +
      `The artifact name MUST be exactly "summary-${stage}" (no suffix, no rearrangement). ` +
      `Visible events: ${JSON.stringify(visible)}. Artifact references: ${JSON.stringify(artifactRefs ?? {})}.`;
    await this.driveRole(role, prompt, { promptId: `summary-${stage}` });
    const { artifact } = await this.acceptArtifact(role, `artifacts/summary-${stage}.json`);
    validateSummary(artifact);
    await this.stopRole(role);
    await this.recorder.record(EVENT_CLASSES.STAGE_END, { stage, summary: true });
    return artifact;
  }

  /**
   * Wrap a protected platform-adapter call: record tool start before, invoke, record end after.
   * The actual authorization (role settled + hash + review PASS + clean dry-run) is confirmed by the
   * Runner before calling this, and the adapter consumes the one-shot grant inside the call.
   */
  async invokeAdapter(adapterBin, action, args, { operationId } = {}) {
    await this.recorder.record(EVENT_CLASSES.TOOL_START, { tool: `adapter:${action}`, operation_id: operationId ?? null });
    let result;
    try {
      result = await runAdapter(adapterBin, action, args);
    } catch (error) {
      await this.recorder.record(EVENT_CLASSES.TOOL_ERROR, { tool: `adapter:${action}`, error: error.message });
      throw error;
    }
    await this.recorder.record(EVENT_CLASSES.TOOL_END, { tool: `adapter:${action}`, operation_id: operationId ?? null });
    return result;
  }

  /** Stop a role: graceful shutdown then await exit. Coordinator requires workflow terminal state. */
  async stopRole(role) {
    const session = this.sessions.get(role);
    if (!session) return;
    if (session.persistent && !this.terminal && role === "coordinator") {
      throw new RunnerError("coordinator may only stop after workflow terminal state");
    }
    await session.gracefulShutdown();
    this.sessions.delete(role);
    await this.recorder.record(EVENT_CLASSES.ROLE_END, { role, exit_code: session.exitCode });
  }

  /** Reclaim a single role by force (timeout/failure); stable artifacts remain for targeted rerun. */
  async reclaimRole(role, reason) {
    const session = this.sessions.get(role);
    if (!session) return;
    await session.forceKill(reason);
    this.sessions.delete(role);
    await this.recorder.record(EVENT_CLASSES.TIMEOUT, { role, reason: String(reason?.message ?? reason) });
  }

  /** Mark the workflow terminal so the persistent coordinator may finally stop. */
  async markTerminal(result) {
    this.terminal = true;
    await this.recorder.record(EVENT_CLASSES.RUN_END, { run_id: this.runId, result });
  }

  /** Reclaim every live session and close the recorder. Never leaves an orphan child. */
  async dispose() {
    for (const role of [...this.sessions.keys()]) {
      const session = this.sessions.get(role);
      try {
        await session.forceKill(new Error(`run ${this.runId} disposing`));
      } catch {
        // ignore — best-effort reclamation
      }
      this.sessions.delete(role);
    }
    await this.recorder.close();
  }
}

/** Spawn the platform_adapter.py CLI for one action and return its parsed JSON envelope. */
export async function runAdapter(adapterBin, action, args) {
  const { spawn } = await import("node:child_process");
  return new Promise((resolve, reject) => {
    const child = spawn(adapterBin, [action, ...args], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.once("error", reject);
    child.once("exit", (code) => {
      let parsed;
      try {
        parsed = stdout ? JSON.parse(stdout) : {};
      } catch (error) {
        return reject(new RunnerError(`adapter ${action} returned non-JSON: ${error.message}`));
      }
      if (code !== 0 && parsed?.status !== "ok") {
        return reject(
          new RunnerError(`adapter ${action} failed (code ${code}): ${parsed?.error_code ?? stderr.slice(0, 200)}`),
        );
      }
      resolve(parsed);
    });
  });
}

export { defaultRoleArgs };
