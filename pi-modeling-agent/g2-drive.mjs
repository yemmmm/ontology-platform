#!/usr/bin/env node
// G2 real-runtime host driver: constructs ModelingOrchestrator with the REAL pinned pi binary,
// migrated deterministic core, and existing platform REST contract, and injects host
// clarify/confirm handlers. This is the G2 acceptance run entry (one real deepseek model run
// against the fixed Dify Foundations corpus on an isolated ownership-proven Project).
//
// Handlers use a recorded reasonable-default policy: the Dify Foundations scenario is ordinary
// additive modeling (within the design's auto-apply regime after independent PASS + clean dry-run),
// and the user authorized proceeding to requirement close. Every confirm/clarify is logged to stdout
// for audit; quality is still gated by independent review, dry-run findings, and post-apply
// CQ/retrieval/provenance verification — never by these handlers alone.

import { mkdir } from "node:fs/promises";
import path from "node:path";

import {
  ModelingOrchestrator,
  realRoleLauncher,
  RealDirectoryDriver,
  writeAdapterLauncher,
  writeAdapterConfig,
  resolvePiAgentDir,
} from "./src/orchestrator.mjs";
import { resolvePiBinary, validateScenario, validateLocalConfig, checkNodeVersion } from "./src/cli.mjs";

const packageRoot = path.resolve(new URL(".", import.meta.url).pathname);
const repoRoot = path.resolve(packageRoot, "..");

checkNodeVersion();
const scenario = await validateScenario(path.join(packageRoot, "scenarios", "dify-foundations-v1.json"));
const config = await validateLocalConfig(path.join(packageRoot, "local.config.json"));

const piBinary = resolvePiBinary(packageRoot);
const piAgentDir = resolvePiAgentDir(packageRoot);
const modelingExtension = path.join(packageRoot, "extensions", "modeling-tools.ts");
const runId = `g2-run-${Date.now()}`;
const workDir = path.join(packageRoot, "workspaces", "modeling-runs", runId);
await mkdir(workDir, { recursive: true });
const adapterScript = path.join(packageRoot, "lib", "platform_adapter.py");
const adapterConfigPath = await writeAdapterConfig({ workDir, config, repoRoot });
const adapterBin = await writeAdapterLauncher({ workDir, adapterScript, adapterConfigPath });
const directory = new RealDirectoryDriver({
  smdPath: path.join(packageRoot, "lib", "shared_modeling_directory.py"),
  runDir: workDir,
});

const confirm = async (plan) => {
  const summary = {
    event: "confirm_business",
    ontology_count: plan.ontologies?.length ?? 0,
    work_unit_count: plan.coverage?.work_units?.length ?? 0,
    competency_questions: plan.coverage?.competency_questions?.length ?? plan.questions?.competency_questions?.length ?? 0,
    brief_fields: Object.keys(plan.brief?.fields ?? {}),
    confirmed_fields: plan.brief?.confirmed_fields ?? [],
  };
  console.log(JSON.stringify(summary));
  return true;
};

const clarify = async (record) => {
  console.log(JSON.stringify({ event: "clarify", title: record.title ?? null, message: record.message ?? null }));
  return "Model the full Dify workflow foundations scope described in the sources (Workflow, Node, Input, Output and their connectivity). Keep every fact traceable to a cited source; mark an explicit gap rather than inventing a fact.";
};

const orchestrator = new ModelingOrchestrator({
  packageRoot,
  repoRoot,
  scenario,
  config,
  runId,
  workDir,
  roleLauncher: realRoleLauncher({
    piBinary,
    packageRoot,
    repoRoot,
    provider: config.provider,
    model: config.model,
    piAgentDir,
    modelingExtension,
    workDir,
  }),
  directory,
  adapterBin,
  adapterConfigPath,
  maxParallelWorkers: config.max_parallel_workers,
  clarify,
  confirm,
});

const result = await orchestrator.execute();
console.log(JSON.stringify({ event: "g2_result", run_id: runId, work_dir: workDir, result }));
process.exit(result.status === "completed" ? 0 : 2);
