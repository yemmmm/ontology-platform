// Section A (entry command) — CLI validation: lock, scenario, local config, workflow package, secrets.

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  checkPiLock,
  validateScenario,
  validateLocalConfig,
  validateWorkflowPackage,
  roleInventory,
  SECRET_PATTERNS,
  CliError,
} from "../src/cli.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const packageRoot = path.resolve(here, "..");

test("checkPiLock accepts the committed lock and rejects a missing or wrongly-pinned one", async () => {
  await assert.doesNotReject(() => checkPiLock(packageRoot));
  const tmp = await mkdtemp(path.join(tmpdir(), "pi-lock-"));
  await assert.rejects(() => checkPiLock(tmp), /package-lock.json missing/);
  const wrong = {
    name: "x",
    lockfileVersion: 3,
    packages: {
      "": { dependencies: { "@earendil-works/pi-coding-agent": "0.80.0" } },
      "node_modules/@earendil-works/pi-coding-agent": { version: "0.80.0" },
    },
  };
  await writeFile(path.join(tmp, "package-lock.json"), JSON.stringify(wrong));
  await assert.rejects(() => checkPiLock(tmp), /exactly/);
});

test("validateScenario rejects malformed, unknown-key, and credential-bearing scenarios", async () => {
  const tmp = await mkdtemp(path.join(tmpdir(), "pi-scenario-"));
  const good = {
    schema_version: 1,
    name: "demo",
    goal: "model foundations",
    source_locators: ["docs/a.md"],
    constraints: ["bound scope"],
    acceptance_questions: ["q1"],
  };
  await writeFile(path.join(tmp, "good.json"), JSON.stringify(good));
  const parsed = await validateScenario(path.join(tmp, "good.json"));
  assert.equal(parsed.goal, "model foundations");

  const extra = { ...good, model_api_key: "sk-abc" };
  await writeFile(path.join(tmp, "extra.json"), JSON.stringify(extra));
  await assert.rejects(() => validateScenario(path.join(tmp, "extra.json")), /unsupported keys/);

  const withSecret = { ...good, constraints: ["api_key=sk-secretvalue123456"] };
  await writeFile(path.join(tmp, "secret.json"), JSON.stringify(withSecret));
  await assert.rejects(() => validateScenario(path.join(tmp, "secret.json")), /credential/);
});

test("validateLocalConfig rejects missing config, unknown keys, and missing model selection", async () => {
  const tmp = await mkdtemp(path.join(tmpdir(), "pi-cfg-"));
  await assert.rejects(() => validateLocalConfig(path.join(tmp, "missing.json")), /not found/);
  const good = {
    schema_version: 1,
    project_id: "p1",
    api_base_url: "http://127.0.0.1:8001/api",
    provider: "deepseek",
    model: "deepseek-v4-flash",
  };
  await writeFile(path.join(tmp, "good.json"), JSON.stringify(good));
  await assert.doesNotReject(() => validateLocalConfig(path.join(tmp, "good.json")));
  const noModel = { ...good, model: undefined };
  delete noModel.model;
  await writeFile(path.join(tmp, "nomodel.json"), JSON.stringify(noModel));
  await assert.rejects(() => validateLocalConfig(path.join(tmp, "nomodel.json")), /provider and model/);
});

test("validateWorkflowPackage confirms role prompts and reports the tool inventory", async () => {
  const tools = await validateWorkflowPackage(packageRoot);
  assert.ok(tools.coordinator.length);
  const inv = roleInventory();
  assert.deepEqual(inv["stage-summarizer"], ["write_modeling_artifact"]);
});

test("secret sentinel matches high-signal key assignments and ignores ordinary hashes", () => {
  assert.ok(SECRET_PATTERNS.some((p) => p.test("api_key=sk-test1234567890abcdef")));
  assert.ok(SECRET_PATTERNS.some((p) => p.test("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")));
  const ordinary = "the run id is pi-run-1740000000000 and hash abc123def456";
  assert.ok(!SECRET_PATTERNS.some((p) => p.test(ordinary)));
});
