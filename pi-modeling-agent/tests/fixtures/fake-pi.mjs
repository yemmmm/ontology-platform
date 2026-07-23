// Fake Pi RPC subprocess for phase-1 contract tests. Speaks the same NDJSON protocol as the real
// `pi --mode rpc --no-session --approve`, but replays a scripted, controllable event stream so tests
// can prove lifecycle behavior without a real model. It writes artifacts to a configured run dir to
// exercise the Runner's acceptance path.
//
// Script format: a JSON array (read from env FAKE_PI_SCRIPT_PATH) of step objects:
//   {type:"event", record:{...}}            emit one protocol record (role is filled if absent)
//   {type:"sleep", ms}                       delay before the next step
//   {type:"artifact", name, json}            emit tool_execution_start/end around writing the artifact
//   {type:"clarify", id, title, question}    emit extension_ui_request input, await matching response
//   {type:"idle"}                            emit extension_ui_request notify modeling_idle
//   {type:"queue", length}                   emit queue_update with the given length
//   {type:"stderr", text}                    write one line to process.stderr (observability only)
//   {type:"exit", code}                      process.exit(code ?? 0)
// The fake begins replaying after it receives the first prompt line on stdin and stays alive after
// the script drains (like real Pi) until stdin closes or it is killed.

import { mkdir, writeFile, readFile, rename } from "node:fs/promises";
import { dirname, join } from "node:path";
import { createInterface } from "node:readline/promises";

const scriptPath = process.env.FAKE_PI_SCRIPT_PATH;
const runDir = process.env.FAKE_PI_RUN_DIR ?? "./fake-run";
const role = process.env.FAKE_PI_ROLE ?? "fake";

if (!scriptPath) {
  process.stderr.write("FAKE_PI_SCRIPT_PATH is required\n");
  process.exit(2);
}

const steps = JSON.parse(await readFile(scriptPath, "utf-8"));

const out = (record) => {
  process.stdout.write(`${JSON.stringify({ role, ...record })}\n`);
};

const stdin = createInterface({ input: process.stdin });
const pendingResponses = new Map();
let promptResolver = null;
const promptReceived = new Promise((resolve) => {
  promptResolver = resolve;
});

stdin.on("line", (line) => {
  if (!line) return;
  let record;
  try {
    record = JSON.parse(line);
  } catch {
    return;
  }
  if (record.type === "prompt") {
    if (promptResolver) {
      const resolve = promptResolver;
      promptResolver = null;
      resolve(record);
    }
  } else if (record.type === "extension_ui_response") {
    pendingResponses.set(record.id, record.value);
  }
});

const awaitResponse = (id) =>
  new Promise((resolve) => {
    const check = () => {
      if (pendingResponses.has(id)) resolve(pendingResponses.get(id));
      else setTimeout(check, 5);
    };
    check();
  });

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const replay = async () => {
  await promptReceived;
  for (const step of steps) {
    switch (step.type) {
      case "event":
        out(step.record);
        break;
      case "sleep":
        await sleep(step.ms ?? 10);
        break;
      case "queue":
        out({ type: "queue_update", queue: Array(step.length).fill(null), length: step.length });
        break;
      case "idle":
        out({ type: "extension_ui_request", method: "notify", message: "modeling_idle" });
        break;
      case "stderr":
        process.stderr.write(step.text ?? "");
        break;
      case "clarify":
        out({
          type: "extension_ui_request",
          method: "input",
          id: step.id,
          title: step.title ?? "Clarification",
          question: step.question ?? "",
        });
        await awaitResponse(step.id);
        break;
      case "artifact": {
        out({ type: "tool_execution_start", toolName: "write_modeling_artifact" });
        // Mirror the real Extension: never append a second `.json` when the script name already has one.
        const fileName = step.name.endsWith(".json") ? step.name : `${step.name}.json`;
        const file = join(runDir, "artifacts", fileName);
        await mkdir(dirname(file), { recursive: true });
        // Atomic write (temp + rename) so a concurrent Runner reader never observes a partial file.
        const temporary = `${file}.${process.pid}.${Date.now()}.tmp`;
        await writeFile(temporary, `${JSON.stringify(step.json, null, 2)}\n`);
        await rename(temporary, file);
        out({
          type: "tool_execution_end",
          toolName: "write_modeling_artifact",
          isError: false,
          content: `artifact_written:${fileName}`,
        });
        break;
      }
      case "exit":
        process.exit(step.code ?? 0);
        break;
      default:
        process.stderr.write(`unknown fake step: ${JSON.stringify(step)}\n`);
    }
  }
};

try {
  await replay();
  // Mirror real Pi: stay alive after settlement until the Runner closes stdin or kills the process.
  await new Promise((resolve) => stdin.on("close", resolve));
  process.exit(0);
} catch (error) {
  process.stderr.write(`fake-pi error: ${error.message}\n`);
  process.exit(1);
}
