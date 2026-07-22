#!/usr/bin/env node
// Real pinned-pi RPC startup smoke (G1). Proves the orchestrator's real launch path (args, env,
// project extension load) starts the real `pi` binary headlessly and that gracefulShutdown reclaims
// it with exit 0 and no orphan. It deliberately sends NO prompt, so no real model is called (that is
// G2's gate). Run manually after `npm ci` and copying a gitignored `.pi/agent/{auth,models-store}.json`:
//
//   node tests/smoke-real-pi.mjs
//
// Not matched by `tests/*.test.mjs`, so it never runs in `npm test`.

import path from "node:path";
import { fileURLToPath } from "node:url";

import { RpcSession } from "../src/rpc-session.mjs";
import { realPiRoleArgs } from "../src/orchestrator.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const packageRoot = path.resolve(here, "..");
const piBinary = path.join(packageRoot, "node_modules", ".bin", "pi");
const piAgentDir = path.join(packageRoot, ".pi", "agent");
const modelingExtension = path.join(packageRoot, "extensions", "modeling-tools.ts");

const args = realPiRoleArgs({
  provider: "deepseek",
  model: "deepseek-v4-flash",
  tools: ["request_modeling_clarification", "complete_stage", "submit_platform_action"],
  modelingExtension,
});

const session = new RpcSession({
  command: piBinary,
  args,
  cwd: packageRoot,
  env: { PI_CODING_AGENT_DIR: piAgentDir },
  role: "coordinator",
  timeoutMs: 20000,
});
session.start();
// Give the real binary a moment to spawn and load the extension, then shut down without prompting.
await new Promise((resolve) => setTimeout(resolve, 1500));
if (session.exited) {
  console.error(JSON.stringify({ smoke: "real-pi-startup", status: "failed", reason: "exited_before_shutdown", exitCode: session.exitCode }));
  process.exit(1);
}
await session.gracefulShutdown();
const aliveChildren = session.exited ? 0 : 1;
const result = {
  smoke: "real-pi-startup",
  status: session.exitCode === 0 ? "ok" : "failed",
  exit_code: session.exitCode,
  orphan_children: aliveChildren,
  pid_observed: session.child?.pid ?? null,
};
console.log(JSON.stringify(result, null, 2));
process.exit(result.status === "ok" ? 0 : 1);
