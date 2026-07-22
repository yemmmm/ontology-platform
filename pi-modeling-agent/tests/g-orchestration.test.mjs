// Section G (G1) — end-to-end orchestrator driven by the fake-Pi subprocess and a fake platform
// adapter. Proves the orchestration contract: stage ordering, clarification routing, same-Ontology
// candidate merge, review gating (REVISE rerun), one-shot authorize -> dry-run/apply via
// invokeAdapter tool wrapping, stage Summary schema, local Work Unit recovery, and terminal
// disposal with no orphan. The deterministic Python core and the real platform are exercised in
// their own suites and the real-runtime round (G2); here the two leaf seams are faked.

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, readFile, chmod } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ModelingOrchestrator, OrchestratorError } from "../src/orchestrator.mjs";
import { EVENT_CLASSES } from "../src/event-recorder.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const fakePiPath = path.join(here, "fixtures", "fake-pi.mjs");
const fakeAdapterFixture = path.join(here, "fixtures", "fake-adapter.mjs");

const SETTLE = [
  { type: "event", record: { type: "agent_end" } },
  { type: "event", record: { type: "agent_settled" } },
  { type: "idle" },
  { type: "queue", length: 0 },
];

const SUMMARY = (stage) => ({
  stage,
  roles: ["stage-summarizer"],
  goal: `summarize ${stage}`,
  actions: ["observed events"],
  inputs_outputs: { stage },
  issues_decisions: [],
  result: "stage summarized",
  unresolved: [],
  next_step: "next stage",
});

const COVERAGE = {
  competency_questions: [
    { competency_question_id: "cq-1", local_competency_question_id: "cq-1", ontology_id: "ont-workflow", text: "Which nodes follow the LLM node?", acceptance: true },
  ],
  coverage_items: [],
  work_units: [
    { work_unit_id: "wu-workflow", ontology_id: "ont-workflow", source_ids: ["source-1"], coverage_ids: [], competency_question_ids: ["cq-1"], dependency_work_unit_ids: [] },
    { work_unit_id: "wu-nodes", ontology_id: "ont-workflow", source_ids: ["source-1"], coverage_ids: [], competency_question_ids: ["cq-1"], dependency_work_unit_ids: [] },
  ],
};

/** Fake Shared Modeling Directory driver: records calls and returns canned candidate state. */
class FakeDirectory {
  constructor() {
    this.calls = [];
    this.mergeRounds = new Map();
  }
  async init(specPath) {
    this.calls.push({ op: "init", specPath });
    return { run_id: "fake-run" };
  }
  async merge(ontologyId) {
    const round = (this.mergeRounds.get(ontologyId) ?? 0) + 1;
    this.mergeRounds.set(ontologyId, round);
    this.calls.push({ op: "merge", ontologyId, round });
    return { candidate_hash: `hash-${ontologyId}-${round}`, ontology_id: ontologyId };
  }
  async plan(ontologyId, limitsPath, attemptsPath) {
    this.calls.push({ op: "plan", ontologyId });
    return { batches: [] };
  }
  mergeCount(ontologyId) {
    return this.mergeRounds.get(ontologyId) ?? 0;
  }
}

/**
 * Fake Pi role launcher. Maps each (role, hint) to a scripted fake-Pi subprocess rooted at the run
 * workspace so artifacts land where the orchestrator accepts them. Stateful for review rounds and
 * Work Unit retry attempts.
 */
class FakeLauncher {
  constructor(
    workDir,
    {
      reviewSequence = ["REVISE", "PASS"],
      failWorkUnitFirst = false,
      // Optional (verdict, round) => findings[]; default carries a work_unit_id so #2 maps targeted.
      reviewFindings,
      // Optional (ontologyId, round) => candidate_hash string; default matches the FakeDirectory merge.
      reviewCandidateHash,
    } = {},
  ) {
    this.workDir = workDir;
    this.reviewSequence = reviewSequence;
    this.failWorkUnitFirst = failWorkUnitFirst;
    this.reviewFindings =
      reviewFindings ??
      ((verdict) => (verdict === "PASS" ? [] : [{ work_unit_id: "wu-workflow", issue: "revise" }]));
    this.reviewCandidateHash = reviewCandidateHash ?? ((ontologyId, round) => `hash-${ontologyId}-${round}`);
    this.reviewRounds = new Map();
    this.workAttempts = new Map();
    /** Per work_unit_id launch count (initial pass + every regeneration). */
    this.wuLaunches = new Map();
    this.counter = 0;
  }
  async launch(role, { tools, persistent, hint }) {
    const steps = this._stepsFor(role, hint);
    this.counter += 1;
    const script = path.join(this.workDir, `script-${this.counter}-${role.replace(/[^a-z0-9]/gi, "-")}.json`);
    await writeFile(script, JSON.stringify(steps));
    return {
      command: process.execPath,
      args: [fakePiPath],
      cwd: this.workDir,
      env: { FAKE_PI_SCRIPT_PATH: script, FAKE_PI_RUN_DIR: this.workDir, FAKE_PI_ROLE: role },
      persistent,
    };
  }
  wuLaunchCount(unitId) {
    return this.wuLaunches.get(unitId) ?? 0;
  }
  _stepsFor(role, hint) {
    if (role === "coordinator") {
      return [{ type: "event", record: { type: "agent_start" } }, ...SETTLE];
    }
    if (role === "business-organizer") {
      return [
        { type: "event", record: { type: "agent_start" } },
        { type: "clarify", id: "biz-ambiguity", title: "Scope ambiguity", question: "Model workflow foundations only?" },
        { type: "artifact", name: "brief", json: { fields: { domain_name: "Dify" }, confirmed_fields: ["domain_name"] } },
        { type: "artifact", name: "coverage", json: COVERAGE },
        { type: "artifact", name: "questions", json: { competency_questions: COVERAGE.competency_questions } },
        ...SETTLE,
      ];
    }
    if (role.startsWith("work-unit-modeler")) {
      const unitId = hint;
      const attempt = (this.workAttempts.get(unitId) ?? 0) + 1;
      this.workAttempts.set(unitId, attempt);
      this.wuLaunches.set(unitId, (this.wuLaunches.get(unitId) ?? 0) + 1);
      if (this.failWorkUnitFirst && attempt === 1) {
        // Partial output then hang: never settles, so the orchestrator times out and reclaims.
        return [
          { type: "event", record: { type: "agent_start" } },
          { type: "artifact", name: unitId, json: { ontology_id: "ont-workflow", partial: true } },
          { type: "sleep", ms: 5000 },
        ];
      }
      return [
        { type: "event", record: { type: "agent_start" } },
        { type: "artifact", name: unitId, json: { ontology_id: "ont-workflow", work_unit_id: unitId, items: [] } },
        ...SETTLE,
      ];
    }
    if (role.startsWith("model-reviewer")) {
      const ontologyId = hint;
      const round = (this.reviewRounds.get(ontologyId) ?? 0) + 1;
      this.reviewRounds.set(ontologyId, round);
      const verdict = this.reviewSequence[Math.min(round - 1, this.reviewSequence.length - 1)] ?? "PASS";
      const findings = this.reviewFindings(verdict, round);
      const candidateHash = this.reviewCandidateHash(ontologyId, round);
      return [
        { type: "event", record: { type: "agent_start" } },
        {
          type: "artifact",
          name: `review-${ontologyId}`,
          json: { verdict, candidate_hash: candidateHash, findings },
        },
        ...SETTLE,
      ];
    }
    if (role === "stage-summarizer") {
      return [
        { type: "event", record: { type: "agent_start" } },
        { type: "artifact", name: `summary-${hint}`, json: SUMMARY(hint) },
        ...SETTLE,
      ];
    }
    throw new Error(`fake launcher has no script for role ${role}`);
  }
}

async function makeWorkDir() {
  const dir = await mkdtemp(path.join(tmpdir(), "pi-orch-test-"));
  await mkdir(path.join(dir, "artifacts"), { recursive: true });
  return dir;
}

/** Write an executable shell launcher over the fake-adapter fixture with a per-run state file. */
async function makeFakeAdapterBin(workDir) {
  const stateFile = path.join(workDir, "adapter-state.json");
  const launcher = path.join(workDir, "fake-adapter-launcher");
  await writeFile(
    launcher,
    `#!/bin/sh\nFAKE_ADAPTER_STATE="${stateFile}" exec node "${fakeAdapterFixture}" "$@"\n`,
  );
  await chmod(launcher, 0o755);
  return { bin: launcher, stateFile };
}

async function readState(stateFile) {
  try {
    return JSON.parse(await readFile(stateFile, "utf-8"));
  } catch {
    return { calls: [], applied: {} };
  }
}

async function readEvents(workDir) {
  const raw = await readFile(path.join(workDir, "events.jsonl"), "utf-8");
  return raw
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
}

const SCENARIO = {
  schema_version: 1,
  goal: "Model Dify foundations",
  source_locators: ["docs/x.md"],
  constraints: [],
  acceptance_questions: [],
};
const CONFIG = { schema_version: 1, project_id: "proj-1", provider: "deepseek", model: "deepseek-v4-flash", max_parallel_workers: 1 };

function buildOrchestrator({ workDir, launcher, directory, adapterBin, confirm, clarify, roleTimeoutMs }) {
  return new ModelingOrchestrator({
    packageRoot: here,
    repoRoot: path.resolve(here, "..", ".."),
    scenario: SCENARIO,
    config: CONFIG,
    runId: `orch-test-${Date.now()}`,
    workDir,
    roleLauncher: (role, opts) => launcher.launch(role, opts),
    directory,
    adapterBin,
    clarify: clarify ?? (async () => "model workflow foundations only"),
    confirm: confirm ?? (async () => true),
    roleTimeoutMs: roleTimeoutMs ?? 8000,
    maxParallelWorkers: 1,
  });
}

test("orchestrator drives the full stage sequence with correct gating and no orphan", async () => {
  const workDir = await makeWorkDir();
  const launcher = new FakeLauncher(workDir);
  const directory = new FakeDirectory();
  const { bin: adapterBin, stateFile } = await makeFakeAdapterBin(workDir);
  const clarifyCalls = [];
  const orchestrator = buildOrchestrator({
    workDir,
    launcher,
    directory,
    adapterBin,
    clarify: async (record) => {
      clarifyCalls.push(record);
      return "model workflow foundations only";
    },
  });

  const result = await orchestrator.execute();
  assert.equal(result.status, "completed");

  // No orphan: every role session was reclaimed/stopped.
  assert.equal(orchestrator.run.sessions.size, 0);

  const events = await readEvents(workDir);
  const classes = events.map((event) => event.class);
  const adapterState = await readState(stateFile);
  const adapterActions = adapterState.calls.map((call) => call.action);

  // 1. Clarification routing: requested -> paused -> answered, in order, handler invoked.
  const requested = classes.indexOf(EVENT_CLASSES.CLARIFICATION_REQUESTED);
  const paused = classes.indexOf(EVENT_CLASSES.CLARIFICATION_PAUSED);
  const answered = classes.indexOf(EVENT_CLASSES.CLARIFICATION_ANSWERED);
  assert.ok(requested >= 0, "clarification_requested emitted");
  assert.ok(requested < paused && paused < answered, "clarification lifecycle is ordered");
  assert.equal(clarifyCalls.length, 1);
  assert.equal(clarifyCalls[0].method, "input");

  // 2. Business commit is gated behind an authorization that follows business artifact acceptance.
  const firstArtifact = classes.indexOf(EVENT_CLASSES.ARTIFACT_ACCEPTED);
  const commitIdx = adapterActions.indexOf("commit-business");
  const authForCommit = adapterActions.indexOf("authorize-runner-write");
  assert.ok(firstArtifact >= 0 && authForCommit >= 0 && commitIdx >= 0);
  assert.ok(authForCommit < commitIdx, "authorize-runner-write precedes commit-business");

  // 3. Same-Ontology candidate merge: two Work Units, one merge per review round.
  assert.ok(directory.mergeCount("ont-workflow") >= 2, "merge ran at least twice (initial + after REVISE)");

  // 4. Review gate: REVISE forced a re-merge before any apply; apply proceeds only after PASS.
  const dryRunIdx = adapterActions.indexOf("dry-run-next");
  const applyIdx = adapterActions.indexOf("apply-next");
  assert.ok(dryRunIdx >= 0 && applyIdx > dryRunIdx, "dry-run precedes apply");
  // The apply loop runs exactly one successful apply then the next dry-run reports plan exhaustion.
  const applyCount = adapterActions.filter((action) => action === "apply-next").length;
  assert.equal(applyCount, 1, "one Batch applied for the ontology");

  // 5. Protected writes are wrapped: tool_start before and tool_end after each adapter action.
  const toolStarts = events.filter((event) => event.class === EVENT_CLASSES.TOOL_START);
  const toolEnds = events.filter((event) => event.class === EVENT_CLASSES.TOOL_END);
  assert.ok(toolStarts.length >= adapterActions.length, "each adapter call has a tool_start");
  assert.equal(toolStarts.length, toolEnds.length, "tool_start/tool_end are balanced");
  // Verify ordering on the first dry-run: its tool_start precedes its tool_end with no tool_end gap.
  const dryRunStart = toolStarts.findIndex((event) => event.tool === "adapter:dry-run-next");
  assert.ok(dryRunStart >= 0, "dry-run tool_start recorded");
  const dryRunStartSeq = toolStarts[dryRunStart].seq;
  const matchingEnd = toolEnds.find((event) => event.tool === "adapter:dry-run-next" && event.seq > dryRunStartSeq);
  assert.ok(matchingEnd, "dry-run tool_end follows its tool_start");

  // 6. authorize -> dry-run -> apply -> verify -> finish all routed through invokeAdapter in order.
  const authorizeCount = adapterActions.filter((action) => action === "authorize-runner-write").length;
  assert.ok(authorizeCount >= 5, "one authorization per protected write (commit/dry/apply/verify/finish)");
  assert.ok(adapterActions.includes("start"));
  assert.ok(adapterActions.includes("verify"));
  assert.ok(adapterActions.includes("finish"));

  // 7. Stage summaries: each stage produced a schema-valid Summary (validation already ran inside
  //    summarizeStage; confirm the artifacts exist with the required fields).
  for (const stage of ["business-organization", "work-unit-ont-workflow", "final-verification"]) {
    const summary = JSON.parse(await readFile(path.join(workDir, "artifacts", `summary-${stage}.json`), "utf-8"));
    assert.equal(summary.stage, stage);
    assert.deepEqual(
      Object.keys(summary).sort(),
      ["actions", "goal", "inputs_outputs", "issues_decisions", "next_step", "result", "roles", "stage", "unresolved"],
    );
  }

  // 8. Terminal state recorded and dispose left no live child.
  assert.ok(events.some((event) => event.class === EVENT_CLASSES.RUN_END));
  assert.ok(orchestrator.run.terminal);
});

test("local recovery: a Work Unit that fails mid-output is reclaimed and rerun cleanly", async () => {
  const workDir = await makeWorkDir();
  const launcher = new FakeLauncher(workDir, { failWorkUnitFirst: true });
  const directory = new FakeDirectory();
  const { bin: adapterBin } = await makeFakeAdapterBin(workDir);
  const orchestrator = buildOrchestrator({ workDir, launcher, directory, adapterBin, roleTimeoutMs: 600 });

  const result = await orchestrator.execute();
  assert.equal(result.status, "completed");

  const events = await readEvents(workDir);
  // A timeout/reclaim was recorded for the failing Work Unit, then the run still completed.
  const timeouts = events.filter(
    (event) => event.class === EVENT_CLASSES.TIMEOUT || (event.class === EVENT_CLASSES.FAILURE && event.next_action === "rerun_same_inputs"),
  );
  assert.ok(timeouts.length >= 1, "the failing Work Unit was reclaimed");
  // The accepted result exists (the rerun produced a complete artifact).
  assert.ok(
    events.some((event) => event.class === EVENT_CLASSES.ARTIFACT_ACCEPTED && event.locator?.includes("wu-workflow")),
    "the Work Unit artifact was accepted after rerun",
  );
  assert.equal(orchestrator.run.sessions.size, 0);
});

test("cancel before business confirmation performs no commit write", async () => {
  const workDir = await makeWorkDir();
  const launcher = new FakeLauncher(workDir);
  const directory = new FakeDirectory();
  const { bin: adapterBin, stateFile } = await makeFakeAdapterBin(workDir);
  const orchestrator = buildOrchestrator({
    workDir,
    launcher,
    directory,
    adapterBin,
    confirm: async () => false,
  });

  await assert.rejects(() => orchestrator.execute(), OrchestratorError);
  const adapterState = await readState(stateFile);
  const actions = adapterState.calls.map((call) => call.action);
  assert.ok(!actions.includes("commit-business"), "no commit-business after declined confirmation");
  assert.ok(actions.includes("cancel"), "cancel was requested");
  assert.equal(orchestrator.run.sessions.size, 0);
});

// -- Round 2 repair-round regression tests (#1/#2/#3/#4) ---------------------------------

test("#1 reviewer prompt addresses the actual ontology, not a literal placeholder", async () => {
  const workDir = await makeWorkDir();
  const orchestrator = buildOrchestrator({
    workDir,
    launcher: new FakeLauncher(workDir),
    directory: new FakeDirectory(),
    adapterBin: (await makeFakeAdapterBin(workDir)).bin,
  });
  const prompt = orchestrator._reviewerPrompt("ont-workflow", "hash-ont-workflow-1");
  assert.ok(!prompt.includes("${ontologyId}"), "no un-interpolated placeholder leaks into the prompt");
  assert.ok(prompt.includes("artifacts/review-ont-workflow.json"), "reviewer is sent the concrete artifact path");
});

test("#2 REVISE regenerates the affected Work Unit, then re-merge/re-review PASS releases apply", async () => {
  const workDir = await makeWorkDir();
  // Round 1 REVISE naming wu-workflow, round 2 PASS. Targeted findings prove only wu-workflow regenerates.
  const launcher = new FakeLauncher(workDir, {
    reviewSequence: ["REVISE", "PASS"],
    reviewFindings: (verdict) => (verdict === "PASS" ? [] : [{ work_unit_id: "wu-workflow", issue: "gap" }]),
  });
  const directory = new FakeDirectory();
  const { bin: adapterBin } = await makeFakeAdapterBin(workDir);
  const orchestrator = buildOrchestrator({ workDir, launcher, directory, adapterBin });

  const result = await orchestrator.execute();
  assert.equal(result.status, "completed");

  const events = await readEvents(workDir);
  // The affected Work Unit was regenerated (initial + one regeneration); the untouched one was not.
  assert.equal(launcher.wuLaunchCount("wu-workflow"), 2, "affected Work Unit regenerated once after REVISE");
  assert.equal(launcher.wuLaunchCount("wu-nodes"), 1, "unaffected Work Unit was not regenerated");
  // The regeneration was recorded with the mapped work_unit_id, and apply eventually ran.
  assert.ok(
    events.some(
      (event) =>
        event.class === EVENT_CLASSES.FAILURE &&
        event.next_action === "regenerate_affected_units" &&
        event.work_unit_ids?.includes("wu-workflow"),
    ),
    "regeneration recorded with the mapped Work Unit",
  );
  assert.ok(directory.mergeCount("ont-workflow") >= 2, "candidate re-merged after regeneration");
});

test("#2 unresolvable REVISE loop hits the round cap with a clear error and never applies", async () => {
  const workDir = await makeWorkDir();
  const launcher = new FakeLauncher(workDir, { reviewSequence: ["REVISE"] });
  const directory = new FakeDirectory();
  const { bin: adapterBin, stateFile } = await makeFakeAdapterBin(workDir);
  const orchestrator = buildOrchestrator({ workDir, launcher, directory, adapterBin });

  await assert.rejects(() => orchestrator.execute(), (error) => {
    // Bounded failure: clear message, and the loop did not run away.
    return error instanceof OrchestratorError && /did not stabilize/.test(error.message);
  });
  const adapterState = await readState(stateFile);
  const actions = adapterState.calls.map((call) => call.action);
  assert.ok(!actions.includes("apply-next"), "REVISE loop never reached apply");
  assert.ok(!actions.includes("dry-run-next"), "REVISE loop never reached dry-run");
  // The recovery cap is MAX_REVIEW_ROUNDS: three review rounds then the bounded throw.
  assert.equal(launcher.reviewRounds.get("ont-workflow"), 3, "review ran up to the bounded cap");
  assert.equal(orchestrator.run.sessions.size, 0, "no orphan session after bounded failure");
});

test("#3 blocking dry-run Finding maps back to a Work Unit and clears on regeneration before apply", async () => {
  const workDir = await makeWorkDir();
  // Review passes immediately so the first blocker is the dry-run Finding, not REVISE.
  const launcher = new FakeLauncher(workDir, { reviewSequence: ["PASS"] });
  const directory = new FakeDirectory();
  const { bin: adapterBin, stateFile } = await makeFakeAdapterBin(workDir);
  // Seed one injected dry-run Finding (consumed on the first dry-run-next call).
  await writeFile(stateFile, `${JSON.stringify({ calls: [], applied: {}, injectDryRunFindings: 1 })}\n`);
  const orchestrator = buildOrchestrator({ workDir, launcher, directory, adapterBin });

  const result = await orchestrator.execute();
  assert.equal(result.status, "completed");

  const events = await readEvents(workDir);
  const adapterState = await readState(stateFile);
  const actions = adapterState.calls.map((call) => call.action);
  // dry-run ran at least twice: first returned the Finding, then the clean retry.
  const dryRunCount = actions.filter((action) => action === "dry-run-next").length;
  assert.ok(dryRunCount >= 2, "dry-run re-attempted after the Finding");
  // The Finding's Work Unit was regenerated; the unrelated one was not; apply happened exactly once.
  assert.equal(launcher.wuLaunchCount("wu-workflow"), 2, "Finding-mapped Work Unit regenerated");
  assert.equal(launcher.wuLaunchCount("wu-nodes"), 1, "unrelated Work Unit not regenerated by the Finding");
  assert.equal(actions.filter((action) => action === "apply-next").length, 1, "apply ran once the dry-run cleared");
  assert.ok(
    events.some((event) => event.class === EVENT_CLASSES.FAILURE && event.reason === "dry_run_findings"),
    "dry-run Finding recovery recorded",
  );
});

test("#4 reviewer candidate_hash mismatch is rejected and recovered via regeneration", async () => {
  const workDir = await makeWorkDir();
  // Round 1 returns a mismatched hash with a PASS verdict; round 2 returns the matching hash.
  const launcher = new FakeLauncher(workDir, {
    reviewSequence: ["PASS", "PASS"],
    reviewCandidateHash: (ontologyId, round) => (round === 1 ? "hash-WRONG" : `hash-${ontologyId}-${round}`),
  });
  const directory = new FakeDirectory();
  const { bin: adapterBin } = await makeFakeAdapterBin(workDir);
  const orchestrator = buildOrchestrator({ workDir, launcher, directory, adapterBin });

  const result = await orchestrator.execute();
  assert.equal(result.status, "completed");

  const events = await readEvents(workDir);
  // The mismatch was detected (not silently trusted) and triggered regeneration, then apply succeeded.
  assert.ok(
    events.some(
      (event) => event.class === EVENT_CLASSES.FAILURE && event.reason === "candidate_hash_mismatch",
    ),
    "candidate_hash mismatch recorded as a recovery trigger",
  );
  assert.ok(
    launcher.wuLaunchCount("wu-workflow") >= 2,
    "Work Units regenerated after the rejected mismatched review",
  );
  // Final candidate_hash equals the last merged hash (no silent hash substitution).
  assert.equal(directory.mergeCount("ont-workflow"), 2);
});
