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
        { type: "artifact", name: "questions", json: { open_questions: [] } },
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

// -- G2 schema-contract regression: business-organizer artifact shape -------------------
// The G1 fake fixture happened to match the platform contract, so a free-form real model (G2) exposed
// a gap: the organizer prompt named no schema and acceptArtifact/_commitBusiness/_initializeDirectory
// diverged. These tests pin the unified contract: the prompt enumerates the platform Brief fields and a
// domain-neutral ontology id; normalization adapts a free-form artifact to the deterministic Shared
// Modeling Directory by dropping only dangling references; and the business manifest walks the coverage
// competency questions authoritatively (what commit_business validates), not the decoupled questions.json.

function bareOrchestrator() {
  // Pure-logic methods (_normalizeBusinessPlan/_businessManifest/_organizerPrompt/_ontologyIdFor) touch
  // none of the launch/directory/adapter leaves, so they can be null here; execute() is never called.
  return buildOrchestrator({ workDir: "/tmp/pi-schema-test", launcher: null, directory: null, adapterBin: "/tmp/pi-schema-test" });
}

test("organizer prompt pins the unified schema and a domain-neutral derived ontology id", () => {
  const orchestrator = bareOrchestrator();
  const scenario = {
    name: "Dify Foundations v1",
    goal: "Model Dify foundations",
    source_locators: ["docs/a.md", "docs/b.md"],
  };
  assert.equal(orchestrator._ontologyIdFor(scenario), "ont-dify-foundations-v1");
  const prompt = orchestrator._organizerPrompt(scenario);
  // Domain-neutral ontology id (slug of the scenario name, not a hard-coded reference-ontology name).
  assert.ok(prompt.includes("ont-dify-foundations-v1"));
  // Deterministic source_ids, one per locator.
  assert.ok(prompt.includes("source-1 = docs/a.md"));
  assert.ok(prompt.includes("source-2 = docs/b.md"));
  // Platform Brief fields enumerated so the model fills only accepted field names.
  for (const field of ["domain_name", "business_goal", "core_concepts", "boundaries", "inference_scope"]) {
    assert.ok(prompt.includes(field), `prompt names brief field ${field}`);
  }
  // All three artifacts named with their fixed shape.
  assert.ok(prompt.includes('name="brief.json"'));
  assert.ok(prompt.includes('name="coverage.json"'));
  assert.ok(prompt.includes('name="questions.json"'));
  assert.ok(prompt.includes('"confirmed_fields"'));
  assert.ok(prompt.includes('"work_units"'));
  assert.ok(prompt.includes('"coverage_items"'));
  assert.ok(prompt.includes('"competency_questions"'));
  assert.ok(prompt.includes('"open_questions"'));
});

test("normalizeBusinessPlan drops only dangling references and keeps the consistent subset", () => {
  const orchestrator = bareOrchestrator();
  const recorded = [];
  orchestrator.run = { recorder: { record: (cls, payload) => recorded.push({ cls, payload }) } };
  const plan = {
    brief: { fields: { domain_name: "Dify", scope: "foundations" }, confirmed_fields: ["domain_name", "scope"] },
    coverage: {
      competency_questions: [
        { competency_question_id: "cq-1", ontology_id: "ont-good", text: "Q1", acceptance: true },
        { competency_question_id: "cq-2", ontology_id: "ont-other", text: "Q2", acceptance: true }, // dropped: no unit declares ont-other
        { competency_question_id: "cq-3", ontology_id: "ont-good", acceptance: true }, // dropped: no text
      ],
      coverage_items: [
        {
          coverage_id: "cov-1",
          ontology_id: "ont-good",
          work_unit_id: "wu-1",
          source_ids: ["source-1", "source-bogus"],
          competency_question_ids: ["cq-1", "cq-missing"],
        },
        { coverage_id: "cov-2", ontology_id: "ont-good", work_unit_id: "wu-ghost" }, // dropped: unknown work_unit_id
      ],
      work_units: [
        {
          work_unit_id: "wu-1",
          ontology_id: "ont-good",
          source_ids: ["source-1", "source-bogus"],
          coverage_ids: ["cov-1", "cov-missing"],
          competency_question_ids: ["cq-1", "cq-missing"],
          dependency_work_unit_ids: ["wu-ghost"],
        },
        { ontology_id: "ont-good" }, // dropped: no work_unit_id
      ],
    },
    questions: { open_questions: [] },
    sources: [{ source_id: "source-1", locator: "docs/x.md", scope: {} }],
    ontologies: [{ ontology_id: "ont-good" }],
  };

  orchestrator._normalizeBusinessPlan(plan);

  // Survivors only.
  assert.deepEqual(
    plan.coverage.competency_questions.map((q) => q.competency_question_id),
    ["cq-1"],
  );
  assert.deepEqual(
    plan.coverage.work_units.map((u) => u.work_unit_id),
    ["wu-1"],
  );
  assert.deepEqual(
    plan.coverage.coverage_items.map((i) => i.coverage_id),
    ["cov-1"],
  );
  // References repaired to the consistent subset only.
  assert.deepEqual(plan.coverage.coverage_items[0].source_ids, ["source-1"]);
  assert.deepEqual(plan.coverage.coverage_items[0].competency_question_ids, ["cq-1"]);
  assert.deepEqual(plan.coverage.work_units[0].source_ids, ["source-1"]);
  assert.deepEqual(plan.coverage.work_units[0].coverage_ids, ["cov-1"]);
  assert.deepEqual(plan.coverage.work_units[0].competency_question_ids, ["cq-1"]);
  assert.deepEqual(plan.coverage.work_units[0].dependency_work_unit_ids, []);
  // local_competency_question_id defaulted; ontology regrouped from survivors.
  assert.equal(plan.coverage.competency_questions[0].local_competency_question_id, "cq-1");
  assert.deepEqual(plan.ontologies.map((o) => o.ontology_id), ["ont-good"]);
  assert.equal(plan.ontologies[0].work_units.length, 1);
  // Source ontology scope derived from the surviving Work Unit usage (platform validate_run requires it).
  assert.deepEqual(plan.sources[0].scope.ontology_ids, ["ont-good"]);
  // The drop is observable, not silent.
  const note = recorded.find((r) => r.payload?.reason === "business_artifact_normalized");
  assert.ok(note, "normalization recorded a failure note");
  assert.equal(note.payload.dropped_work_units, 1);
  assert.equal(note.payload.dropped_competency_questions, 2);
  assert.equal(note.payload.dropped_coverage_items, 1);
});

test("normalizeBusinessPlan throws when no consistent ontology/work_unit/question remains", () => {
  const orchestrator = bareOrchestrator();
  orchestrator.run = { recorder: { record() {} } };
  const plan = {
    brief: { fields: { domain_name: "x" }, confirmed_fields: ["domain_name"] },
    coverage: {
      competency_questions: [{ competency_question_id: "cq-1", ontology_id: "ont-missing", text: "Q" }],
      coverage_items: [],
      work_units: [],
    },
    questions: { open_questions: [] },
    sources: [],
    ontologies: [],
  };
  assert.throws(() => orchestrator._normalizeBusinessPlan(plan), OrchestratorError);
});

test("normalizeBusinessPlan derives each source ontology scope from declared Work Unit/Coverage usage", () => {
  const orchestrator = bareOrchestrator();
  orchestrator.run = { recorder: { record() {} } };
  const plan = {
    brief: { fields: { domain_name: "x" }, confirmed_fields: ["domain_name"] },
    coverage: {
      competency_questions: [
        { competency_question_id: "cq-1", ontology_id: "ont-a", text: "Q1", acceptance: true },
        { competency_question_id: "cq-2", ontology_id: "ont-b", text: "Q2", acceptance: true },
      ],
      coverage_items: [
        { coverage_id: "cov-1", ontology_id: "ont-a", work_unit_id: "wu-1", source_ids: ["source-1", "source-2"], competency_question_ids: ["cq-1"] },
        { coverage_id: "cov-2", ontology_id: "ont-b", work_unit_id: "wu-2", source_ids: ["source-2"], competency_question_ids: ["cq-2"] },
      ],
      work_units: [
        { work_unit_id: "wu-1", ontology_id: "ont-a", source_ids: ["source-1", "source-2"], coverage_ids: ["cov-1"], competency_question_ids: ["cq-1"], dependency_work_unit_ids: [] },
        { work_unit_id: "wu-2", ontology_id: "ont-b", source_ids: ["source-2"], coverage_ids: ["cov-2"], competency_question_ids: ["cq-2"], dependency_work_unit_ids: [] },
      ],
    },
    questions: { open_questions: [] },
    sources: [
      { source_id: "source-1", locator: "docs/a.md", scope: {} },
      { source_id: "source-2", locator: "docs/b.md", scope: {} },
      { source_id: "source-3", locator: "docs/c.md", scope: {} }, // unreferenced
    ],
    ontologies: [{ ontology_id: "ont-a" }, { ontology_id: "ont-b" }],
  };
  orchestrator._normalizeBusinessPlan(plan);
  const byId = Object.fromEntries(plan.sources.map((s) => [s.source_id, s.scope.ontology_ids]));
  // source-1 used only by ont-a; source-2 shared by both ontologies; source-3 unused -> empty.
  assert.deepEqual(byId["source-1"], ["ont-a"]);
  assert.deepEqual(byId["source-2"], ["ont-a", "ont-b"]);
  assert.deepEqual(byId["source-3"], []);
});

test("normalizeBusinessPlan adapts a free-form Brief to the platform _business_manifest contract", () => {
  const orchestrator = bareOrchestrator();
  const recorded = [];
  orchestrator.run = { recorder: { record: (cls, payload) => recorded.push({ cls, payload }) } };
  // Mirror the real free-form deviation observed from deepseek: confirmed_fields merged INTO fields,
  // plus an unsupported invented field key. The platform _business_manifest rejects both.
  const plan = {
    brief: {
      fields: {
        domain_name: "Dify",
        scope: "foundations",
        confirmed_fields: ["domain_name", "scope"],
        invented_field: "junk",
      },
      confirmed_fields: ["domain_name", "scope", "phantom"],
    },
    coverage: {
      competency_questions: [
        { competency_question_id: "cq-1", ontology_id: "ont-good", text: "Q1", acceptance: true },
      ],
      coverage_items: [],
      work_units: [{ work_unit_id: "wu-1", ontology_id: "ont-good" }],
    },
    questions: { open_questions: [] },
    sources: [],
    ontologies: [{ ontology_id: "ont-good" }],
  };

  orchestrator._normalizeBusinessPlan(plan);

  // brief rebuilt with exactly the two platform keys; spurious keys dropped; confirmed reconciled.
  assert.deepEqual(Object.keys(plan.brief).sort(), ["confirmed_fields", "fields"]);
  assert.deepEqual(Object.keys(plan.brief.fields).sort(), ["domain_name", "scope"]);
  assert.deepEqual(plan.brief.confirmed_fields, ["domain_name", "scope"]);
  const note = recorded.find((r) => r.payload?.reason === "business_brief_normalized");
  assert.ok(note, "brief normalization recorded");
  assert.equal(note.payload.dropped_field_keys, 2);
});

test("normalizeBusinessPlan throws when the Brief has no recognized platform field", () => {
  const orchestrator = bareOrchestrator();
  orchestrator.run = { recorder: { record() {} } };
  const plan = {
    brief: { fields: { only_invented: "x" }, confirmed_fields: [] },
    coverage: { competency_questions: [], coverage_items: [], work_units: [] },
    questions: { open_questions: [] },
    sources: [],
    ontologies: [],
  };
  assert.throws(() => orchestrator._normalizeBusinessPlan(plan), OrchestratorError);
});

test("businessManifest accepts every coverage competency question regardless of questions.json", () => {
  const orchestrator = bareOrchestrator();
  const plan = {
    brief: { fields: { domain_name: "Dify" }, confirmed_fields: ["domain_name"] },
    coverage: {
      competency_questions: [
        { competency_question_id: "cq-1", local_competency_question_id: "cq-1", ontology_id: "ont-good", text: "Q1", acceptance: true },
        { competency_question_id: "cq-2", local_competency_question_id: "cq-2", ontology_id: "ont-good", text: "Q2", acceptance: true },
      ],
      coverage_items: [],
      work_units: [{ work_unit_id: "wu-1", ontology_id: "ont-good" }],
    },
    // questions.json is decoupled from the manifest; commit_business validates coverage, not this.
    questions: { open_questions: [{ question: "unrelated", status: "open" }] },
    sources: [],
    ontologies: [{ ontology_id: "ont-good" }],
  };
  const manifest = orchestrator._businessManifest(plan);
  assert.deepEqual(Object.keys(manifest).sort(), ["brief", "questions"]);
  assert.deepEqual(Object.keys(manifest.questions).sort(), ["cq-1", "cq-2"]);
  assert.equal(manifest.questions["cq-1"].accepted, true);
  assert.equal(manifest.questions["cq-2"].accepted, true);
  assert.deepEqual(manifest.brief.fields, { domain_name: "Dify" });
  assert.deepEqual(manifest.brief.confirmed_fields, ["domain_name"]);
});
