// Section B — role isolation and structured handoff.

import { test } from "node:test";
import assert from "node:assert/strict";

import { ROLE_TOOLS, ModelingRun, RunnerError } from "../src/runner.mjs";
import { makeRun, makeWorkDir, startFakeRole } from "./helpers.mjs";

const settle = () => [
  { type: "event", record: { type: "agent_start" } },
  { type: "event", record: { type: "agent_end" } },
  { type: "event", record: { type: "agent_settled" } },
  { type: "idle" },
  { type: "queue", length: 0 },
];

test("role tool inventories are distinct and the organizer cannot submit platform actions", () => {
  const tools = ROLE_TOOLS;
  assert.ok(!tools["business-organizer"].includes("submit_platform_action"));
  assert.ok(!tools["business-organizer"].includes("apply_next"));
  assert.ok(tools.coordinator.includes("submit_platform_action"));
  assert.ok(tools["work-unit-modeler"].includes("write_modeling_artifact"));
  assert.ok(!tools["work-unit-modeler"].includes("submit_platform_action"));
  // reviewer and summarizer have no platform action tool
  assert.ok(!tools["model-reviewer"].includes("submit_platform_action"));
  assert.deepEqual(tools["stage-summarizer"], ["write_modeling_artifact"]);
});

test("each role gets a distinct Pi session identity (pid) and prompt scope", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  const roles = ["coordinator", "business-organizer", "work-unit-modeler", "model-reviewer", "stage-summarizer"];
  const pids = new Set();
  for (const role of roles) {
    const session = await startFakeRole({
      run,
      role,
      workDir,
      steps: settle(),
      timeoutMs: 5000,
      persistent: role === "coordinator",
    });
    session.sendPrompt(`${role}-prompt`, `you are ${role}`);
    await session.awaitSettlement();
    assert.ok(session.child.pid > 0);
    pids.add(session.child.pid);
  }
  assert.equal(pids.size, roles.length, "each role has a distinct child pid");
  await run.dispose();
});

test("reviewer artifact carrying hidden transcript is rejected", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  await startFakeRole({
    run,
    role: "model-reviewer",
    workDir,
    steps: [
      ...settle(),
      {
        type: "artifact",
        name: "review",
        json: {
          verdict: "PASS",
          candidate_hash: "h",
          findings: [],
          next_action: "dry-run-next",
          transcript: "hidden modeler chat",
        },
      },
    ],
    timeoutMs: 5000,
  });
  await run.driveRole("model-reviewer", "review");
  await assert.rejects(
    () => run.acceptArtifact("model-reviewer", "artifacts/review.json", { forbiddenKeys: ["transcript"] }),
    (err) => err instanceof RunnerError && /forbidden key transcript/.test(err.message),
  );
  await run.dispose();
});

test("malformed and schema-mismatched artifacts are rejected; only valid ones are accepted", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  // missing artifact
  await startFakeRole({
    run,
    role: "work-unit-modeler",
    workDir,
    steps: settle(),
    timeoutMs: 5000,
  });
  await run.driveRole("work-unit-modeler", "model");
  await assert.rejects(
    () => run.acceptArtifact("work-unit-modeler", "artifacts/missing.json"),
    /artifact missing/,
  );
  // malformed artifact
  const { writeFile } = await import("node:fs/promises");
  const { join } = await import("node:path");
  await writeFile(join(workDir, "artifacts", "malformed.json"), "{not json", "utf-8");
  await assert.rejects(
    () => run.acceptArtifact("work-unit-modeler", "artifacts/malformed.json"),
    /artifact malformed/,
  );
  // valid artifact with required key accepted
  await startFakeRole({
    run,
    role: "business-organizer",
    workDir,
    steps: [...settle(), { type: "artifact", name: "brief", json: { fields: {}, confirmed_fields: [] } }],
    timeoutMs: 5000,
  });
  await run.driveRole("business-organizer", "organize");
  const accepted = await run.acceptArtifact("business-organizer", "artifacts/brief.json", {
    requiredKeys: ["fields", "confirmed_fields"],
  });
  assert.equal(accepted.artifact.confirmed_fields.length, 0);
  assert.ok(accepted.hash.length >= 8);
  await run.dispose();
});

test("artifact cannot be accepted from an unsettled role", async () => {
  const workDir = await makeWorkDir();
  const run = await makeRun(workDir);
  await startFakeRole({
    run,
    role: "work-unit-modeler",
    workDir,
    // agent_end but no settlement
    steps: [{ type: "event", record: { type: "agent_start" } }, { type: "event", record: { type: "agent_end" } }, { type: "exit", code: 0 }],
    timeoutMs: 5000,
  });
  const session = run.sessions.get("work-unit-modeler");
  session.sendPrompt("p", "model");
  await assert.rejects(() => session.awaitSettlement(), /before role settlement/);
  await assert.rejects(
    () => run.acceptArtifact("work-unit-modeler", "artifacts/whatever.json"),
    /unsettled role/,
  );
  await run.dispose();
});
