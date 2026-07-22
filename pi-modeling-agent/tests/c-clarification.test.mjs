// Section C — business confirmation and clarification roundtrip.

import { test } from "node:test";
import assert from "node:assert/strict";

import { makeRun, makeWorkDir, startFakeRole, readEvents } from "./helpers.mjs";

test("a multi-turn clarification pauses, is answered, and resumes on the same run", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  const answers = [];
  await startFakeRole({
    run,
    role: "business-organizer",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "clarify", id: "q-scope", title: "Scope", question: "Which scope?" },
      { type: "clarify", id: "q-bound", title: "Boundary", question: "Any boundary?" },
      { type: "event", record: { type: "agent_end" } },
      { type: "event", record: { type: "agent_settled" } },
      { type: "idle" },
      { type: "queue", length: 0 },
      { type: "artifact", name: "brief", json: { fields: {}, confirmed_fields: [] } },
    ],
    timeoutMs: 8000,
  });
  await run.driveRole("business-organizer", "organize the brief", {
    clarify: (record) => {
      answers.push(record.id);
      return record.id === "q-scope" ? "workflow-only" : "foundations-only";
    },
  });
  assert.deepEqual(answers, ["q-scope", "q-bound"]);
  const events = await readEvents(workDir);
  const classes = events.map((entry) => entry.class);
  // Each clarification has requested -> paused -> answered, in order.
  const requested = classes.filter((c) => c === "clarification_requested").length;
  const paused = classes.filter((c) => c === "clarification_paused").length;
  const answered = classes.filter((c) => c === "clarification_answered").length;
  assert.equal(requested, 2);
  assert.equal(paused, 2);
  assert.equal(answered, 2);
  for (const cls of ["clarification_requested", "clarification_paused", "clarification_answered"]) {
    assert.ok(classes.indexOf(cls) >= 0);
  }
  // answered always follows paused for each occurrence
  let cursor = 0;
  for (let i = 0; i < 2; i += 1) {
    const p = classes.indexOf("clarification_paused", cursor);
    const a = classes.indexOf("clarification_answered", p);
    assert.ok(a > p, "answered follows paused");
    cursor = a + 1;
  }
  await run.dispose();
});

test("cancel before confirmation performs no accepted artifact write", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  await startFakeRole({
    run,
    role: "business-organizer",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      // clarification asked but never answered; the run is cancelled/reclaimed instead
      { type: "clarify", id: "q-open", title: "Scope", question: "Which scope?" },
      { type: "sleep", ms: 5000 },
    ],
    timeoutMs: 4000,
  });
  // Do not drive with an answer; reclaim (cancel) the role instead.
  const session = run.sessions.get("business-organizer");
  session.sendPrompt("p", "organize");
  // Wait until the clarification is pending, then cancel.
  await new Promise((resolve) => setTimeout(resolve, 150));
  await run.reclaimRole("business-organizer", new Error("cancelled before confirmation"));
  // No artifact accepted event should exist.
  const events = await readEvents(workDir);
  assert.ok(!events.some((entry) => entry.class === "artifact_accepted"));
  assert.ok(events.some((entry) => entry.class === "timeout"));
  await run.dispose();
});

test("the same question id is not answered twice (no duplicate clarification)", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  const seen = new Set();
  await startFakeRole({
    run,
    role: "business-organizer",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "clarify", id: "q1", title: "Scope", question: "Which?" },
      { type: "event", record: { type: "agent_end" } },
      { type: "event", record: { type: "agent_settled" } },
      { type: "idle" },
      { type: "queue", length: 0 },
    ],
    timeoutMs: 5000,
  });
  await run.driveRole("business-organizer", "organize", {
    clarify: (record) => {
      assert.ok(!seen.has(record.id), "duplicate clarification id");
      seen.add(record.id);
      return "answer";
    },
  });
  assert.equal(seen.size, 1);
  await run.dispose();
});
