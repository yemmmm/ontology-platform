# R2.2-001 Ontology Modeling Team L1 Design

## 1. Goal

Prove that the L0 three-role collaboration contract can consume a small real business slice and that
only the Platform Protocol Agent can turn an approved candidate into a real, governed platform
write. The source is the v2.1 pinned Dify Version Control page; the slice distinguishes Current
Draft from Latest Version for one synthetic Workflow.

## 2. Current minimal scope

### 2.1 Source and business question

Agent-visible source:

- the pinned English Version Control page from snapshot
  `dify-foundations-2026-07-18-5396c1a`;
- the matching snapshot manifest entry and source hash;
- a synthetic Workflow identifier that is explicitly not an official Dify example;
- the public Modeling Batch command contract and the L1 role contract.

Business questions:

1. How should a Workflow's working version be distinguished from the live version users see?
2. How can both versions be represented without treating an unpublished draft as live?
3. What minimum deterministic constraint prevents an unclassified or multiply classified version?

The Agent must not receive the M1 ontology, Shapes, fixtures, M2/M3 Batch items, historical correct
queries, tester assertions, or delivery-session history.

### 2.2 Two stages

`L1-S0` is a no-write simulation. A fresh coordinator delegates semantic interpretation to a
Modeling Agent and protocol planning to a Platform Protocol Agent. The protocol result is a proposed
generic command plan, not executable JSON and not a platform receipt. The audit rejects all
platform writes.

`L1-S1` is a fresh real run. The Modeling Agent reads the same bounded source and returns a candidate
in business/ontology language. The coordinator either approves it or returns it for semantic
revision, then emits a protocol dispatch containing only that candidate and the frozen task ID. A
separate isolated Platform Protocol Agent converts it to exact MCP arguments, reads authoritative
state, performs dry-run/apply and reports receipts. The coordinator receives the normalized result
and closes the team run.

## 3. Role and process boundary

```text
Delivery launcher
  ├─ prepares fresh Project/Ontology and source allow-list
  ├─ starts coordinator namespace (no ontology MCP)
  │    ├─ coordinator Session
  │    └─ modeling child (no ontology MCP)
  ├─ observes coordinator-authored protocol dispatch
  ├─ starts protocol namespace (temporary model key + allow-listed ontology MCP)
  │    └─ platform protocol Agent
  ├─ returns normalized protocol result to the same coordinator Session
  └─ revokes key, audits, cleans owned resources
```

The launcher is mechanical experiment infrastructure, not a fourth team Agent or a product Host
Workflow. It may create empty test scope, move immutable artifacts, start processes, normalize
terminal state and clean owned resources. It may not write Modeling Items, select classes or
properties, interpret the source, retry semantic conflicts or alter an Agent candidate.

The coordinator dispatch is the authorization to start the protocol Agent. It includes a task ID,
candidate artifact hash and requested outcome; it contains no credential or hidden answer.

## 4. Write-credential isolation

Codex 0.146.0 did not prove child-only MCP provisioning in L0. L1 therefore uses two OS namespaces:

- coordinator namespace: source and team-work only; no ontology MCP server, backend mount, platform
  key or protocol Codex home;
- protocol namespace: approved candidate, public protocol, protocol team-work and a distinct
  temporary Codex home containing one Project-scoped `model` key.

The temporary key is created only after the coordinator dispatch exists, is bound to the owned
Project, and is revoked on success, failure, timeout or cleanup. The plaintext is excluded from
transcripts and audit. The protocol namespace exposes only the MCP tools required for Build Session,
Lease, Modeling Batch, current-state/read-model verification and Session completion/cancellation.

## 5. Real platform workflow

The Delivery launcher creates a fresh, uniquely tagged Project and Ontology but no ontology content.
The protocol Agent must:

1. read the Project/Ontology modeling context;
2. create one Build Session;
3. acquire the Ontology lease;
4. produce a bounded structural candidate from the coordinator-approved description;
5. submit the immutable candidate as `dry_run`;
6. submit unchanged content as `apply_atomic` with a fresh workspace version and lease token;
7. if necessary, submit a second bounded fixture Batch using stable outputs from the applied
   structural Batch;
8. read the applied model and prove draft/latest state distinction plus the minimum constraint;
9. save a concise checkpoint and complete the Build Session.

Every semantic content change requires a new candidate returned through the coordinator. The
protocol Agent may fix mechanical JSON, schema, reference, IRI and call-order mistakes without
changing meaning. L2 conflict-routing matrices are not part of this run.

Each structural or fixture candidate uses one immutable `client_batch_id` and identical Items for
its `dry_run -> apply_atomic` transition; only the idempotency key, current workspace version,
mode and apply lease token change. A negative candidate is submitted as dry-run only and must be
rejected by the platform before any apply.

## 6. Semantic acceptance without a frozen answer ontology

Acceptance is behavioral rather than graph-isomorphic:

- Workflow and Workflow Version are distinguishable resources or concepts;
- the synthetic Workflow has one explicitly draft version and one explicitly live/latest version;
- a generic read path returns both and preserves their different states;
- at least one deterministic Shape or equivalent platform constraint rejects a version whose
  required workflow/state classification is missing or invalid;
- no Tool Invocation, Binding, Change Set or impact-level conclusion is required.

The Agent may choose names, IRIs and internal structure. Tester-only code derives stable resource
identities from Batch outputs/read models and evaluates the behavior, not exact labels beyond the
business terms supplied in the source.

## 7. Evidence and terminal states

Committed artifacts freeze inputs, prompts, allowed tools, expected event categories and offline
tests. Gitignored runtime evidence retains redacted JSONL, child rollout IDs, dispatch/result hashes,
MCP tool inventory, Batch IDs/statuses, workspace before/after versions, Build Session/Lease terminal
state, key ID/revocation, cleanup ownership and service health.

Terminal outcomes are:

- `PASS`: S0 and S1 acceptance pass, key revoked, owned resources cleaned;
- `FAIL`: the team or platform completed but violated an L1 acceptance rule;
- `INCONCLUSIVE`: provider/runtime/infrastructure prevented a trustworthy result.

Failure is categorized as `modeling-quality`, `platform-contract`, or `runtime/infrastructure`.

## 8. Non-goals and future productization

No backend/frontend product code, permanent Agent Runtime, generalized job queue, credential broker,
management UI, Dify-specific platform branch, full C -> B -> A model, Consumer/Judge/mutation,
repeatability campaign, Pi parity, L2 error-routing matrix or L3 modeling-quality claim is included.

Future productization may replace the scenario launcher with a durable runtime and role-aware
credential service. L1 does not make those prerequisites for this bounded quality experiment.

## 9. Isolated platform runtime and host bootstrap

The resident `8001` service remains unchanged and currently runs `legacy_only`. L1 starts one
uniquely allocated loopback REST port with `SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary`, using the
current migrated PostgreSQL and Oxigraph. Before creating any L1 credential or starting a team, the
launcher runs a configuration probe in the exact sanitized application/runtime mount and fails
unless it resolves `rdf_primary`; after startup it checks health and, with the host admin key,
confirms the canonical mode.

The protocol stdio MCP is launched from the same sanitized application/runtime mount and receives
the same PostgreSQL, Oxigraph and `rdf_primary` values explicitly. It must not inherit the resident
service's `legacy_only` default.

No persistent admin credential is currently configured. The trusted local launcher therefore uses
the existing security helper and database session as a narrow bootstrap to create one ephemeral,
unbound org-admin key after the mode probe. That key:

- never enters coordinator, Modeling Agent or protocol Agent mounts/configuration/environment;
- is used through formal REST routes only to create the empty Project/Ontology, create/revoke the
  Project-scoped protocol `model` key, delete the owned Project and verify cleanup;
- is self-revoked through the trusted bootstrap in every terminal path, with an audit entry.

The protocol model key is created only after the Project and coordinator dispatch exist. Project
deletion revokes any remaining Project keys; the launcher still verifies the exact model-key record
is revoked before self-revoking the host-admin key.

## 10. Sanitized MCP mount

The protocol namespace does not bind the repository's `backend/` directory. It binds only the
required `backend/app` code at `/backend/app` plus the existing virtualenv/runtime at its resolved
read-only path. `/backend/.env` does not exist. The MCP interpreter runs directly with `/backend` as
its working directory and receives an explicit allow-list of settings:

- the run's Project-scoped model key;
- PostgreSQL and Oxigraph connection values required by the platform process;
- `SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary`;
- non-secret deterministic settings required for the current application.

No host Codex configuration or long-term ontology key is mounted. A preflight starts the same MCP
command once with the run key removed and requires authentication failure. Isolation probes require
`/backend/.env` absent, no host-key fingerprint in files/environment/evidence, and no fallback
principal. The protocol Agent is authorized to its own model key; production-grade protection from
that Agent reading its own process configuration remains a stated non-goal.

## 11. Implementation result

The bounded L1 experiment completed on 2026-07-30 using retained run `l1-i`. The protocol Agent
performed governed dry-run/apply transitions, advanced the workspace, proved deterministic rejection
with a negative dry-run, returned the distinct draft/latest semantic read, completed the Build
Session and released its lease. The owned Project was deleted and both ephemeral keys were revoked.

The launcher's rollout-count heuristic reported `INCONCLUSIVE` because it counted S0 children when
looking for the S1 Modeling Agent. Direct review of the session metadata identifies the S1 child
unambiguously, and direct review of platform receipts proves the modeled result. Per the user's
decision, this experiment does not add another automated Judge: the Delivery Agent and independent
Requirement Tester accepted the retained evidence manually. Independent Round 2 is `PASS`; the
heuristic issue remains non-blocking test-infrastructure maintenance.
