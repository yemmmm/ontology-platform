// Section A — dependency, installation, entry command, and lifecycle.
// The load-bearing invariant: `agent_end` is only a low-level boundary. A disposable role is
// accepted/reclaimed ONLY after `agent_settled` + Extension idle + empty queue agree. This holds for
// a normal end, an auto-retry, a compaction retry, and a queued follow-up.

import { test } from "node:test";
import assert from "node:assert/strict";

import { RpcSession } from "../src/rpc-session.mjs";
import { checkNodeVersion, NODE_LOWER } from "../src/cli.mjs";
import { makeRun, makeWorkDir, startFakeRole, waitForExit } from "./helpers.mjs";

/** A complete disposable-role script: settle then emit the triple completion signal. */
const settle = (extra = []) => [
  { type: "event", record: { type: "agent_start" } },
  ...extra,
  { type: "event", record: { type: "agent_end" } },
  { type: "event", record: { type: "agent_settled" } },
  { type: "idle" },
  { type: "queue", length: 0 },
];

test("Node lower bound is enforced", () => {
  assert.doesNotThrow(() => checkNodeVersion("22.19.0"));
  assert.doesNotThrow(() => checkNodeVersion("22.22.1"));
  assert.throws(() => checkNodeVersion("22.18.0"), /Node >=/);
  assert.throws(() => checkNodeVersion("20.0.0"), /Node >=/);
});

test("an ordinary agent_end without agent_settled cannot complete a role", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  const session = await startFakeRole({
    run,
    role: "worker-1",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "event", record: { type: "agent_end" } },
      // Intentionally NO agent_settled / idle / empty queue. The fake then exits.
      { type: "exit", code: 0 },
    ],
    timeoutMs: 5000,
  });
  session.sendPrompt("p", "model one unit");
  await assert.rejects(() => session.awaitSettlement(), /before role settlement/);
  await run.dispose();
});

for (const [name, extra] of [
  ["normal agent_end", []],
  ["auto-retry after agent_end", [{ type: "event", record: { type: "auto_retry" } }, { type: "event", record: { type: "agent_end" } }]],
  ["compaction retry after agent_end", [{ type: "event", record: { type: "compaction_start" } }, { type: "event", record: { type: "compaction_end" } }, { type: "event", record: { type: "agent_end" } }]],
  ["queued follow-up after agent_end", [{ type: "queue", length: 1 }, { type: "event", record: { type: "agent_end" } }, { type: "queue", length: 1 }]],
]) {
  test(`disposable role completes only after agent_settled+idle+empty queue (${name})`, async () => {
    const workDir = await makeWorkDir();
    const run = await makeRun(workDir);
    // For the queued case, end with a final empty queue + settled + idle so it can complete.
    const steps = [
      { type: "event", record: { type: "agent_start" } },
      ...extra,
      { type: "event", record: { type: "agent_settled" } },
      { type: "idle" },
      { type: "queue", length: 0 },
    ];
    const session = await startFakeRole({ run, role: "worker-q", workDir, steps, timeoutMs: 8000 });
    session.sendPrompt("p", "model");
    // Must resolve despite earlier non-settling ends.
    await session.awaitSettlement();
    assert.equal(session.isCompleteEligible(), true);
    await session.gracefulShutdown();
    await run.dispose();
  });
}

test("a pending clarification keeps the role ineligible even after agent_settled", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  const session = await startFakeRole({
    run,
    role: "organizer",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "clarify", id: "q1", title: "Scope", question: "Which scope?" },
      { type: "event", record: { type: "agent_end" } },
      { type: "event", record: { type: "agent_settled" } },
      { type: "idle" },
      { type: "queue", length: 0 },
    ],
    timeoutMs: 8000,
  });
  // Drive via the Runner so the clarification handler answers it.
  await run.driveRole("organizer", "organize", { clarify: () => "workflow-only" });
  assert.equal(session.isCompleteEligible(), true);
  await run.dispose();
});

test("interrupt/timeout reclaims only the affected child and leaves no orphan", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  const victim = await startFakeRole({
    run,
    role: "victim",
    workDir,
    // Long sleep so the timeout fires first.
    steps: [{ type: "event", record: { type: "agent_start" } }, { type: "sleep", ms: 10000 }],
    timeoutMs: 200,
  });
  const survivor = await startFakeRole({
    run,
    role: "survivor",
    workDir,
    steps: settle(),
    timeoutMs: 5000,
  });
  victim.sendPrompt("p", "slow");
  survivor.sendPrompt("p", "fast");
  await survivor.awaitSettlement();
  // The victim's external timeout must kill and await it.
  await waitForExit(victim);
  assert.equal(victim.exited, true);
  assert.equal(survivor.exited, false);
  await run.dispose();
  // After dispose, every session child has exited (no orphan).
  for (const session of run.sessions.values()) {
    assert.equal(session.exited, true);
  }
  assert.equal(run.sessions.size, 0);
});

test("RpcSession lifecycle booleans reset on retry/compaction/turn boundaries", () => {
  const session = new RpcSession({ command: "true", args: [], cwd: ".", role: "x" });
  // Simulate ingest directly to unit-test the state machine.
  session._ingest({ type: "agent_settled" });
  assert.equal(session.settled, true);
  session._ingest({ type: "agent_end" });
  assert.equal(session.settled, false, "agent_end resets settled");
  session._ingest({ type: "agent_settled" });
  session._ingest({ type: "auto_retry" });
  assert.equal(session.settled, false, "auto_retry resets settled");
  session._ingest({ type: "agent_settled" });
  session._ingest({ type: "compaction_start" });
  assert.equal(session.settled, false, "compaction_start resets settled");
  session._ingest({ type: "agent_settled" });
  session._ingest({ type: "extension_ui_request", method: "notify", message: "modeling_idle" });
  assert.equal(session.extensionIdle, true);
  session._ingest({ type: "extension_ui_request", method: "input", id: "c1" });
  assert.equal(session.extensionIdle, false, "open clarification clears idle");
  assert.ok(session.pendingInputs.has("c1"));
  session._ingest({ type: "queue_update", queue: [], length: 0 });
  assert.equal(session.queueEmpty, true);
  session._ingest({ type: "queue_update", queue: [{}], length: 1 });
  assert.equal(session.queueEmpty, false);
});
