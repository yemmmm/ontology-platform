// Section E — events and stage summaries.

import { test } from "node:test";
import assert from "node:assert/strict";

import { validateSummary, summarizeVisibleEvents, SUMMARY_FIELDS, SummaryValidationError } from "../src/stage-summary.mjs";
import { EVENT_CLASSES } from "../src/event-recorder.mjs";
import { ModelingRun, RunnerError } from "../src/runner.mjs";
import { makeRun, makeWorkDir, startFakeRole, readEvents } from "./helpers.mjs";

const validSummary = () => ({
  stage: "business-organization",
  roles: ["business-organizer"],
  goal: "produce brief and coverage",
  actions: ["read sources", "asked one clarification"],
  inputs_outputs: { brief: "artifacts/brief.json", coverage: "artifacts/coverage.json" },
  issues_decisions: ["scope bounded to foundations"],
  result: "Brief and Coverage accepted",
  unresolved: [],
  next_step: "model work units",
});

test("validateSummary accepts the canonical shape and rejects missing/extra/hidden fields", () => {
  assert.equal(validateSummary(validSummary()), true);
  for (const field of SUMMARY_FIELDS) {
    const partial = validSummary();
    delete partial[field];
    assert.throws(() => validateSummary(partial), SummaryValidationError);
  }
  const extra = { ...validSummary(), hidden_reasoning: "..." };
  assert.throws(() => validateSummary(extra), SummaryValidationError);
  const smuggled = validSummary();
  smuggled.inputs_outputs = { leak: { transcript: "full chat", raw: "..." } };
  assert.throws(() => validateSummary(smuggled), SummaryValidationError);
});

test("summarizeVisibleEvents exposes only bounded event fields", () => {
  const visible = summarizeVisibleEvents([
    { type: "agent_start" },
    { type: "tool_execution_start", toolName: "write_modeling_artifact" },
    { type: "tool_execution_end", toolName: "write_modeling_artifact", isError: false },
    { type: "extension_ui_request", method: "input", id: "q1" },
    { type: "secret_leak", apiKey: "sk-..." },
  ]);
  assert.ok(visible.every((entry) => !("apiKey" in entry)));
  assert.ok(visible.some((entry) => entry.type === "tool_execution_end"));
});

test("recorded events are ordered with stable run/role correlation", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  await startFakeRole({
    run,
    role: "work-unit-modeler",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "queue", length: 1 },
      { type: "event", record: { type: "auto_retry" } },
      { type: "event", record: { type: "compaction_start" } },
      { type: "event", record: { type: "compaction_end" } },
      { type: "event", record: { type: "agent_end" } },
      { type: "event", record: { type: "agent_settled" } },
      { type: "idle" },
      { type: "queue", length: 0 },
    ],
    timeoutMs: 6000,
  });
  await run.driveRole("work-unit-modeler", "model");
  const events = await readEvents(workDir);
  const classes = events.map((entry) => entry.class);
  const order = ["run_start", "role_start", "queue_update", "auto_retry", "compaction_start", "compaction_end", "agent_end", "agent_settled", "terminal_idle"];
  let cursor = 0;
  for (const cls of order) {
    const found = classes.indexOf(cls, cursor);
    assert.ok(found >= 0, `expected ${cls} in order after cursor ${cursor}`);
    cursor = found;
  }
  assert.ok(events.every((entry) => entry.run_id === run.runId));
  await run.dispose();
});

test("invokeAdapter wraps the call with tool start before and tool end after", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  // Provide a fake adapter bin that echoes an ok envelope.
  const { writeFile } = await import("node:fs/promises");
  const { join } = await import("node:path");
  const fakeAdapter = join(workDir, "fake-adapter.sh");
  await writeFile(
    fakeAdapter,
    `#!/usr/bin/env bash\necho '{"schema_version":1,"action":"authorize-runner-write","status":"ok","references":{},"findings":[],"error_code":null,"retryable":false,"next_action":"execute_protected_write"}'\n`,
    { mode: 0o755 },
  );
  await run.invokeAdapter(fakeAdapter, "authorize-runner-write", [], { operationId: "op-1" });
  const events = await readEvents(workDir);
  const classes = events.map((entry) => entry.class);
  const start = classes.indexOf("tool_start");
  const end = classes.indexOf("tool_end");
  assert.ok(start >= 0 && end > start, "tool_start precedes tool_end around adapter call");
  await run.dispose();
});

test("a valid stage summary is produced and an invalid one blocks the stage without rolling back", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  // First produce and accept a valid business artifact (simulating applied state).
  await startFakeRole({
    run,
    role: "business-organizer",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "event", record: { type: "agent_end" } },
      { type: "event", record: { type: "agent_settled" } },
      { type: "idle" },
      { type: "queue", length: 0 },
      { type: "artifact", name: "brief", json: { fields: {}, confirmed_fields: [] } },
    ],
    timeoutMs: 6000,
  });
  await run.driveRole("business-organizer", "organize");
  const accepted = await run.acceptArtifact("business-organizer", "artifacts/brief.json", {
    requiredKeys: ["fields", "confirmed_fields"],
  });
  await run.stopRole("business-organizer");

  // Valid summary stage: start the summarizer fake first, then drive+validate.
  await startFakeRole({
    run,
    role: "stage-summarizer",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "event", record: { type: "agent_end" } },
      { type: "event", record: { type: "agent_settled" } },
      { type: "idle" },
      { type: "queue", length: 0 },
      { type: "artifact", name: "summary-business-organization", json: validSummary() },
    ],
    timeoutMs: 6000,
  });
  const summary = await run.summarizeStage("stage-summarizer", {
    stage: "business-organization",
    stageRecords: [],
    artifactRefs: { brief: "artifacts/brief.json" },
  });
  assert.equal(summary.stage, "business-organization");

  // Invalid summary blocks the stage but the previously accepted artifact remains.
  await startFakeRole({
    run,
    role: "stage-summarizer",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "event", record: { type: "agent_end" } },
      { type: "event", record: { type: "agent_settled" } },
      { type: "idle" },
      { type: "queue", length: 0 },
      { type: "artifact", name: "summary-review", json: { stage: "review" } },
    ],
    timeoutMs: 6000,
  });
  await assert.rejects(
    () => run.summarizeStage("stage-summarizer", {
      stage: "review",
      stageRecords: [],
      artifactRefs: {},
    }),
    SummaryValidationError,
  );
  // Accepted artifact still on disk (applied state retained).
  const { readFile } = await import("node:fs/promises");
  const direct = JSON.parse(await readFile(`${workDir}/${accepted.locator}`, "utf-8"));
  assert.deepEqual(direct.confirmed_fields, []);
  await run.dispose();
});
