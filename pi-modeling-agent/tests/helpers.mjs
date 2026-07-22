// Shared helpers for phase-1 Node contract tests. Builds fake-Pi sessions and ModelingRun fixtures.

import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ModelingRun } from "../src/runner.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
export const fakePiPath = path.join(here, "fixtures", "fake-pi.mjs");

let scriptCounter = 0;

/** Write a fake-Pi script to a temp file and return its absolute path. */
export async function writeScript(steps, dir) {
  scriptCounter += 1;
  const file = path.join(dir, `script-${process.pid}-${scriptCounter}.json`);
  await writeFile(file, JSON.stringify(steps), "utf-8");
  return file;
}

/** Create a fresh isolated work directory for a run. */
export async function makeWorkDir() {
  const root = await mkdtemp(path.join(tmpdir(), "pi-modeling-test-"));
  await mkdir(path.join(root, "artifacts"), { recursive: true });
  return root;
}

/** Create a ModelingRun rooted at the given work directory. */
export async function makeRun(workDir, runId = `test-run-${Date.now()}`) {
  const run = new ModelingRun({
    runId,
    eventFile: path.join(workDir, "events.jsonl"),
    workDir,
  });
  await run.start();
  return run;
}

/**
 * Start a fake-Pi role session attached to a run.
 * @param {Object} options
 * @param {ModelingRun} options.run
 * @param {string} options.role
 * @param {Array} options.steps     Fake-Pi script steps.
 * @param {string} options.workDir  Artifact root (the fake writes under <workDir>/artifacts).
 * @param {number} [options.timeoutMs]
 * @param {boolean} [options.persistent]
 */
export async function startFakeRole({ run, role, steps, workDir, timeoutMs, persistent }) {
  const scriptPath = await writeScript(steps, workDir);
  return run.startRole({
    role,
    command: process.execPath,
    args: [fakePiPath],
    cwd: workDir,
    env: {
      FAKE_PI_SCRIPT_PATH: scriptPath,
      FAKE_PI_RUN_DIR: workDir,
      FAKE_PI_ROLE: role,
    },
    timeoutMs,
    persistent,
  });
}

/** Read the recorded JSONL events back as an array of parsed entries. */
export async function readEvents(workDir) {
  const { readFile } = await import("node:fs/promises");
  const raw = await readFile(path.join(workDir, "events.jsonl"), "utf-8");
  return raw
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
}

/**
 * Poll until a session's child has exited and its lifecycle booleans have settled. The RpcSession
 * sets `exited` in an exit-event microtask; polling avoids reading it before that microtask flushes.
 */
export async function waitForExit(session, timeoutMs = 5000) {
  const start = Date.now();
  while (!session.exited && Date.now() - start < timeoutMs) {
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  if (!session.exited) {
    throw new Error(`session ${session.role} did not exit within ${timeoutMs}ms`);
  }
  return session;
}
