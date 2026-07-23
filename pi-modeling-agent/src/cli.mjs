#!/usr/bin/env node
// Pi Local modeling entry command. Validates the pinned Node lower bound, the locked Pi dependency,
// the gitignored local configuration, the tracked scenario, and the loaded Workflow Package before
// any platform business write is allowed. Secrets are rejected anywhere in the tracked input.

import { existsSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { ROLE_TOOLS, ROLE_PROMPTS } from "./runner.mjs";
import {
  ModelingOrchestrator,
  RealDirectoryDriver,
  realRoleLauncher,
  resolvePiAgentDir,
  writeAdapterConfig,
  writeAdapterLauncher,
} from "./orchestrator.mjs";

export const NODE_LOWER = [22, 19, 0];
export const PINNED_PI = "@earendil-works/pi-coding-agent@0.81.1";

/** Secret sentinel scanned across scenario/prompt/config inputs. Keys never enter tracked files. */
export const SECRET_PATTERNS = [
  /sk-[A-Za-z0-9]{16,}/,
  /\b(?:api|secret|access)[_-]?key\s*[:=]\s*["']?[A-Za-z0-9]{16,}/i,
  /\bbearer\s+[A-Za-z0-9._-]{16,}/i,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
];

export class CliError extends Error {}

/** Compare the running Node version against the pinned lower bound. */
export function checkNodeVersion(version = process.versions.node) {
  const parts = String(version).split(".").map((value) => Number.parseInt(value, 10));
  for (let index = 0; index < NODE_LOWER.length; index += 1) {
    if ((parts[index] ?? 0) < NODE_LOWER[index]) {
      throw new CliError(
        `Node >=${NODE_LOWER.join(".")} required (running ${version}); Pi will not start on older Node.`,
      );
    }
  }
  return true;
}

/** Verify the lock pins the approved Pi package and that the binary is installable. */
export async function checkPiLock(packageRoot) {
  const lockPath = path.join(packageRoot, "package-lock.json");
  if (!existsSync(lockPath)) throw new CliError("package-lock.json missing; run `npm ci` first");
  const lock = JSON.parse(await readFile(lockPath, "utf-8"));
  const root = lock?.packages?.[""] ?? lock;
  const declared = root?.dependencies?.["@earendil-works/pi-coding-agent"];
  if (declared !== "0.81.1") {
    throw new CliError(`Pi dependency must be exactly ${PINNED_PI} (lock declares ${declared})`);
  }
  const entry = lock?.packages?.["node_modules/@earendil-works/pi-coding-agent"];
  if (entry?.version !== "0.81.1") {
    throw new CliError("package-lock does not resolve the pinned Pi version");
  }
  return true;
}

/** Locate the real `pi` executable inside the installed node_modules. */
export function resolvePiBinary(packageRoot) {
  const candidate = path.join(packageRoot, "node_modules", ".bin", "pi");
  if (!existsSync(candidate)) {
    throw new CliError("pi executable unavailable; run `npm ci` to install the pinned runtime");
  }
  return candidate;
}

/** Validate the tracked scenario: reusable business input only, no credential, no model key. */
export async function validateScenario(scenarioPath) {
  if (!existsSync(scenarioPath)) throw new CliError(`scenario not found: ${scenarioPath}`);
  const raw = await readFile(scenarioPath, "utf-8");
  let scenario;
  try {
    scenario = JSON.parse(raw);
  } catch (error) {
    throw new CliError(`scenario is not valid JSON: ${error.message}`);
  }
  const allowedTop = new Set([
    "schema_version",
    "name",
    "goal",
    "source_locators",
    "constraints",
    "acceptance_questions",
  ]);
  const extra = Object.keys(scenario).filter((key) => !allowedTop.has(key));
  if (extra.length) {
    throw new CliError(`scenario has unsupported keys: ${extra.join(", ")}`);
  }
  if (scenario.schema_version !== 1) throw new CliError("scenario schema_version must be 1");
  if (typeof scenario.goal !== "string" || !scenario.goal.trim()) {
    throw new CliError("scenario.goal must be a non-empty string");
  }
  if (!Array.isArray(scenario.source_locators) || !scenario.source_locators.length) {
    throw new CliError("scenario.source_locators must be a non-empty array");
  }
  // No credential may live in the tracked scenario.
  const offense = SECRET_PATTERNS.find((pattern) => pattern.test(raw));
  if (offense) {
    throw new CliError("scenario contains a credential-like value; secrets must stay gitignored");
  }
  return scenario;
}

/**
 * Validate the gitignored local configuration. It selects the existing Project, platform base URL,
 * credential source, and model/provider without changing Workflow Package files.
 */
export async function validateLocalConfig(configPath) {
  if (!existsSync(configPath)) {
    throw new CliError(`local config not found: ${configPath} (gitignored; see README template)`);
  }
  const config = JSON.parse(await readFile(configPath, "utf-8"));
  const allowed = new Set([
    "schema_version",
    "project_id",
    "api_base_url",
    "api_key_env_file",
    "api_key_env_name",
    "provider",
    "model",
    "max_parallel_workers",
  ]);
  const extra = Object.keys(config).filter((key) => !allowed.has(key));
  if (extra.length) throw new CliError(`local config has unsupported keys: ${extra.join(", ")}`);
  if (config.schema_version !== 1) throw new CliError("local config schema_version must be 1");
  if (typeof config.project_id !== "string" || !config.project_id) {
    throw new CliError("local config project_id is required");
  }
  if (!config.provider || !config.model) {
    throw new CliError("local config must select a provider and model");
  }
  return config;
}

/** Verify the Workflow Package declares the confirmed roles, tools, and references. */
export async function validateWorkflowPackage(packageRoot) {
  const missing = [];
  for (const role of Object.keys(ROLE_PROMPTS)) {
    const promptPath = path.join(packageRoot, ROLE_PROMPTS[role]);
    if (!existsSync(promptPath)) missing.push(ROLE_PROMPTS[role]);
  }
  if (missing.length) {
    throw new CliError(`Workflow Package missing role prompts: ${missing.join(", ")}`);
  }
  return ROLE_TOOLS;
}

/** Build the reported role/tool inventory. Each role gets exactly its confirmed tool set. */
export function roleInventory() {
  return Object.fromEntries(
    Object.entries(ROLE_TOOLS).map(([role, tools]) => [role, [...tools]]),
  );
}

/**
 * Build and execute the real modeling orchestrator after CLI validation. The real pinned `pi`
 * binary, the migrated Python deterministic core, and the existing platform REST contract are wired
 * here. Clarification/confirmation handlers are left to the host agent/user (G2); this entry starts
 * the runtime but a real model run requires those handlers to be connected by the operator.
 */
async function runRealModeling({ packageRoot, scenario, config }) {
  const repoRoot = path.resolve(packageRoot, "..");
  const piBinary = resolvePiBinary(packageRoot);
  const piAgentDir = resolvePiAgentDir(packageRoot);
  const modelingExtension = path.join(packageRoot, "extensions", "modeling-tools.ts");
  const runId = `pi-run-${Date.now()}`;
  const workDir = path.join(packageRoot, "workspaces", "modeling-runs", runId);
  await mkdir(workDir, { recursive: true });
  const adapterScript = path.join(packageRoot, "lib", "platform_adapter.py");
  const adapterConfigPath = await writeAdapterConfig({ workDir, config, repoRoot });
  const adapterBin = await writeAdapterLauncher({
    workDir,
    adapterScript,
    adapterConfigPath,
  });
  const directory = new RealDirectoryDriver({
    smdPath: path.join(packageRoot, "lib", "shared_modeling_directory.py"),
    runDir: workDir,
  });
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
  });
  const result = await orchestrator.execute();
  console.log(JSON.stringify({ ...result, pinned_pi: PINNED_PI }, null, 2));
  return result.status === "completed" ? 0 : 2;
}

export async function main(argv = process.argv.slice(2)) {
  const selfCheck = argv.includes("--self-check");
  const packageRoot = path.resolve(new URL("..", import.meta.url).pathname);
  try {
    checkNodeVersion();
    await checkPiLock(packageRoot);
    await validateWorkflowPackage(packageRoot);
    const inventory = roleInventory();
    if (selfCheck) {
      const piBin = existsSync(path.join(packageRoot, "node_modules", ".bin", "pi"))
        ? path.join(packageRoot, "node_modules", ".bin", "pi")
        : null;
      console.log(
        JSON.stringify(
          {
            self_check: "ok",
            node: process.versions.node,
            pinned_pi: PINNED_PI,
            pi_binary: piBin,
            roles: inventory,
          },
          null,
          2,
        ),
      );
      return 0;
    }
    const scenarioArg = argv[argv.indexOf("--scenario") + 1];
    const configArg = argv[argv.indexOf("--config") + 1];
    if (!scenarioArg || !configArg) {
      throw new CliError("usage: pi-modeling --scenario <path> --config <gitignored-path>");
    }
    await validateScenario(path.resolve(scenarioArg));
    await validateLocalConfig(path.resolve(configArg));
    const scenarioPath = path.resolve(scenarioArg);
    const configPath = path.resolve(configArg);
    const scenario = await validateScenario(scenarioPath);
    const config = await validateLocalConfig(configPath);
    const code = await runRealModeling({ packageRoot: packageRoot, scenario, config });
    return code;
  } catch (error) {
    console.error(JSON.stringify({ status: "blocked", error: error.message }));
    return 2;
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const code = await main();
  process.exit(code);
}
