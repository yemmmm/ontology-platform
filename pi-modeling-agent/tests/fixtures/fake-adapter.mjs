#!/usr/bin/env node
// Fake platform-adapter for the G1 orchestration test. It is spawned exactly like the real adapter
// launcher (`spawn(launcher, [action, ...args])`) and returns bounded ok/blocked envelopes so the
// orchestrator's protected-write gating and apply loop can be exercised without a real platform.
//
// State (one dry-run+apply cycle per ontology, then "plan exhausted") is kept in a JSON file named by
// FAKE_ADAPTER_STATE so successive subprocess invocations share it. Logs every call to that file too.
//
// argv shape (after the shebang exec): [node, this_script, action, ...args]
//   action = process.argv[2]

import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";

const action = process.argv[2] ?? "status";
const statePath = process.env.FAKE_ADAPTER_STATE;
const workDir = process.argv[3] ?? ".";

const envelope = (actionName, status, { refs, nextAction, error, findings } = {}) => ({
  schema_version: 1,
  action: actionName,
  status,
  references: refs ?? {},
  findings: findings ?? [],
  error_code: error ?? null,
  retryable: error === "platform_unavailable" || error === "platform_http_409",
  next_action: nextAction ?? (status === "ok" ? "continue" : "resolve_blocker"),
});

async function loadState() {
  if (!statePath) return { calls: [], applied: {} };
  try {
    return JSON.parse(await readFile(statePath, "utf-8"));
  } catch {
    return { calls: [], applied: {} };
  }
}

async function saveState(state) {
  state.calls.push({ action, args: process.argv.slice(3) });
  if (statePath) {
    await mkdir(path.dirname(statePath), { recursive: true });
    await writeFile(statePath, `${JSON.stringify(state, null, 2)}\n`);
  }
}

function ontologyFromArgs() {
  // Ontology-scoped actions pass the ontology id as the arg after the run dir: [runDir, ontologyId, ...]
  const candidate = process.argv[4];
  return typeof candidate === "string" && candidate && !candidate.startsWith("--") ? candidate : "default";
}

const state = await loadState();
let result;

switch (action) {
  case "authorize-runner-write":
    result = envelope("authorize-runner-write", "ok", { nextAction: "execute_protected_write" });
    break;
  case "start":
    result = envelope("start", "ok", { refs: { run_id: "fake-run", build_session_id: "fake-session" }, nextAction: "organize_business" });
    break;
  case "commit-business":
    result = envelope("commit-business", "ok", { refs: { run_id: "fake-run" }, nextAction: "model_work_units" });
    break;
  case "dry-run-next": {
    const ontologyId = ontologyFromArgs();
    // Test hook (#3): a seeded one-shot dry-run Finding lets the orchestrator prove it maps the Finding
    // back to affected Work Units, regenerates, re-merges/re-reviews, and only then re-dry-runs.
    if ((state.injectDryRunFindings ?? 0) > 0) {
      state.injectDryRunFindings -= 1;
      result = envelope("dry-run-next", "blocked", {
        error: "dry_run_findings",
        findings: [{ work_unit_id: "wu-workflow", issue: "missing modeled relation" }],
        nextAction: "resolve_blocker",
      });
      break;
    }
    if ((state.applied[ontologyId] ?? 0) >= 1) {
      // Plan exhausted: no further dependency-ready Batch.
      result = envelope("dry-run-next", "blocked", { error: "no_dependency_ready_batch", nextAction: "verify" });
    } else {
      result = envelope("dry-run-next", "ok", {
        refs: { client_batch_id: "fake-batch", batch_id: "fake-platform-batch" },
        nextAction: "apply-next",
      });
    }
    break;
  }
  case "apply-next": {
    const ontologyId = ontologyFromArgs();
    state.applied[ontologyId] = (state.applied[ontologyId] ?? 0) + 1;
    result = envelope("apply-next", "ok", {
      refs: { client_batch_id: "fake-batch", batch_id: "fake-platform-batch" },
      nextAction: "dry-run-next",
    });
    break;
  }
  case "reconcile-apply":
    result = envelope("reconcile-apply", "ok", { refs: { client_batch_id: "fake-batch" }, nextAction: "dry-run-next" });
    break;
  case "verify":
    result = envelope("verify", "ok", { refs: { ontology_id: ontologyFromArgs() }, nextAction: "finish" });
    break;
  case "finish":
    result = envelope("finish", "ok", { refs: { build_session_id: "fake-session" }, nextAction: "done" });
    break;
  case "cancel":
    result = envelope("cancel", "ok", { refs: { build_session_id: "fake-session" }, nextAction: "done" });
    break;
  default:
    result = envelope(action, "ok", {});
}

await saveState(state);
process.stdout.write(`${JSON.stringify(result)}\n`);
process.exit(0);
