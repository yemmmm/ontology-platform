# Astra instruction audit — 2026-09-08

## Scope and evidence

Requested outcome: simplify the current instruction stack for GPT-6 Astra without changing
business semantics, weakening independent acceptance, or rebuilding the modeling runtime.
This is an instruction-maintenance delivery, not a new modeling start or completion of a v3
requirement. The applicable v3 source is `docs/requirements/requirements-v3.0.md`, including its
R3.0-008B/R3.0-009/R3.0-011 status and declared v2.3 baseline.

Reviewed the shared AGENTS/CLAUDE rules, all ten project skill entrypoints, the current modeling
skill references, deprecated Harness entrypoints and role metadata, Team task/Profile/package
boundaries, and the package loader. Team role instructions were inspected for version-specific
gates and duplication; this is not a line-by-line proof of all Runner behavior. Historical
corpora, frozen tasks, acceptance evidence, and implementation contracts were not rewritten.
Personal global configuration and duplicate skill discovery were inspected read-only. Plugin
caches and unrelated personal skills were not exhaustively audited or modified.

Official pages fetched on 2026-09-08:

- [GPT-6 Astra model guidance](https://developers.openai.com/api/docs/guides/latest-model):
  audit conflicting file instructions; make authorization, initiative, delegation, writing style,
  and verification proportional to the task explicit. These are prompting recommendations, not
  evidence that a particular repository revision improves modeling quality.
- [AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md):
  layered instructions, per-directory selection, and session-start loading.
- [Skills](https://learn.chatgpt.com/docs/build-skills): progressive disclosure, precise triggers,
  `.agents/skills` discovery, symlink support, and duplicate names not being merged.

## Findings and disposition

| Finding | Evidence surface | Disposition |
|---|---|---|
| Shared rules drifted between Codex and Claude | AGENTS.md / CLAUDE.md | CLAUDE now points to AGENTS; retain generated GitNexus metadata. |
| Productization and experiment sections repeat the unified guardrails | AGENTS.md | Consolidated into task routing and current-scope rules. Unified modeling guardrails remain intact. |
| Ordinary status questions force a long teaching format and quiz | AGENTS.md | Plain concise Chinese by default; full two-layer format for requested teaching. |
| Reversible authorized work can inherit unnecessary permission pauses | AGENTS.md | Explicitly continue within authorization; ask only for material missing decisions. |
| Any backend file edit implied full backend testing | AGENTS.md | Executable changes retain required suites; docs/instructions use applicable format/link/contract checks. |
| Active modeling skill was absent from the normal repository discovery directory | skills/ontology-modeling; .agents/skills | Added a tracked symlink to the single canonical skill, with a narrow gitignore exception. |
| Historical v1.0 was offered before the owning requirement | ontology-modeling/SKILL.md | Delivery selects current version; isolated Modeling reads only supplied inputs. |
| Single-Agent wording conflicts with an explicit Modeling/Protocol Profile | skill, prompts, deprecated-artifacts | Role ownership follows selected Profile; current Team Runner is distinguished from deprecated Harness. |
| One correction per defect conflicts with same-run recovery | ontology-modeling/SKILL.md | Removed arbitrary correction count; uncertain writes still require inspection. |
| Missing API schema was phrased as a terminal block | skill and prompt reference | Report exact missing contract, suspend dependent operation, resume safely after correction. |
| Generic instance application can be misread as copying relational rows | skill and platform-flow | Explicit semantic-resource versus business-row boundary. |
| Every attempt required fresh Project/Ontology despite existing-scope tasks | skill and ledger reference | Fresh semantic start consumes authorization; resource freshness follows selected task. |
| Evidence sequences read as universal phase schedulers | platform-flow and skill | Selected requirement stages control execution; final semantic evidence remains required. |

No backend/frontend functions, schemas, tool envelopes, runtime model routes, or versioned task
contracts changed. Root modeling rules retain the 20-minute start objective, default three-start
authorization, failure-layer attribution, T0 defensive review, source fidelity, bounded scope,
dry-run/application integrity, governed retrieval, and independent semantic acceptance.

## Remaining instruction surfaces

- Local config already sets `model = "gpt-6-astra"`, `model_reasoning_effort = "medium"`, with
  no `model_catalog_json` override. No evidence warrants changing these values merely for this audit.
- The three inspected authoring roots (`~/.agents/skills`, `~/.codex/skills`, repo `.agents/skills`)
  contain 24 duplicate skill names; plugin copies are additional and not included in that count.
  Notably `requirement-delivery` exists in both personal roots. Its broad mandatory refinement
  and fixed role sequence can still add work to a settled task. Consolidating personal/plugin
  sources is separate from this repository change; do not silently delete installed packages.
- Untracked `.codex/agents/` contains deprecated metadata followed by old executable instructions.
  Those pre-existing files were preserved. The repository now explicitly excludes that workflow
  from new modeling. Removing the trailing historical text should be done at the role's owning
  installation source, with a reload check, not by assuming the local copy is the source of truth.
- Team role instructions total 1,439 lines, including 642 Protocol lines. Several versioned paths
  repeat receipt, evidence, and terminal-handoff details. Their required schemas, capability
  availability, and mounted-reference rules make wholesale text deduplication a runtime change.
  No loader change or broad reference extraction was made without runtime evidence.
- `platform-examiner` has a three-round/ten-call stopping rule, and the lean examiner has an
  inference deadline. These are existing Runner acceptance contracts, not general prompting
  best practices. Do not copy them into ordinary retrieval. R3.0-011 remains unimplemented;
  this audit does not claim to migrate its hidden-question acceptance path.
- GitNexus-generated mandatory analysis blocks remain unchanged; replacing a generated block
  locally would not fix its generator. Direct callers indicate potential impact, not inevitable
  breakage. This instruction-only revision edits no function/class/method.

## Verification and limits

- `python3 skills/ontology-modeling/evals/validate_skill.py`: passed.
- System skill-creator `quick_validate.py skills/ontology-modeling`: passed.
- `uv run --project backend python -m pytest modeling_team/tests/test_contracts.py modeling_team/tests/test_r23003_incremental_contract.py modeling_team/tests/test_r23005_contracts.py -q`:
  71 passed, 23 subtests passed.
- GitNexus `detect_changes(scope="all")`: low risk, no affected execution processes for the
  tracked instruction changes. New symlink/report checked separately through git and filesystem.
- `git diff --check`, edited-document local links, symlink resolution, and staged scope checked.

These are static and deterministic checks. No independent behavioral A/B evaluation, real semantic
modeling start, real Runner acceptance, or backend/frontend restart was performed. Quality and
latency improvement remain unmeasured; do not relabel this as L1/L2 semantic PASS.
Start a new Codex session to reload AGENTS.md; skill discovery supports updates, but the new
entrypoint should be checked in that session's skill list.

Commit scope excludes pre-existing GitNexus count changes and untracked `.codex/agents/`.
Resolve the commit using `git log -- docs/delivery/records/2026-09-08-astra-instruction-audit.md`.
