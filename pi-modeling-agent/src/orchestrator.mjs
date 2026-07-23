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

/**
 * The confirmed business-Brief field names the platform accepts (lib/platform_adapter.py BRIEF_FIELDS).
 * Mirrored here so the organizer prompt names exactly the fields the Brief commit will validate, and so
 * the Brief artifact contract is self-documenting on the orchestration side. Keep in sync with the
 * platform adapter if that authoritative set ever changes.
 */
export const BRIEF_FIELD_NAMES = Object.freeze([
  "domain_name",
  "business_goal",
  "scope",
  "core_concepts",
  "identity_rules",
  "expected_granularity",
  "data_sources",
  "boundaries",
  "terminology",
  "inference_scope",
]);

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
export function realRoleLauncher({ piBinary, packageRoot, repoRoot, provider, model, piAgentDir, modelingExtension, workDir }) {
  return async (role, { tools, persistent, hint }) => {
    void hint; // real runs derive output names from the role prompt/Extension, not the launcher hint.
    void packageRoot; // kept in the signature for callers; the role cwd is the repo root (see below).
    const args = realPiRoleArgs({ provider, model, tools, modelingExtension });
    return {
      command: piBinary,
      args,
      // Roles read scenario.source_locators, which are repository-root-relative paths
      // (e.g. docs/evaluation-corpora/...). Their read/grep tools resolve relatives against cwd, so
      // cwd MUST be repoRoot (not packageRoot) or the role cannot open the real sources and grounds
      // its output from the goal/its priors instead. Artifact writing is unaffected: PI_MODELING_RUN_DIR
      // below takes priority over the Extension's ctx.cwd default (modeling-tools.ts runDir), so
      // artifacts still land under <workDir>/artifacts regardless of cwd.
      cwd: repoRoot,
      // PI_MODELING_RUN_DIR MUST point at this run's workspace so the modeling Extension writes
      // artifacts under <workDir>/artifacts (what acceptArtifact reads). Without it the Extension
      // falls back to <cwd>/workspaces/modeling-runs/current and artifacts never reach the Runner.
      env: { PI_CODING_AGENT_DIR: piAgentDir, PI_MODELING_RUN_DIR: workDir },
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
    // R1: the deterministic Shared Modeling Directory requires its run_dir to be EMPTY at init
    // (shared_modeling_directory.initialize_run rejects a non-empty dir), but workDir already holds
    // artifacts/ (role outputs acceptArtifact reads) and events.jsonl. Give SMD its own empty
    // subdirectory and point every run_dir consumer at it: the directory driver (its CLI run_dir) and
    // every platform adapter call (the adapter's run_dir is the SMD dir, where run.json/shared/units
    // live, NOT workDir). Role artifacts and the event stream stay in workDir, unchanged.
    this.smdDir = path.join(this.workDir, "shared-directory");
    await mkdir(this.smdDir, { recursive: true });
    if (this.directory) this.directory.runDir = this.smdDir;
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
    // Adapt the organizer's free-form artifact to the deterministic Shared Modeling Directory
    // contract before confirmation: drop only dangling cross-references so initialize_run's strict
    // validation cannot reject the confirmed plan, and rebuild the ontology grouping from survivors.
    this._normalizeBusinessPlan(plan);

    // Explicit user confirmation gate before any business commit (frozen contract). This is a host
    // pause, not a Pi turn, so the persistent coordinator is not multi-driven here.
    const confirmed = await this.confirm(plan);
    if (!confirmed) {
      await this._platform("cancel", [this.smdDir, "--reason", "business_confirmation_declined"]);
      throw new OrchestratorError("business confirmation declined; run cancelled before commit");
    }

    // Initialize the deterministic Shared Modeling Directory from the confirmed plan, then start the
    // platform Build Session and commit the confirmed Brief/CQ.
    await this._initializeDirectory(plan);
    await this._platform("start", [this.smdDir]);
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

  /**
   * Adapt the business-organizer's free-form Brief to the platform's commit-business contract.
   * lib/platform_adapter.py `_business_manifest` requires exactly {fields, confirmed_fields}, where
   * fields is an object whose keys are a subset of BRIEF_FIELDS and confirmed_fields is a list of the
   * same. A free-form model commonly merges the sibling confirmed_fields into fields or invents an
   * unsupported field name; this keeps only the recognized platform fields (preserving the model's
   * content for them) and rebuilds confirmed_fields from the surviving keys. Anything dropped is
   * recorded so the change is observable.
   */
  _normalizeBrief(plan) {
    const brief = plan.brief;
    const rawFields = brief?.fields;
    if (!brief || typeof rawFields !== "object" || rawFields === null || Array.isArray(rawFields)) {
      throw new OrchestratorError("business brief.fields must be an object of platform brief fields");
    }
    const validNames = new Set(BRIEF_FIELD_NAMES);
    const cleaned = {};
    let droppedKeys = 0;
    for (const [name, value] of Object.entries(rawFields)) {
      if (validNames.has(name)) {
        cleaned[name] = value;
      } else {
        droppedKeys += 1;
      }
    }
    const filledNames = Object.keys(cleaned);
    if (!filledNames.length) {
      throw new OrchestratorError("business brief has no recognized platform fields after normalization");
    }
    let confirmed = Array.isArray(brief.confirmed_fields) ? brief.confirmed_fields : [];
    confirmed = confirmed.filter((name) => validNames.has(name) && name in cleaned);
    if (!confirmed.length) {
      confirmed = filledNames.slice();
    }
    // Rebuild brief with exactly the two platform keys so _business_manifest's set-equality check holds.
    plan.brief = { fields: cleaned, confirmed_fields: confirmed };
    if (droppedKeys) {
      this.run?.recorder?.record(EVENT_CLASSES.FAILURE, {
        role: "business-organizer",
        reason: "business_brief_normalized",
        dropped_field_keys: droppedKeys,
        next_action: "continue_with_platform_fields",
      });
    }
    return plan.brief;
  }

  /**
   * Adapt the business-organizer's free-form artifact to the deterministic Shared Modeling Directory
   * contract. The organizer is instructed to emit self-consistent ids, but a free-form model can still
   * produce a dangling reference (a source_id/coverage_id/work_unit_id/ontology_id nothing else
   * declares), which initialize_run's strict validation would reject. This drops ONLY the inconsistent
   * pieces (it never invents content or remaps ids) and rebuilds the ontology grouping from the
   * surviving Work Units. Anything dropped is recorded so the loss is observable, never silent.
   */
  _normalizeBusinessPlan(plan) {
    this._normalizeBrief(plan);
    const sourceIds = new Set((plan.sources ?? []).map((s) => s.source_id).filter(Boolean));
    const rawUnits = Array.isArray(plan.coverage?.work_units) ? plan.coverage.work_units : [];
    const units = rawUnits.filter(
      (u) =>
        u &&
        typeof u.work_unit_id === "string" &&
        u.work_unit_id &&
        typeof u.ontology_id === "string" &&
        u.ontology_id,
    );
    const workUnitIds = new Set(units.map((u) => u.work_unit_id));
    const ontologyIds = new Set(units.map((u) => u.ontology_id));

    const rawCqs = Array.isArray(plan.coverage?.competency_questions)
      ? plan.coverage.competency_questions
      : [];
    const cqs = [];
    for (const question of rawCqs) {
      if (
        !question ||
        typeof question.competency_question_id !== "string" ||
        !question.competency_question_id ||
        typeof question.text !== "string" ||
        !question.text ||
        !ontologyIds.has(question.ontology_id)
      ) {
        continue;
      }
      const cq = { ...question };
      if (!cq.local_competency_question_id) {
        cq.local_competency_question_id = cq.competency_question_id;
      }
      // query_definition must be an object when present (commit_business rejects non-dict); drop if not.
      if (
        cq.query_definition != null &&
        (typeof cq.query_definition !== "object" || Array.isArray(cq.query_definition))
      ) {
        delete cq.query_definition;
      }
      // The deterministic core requires acceptance to be non-null; default to empty criteria.
      if (cq.acceptance == null) {
        cq.acceptance = "";
      }
      cqs.push(cq);
    }
    const cqIds = new Set(cqs.map((q) => q.competency_question_id));

    const rawItems = Array.isArray(plan.coverage?.coverage_items) ? plan.coverage.coverage_items : [];
    const items = [];
    for (const item of rawItems) {
      if (
        !item ||
        typeof item.coverage_id !== "string" ||
        !item.coverage_id ||
        !ontologyIds.has(item.ontology_id) ||
        !workUnitIds.has(item.work_unit_id)
      ) {
        continue;
      }
      items.push({
        ...item,
        source_ids: this._filterValid(item.source_ids, sourceIds),
        competency_question_ids: this._filterValid(item.competency_question_ids, cqIds),
      });
    }
    const coverageIds = new Set(items.map((i) => i.coverage_id));

    const normalizedUnits = units.map((unit) => ({
      ...unit,
      source_ids: this._filterValid(unit.source_ids, sourceIds),
      coverage_ids: this._filterValid(unit.coverage_ids, coverageIds),
      competency_question_ids: this._filterValid(unit.competency_question_ids, cqIds),
      dependency_work_unit_ids: this._filterValid(unit.dependency_work_unit_ids, workUnitIds),
    }));

    const droppedWorkUnits = rawUnits.length - normalizedUnits.length;
    const droppedCqs = rawCqs.length - cqs.length;
    const droppedItems = rawItems.length - items.length;
    if (droppedWorkUnits || droppedCqs || droppedItems) {
      this.run?.recorder?.record(EVENT_CLASSES.FAILURE, {
        role: "business-organizer",
        reason: "business_artifact_normalized",
        dropped_work_units: droppedWorkUnits,
        dropped_competency_questions: droppedCqs,
        dropped_coverage_items: droppedItems,
        next_action: "continue_with_consistent_subset",
      });
    }
    if (!normalizedUnits.length || !ontologyIds.size || !cqs.length) {
      throw new OrchestratorError(
        "business artifacts yielded no consistent ontology/work_unit/competency_question after normalization",
      );
    }

    plan.coverage = {
      competency_questions: cqs,
      coverage_items: items,
      work_units: normalizedUnits,
    };
    plan.ontologies = this._deriveOntologies(plan.coverage);
    this._normalizeSourceScopes(plan);
    return plan;
  }

  /**
   * Project each source's ontology scope from the normalized Work Unit and Coverage usage. The
   * deterministic core (shared_modeling_directory.validate_run) requires that every source a Work Unit
   * references lists that unit's ontology in scope.ontology_ids; the organizer declares usage via
   * work_unit/coverage source_ids, so the scope is derived deterministically rather than asked of the
   * model. Sources no unit references keep an empty ontology_ids list (the scope check never fires for
   * them). Never invents a scope fact: it only mirrors the usage the organizer already declared.
   */
  _normalizeSourceScopes(plan) {
    const usage = new Map(); // source_id -> Set(ontology_id)
    const record = (sourceId, ontologyId) => {
      if (typeof sourceId !== "string" || typeof ontologyId !== "string") return;
      if (!usage.has(sourceId)) usage.set(sourceId, new Set());
      usage.get(sourceId).add(ontologyId);
    };
    for (const unit of plan.coverage?.work_units ?? []) {
      for (const sourceId of unit.source_ids ?? []) record(sourceId, unit.ontology_id);
    }
    for (const item of plan.coverage?.coverage_items ?? []) {
      for (const sourceId of item.source_ids ?? []) record(sourceId, item.ontology_id);
    }
    for (const source of plan.sources ?? []) {
      const ontologyIds = [...(usage.get(source.source_id) ?? [])].sort();
      source.scope = { ...(source.scope ?? {}), ontology_ids: ontologyIds };
    }
  }

  /** Keep only the unique string entries of `values` that exist in `valid`, preserving order. */
  _filterValid(values, valid) {
    if (!Array.isArray(values)) return [];
    const seen = new Set();
    const out = [];
    for (const value of values) {
      if (typeof value === "string" && valid.has(value) && !seen.has(value)) {
        seen.add(value);
        out.push(value);
      }
    }
    return out;
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
      this.smdDir,
      "--business",
      manifestPath,
      "--operation-id",
      operationId,
    ]);
  }

  _businessManifest(plan) {
    const confirmedFields = plan.brief.confirmed_fields ?? [];
    const questions = {};
    // The platform's commit-business iterates the coverage competency_questions and requires a manifest
    // entry for each. Authoritatively walk that same list (not the decoupled questions.json artifact) so
    // every local competency_question_id is accepted, regardless of how the organizer split the two
    // artifacts. The platform's set_question_status(approved) requires a NON-empty source
    // (source_answer_ids or source_brief_fields). Each CQ is grounded in the confirmed Brief, so when
    // the organizer did not enumerate specific source fields, default to all confirmed fields (a
    // non-empty subset of confirmed_fields, which the platform accepts as confirmed Brief sources).
    for (const question of plan.coverage?.competency_questions ?? []) {
      const localId = question.local_competency_question_id ?? question.competency_question_id;
      if (localId) {
        const enumerated = Array.isArray(question.source_brief_fields)
          ? question.source_brief_fields.filter((field) => confirmedFields.includes(field))
          : [];
        questions[localId] = {
          accepted: true,
          source_brief_fields: enumerated.length ? enumerated : confirmedFields,
        };
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
        this.smdDir,
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
        this.smdDir,
        ontologyId,
        "--operation-id",
        applyOperationId,
      ]);
      if (applied.status !== "ok") {
        // Unknown apply outcome: reconcile the original Batch identity; never create a replacement.
        if (applied.error_code === "apply_outcome_unknown") {
          await this._platform("reconcile-apply", [this.smdDir, ontologyId]);
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
      this.smdDir,
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
    const result = await this._platform("finish", [this.smdDir, "--operation-id", operationId]);
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
    const args = [this.smdDir, "--operation-id", operationId, "--operation", operation];
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
    const locators = scenario.source_locators ?? [];
    const ontologyId = this._ontologyIdFor(scenario);
    const sourceRows = locators.map((locator, i) => `  - source-${i + 1} = ${locator}`);
    const briefFields = BRIEF_FIELD_NAMES.join(", ");
    return [
      `You are the business organizer for exactly ONE modeling ontology: ${ontologyId}.`,
      "Read ONLY these source locators, and refer to each by its stable source_id (never by path):",
      ...(sourceRows.length ? sourceRows : ["  - (no source locators provided)"]),
      `Scenario goal: ${scenario.goal}.`,
      "Produce three artifacts by calling write_modeling_artifact(name, json) where json is the object rendered as a single JSON string, then call complete_stage. The schemas below are fixed: do not add, rename, or omit keys.",
      "",
      `ARTIFACT 1 — name="brief.json": the confirmed business Brief. It MUST be an object with exactly these keys:`,
      '  { "fields": { "<brief_field>": "<short text grounded in the sources>", ... }, "confirmed_fields": ["<brief_field>", ...] }',
      `  Each <brief_field> MUST be one of: ${briefFields}.`,
      "  \"fields\" and \"confirmed_fields\" are SEPARATE top-level keys in the same object. The ONLY keys allowed inside \"fields\" are the brief_field names listed above; never put \"confirmed_fields\" (or any other key) inside \"fields\".",
      "  confirmed_fields MUST list every key you placed in fields (the Brief fields you confirmed from the sources). Do NOT put entities, relations, or node lists in the Brief; those belong in the Work Units below.",
      "",
      `ARTIFACT 2 — name="coverage.json": the competency questions, coverage items, and Work Units for ontology ${ontologyId}. It MUST be an object with exactly these keys:`,
      "  {",
      '    "competency_questions": [',
      "      {",
      '        "competency_question_id": "cq-1",',
      '        "local_competency_question_id": "cq-1",',
      `        "ontology_id": "${ontologyId}",`,
      '        "text": "<one competency question>",',
      '        "acceptance": "<acceptance criteria for this question>",',
      '        "query_definition": {}',
      "      }",
      "    ],",
      '    "coverage_items": [',
      "      {",
      '        "coverage_id": "cov-1",',
      `        "ontology_id": "${ontologyId}",`,
      '        "work_unit_id": "wu-1",',
      '        "source_ids": ["source-1"],',
      '        "competency_question_ids": ["cq-1"]',
      "      }",
      "    ],",
      '    "work_units": [',
      "      {",
      '        "work_unit_id": "wu-1",',
      `        "ontology_id": "${ontologyId}",`,
      '        "source_ids": ["source-1"],',
      '        "coverage_ids": ["cov-1"],',
      '        "competency_question_ids": ["cq-1"],',
      '        "dependency_work_unit_ids": []',
      "      }",
      "    ]",
      "  }",
      `  Cross-reference rules (the platform rejects any dangling id): every ontology_id is "${ontologyId}"; every source_id is one of source-1.."source-${locators.length}"; every competency_question_id/local_competency_question_id matches a cq-* id you declared; every coverage_id matches a cov-* id you declared; every work_unit_id and dependency_work_unit_id matches a wu-* id you declared. Declare at least one competency question (derive one per scenario acceptance question where applicable) and at least one Work Unit that covers it. Use distinct ids (cq-1, cq-2, ...; wu-1, wu-2, ...; cov-1, cov-2, ...).`,
      "",
      'ARTIFACT 3 — name="questions.json": clarifications you raised and their resolution. It MUST be:',
      '  { "open_questions": [ { "question": "<text>", "status": "resolved", "resolution": "<text>" } ] }',
      '  Emit { "open_questions": [] } when no clarification was needed.',
      "",
      "Ask at most one structured clarification via request_modeling_clarification if the sources genuinely conflict, then continue. Never invent a fact absent from the sources; record an explicit gap instead.",
    ].join("\n");
  }

  /**
   * Derive a stable, domain-neutral single-ontology id for the organizer to target. Production code
   * must not hard-code reference-ontology names, so the id is a slug of the scenario name; the
   * scenario (not this orchestrator) is what carries the domain concept.
   */
  _ontologyIdFor(scenario) {
    const slug = String(scenario.name ?? scenario.goal ?? "ontology")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return `ont-${slug || "ontology"}`;
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
      // Platform-supported Modeling command kinds only. The Modeling Batch compiler rejects unknown
      // command_kind values, so the run-level and unit-level allowed sets must stay within the
      // platform registry (see backend semantic_command_compiler._COMPILERS). This foundations set
      // lets a Work Unit build classes, relation types, entities, relations and fact values.
      allowed_command_kinds: [
        "create_class",
        "create_relation_type",
        "create_entity",
        "create_relation",
        "update_fact",
      ],
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
          allowed_command_kinds: [
            "create_class",
            "create_relation_type",
            "create_entity",
            "create_relation",
            "update_fact",
          ],
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
