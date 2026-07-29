# M7 Workflow orchestration and typed variable flow

## L0 local runtime slice

`m7_l0.py` is a standalone L0 probe. Its `prepare` command performs a clean-shell execution of the
visible Python3 sealing helper in a temporary copy, then creates a separately ignored
`runtime/l0/<run-id>/agent-visible/` staging directory with only the L0 contract, run/staging manifests,
the executable helper and `l0-runtime-receipt.json`. Its `verify` command checks all membership, helper
identity/executable mode, fixed nonce, canonical hashes and interpreter receipt fields. It has no API,
credential, Project, Ontology, Build Session, modeling ledger, semantic package or CQ-proof path.

L0 proves only that the local helper can start under the controlled shell. It does not authorize or
claim an L1 modeling attempt, semantic dry-run/application, validation, reasoning or CQ acceptance.

Offline implementation of the reviewed `m7-contract-v4-recovery` scenario. It freezes the selected English
official sources, synthetic business fixture, deterministic accepted base slice, hidden acceptance
contracts and scenario-global modeling-attempt ledger. `m7_host.py` is an explicit two-phase Host:
`prepare` creates a fresh scope, runs the base dry-run/apply and writes the run-specific
`agent-visible/` directory; `continue` reads the semantic package from that same staging directory,
runs principal dry-run, resolves only output-capable resource roles from the Batch envelope, freezes
Host-generated assertion SPARQL, runs invalid dry-run only, applies the identical candidate, then runs
graph-set validation/reasoning details and bounded scoped SPARQL. It records a sealed
`PRODUCER_EVIDENCE_SEALED` boundary before creating isolated Judge staging. `finalize`
mechanically validates a paired Judge verdict, exact evidence citations, non-empty conclusion,
missing/contradictory-evidence notes and status-dependent failure classification; it does not
interpret their semantic content. Valid FAIL/INCONCLUSIVE verdicts and no-verdict abort receipts are
persisted before cleanup. Only an all-PASS verdict
accepted by main-Agent adjudication enters read-only `AWAITING_L2_CONSUMER`. Non-PASS, invalid,
crash/timeout abort, and paired Consumer completion/abort clean the owned scope idempotently. Scope
IDs, receipts, hashes and cleanup evidence stay in the
sibling Host-only state file, never inside `agent-visible/`. The only permitted Agent outputs are the
staged `semantic-package.json` and `clarifications.jsonl`; immutable staged inputs and the run
manifest are hash-checked before continuation. Every phase is inert unless the Host explicitly
invokes `--execute-guarded`; route integration tests use real FastAPI/Pydantic routes with
dependency-overridden services and never write.

The visible v4 authoring contract is self-contained: an Agent writes principal and invalid candidates
plus generic resource roles, positive edge assertions, optional snapshot-absence guards and CQ claims;
it runs exactly `./seal_semantic_package.py --agent-visible .` in the staged directory. The helper
validates item references, output-capable roles, predicate/literal grammar and positive-only claims,
then atomically adds run metadata, candidate hashes and a sealing receipt. It never reads parent or
platform state. The Host rejects unsealed, altered or legacy envelopes before any principal dry-run.

A failed owned-resource deletion is a terminal failure: `continue` writes `CLEANUP_FAILED` and raises
after an otherwise successful execution; direct `cleanup` does the same. If execution itself failed,
the original execution error remains the raised error while cleanup failure is retained in evidence.

Run the focused tests from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --directory backend pytest -p no:cacheprovider \
  ../docs/evaluation-scenarios/dify-workflow-impact-m7/tests
PYTHONDONTWRITEBYTECODE=1 uv run --directory backend pytest -p no:cacheprovider \
  ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests \
  ../docs/evaluation-scenarios/dify-workflow-impact-m6/tests
uv run --directory backend ruff check \
  ../docs/evaluation-scenarios/dify-workflow-impact-m7
```

The experiment is paused with L1 incomplete. See
`docs/delivery/records/2026-07-29-r2-1-001-m7-paused-closeout.md` before resuming.

## Stable scenario hash

Use `python3 docs/evaluation-scenarios/dify-workflow-impact-m7/m7_stable_hash.py` from the repository
root. The helper hashes sorted relative-path records as `path + NUL + SHA-256(file) + LF`; it excludes
only mutable `runtime/`, `attempts.jsonl`, `.pytest_cache/`, and `__pycache__/`. This is the canonical
developer/tester stable-state algorithm; do not substitute shell `find` output or include runtime data.

After independent authorization, the Host runs only named phases with `--execute-guarded`: `prepare`
needs a fresh `--run-id`; `continue`, `finalize`, `abort-judge`, `complete-consumer`,
`abort-consumer` and `cleanup` require the previous `--state`. The semantic package is read only from the previous run's
`agent-visible/semantic-package.json`, so continuation cannot construct a replacement scope. The
command requires an API key only in its Host environment and does not launch an Agent itself.

## v4 evidence-reference and recovery rules

The current run manifest has no governed Evidence or CompetencyQuestion IDs. Every principal and
invalid Modeling Item therefore uses exact empty `evidence_reference_ids` and
`competency_question_ids` arrays; source excerpts remain inline in `evidence`, while scenario CQ
semantics stay in top-level `cq_claims`. The visible sealer and Host admission both reject non-empty
arrays before package publication or dry-run.

The append-only attempt ledger permits five L1 starts. Historical v1/v2/v3 events remain history;
the active v4 fourth start is permitted, while the fifth requires a separately recorded paired
`l1_pass_authorized` event from an all-PASS, main-Agent-accepted Judge finalization. Producer/Consumer
paths cannot write that authorization, and cleanup never resets the ledger.
