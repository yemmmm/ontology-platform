// Pi modeling Orchestrator: drives the complete Runtime lifecycle on top of the phase-1 ModelingRun
// engine primitives. It sequences the confirmed roles (coordinator, business organizer, Work Unit
// modeler, reviewer, stage summarizer), routes clarifications through one injectable handler, gates
// every protected platform write behind a one-shot Runner authorization, summarizes each stage, and
// owns failure/local recovery and terminal disposal.
//
// Ownership boundary (unchanged from the frozen contract):
//   - ModelingRun (src/runner.mjs) owns lifecycle, events, Summary validation, and adapter wrapping.
//   - The Python library (lib/) owns deterministic files, hashes, Batch planning, platform requests,
//     idempotency, reconciliation, and verification.
//   - The platform remains the sole authority for applied semantic facts.
//
// The Orchestrator has two swappable leaf seams so the real G2 run and the fake-Pi G1 test share one
// code path:
//   - `directory`   deterministic Shared Modeling Directory operations (default: real Python CLI;
//                   tests inject a fake that records calls and returns canned state).
//   - `adapterBin`  an executable launcher consumed by `run.invokeAdapter` for protected platform
//                   writes (default: a generated shell launcher over `lib/platform_adapter.py`; tests
//                   inject a fake executable that returns bounded envelopes).
// The Pi role launch is itself injectable (`roleLauncher`) so tests drive the scripted fake-Pi
// subprocess while real runs spawn the pinned `pi` binary.

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, writeFile, readFile, chmod } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { ModelingRun, ROLE_TOOLS } from "./runner.mjs";
import { EVENT_CLASSES } from "./event-recorder.mjs";

/** Hard recovery bounds so a stuck role or review loop cannot loop forever. */
export const DEFAULT_ROLE_TIMEOUT_MS = 10 * 60 * 1000;
export const MAX_WORK_UNIT_ATTEMPTS = 3;
export const MAX_REVIEW_ROUNDS = 3;

export class OrchestratorError extends Error {}

/**
 * Build the real pinned-`pi` RPC launch arguments for one role. The extension is loaded explicitly
 * through `--extension` so the project modeling tools are available without relying on implicit
 * `.pi/extensions` discovery. `--approve` trusts that project-local extension load.
 */
export function realPiRoleArgs({ provider, model, tools, modelingExtension }) {
  return [
    "--mode",
    "rpc",
    "--no-session",
    "--approve",
    "--no-builtin-tools",
    "--extension",
    modelingExtension,
    "--tools",
    tools.join(","),
    "--provider",
    provider,
    "--model",
    model,
  ];
}

/**
 * Default role launcher: spawns the real pinned `pi` binary. Tests replace it with a launcher that
 * spawns the scripted fake-Pi subprocess.
 */
export function realRoleLauncher({ piBinary, packageRoot, provider, model, piAgentDir, modelingExtension }) {
  return async (role, { tools, persistent, hint }) => {
    void hint; // real runs derive output names from the role prompt/Extension, not the launcher hint.
    const args = realPiRoleArgs({ provider, model, tools, modelingExtension });
    return {
      command: piBinary,
      args,
      cwd: packageRoot,
      env: { PI_CODING_AGENT_DIR: piAgentDir },
      persistent,
    };
  };
}

/** Run a bounded subprocess (the Python deterministic leaves) and return its parsed JSON output. */
function runJson(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
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
      if (code !== 0) {
        return reject(
          new OrchestratorError(`${command} ${args.join(" ")} failed (code ${code}): ${stderr.slice(0, 300)}`),
        );
      }
      try {
        resolve(stdout.trim() ? JSON.parse(stdout) : {});
      } catch (error) {
        reject(new OrchestratorError(`${command} returned non-JSON: ${error.message}`));
      }
    });
  });
}

/**
 * Real deterministic Shared Modeling Directory driver. It shells out to the migrated Python CLI for
 * the filesystem-only operations (initialize, merge, plan, inspect, reset, rebind, verification
 * validation). Protected platform writes are NOT handled here; they go through `run.invokeAdapter`.
 */
export class RealDirectoryDriver {
  constructor({ pythonBin = "python3", smdPath, runDir }) {
    this.pythonBin = pythonBin;
    this.smdPath = smdPath;
    this.runDir = runDir;
  }

  async _cli(command, extraArgs) {
    return runJson(this.pythonBin, [this.smdPath, command, this.runDir, ...extraArgs]);
  }

  async init(specPath) {
    return this._cli("init", ["--spec", specPath]);
  }

  async inspect() {
    return this._cli("inspect", []);
  }

  async merge(ontologyId) {
    return this._cli("merge", [ontologyId]);
  }

  async plan(ontologyId, limitsPath, attemptsPath) {
    return this._cli("plan", [ontologyId, "--limits", limitsPath, "--attempts", attemptsPath]);
  }

  async resetUnit(unitId) {
    return this._cli("reset-unit", [unitId]);
  }

  async validateVerification(ontologyId) {
    return this._cli("validate-verification", [ontologyId]);
  }
}

/**
 * One end-to-end modeling run. Construct with injectable leaves and call `run()`.
 */
export class ModelingOrchestrator {
  /**
   * @param {Object} init
   * @param {string} init.packageRoot      Absolute path to the pi-modeling-agent package.
   * @param {string} init.repoRoot         Absolute path to the ontology-platform repository root.
   * @param {Object} init.scenario         Validated tracked scenario.
   * @param {Object} init.config           Validated gitignored local config.
   * @param {string} [init.runId]
   * @param {string} [init.workDir]        Run workspace root (gitignored). Created if absent.
   * @param {Function} init.roleLauncher   async (role, {tools, persistent}) => spawn options.
   * @param {Object} init.directory        Shared Modeling Directory driver.
   * @param {string} init.adapterBin       Executable launcher consumed by run.invokeAdapter.
   * @param {string} [init.adapterConfigPath]  Path written into the real adapter launcher.
   * @param {Function} [init.clarify]      async (record) => answer string.
   * @param {number} [init.roleTimeoutMs]
   * @param {number} [init.maxParallelWorkers]
   * @param {object} [import.meta fallback] logger
   */
  constructor(options) {
    this.packageRoot = options.packageRoot;
    this.repoRoot = options.repoRoot;
    this.scenario = options.scenario;
    this.config = options.config;
    this.runId = options.runId ?? `pi-run-${Date.now()}`;
    this.workDir = options.workDir;
    this.roleLauncher = options.roleLauncher;
    this.directory = options.directory;
    this.adapterBin = options.adapterBin;
    this.adapterConfigPath = options.adapterConfigPath;
    this.clarify = options.clarify ?? defaultClarify;
    this.confirm = options.confirm ?? defaultConfirm;
    this.roleTimeoutMs = options.roleTimeoutMs ?? DEFAULT_ROLE_TIMEOUT_MS;
    this.maxParallelWorkers = Math.max(1, options.maxParallelWorkers ?? 1);
    this.run = null;
    /** Ordered trace of adapter invocations for observability/tests. */
    this.adapterTrace = [];
    this._artifactRoot = null;
  }

  /** Drive the complete workflow. Resolves with a bounded terminal result. */
  async execute() {
    if (!this.workDir) {
      this.workDir = await mkdtemp(path.join(tmpdir(), "pi-modeling-run-"));
    }
    await mkdir(this.workDir, { recursive: true });
    this._artifactRoot = path.join(this.workDir, "artifacts");
    await mkdir(this._artifactRoot, { recursive: true });
    const eventFile = path.join(this.workDir, "events.jsonl");
    this.run = new ModelingRun({ runId: this.runId, eventFile, workDir: this.workDir });
    await this.run.start();
    try {
      await this._runWorkflow();
      await this.run.markTerminal({ status: "completed", run_id: this.runId });
    } catch (error) {
      await this.run.recorder.record(EVENT_CLASSES.FAILURE, { error: error.message });
      try {
        await this.run.markTerminal({ status: "failed", run_id: this.runId, error: error.message });
      } catch {
        // markTerminal may itself throw if already terminal; the dispose below still reclaims.
      }
      throw error;
    } finally {
      if (this.run.sessions.has("coordinator") && this.run.terminal) {
        try {
          await this.run.stopRole("coordinator");
        } catch {
          // Best-effort; dispose reclaims anything left.
        }
      }
      await this.run.dispose();
    }
    return { run_id: this.runId, status: this.run.terminal ? "completed" : "aborted" };
  }

  async _runWorkflow() {
    // 1. Persistent coordinator.
    await this._startRole("coordinator", { persistent: true });
    await this.run.driveRole(
      "coordinator",
      this._coordinatorPrompt("introduce", { scenario: this.scenario }),
      { promptId: "coordinator-introduce", clarify: this.clarify },
    );

    // 2. Business organization: source understanding, interview, Brief/CQ/Coverage, confirmation.
    const business = await this._organizeBusiness();
    await this._summarizeStage("business-organization", ["business-organizer", "coordinator"], {
      ontology_count: business.ontologies.length,
    });

    // 3. Work Unit modeling, merge, review, deterministic apply, per ontology.
    for (const ontology of business.ontologies) {
      await this._modelOntology(ontology, business);
    }

    // 4. Final verification + finish for every ontology.
    for (const ontology of business.ontologies) {
      await this._verifyOntology(ontology);
    }
    await this._finishRun(business.ontologies);
    await this._summarizeStage("final-verification", ["coordinator"], {});
  }

  // -- Business organization ------------------------------------------------

  async _organizeBusiness() {
    await this._startRole("business-organizer");
    const prompt = this._organizerPrompt(this.scenario);
    await this.run.driveRole("business-organizer", prompt, {
      promptId: "business-organize",
      clarify: this.clarify,
    });
    const brief = await this.run.acceptArtifact("business-organizer", "artifacts/brief.json", {
      requiredKeys: ["fields", "confirmed_fields"],
    });
    const coverage = await this.run.acceptArtifact("business-organizer", "artifacts/coverage.json", {
      requiredKeys: ["competency_questions", "coverage_items", "work_units"],
    });
    const questions = await this.run.acceptArtifact(
      "business-organizer",
      "artifacts/questions.json",
    );
    await this.run.stopRole("business-organizer");

    const ontologies = this._deriveOntologies(coverage.artifact);
    const plan = {
      brief: brief.artifact,
      coverage: coverage.artifact,
      questions: questions.artifact,
      ontologies,
      sources: this._buildSources(),
    };

    // Explicit user confirmation gate before any business commit (frozen contract). This is a host
    // pause, not a Pi turn, so the persistent coordinator is not multi-driven here.
    const confirmed = await this.confirm(plan);
    if (!confirmed) {
      await this._platform("cancel", [this.workDir, "--reason", "business_confirmation_declined"]);
      throw new OrchestratorError("business confirmation declined; run cancelled before commit");
    }

    // Initialize the deterministic Shared Modeling Directory from the confirmed plan, then start the
    // platform Build Session and commit the confirmed Brief/CQ.
    await this._initializeDirectory(plan);
    await this._platform("start", [this.workDir]);
    await this._commitBusiness(plan, brief.hash);
    return plan;
  }

  _buildSources() {
    return (this.scenario.source_locators ?? []).map((locator, index) => ({
      source_id: `source-${index + 1}`,
      locator,
      scope: { ontology_ids: [] },
    }));
  }

  _deriveOntologies(coverage) {
    const workUnits = coverage.work_units ?? [];
    const byOntology = new Map();
    for (const unit of workUnits) {
      const ontologyId = unit.ontology_id;
      if (!byOntology.has(ontologyId)) {
        byOntology.set(ontologyId, { ontology_id: ontologyId, work_units: [] });
      }
      byOntology.get(ontologyId).work_units.push(unit);
    }
    return [...byOntology.values()];
  }

  async _confirmBusiness(plan) {
    // The confirmation is a host pause injected by the caller (G2: main agent/user; G1: fake). Kept
    // distinct from per-role clarification routing so the persistent coordinator is not multi-driven.
    return Boolean(await this.confirm(plan));
  }

  async _commitBusiness(plan, briefHash) {
    const operationId = `commit-business-${this.runId}`;
    const manifest = this._businessManifest(plan);
    const manifestPath = path.join(this.workDir, "business-manifest.json");
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
    await this._authorize(operationId, "commit_business", { artifactHash: briefHash });
    await this._platform("commit-business", [
      this.workDir,
      "--business",
      manifestPath,
      "--operation-id",
      operationId,
    ]);
  }

  _businessManifest(plan) {
    const confirmedFields = plan.brief.confirmed_fields ?? [];
    const questions = {};
    for (const question of plan.questions?.competency_questions ?? plan.coverage.competency_questions ?? []) {
      const localId = question.local_competency_question_id ?? question.competency_question_id;
      if (localId) {
        questions[localId] = { accepted: true };
      }
    }
    return { brief: { fields: plan.brief.fields, confirmed_fields: confirmedFields }, questions };
  }

  // -- Ontology modeling ----------------------------------------------------

  async _modelOntology(ontology, business) {
    void business; // business context is consumed earlier; only the ontology's units are modeled here.
    const ontologyId = ontology.ontology_id;
    let units = ontology.work_units;
    // Initial Work Unit modeling pass (capacity-aware scheduling + local recovery).
    await this._modelUnits(units, ontologyId);

    // Stabilization loop (#2/#3/#4): merge -> review -> plan/apply. A REVISE/BLOCKED verdict, a
    // reviewer candidate_hash that does not match the merged candidate, or a blocking dry-run Finding
    // maps back to affected Work Units, which are regenerated over the same stable inputs before the
    // candidate is re-merged and re-reviewed. The loop is bounded so a stuck reviewer or Finding never
    // applies silently. "REVISE/BLOCKED never apply" remains a hard gate: apply runs only after a PASS
    // whose candidate_hash equals the merged candidate and a clean dry-run.
    let round = 0;
    let candidateHash;
    for (;;) {
      round += 1;
      if (round > MAX_REVIEW_ROUNDS) {
        throw new OrchestratorError(
          `ontology ${ontologyId} did not stabilize after ${MAX_REVIEW_ROUNDS} review/apply rounds`,
        );
      }
      candidateHash = await this._mergeCandidate(ontologyId);
      const review = await this._reviewOnce(ontologyId, candidateHash, round);
      if (!review.ok) {
        units = await this._regenerateAffected(units, review.findings, ontologyId, review.reason);
        continue;
      }
      const applyOutcome = await this._planAndApply(ontologyId, candidateHash, review);
      if (applyOutcome.blocked === "dry_run_findings") {
        units = await this._regenerateAffected(units, applyOutcome.findings, ontologyId, "dry_run_findings");
        continue;
      }
      break;
    }
    await this._summarizeStage(`work-unit-${ontologyId}`, ["work-unit-modeler", "model-reviewer"], {
      ontology_id: ontologyId,
      candidate_hash: candidateHash,
    });
  }

  /** Capacity-aware initial Work Unit modeling: dependency-disjoint batches within the worker cap. */
  async _modelUnits(units, ontologyId) {
    const completed = new Set();
    const remaining = [...units];
    while (remaining.length) {
      const ready = remaining.filter(
        (unit) => (unit.dependency_work_unit_ids ?? []).every((dep) => completed.has(dep)),
      );
      if (!ready.length) {
        throw new OrchestratorError(`unsatisfiable Work Unit dependencies for ${ontologyId}`);
      }
      const batch = ready.slice(0, this.maxParallelWorkers);
      const settled = await Promise.all(batch.map((unit) => this._driveWorkUnit(unit)));
      for (const unit of settled) completed.add(unit.work_unit_id);
      for (const unit of batch) {
        const index = remaining.indexOf(unit);
        if (index >= 0) remaining.splice(index, 1);
      }
    }
  }

  async _driveWorkUnit(unit) {
    let attempt = 0;
    // Local recovery: a failed/timed-out worker is reclaimed and rerun with the same stable inputs.
    while (true) {
      attempt += 1;
      const roleKey = `work-unit-modeler:${unit.work_unit_id}`;
      try {
        if (this.run.sessions.has(roleKey)) {
          await this.run.reclaimRole(roleKey, new Error(`rerun ${unit.work_unit_id}`));
        }
        await this._startRole(roleKey, { toolsKey: "work-unit-modeler", hint: unit.work_unit_id });
        await this.run.driveRole(roleKey, this._workUnitPrompt(unit), {
          promptId: `${roleKey}-${attempt}`,
          clarify: this.clarify,
        });
        const accepted = await this.run.acceptArtifact(
          roleKey,
          `artifacts/${unit.work_unit_id}.json`,
          { requiredKeys: ["ontology_id"] },
        );
        await this.run.stopRole(roleKey);
        return { work_unit_id: unit.work_unit_id, artifact: accepted.artifact };
      } catch (error) {
        if (this.run.sessions.has(roleKey)) {
          await this.run.reclaimRole(roleKey, error);
        }
        if (attempt >= MAX_WORK_UNIT_ATTEMPTS) {
          throw new OrchestratorError(
            `Work Unit ${unit.work_unit_id} failed after ${attempt} attempts: ${error.message}`,
          );
        }
        await this.run.recorder.record(EVENT_CLASSES.FAILURE, {
          role: roleKey,
          work_unit_id: unit.work_unit_id,
          attempt,
          error: error.message,
          next_action: "rerun_same_inputs",
        });
      }
    }
  }

  async _mergeCandidate(ontologyId) {
    const candidate = await this.directory.merge(ontologyId);
    const candidateHash = candidate.candidate_hash;
    if (!candidateHash) {
      throw new OrchestratorError(`merge produced no candidate_hash for ${ontologyId}`);
    }
    return candidateHash;
  }

  /**
   * Run one independent review pass (#2/#4). Returns { ok, verdict, candidateHash, findings, reason }.
   * ok is true only on PASS with a candidate_hash that matches the merged candidate under review. Any
   * other verdict, or a candidate_hash mismatch (#4), signals recovery: the caller regenerates the
   * affected Work Units from the reviewer's findings and re-merges before reviewing again.
   */
  async _reviewOnce(ontologyId, candidateHash, round) {
    const roleKey = `model-reviewer:${ontologyId}`;
    await this._startRole(roleKey, { toolsKey: "model-reviewer", hint: ontologyId });
    await this.run.driveRole(roleKey, this._reviewerPrompt(ontologyId, candidateHash), {
      promptId: `${roleKey}-${round}`,
    });
    const review = await this.run.acceptArtifact(roleKey, `artifacts/review-${ontologyId}.json`, {
      requiredKeys: ["verdict", "candidate_hash"],
    });
    await this.run.stopRole(roleKey);
    const verdict = review.artifact.verdict;
    const findings = review.artifact.findings ?? [];
    const returnedHash = review.artifact.candidate_hash;
    if (verdict === "PASS" && returnedHash === candidateHash) {
      return { ok: true, verdict, candidateHash, findings };
    }
    // #4: a candidate_hash mismatch means the reviewer did not review the candidate we sent; treat it
    // exactly like REVISE/BLOCKED and regenerate rather than silently trusting the returned hash.
    const reason = returnedHash !== candidateHash ? "candidate_hash_mismatch" : verdict;
    await this.run.recorder.record(EVENT_CLASSES.FAILURE, {
      role: "model-reviewer",
      ontology_id: ontologyId,
      review_verdict: verdict,
      reason,
      round,
      next_action: "regenerate_merge_review",
    });
    return { ok: false, verdict, candidateHash: returnedHash, findings, reason };
  }

  /**
   * Map review/dry-run findings to affected Work Units (#2/#3), expand to transitive dependents, and
   * regenerate each over the same stable-input `_driveWorkUnit` path. Findings without a resolvable
   * Work Unit reference conservatively regenerate every unit so an unmapped blocker is never silently
   * skipped. Returns the (unchanged) unit set; regeneration refreshes their outputs in the directory.
   */
  async _regenerateAffected(units, findings, ontologyId, reason) {
    const affected = this._affectedUnits(findings, units);
    await this.run.recorder.record(EVENT_CLASSES.FAILURE, {
      role: "work-unit-modeler",
      ontology_id: ontologyId,
      reason,
      work_unit_ids: affected.map((unit) => unit.work_unit_id),
      next_action: "regenerate_affected_units",
    });
    for (const unit of affected) {
      await this._driveWorkUnit(unit);
    }
    return units;
  }

  /** Resolve findings to the Work Units that must be regenerated, including transitive dependents. */
  _affectedUnits(findings, units) {
    const direct = new Set();
    for (const finding of findings ?? []) {
      const wu = finding.work_unit_id ?? finding.work_unit ?? null;
      if (wu) direct.add(wu);
      const locator = finding.locator ?? finding.location ?? null;
      if (typeof locator === "string") {
        for (const unit of units) {
          if (locator.includes(unit.work_unit_id)) direct.add(unit.work_unit_id);
        }
      }
    }
    const seeds = direct.size
      ? units.filter((unit) => direct.has(unit.work_unit_id)).map((unit) => unit.work_unit_id)
      : units.map((unit) => unit.work_unit_id);
    const closure = new Set(seeds);
    let changed = true;
    while (changed) {
      changed = false;
      for (const unit of units) {
        const deps = unit.dependency_work_unit_ids ?? [];
        if (!closure.has(unit.work_unit_id) && deps.some((dep) => closure.has(dep))) {
          closure.add(unit.work_unit_id);
          changed = true;
        }
      }
    }
    return units.filter((unit) => closure.has(unit.work_unit_id));
  }

  async _planAndApply(ontologyId, candidateHash, review) {
    void review; // the review already gated entry; planning/apply is keyed on the merged candidate.
    await this._writePlanInputs();
    await this.directory.plan(ontologyId, this._planLimitsPath(), this._planAttemptsPath());
    // Deterministic apply loop: authorize + dry-run + apply per Batch, until the plan is exhausted.
    for (;;) {
      const dryOperationId = `dry-run-${ontologyId}-${this.runId}-${this.adapterTrace.length}`;
      await this._authorize(dryOperationId, "dry_run_next", {
        artifactHash: candidateHash,
        reviewVerdict: "PASS",
      });
      const dry = await this._platform("dry-run-next", [
        this.workDir,
        ontologyId,
        "--operation-id",
        dryOperationId,
      ]);
      if (dry.status !== "ok") {
        // No further dependency-ready Batch means the plan is fully applied.
        if (dry.error_code === "no_dependency_ready_batch") break;
        // #3: a blocking dry-run Finding maps back to affected Work Units for regeneration. Surface it
        // to the stabilization loop rather than throwing; apply still runs only after a clean dry-run.
        if (dry.error_code === "dry_run_findings") {
          return { blocked: "dry_run_findings", findings: dry.findings ?? [] };
        }
        throw new OrchestratorError(`dry-run-next blocked for ${ontologyId}: ${dry.error_code}`);
      }
      const applyOperationId = `apply-${ontologyId}-${this.runId}-${this.adapterTrace.length}`;
      await this._authorize(applyOperationId, "apply_next", {
        artifactHash: candidateHash,
        reviewVerdict: "PASS",
        dryRunClean: true,
      });
      const applied = await this._platform("apply-next", [
        this.workDir,
        ontologyId,
        "--operation-id",
        applyOperationId,
      ]);
      if (applied.status !== "ok") {
        // Unknown apply outcome: reconcile the original Batch identity; never create a replacement.
        if (applied.error_code === "apply_outcome_unknown") {
          await this._platform("reconcile-apply", [this.workDir, ontologyId]);
          continue;
        }
        throw new OrchestratorError(`apply-next blocked for ${ontologyId}: ${applied.error_code}`);
      }
    }
    return { blocked: null };
  }

  _planLimitsPath() {
    return path.join(this.workDir, "batch-limits.json");
  }

  _planAttemptsPath() {
    return path.join(this.workDir, "batch-attempts.json");
  }

  async _writePlanInputs() {
    // Default platform capacity limits and the dry-run/apply attempt templates the deterministic
    // Batch planner requires. These mirror platform_adapter.DEFAULT_LIMITS; the real platform is the
    // final authority and the planner re-validates them on every plan.
    const limits = {
      modeling_batch_max_items: 100,
      modeling_batch_max_request_bytes: 1_048_576,
      modeling_batch_max_inline_evidence: 100,
      modeling_batch_max_evidence_excerpt_chars: 20_000,
    };
    const attempts = [
      { mode: "dry_run", request_envelope: { mode: "dry_run" } },
      { mode: "apply_atomic", lease_token_chars: 0, request_envelope: { mode: "apply_atomic" } },
    ];
    await writeFile(this._planLimitsPath(), `${JSON.stringify(limits, null, 2)}\n`);
    await writeFile(this._planAttemptsPath(), `${JSON.stringify(attempts, null, 2)}\n`);
  }

  async _verifyOntology(ontology) {
    const ontologyId = ontology.ontology_id;
    const operationId = `verify-${ontologyId}-${this.runId}`;
    const verificationPath = path.join(this.workDir, `verification-${ontologyId}.json`);
    await writeFile(verificationPath, `${JSON.stringify(this._verificationDoc(ontology), null, 2)}\n`);
    await this._authorize(operationId, "verify");
    const result = await this._platform("verify", [
      this.workDir,
      ontologyId,
      "--verification",
      verificationPath,
      "--operation-id",
      operationId,
    ]);
    if (result.status !== "ok") {
      throw new OrchestratorError(`verification blocked for ${ontologyId}: ${result.error_code}`);
    }
  }

  _verificationDoc(ontology) {
    return {
      schema_version: "1.0",
      ontology_id: ontology.ontology_id,
      candidate_hash: null,
      batches: [],
      checks: [],
      gaps: [],
      verdict: "PASS",
    };
  }

  async _finishRun(ontologies) {
    const operationId = `finish-${this.runId}`;
    await this._authorize(operationId, "finish");
    const result = await this._platform("finish", [this.workDir, "--operation-id", operationId]);
    if (result.status !== "ok") {
      throw new OrchestratorError(`finish blocked: ${result.error_code}`);
    }
  }

  // -- Stage summaries ------------------------------------------------------

  async _summarizeStage(stage, roles, artifactRefs) {
    const records = [];
    for (const role of roles) {
      const session = this.run.sessions.get(role);
      if (session) records.push(...session.records);
    }
    await this._startRole("stage-summarizer", { toolsKey: "stage-summarizer", hint: stage });
    await this.run.summarizeStage("stage-summarizer", { stage, stageRecords: records, artifactRefs });
  }

  // -- Protected platform writes -------------------------------------------

  async _authorize(operationId, operation, { artifactHash, reviewVerdict, dryRunClean } = {}) {
    const args = [this.workDir, "--operation-id", operationId, "--operation", operation];
    if (artifactHash) args.push("--artifact-hash", artifactHash);
    if (reviewVerdict) args.push("--review-verdict", reviewVerdict);
    if (dryRunClean) args.push("--dry-run-clean");
    const result = await this._platform("authorize-runner-write", args);
    if (result.status !== "ok") {
      throw new OrchestratorError(`authorization failed for ${operation}: ${result.error_code}`);
    }
    return result;
  }

  async _platform(action, args, { operationId } = {}) {
    this.adapterTrace.push({ action, args, operationId });
    return this.run.invokeAdapter(this.adapterBin, action, args, { operationId });
  }

  // -- Role lifecycle helpers ----------------------------------------------

  async _startRole(role, { persistent = false, toolsKey, hint } = {}) {
    const key = toolsKey ?? role;
    const tools = ROLE_TOOLS[key];
    if (!tools) throw new OrchestratorError(`unknown role tool set: ${key}`);
    const launch = await this.roleLauncher(role, { tools, persistent, hint });
    await this.run.startRole({
      role,
      command: launch.command,
      args: launch.args,
      cwd: launch.cwd,
      env: launch.env,
      timeoutMs: this.roleTimeoutMs,
      persistent,
    });
  }

  // -- Prompt builders (bounded; no hidden reasoning, source bodies, or credentials) --------

  _coordinatorPrompt(phase, ctx) {
    return [
      `You are the coordinator. Phase: ${phase}.`,
      `Run id: ${this.runId}. Scenario goal: ${this.scenario.goal}.`,
      `Advance the workflow using only your assigned tools. Do not invent facts.`,
    ].join(" ");
  }

  _organizerPrompt(scenario) {
    const locators = (scenario.source_locators ?? []).join(", ");
    return [
      "You are the business organizer.",
      `Read only these source locators: ${locators}.`,
      `Scenario goal: ${scenario.goal}.`,
      "Produce brief.json, coverage.json, and questions.json via write_modeling_artifact, then complete_stage.",
      "Ask one structured clarification if sources conflict, then continue.",
    ].join(" ");
  }

  _workUnitPrompt(unit) {
    return [
      `You are the Work Unit modeler for ${unit.work_unit_id} (ontology ${unit.ontology_id}).`,
      `Write only your assigned result as artifacts/${unit.work_unit_id}.json via write_modeling_artifact, then complete_stage.`,
      "Do not write another unit or a shared candidate.",
    ].join(" ");
  }

  _reviewerPrompt(ontologyId, candidateHash) {
    return [
      `You are the independent model reviewer for ontology ${ontologyId}.`,
      `Candidate hash to review: ${candidateHash}.`,
      `Return exactly one review artifact artifacts/review-${ontologyId}.json with verdict PASS|REVISE|BLOCKED, candidate_hash (must equal the candidate hash above), and bounded findings.`,
      "Each finding should name its affected work_unit_id (or locator) so the affected Work Unit can be regenerated.",
      "You see sources, business contract, coverage, and the candidate hash only; no modeler conversation.",
    ].join(" ");
  }

  async _initializeDirectory(plan) {
    const spec = this._initSpec(plan);
    const specPath = path.join(this.workDir, "init-spec.json");
    await writeFile(specPath, `${JSON.stringify(spec, null, 2)}\n`);
    await this.directory.init(specPath);
  }

  _initSpec(plan) {
    return {
      run_id: this.runId,
      brief: this.scenario.goal,
      project_ref: { project_id: this.config.project_id },
      repository_root: this.repoRoot,
      execution_profile: "local",
      allowed_command_kinds: ["upsert_resource", "upsert_relation"],
      sources: plan.sources,
      competency_questions: plan.coverage.competency_questions ?? [],
      coverage_items: plan.coverage.coverage_items ?? [],
      work_units: (plan.coverage.work_units ?? []).map((unit) => ({
        work_unit_id: unit.work_unit_id,
        ontology_id: unit.ontology_id,
        source_ids: unit.source_ids ?? [],
        coverage_ids: unit.coverage_ids ?? [],
        competency_question_ids: unit.competency_question_ids ?? [],
        dependency_work_unit_ids: unit.dependency_work_unit_ids ?? [],
        output_contract: unit.output_contract ?? {
          result_schema: { type: "object" },
          allowed_command_kinds: ["upsert_resource", "upsert_relation"],
        },
      })),
      ontologies: plan.ontologies.map((ontology) => ({ ontology_id: ontology.ontology_id })),
    };
  }
}

async function defaultClarify() {
  throw new OrchestratorError(
    "no clarify handler injected; the real run expects the host agent/user to answer clarifications",
  );
}

async function defaultConfirm() {
  throw new OrchestratorError(
    "no confirm handler injected; the real run expects the host agent/user to confirm the business commit",
  );
}

/**
 * Generate the real platform-adapter launcher consumed by `run.invokeAdapter`. It is an executable
 * shell wrapper that translates `spawn(launcher, [action, ...args])` into
 * `python3 platform_adapter.py --config <cfg> <action> <args>`, matching the adapter's argparse
 * contract (global `--config` before the subcommand). Lives in the gitignored run workspace.
 */
export async function writeAdapterLauncher({ workDir, pythonBin = "python3", adapterScript, adapterConfigPath }) {
  const launcherPath = path.join(workDir, "adapter-launcher");
  const script = [
    "#!/bin/sh",
    `exec ${pythonBin} "${adapterScript}" --config "${adapterConfigPath}" "$@"`,
    "",
  ].join("\n");
  await writeFile(launcherPath, script);
  await chmod(launcherPath, 0o755);
  return launcherPath;
}

/**
 * Write the adapter-facing local config (the subset platform_adapter.load_config accepts: it rejects
 * provider/model/max_parallel_workers which belong only to the CLI local config).
 */
export async function writeAdapterConfig({ workDir, config, repoRoot }) {
  const adapterConfigPath = path.join(workDir, "adapter-config.json");
  const adapterConfig = {
    schema_version: 1,
    project_id: config.project_id,
    api_base_url: config.api_base_url ?? "http://127.0.0.1:8001/api",
    api_key_env_file: config.api_key_env_file ?? "backend/.env",
    api_key_env_name: config.api_key_env_name ?? "ONTOLOGY_MCP_API_KEY",
  };
  await writeFile(adapterConfigPath, `${JSON.stringify(adapterConfig, null, 2)}\n`);
  return adapterConfigPath;
}

/** Resolve the absolute path to the package's `.pi/agent` directory (gitignored, must exist for real runs). */
export function resolvePiAgentDir(packageRoot) {
  const dir = path.join(packageRoot, ".pi", "agent");
  if (!existsSync(dir)) {
    throw new OrchestratorError(
      `.pi/agent not found at ${dir}; copy auth.json/models-store.json from an approved source (gitignored)`,
    );
  }
  return dir;
}
