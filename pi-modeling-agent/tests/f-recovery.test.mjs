// Section F — failure and local recovery.

import { test } from "node:test";
import assert from "node:assert/strict";

import { makeRun, makeWorkDir, startFakeRole, readEvents, waitForExit } from "./helpers.mjs";

test("a worker killed mid-output leaves no accepted artifact and the unit reruns cleanly", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  // Worker writes a partial artifact but never settles (killed by timeout).
  await startFakeRole({
    run,
    role: "work-unit-modeler",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "artifact", name: "unit-u", json: { ontology_id: "o", partial: true } },
      { type: "sleep", ms: 5000 },
    ],
    timeoutMs: 300,
  });
  const failed = run.sessions.get("work-unit-modeler");
  failed.sendPrompt("p", "model unit u");
  await waitForExit(failed);
  assert.equal(failed.exited, true);
  // Partial artifact must not be accepted (role never settled).
  await assert.rejects(
    () => run.acceptArtifact("work-unit-modeler", "artifacts/unit-u.json"),
    /unsettled role/,
  );
  const events = await readEvents(workDir);
  assert.ok(!events.some((entry) => entry.class === "artifact_accepted"));
  // Release the dead session so the same role can be rerun against the same unit.
  await run.stopRole("work-unit-modeler");

  // Rerun the SAME unit with a fresh session that completes; it is accepted this time.
  await startFakeRole({
    run,
    role: "work-unit-modeler",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "event", record: { type: "agent_end" } },
      { type: "event", record: { type: "agent_settled" } },
      { type: "idle" },
      { type: "queue", length: 0 },
      { type: "artifact", name: "unit-u", json: { ontology_id: "o", items: [] } },
    ],
    timeoutMs: 6000,
  });
  await run.driveRole("work-unit-modeler", "model unit u again");
  const accepted = await run.acceptArtifact("work-unit-modeler", "artifacts/unit-u.json", {
    requiredKeys: ["ontology_id"],
  });
  assert.equal(accepted.artifact.ontology_id, "o");
  await run.dispose();
});

test("coordinator process loss starts a new process against stable files with no restore claim", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  const first = await startFakeRole({
    run,
    role: "coordinator",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "event", record: { type: "agent_end" } },
      { type: "event", record: { type: "agent_settled" } },
      { type: "idle" },
      { type: "queue", length: 0 },
    ],
    timeoutMs: 6000,
    persistent: true,
  });
  first.sendPrompt("turn-1", "advance");
  await first.awaitSettlement();
  // Per-turn settlement must NOT end the persistent coordinator.
  assert.equal(run.sessions.has("coordinator"), true);
  // Simulate process loss: force-kill the coordinator.
  const lostPid = first.child.pid;
  await run.reclaimRole("coordinator", new Error("process lost"));
  assert.equal(run.sessions.has("coordinator"), false);

  // Restart a NEW coordinator process against the same stable run files.
  const restarted = await startFakeRole({
    run,
    role: "coordinator",
    workDir,
    steps: [
      { type: "event", record: { type: "agent_start" } },
      { type: "event", record: { type: "agent_end" } },
      { type: "event", record: { type: "agent_settled" } },
      { type: "idle" },
      { type: "queue", length: 0 },
    ],
    timeoutMs: 6000,
    persistent: true,
  });
  assert.notEqual(restarted.child.pid, lostPid);
  // The new session has no inherited hidden chat: its record buffer starts empty of prior turns.
  assert.ok(restarted.records.every((record) => record.type !== "agent_start" || record === restarted.records[0]));
  // Workflow terminal state lets the persistent coordinator finally stop.
  await run.markTerminal("completed");
  await run.stopRole("coordinator");
  await run.dispose();
});
