/* Modeling Extension for the Pi first-party modeling Runtime.
 *
 * Exposes schema-validated tools for clarification, bounded artifact writes, stage completion, and
 * protected platform-action requests. Tools return bounded envelopes only: status, stable references,
 * findings, and next action. They never return credentials, lease tokens, full transcripts, hidden
 * reasoning, or raw platform responses.
 *
 * The model never receives an unrestricted generic platform write tool. `submit_platform_action`
 * only records the model's bounded request; the Runner performs the actual deterministic adapter
 * call after confirming role settlement, the candidate hash, an independent review PASS, and (where
 * applicable) a clean dry-run, and the adapter consumes a one-shot Runner authorization.
 *
 * After each tool returns, the Extension notifies `modeling_idle` so the external Runner has an
 * independent "Extension has no pending work" signal alongside Pi's `agent_settled`.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const IDLE = "modeling_idle";

function runDir(ctx: { cwd: string }): string {
  return process.env.PI_MODELING_RUN_DIR ?? join(ctx.cwd, "workspaces", "modeling-runs", "current");
}

function parseJsonObject(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("json must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

export default function modelingTools(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "request_modeling_clarification",
    label: "Request Modeling Clarification",
    description:
      "Ask the external coordinator exactly one structured modeling question and wait for its answer.",
    parameters: Type.Object({
      title: Type.String({ maxLength: 200 }),
      question: Type.String({ maxLength: 2000 }),
    }),
    execute: async (_id, params, _signal, _update, ctx) => {
      const answer = await ctx.ui.input(params.title, params.question);
      await ctx.ui.notify(IDLE);
      return {
        content: [{ type: "text", text: `clarification_answer:${answer ?? "cancelled"}` }],
        details: { answer: answer ?? null },
      };
    },
  });

  pi.registerTool({
    name: "write_modeling_artifact",
    label: "Write Modeling Artifact",
    description:
      "Persist exactly one bounded JSON artifact under the controlled shared modeling directory.",
    parameters: Type.Object({
      name: Type.String({ pattern: "^[a-zA-Z0-9_.-]{1,120}$" }),
      json: Type.String({ maxLength: 262144 }),
    }),
    execute: async (_id, params, _signal, _update, ctx) => {
      const parsed = parseJsonObject(params.json);
      const directory = join(runDir(ctx), "artifacts");
      await mkdir(directory, { recursive: true });
      const file = join(directory, `${params.name}.json`);
      await writeFile(file, `${JSON.stringify(parsed, null, 2)}\n`);
      await ctx.ui.notify(IDLE);
      return {
        content: [{ type: "text", text: `artifact_written:${params.name}` }],
        details: { locator: `artifacts/${params.name}.json` },
      };
    },
  });

  pi.registerTool({
    name: "complete_stage",
    label: "Complete Stage",
    description:
      "Mark one modeling stage complete with a bounded result marker. Does not perform platform writes.",
    parameters: Type.Object({
      stage: Type.String({ pattern: "^[a-z0-9-]{1,80}$" }),
      result: Type.String({ maxLength: 500 }),
    }),
    execute: async (_id, params, _signal, _update, ctx) => {
      const directory = join(runDir(ctx), "stages");
      await mkdir(directory, { recursive: true });
      await writeFile(
        join(directory, `${params.stage}.json`),
        `${JSON.stringify({ stage: params.stage, result: params.result }, null, 2)}\n`,
      );
      await ctx.ui.notify(IDLE);
      return {
        content: [{ type: "text", text: `stage_complete:${params.stage}` }],
        details: { stage: params.stage },
      };
    },
  });

  pi.registerTool({
    name: "submit_platform_action",
    label: "Submit Platform Action Request",
    description:
      "Record one bounded request for a protected platform write. The Runner performs the actual " +
      "deterministic adapter call after confirming settlement, hash, review, and clean dry-run.",
    parameters: Type.Object({
      operation: Type.String({ pattern: "^(commit_business|dry_run_next|apply_next|verify|finish)$" }),
      operation_id: Type.String({ minLength: 1, maxLength: 200 }),
      artifact_hash: Type.Optional(Type.String({ minLength: 8, maxLength: 128 })),
      review_verdict: Type.Optional(Type.Union([Type.Literal("PASS"), Type.Literal("REVISE"), Type.Literal("BLOCKED")])),
      dry_run_clean: Type.Optional(Type.Boolean()),
    }),
    execute: async (_id, params, _signal, _update, ctx) => {
      await ctx.ui.notify(IDLE);
      return {
        content: [
          {
            type: "text",
            text: `platform_action_requested:${params.operation}`,
          },
        ],
        details: {
          operation: params.operation,
          operation_id: params.operation_id,
          next_action: "runner_authorizes_and_executes",
        },
      };
    },
  });
}
