# R2.3-005 Luna-max Team Model Switch

## Objective

After the semantically successful but overall failed start72 run, switch every
model-backed participant in the formal
R2.3-005 Team from DeepSeek to the OpenAI `gpt-5.6-luna` model with
`model_reasoning_effort = "max"`. This applies to the four persistent roster roles
(Coordinator, Modeling, Protocol, Acceptance) and both fresh Acceptance children
(Source Examiner and Platform Examiner). It does not alter or relabel retained start72
evidence.

Start72 is terminally classified `runtime/infrastructure` with
`complete_modeling_quality_result=false`: its two-CQ PASS and settlement remain useful
diagnostic evidence, but the retained DeepSeek credential breach prevents requirement
completion and must not be promoted to a full PASS.

## Current minimal scope

1. Declare the same complete Codex model override (`model`, `model_provider`, and
   `model_reasoning_effort`) in one formal R2.3-005-only manifest bound to all six
   applicable package IDs. Do not change the shared package YAML runtime defaults.
2. Add one zero-side-effect preflight over the complete four-role roster and both
   Examiner packages in `TeamRunner.prepare`, immediately after formal configuration
   loading and before platform preflight, ledger reservation, run-root creation,
   transport/capability startup, or any process/child factory. It requires every
   manifest entry to bind an existing exact package ID to the supported tuple
   `gpt-5.6-luna/openai/max`, rejects unknown/missing package IDs, unknown model fields,
   partial tuples, any other value, and cross-entry inconsistency.
3. Project the two Examiner manifest entries into their private child configs. Their
   package defaults, isolation, tools, tickets, input projections, and lifecycle remain
   unchanged.
4. Remove the DeepSeek environment-key path from formal R2.3-005 persistent and child
   launches. Formal execution must never place a provider secret in process env,
   config, argv, evidence, shell snapshots, rollout JSONL, or SQLite/WAL files.
5. Stage OpenAI `auth.json` at mode `0600` only for app-server/provider request
   initialization. Real smoke evidence shows deleting it before `turn/start` does not
   yield a usable Luna turn, so keep it through the synchronous `turn/start` acceptance
   response and unlink it immediately afterward, before the first model tool/MCP call
   can be dispatched. Stop remains an idempotent fallback cleanup. Authentication bytes
   must not be copied to any retained generated artifact or be readable by a model-
   launched tool.
6. Keep start72 evidence byte-for-byte unchanged apart from the already applied mode
   tightening; record the incident and require external revocation/rotation of its
   exposed DeepSeek key before release.

## Out of scope

- No deletion, redaction, or semantic rewriting of start72 artifacts, verdicts,
  retained ontology, or ledger history. Its already recorded failure stays immutable.
- No semantic start73/74 as part of implementation testing.
- No provider fallback, runtime model selection UI, or generalized multi-provider
  policy. DeepSeek support for future formal execution is disabled until it has a
  separate design that does not expose credentials through the child environment.
- No change to prompts, acceptance questions, tool permissions, or terminal routing.

## Implementation

1. Add a formal-only manifest that maps all six exact package IDs to
   `gpt-5.6-luna` / `openai` / `max`. Shared package YAML remains byte-compatible for
   nonformal and R2.3-002 callers. The authoritative artifact is
   `modeling_team/model-manifests/r2-3-005-luna-max.yaml`, schema version 1, with exact
   keys `schema_version`, `manifest_id`, `profile_id`, `task_id`, and `packages`;
   `packages` is an exact six-ID mapping whose values contain only `model`,
   `model_provider`, and `model_reasoning_effort`.
2. Add a shared validated six-package formal model manifest loader whose first caller
   is `TeamRunner.prepare` directly after configuration load. This call precedes the
   existing platform preflight, baseline freeze/reservation, run-root creation, Team
   Transport, Acceptance capabilities, and Agent startup. Runtime config generation
   and Examiner launch consume the already validated manifest rather than reparsing a
   looser shape. Its allowlist is exactly `gpt-5.6-luna/openai/max`; missing/extra
   package bindings, unknown model keys, incomplete tuples, other values, and mismatches
   fail closed. The loader returns the parsed immutable mapping plus artifact digest.
   `_baseline_manifest` binds that path/digest, and the existing post-platform-preflight
   baseline reread must reject TOCTOU drift before ledger reservation/run-root creation.
   The digest returned by the loader must equal the manifest digest in the *initial*
   baseline as well as the post-preflight baseline; loader-A -> initial-baseline-B drift
   fails even when both later baseline reads see B.
3. In `_write_config` and the Acceptance child launch path, emit the already validated
   OpenAI tuple. Do not resolve, inject, or retain a DeepSeek key on any formal path.
4. After each persistent or child app-server completes initialization, thread start,
   exact MCP discovery, and the first `turn/start` RPC has synchronously returned an
   accepted turn identity, unlink its private `auth.json` before dispatching any
   notification that could execute a model-selected tool. On any RPC/startup error,
   cleanup removes it before propagating failure. Persist the auth-removal timestamp
   and first tool/MCP-dispatch timestamp as non-secret ordering evidence.
   Because the current `_rpc_locked` dispatches out-of-band notifications while waiting
   for its matching response, the first-turn helper uses an auth barrier while holding
   the Agent I/O lock. Ordinary streaming/state notifications are buffered. If the
   matching `turn/start` response arrives first, it unlinks auth and replays the buffer.
   If any unmatched JSON-RPC message carrying an `id` arrives first, treat it as a
   server-initiated request requiring a client response. It proves provider inference
   has already reached an actionable boundary: unlink auth first, latch the ordering
   evidence, then dispatch/respond to that request so the server cannot deadlock, and
   continue waiting for the matching turn response. The existing allowlisted tool/MCP
   requests keep their typed handlers; command/file-change/permissions approvals are
   explicitly declined, user-input requests receive a typed unavailable response, and
   every other unknown server request gets a JSON-RPC method-not-supported error. No
   request with an `id` may enter the ordinary-notification buffer. Every buffered/event
   item is handled exactly once;
   error/timeout unlinks auth and does not replay ordinary buffered notifications. Later
   turns keep the existing RPC path.
5. Validate host `auth.json` as an owner-only, non-symlink regular file and stage it for
   persistent roles and Examiner children exclusively through the existing private-copy
   primitive (`O_NOFOLLOW`, `O_EXCL`, mode `0600`, flush+fsync). `shutil.copyfile` is not
   permitted for credentials. Source drift, insecure modes, existing destinations, and
   copy failures must fail before a model turn and remove partial output.
6. Add a generic private-artifact secret audit used at cleanup and by tests. It compares
   sentinel/credential bytes without logging them and covers auth/config, argv/process
   env manifests, evidence, shell snapshots, session JSONL, and SQLite plus WAL/SHM.
   Cleanup state cannot report credentials destroyed when this audit finds a match.
   Shell coverage includes `.sh` and extensionless files beneath any
   `shell_snapshots/` directory; it must not depend only on a suffix allowlist.
7. Update the owning R2.3-005 requirement, design, test plan, and delivery record to
   record the user's post-start72 provider decision and supersede the older conditional
   DeepSeek-to-Luna rule for subsequent formal starts; record start72 overall FAIL and
   the retained credential incident separately from its valid semantic evidence.
8. Close the provider-error liveness gap exposed by Independent Round 17 with a typed
   Runtime failure path, not the inactivity-only queue. Strictly parse the generated
   `ErrorNotification` envelope: `threadId` and `turnId` must bind to the current Agent
   and accepted turn; `willRetry` must be a real boolean; `error.codexErrorInfo` must be
   null, one allowed string variant, or one exact allowed object variant whose payload
   follows the generated schema (including nullable uint16 HTTP status where present).
   Any malformed/mismatched envelope fails closed. Persist only `will_retry`, normalized
   variant name, optional integer HTTP status, Agent/role and turn digest; never persist
   `message`, `additionalDetails`, raw params, token, or provider response text.
   `willRetry=false` or an invalid envelope latches one `runtime/infrastructure` failure
   immediately. `willRetry=true` remains eligible for App Server recovery but does not
   itself refresh the model-progress clock.
9. Add one idempotent Adapter-owned Runtime failure latch/queue used by both provider
   terminal errors and the existing inactivity watchdog. It sets the Agent failed once,
   records only the sanitized detail, terminates its process group once, and exposes a
   `consume_runtime_failures()` API. Keep the old inactivity reader only as a compatibility
   projection for existing callers/tests; do not mislabel provider failures as
   `llm-inactivity-timeout`. `TeamRunner.drain` consumes the typed queue both before work
   and immediately after `receive_messages()` (where a just-read error is latched), writes
   the exact runtime-failure evidence/type, records `runtime/infrastructure,false`, runs
   cleanup once, and reaches `TERMINAL_REPORT_COMPLETE` once. Once notification handling
   latches and kills an Agent, `_drain_agent_output_locked` stops reading that pipe in the
   same critical section. `receive_messages` treats a subsequent expected closed pipe as
   secondary only when the same Agent already has a typed failure; otherwise it keeps the
   existing error. Runner additionally uses a `try/finally`-equivalent post-pump consume so
   an expected close cannot bypass typed terminal finalization.
10. Define model progress by an explicit current-schema allowlist rather than every App
   Server notification. Accepted turn/item lifecycle, model output deltas, command/process
   output, MCP tool progress/server request handling, hook lifecycle, and matching terminal
   events may refresh the clock. `error`, warning/config/deprecation/guardian notices,
   skills/remote-control/MCP-startup/thread-status heartbeats and unknown notifications do
   not. A later allowlisted progress event may recover a retrying turn normally; otherwise
   the existing code-default 300-second watchdog latches the typed inactivity failure.
11. Close the first-turn ordering race. Once the matching `turn/start` response arrives,
   freeze its non-empty turn ID on the Agent before replaying buffered notifications.
   A buffered error therefore validates against that ID and can latch failure. Persistent
   `start_task` must not overwrite a replayed failed state with `running`. It must also
   preserve a matching replayed `turn/completed`/`turn/finished` as `idle` with the exact
   `last_completed_turn_id`, rather than resurrecting that turn as active. A terminal for
   another turn fails closed. Examiner startup instead raises a sanitized startup failure
   and performs its existing child cleanup. Before the first-turn helper releases the
   re-entrant Agent I/O lock, it also drains every response-following line already readable
   with a zero-timeout read; this closes the observed response-then-error queueing boundary
   without waiting for future traffic. Neither path fabricates a terminal event.
12. Make initial Team startup fail fast. After every persistent `start_task`, before
   starting the next role, `TeamRunner.start` checks/consumes the typed Runtime failure
   queue. On a failure it stops the roster loop, invokes the same exactly-once Runner
   runtime-failure finalizer used by `drain`, records `runtime/infrastructure,false`,
   cleans the partially started Team, reaches `TERMINAL_REPORT_COMPLETE`, and starts no
   later Agent. A matching replayed early terminal is not a Runtime failure and does not
   prevent the remaining roster from starting.
13. Sanitize matching JSON-RPC error responses as well as asynchronous provider-error
   notifications. Introduce a typed Runtime RPC exception containing only request method,
   strict integer code, and a closed safe category; discard `message` and `data` before
   exception formatting, evidence, stderr, or Runner propagation. Preserve the existing
   steer recovery without raw text by mapping only the two exact recognized conditions to
   typed fields (`no_active_turn_to_steer`, or `active_turn_mismatch` with a strictly
   validated in-memory turn ID). Every other response is `rpc_error`; malformed error
   envelopes fail closed as `malformed_rpc_error`. The active turn ID may drive the one
   existing retry but is never copied into the exception string or error evidence.

## Verification

- Formal manifest contract: all six exact package IDs resolve to
  `gpt-5.6-luna`, `openai`, `max`; the shared package YAML files remain unchanged and
  representative nonformal/R2.3-002 configs retain their prior model behavior.
- Six-package `TeamRunner.prepare` preflight tests prove malformed/partial/unsupported/
  inconsistent/missing declarations fail with no platform preflight call, no ledger
  append/reservation, no run root, no runtime/transport/capability path, and zero
  process/child-factory calls.
- Four-role real `prepare/start` runtime-config test with `DEEPSEEK_API_KEY` absent:
  every private config selects Luna-max and contains no DeepSeek provider or env key.
- Repeat the four-role and both-Examiner launch/cleanup tests with a sentinel
  `DEEPSEEK_API_KEY` deliberately present in the Host environment. Assert
  `_resolve_deepseek_api_key` is never called and the sentinel is absent from every
  process env, config, argv, evidence, shell snapshot, session JSONL, SQLite,
  WAL, and SHM artifact.
- Source and Platform Examiner launch-config tests with `DEEPSEEK_API_KEY` absent:
  each private config selects Luna-max and preserves its existing tool/isolation
  surface.
- A formal manifest without the exact package binding fails before launch; nonformal behavior
  stays unchanged and receives no new provider environment.
- Synthetic auth sentinels are staged only at `0600`, removed immediately after each
  accepted first `turn/start` and before any model-selected tool/MCP dispatch,
  and absent from config/argv/env/evidence/shell snapshots/session JSONL/SQLite/WAL/SHM
  after success and startup failure for all persistent and Examiner paths.
- Adversarial JSON-RPC ordering tests emit a tool/MCP notification before the matching
  first `turn/start` response and make the fake server wait for the client response.
  They prove auth is unlinked before the request is dispatched/responded, the server
  does not deadlock, the matching response is consumed, and each event is handled once;
  ordinary early notifications follow the buffer/replay path. RPC error/timeout removes
  auth and replays no buffered ordinary notification.
- Parameterized first-turn tests cover every current Codex ServerRequest method
  (`item/tool/call`, MCP elicitation, command/file-change/permissions approval, and
  request-user-input) plus an unknown method. Each receives its typed fail-closed or
  allowlisted response after auth deletion and cannot deadlock the turn response.
- Auth staging tests cover wrong owner/mode, symlink, pre-existing target, short write/
  copy failure, and successful fsynced mode-0600 staging for persistent and Examiner
  paths; no first turn or partial credential artifact survives failure.
- A fixture matching the real start72 `shell_snapshots/*.sh` shape and an extensionless
  shell-snapshot fixture each contain only one secret leaf value. Both must be detected,
  make cleanup report credentials not destroyed, and keep the secret itself out of the
  audit result; clean equivalents must pass.
- One bounded real Luna provider smoke (no business source, no platform mutation, no
  StartLedger write) requires a terminal Luna response, proves auth-unlink time precedes
  the first tool/MCP dispatch time, and verifies all generated artifacts contain none
  of the real host-auth secret byte values. Its harness retains only sanitized RPC
  stage/error code, process exit class, terminal state, counts, and digests; never
  credential content. The prior unobservable smoke (`RuntimeError`, no terminal state)
  is a harness FAIL and is not acceptance evidence.
- Provider-error regression tests cover every generated-schema string/object
  `codexErrorInfo` variant, null, nullable uint16 status, invalid bool/enum/object/status,
  wrong thread/turn binding, and forbidden free text. `willRetry=false` produces one
  immediate Runner-visible typed failure; repeated `willRetry=true` plus each explicitly
  non-progress notification cannot postpone the inactivity deadline; each allowlisted
  progress family resets it and can still reach its matching terminal. Duplicate or
  post-failure errors append no second failure and kill no second process group.
- First-turn adversarial tests place retryable, non-retryable, malformed, and wrong-turn
  errors both before the matching response and immediately behind that response in the
  same readable pipe. They prove the accepted turn ID is frozen before replay/drain,
  persistent state is never overwritten from failed to running, Examiner startup
  cleans and raises, a matching early completed/finished notification remains idle with
  the exact completed ID, a wrong-turn terminal fails closed, and no false terminal is
  emitted.
- Runner integration tests inject a provider failure during `receive_messages()` and from
  the pre-drain queue. Both produce exactly one sanitized runtime-failure evidence row,
  one `runtime/infrastructure,false` ledger terminal, one cleanup, and one
  `TERMINAL_REPORT_COMPLETE`; no `llm-inactivity-timeout` label is used for provider errors.
  A real `TeamRunner.start` fake-server test injects the buffered failure into the first
  role and proves roles two through four never start, while the partial Team receives the
  same terminal finalization and cleanup exactly once.
  The receive-path integration uses a real fake pipe sequence `error(willRetry=false) ->
  process-group termination -> EOF`; it proves EOF is suppressed only for the already
  latched Agent and the Runner still emits exactly one typed terminal. EOF without a typed
  failure remains an error.
- RPC error tests inject secret-bearing `message` and `data` into initialize, first-turn,
  later-turn and steer responses. Exceptions, stderr-equivalent strings, Runtime evidence,
  and cleanup artifacts contain only method/code/category and no injected bytes. Typed
  no-active-turn and active-turn-mismatch cases retain the existing fresh-turn/one-retry
  behavior without parsing `str(exc)`; malformed codes/envelopes fail closed.
- The next bounded real smoke must use the public no-argument `receive_messages()` loop
  at intervals no greater than 0.25 seconds, freeze the non-empty active turn ID after
  `start_task`, accept only a matching `turn/completed` or `turn/finished`, and run for
  at most the Runtime's code-default 300-second inactivity bound. It retains sanitized
  method counts and normalized provider error codes only. A Runner-visible failure is a
  valid liveness result but is not a successful Luna provider smoke; only a matching
  terminal response satisfies the provider gate.
- After the user-confirmed DeepSeek-key revocation, one final diagnostic smoke may run
  from committed code. It has no business source, platform client, or StartLedger. It
  stops on the first matching terminal or typed Runtime failure and captures only the
  safe provider-error projection already written by the Adapter. Because the 300-second
  watchdog is an inactivity window that begins again on genuine allowlisted progress,
  the harness uses a 420-second absolute safety cap: a timeout before the Adapter's own
  typed watchdog failure is `BLOCKED/inconclusive`, not a product PASS or failure. No
  retry is permitted in that round.
- A retained start72 scan continues to detect the historical DeepSeek breach without
  modifying it; release notes require provider-side revocation/rotation confirmation.
- Run focused model/runtime tests, all R2.3-005 tests, full `modeling_team` tests, Ruff,
  `git diff --check`, GitNexus `detect_changes`, service restart, and backend/frontend
  health checks.

## Delivery gates

Implementation starts only after mandatory plan review returns PASS. A separate tester
must verify the final frozen hashes. Documentation and commit closure follow a passing
deterministic and credential-sanitization gates. Start72 does not satisfy the full
requirement. The remaining authorization may be used for a later fresh semantic run
only after this repair is committed, the exposed DeepSeek key is revoked/rotated, and
the user confirms continuation. The user confirmed revocation on 2026-08-10; the Luna
matching-terminal gate remains open. Independent Round 19 consumed the single permitted
post-revocation diagnostic, not a semantic start: setup succeeded, but the Adapter emitted
typed `inactivity-watchdog/llm-inactivity-timeout` before the 420-second cap and without a
matching terminal. No retry is authorized by this plan.

## Post-Round-19 cold app-server repair

1. Reuse the existing validated `FormalModelManifest`; do not add another model registry or copy
   host `models_cache.json`. For formal persistent roles, `_initialize` passes the role's exact
   manifest model as the `model` field of `thread/start`. For formal Source/Platform Examiner
   children, the private child launch passes the child package's exact manifest model in the same
   field. Existing manifest-backed TOML remains the sole provider/reasoning binding.
2. Keep the projection formal-only. Non-formal and R2.3-002 `thread/start` payloads remain unchanged
   and omit `model`; missing manifest, unknown package, tuple mismatch, or drift stays fail-closed
   before launch. Do not broaden Runtime configuration, cache copying, retry policy, or timeout
   behavior.
3. Add focused capture tests for Coordinator, Modeling, Protocol, Acceptance, Source Examiner, and
   Platform Examiner. Assert exact `model=gpt-5.6-luna`, unchanged config/auth/MCP ordering, and no
   second source of truth. Add non-formal request-shape regression and malformed/drift failure cases.
4. After deterministic and full regressions pass, an independent tester runs exactly one bounded
   formal Coordinator empty-business app-server smoke from the frozen state. It uses no source,
   platform client, Runner reservation, or StartLedger, stops on a matching terminal or typed
   Runtime failure, retains only sanitized evidence, and does not retry. Only a matching terminal
   opens start73.

This repair was explicitly approved by the user on 2026-08-10. Implementation remains gated on a
fresh mandatory plan-review PASS.

## Post-Round-20 auth-lifetime differential probe

Round 20 proved the explicit model reached the live request but did not produce a terminal. Before
another production change, run one single-variable diagnostic against the same frozen formal
Coordinator configuration: keep the private 0600 `auth.json` staged through the turn instead of
unlinking it after the accepted `turn/start`; delete and audit it during cleanup. This is a probe,
not the proposed production security contract.

The probe must use the same explicit manifest model, TOML provider/reasoning, bwrap namespace, MCP
surface, instructions, task input, public receive pump, inactivity watchdog, and absolute cap as
Round 20. It may alter only auth unlink timing in its temporary harness. Retain sanitized
notification method counts and Adapter provider-error fields (`variant`, bounded `http_status`,
`will_retry`, turn digest) plus typed failure/terminal summary; never retain provider message/data,
stderr, token bytes, or auth contents. Use no source, platform client, Runner reservation, or
StartLedger and do not retry.

A matching terminal would attribute the remaining failure to the current auth lifetime and require
a separately reviewed production credential-delivery design. The same inactivity failure with no
safe provider event rejects that hypothesis and leaves app-server/MCP or prompt execution as the
next diagnostic layer. Either outcome is evidence only and cannot open start73 by itself, because
retaining auth through model execution violates the currently accepted production boundary.

Round 21 did not reach first-turn execution: the temporary test harness raised a local closure error
at the auth-retention seam and then cleaned successfully. Preserve that round as `BLOCKED/test-harness`.
One corrected Round 22 probe is permitted only after the replacement callback passes a deterministic,
no-process preflight proving that it changes only auth-file lifetime, preserves the barrier state and
safe evidence transition, and completes cleanup without exception. If that preflight passes, Round 22
uses the unchanged single-variable contract above exactly once and without retry.

## Superseding implementation — formal DeepSeek v4 Flash rollback

1. Replace the formal-only Luna manifest with one exact six-package DeepSeek artifact and update
   `model_manifest.py` constants/schema validation to accept only
   `deepseek-v4-flash/deepseek/max`. Preserve loader/initial-baseline/post-preflight digest equality and
   formal-only projection; shared packages and non-formal/R2.3-002 behavior do not change.
2. Add a small Runner-owned loopback provider proxy module. Its production credential path is fixed at
   `~/.config/ontology-platform/modeling-team-deepseek.env` (constructor injection exists only for tests). It binds
   `127.0.0.1:0`, accepts only `POST /responses` with a 32 MiB request cap, removes inbound auth,
   injects the Host bearer token upstream, streams the response, and retains only safe counters/status categories.
   It forwards a fixed non-auth header allowlist to TLS-verified `https://api.deepseek.com/responses` with ambient
   proxies and redirects disabled and bounded timeouts. It must not log or persist provider headers/body/free text.
   The key is held in a mutable buffer and overwritten on idempotent stop.
3. Move formal credential preflight into `TeamRunner.prepare` beside the current model-manifest no-side-effect gate.
   Missing, symlinked, non-owner, non-0600, malformed, or multi-assignment files fail before platform, ledger,
   run-root, transport, capability, proxy, process, or child creation. Store only a non-persisted binding of canonical
   path/device/inode/size/mtime-ns; Runtime reopens with `O_NOFOLLOW` and requires exact fstat equality before reading.
   Never store key bytes or key digest in `TeamRun`, baseline, manifest, or evidence. Remove the formal
   `os.environ[DEEPSEEK_API_KEY]` audit-sentinel read and ignore ambient `DEEPSEEK_API_KEY`/`LLM_API_KEY` completely;
   preserve the existing non-formal/R2.3-002 resolution path.
4. In `CodexRuntimeAdapter.start_roster`, resolve the key only after the frozen run is attached, start exactly one
   proxy before Agent launch, and configure all formal persistent roles and Examiner children with the proxy URL plus
   exact manifest tuple. Formal configs omit `env_key`, static token, auth command, and OpenAI `auth.json`; process env
   remains minimal and key-free. Add an explicit `provider_proxy` first-turn credential mode: keep the existing
   notification buffer/replay and early ServerRequest response logic, but complete a safe no-file transition instead
   of calling file unlink with `auth_path=None`. Existing file-auth behavior remains unchanged. Startup failure unwinds
   the proxy and partial roster exactly once.
5. Extend stop/child cleanup so Agent and Examiner processes terminate before the proxy listener closes. Scan process
   surfaces and artifacts with the actual mutable key buffer before wiping it; for formal provider-key audits suppress
   `matched_secret_digests` and persist counts/booleans only. Any match makes credential cleanup fail and the run
   overall `runtime/infrastructure,false`. After the final scan overwrite/release the proxy key buffer. Preserve typed
   provider/RPC failure normalization and the 300-second inactivity watchdog.
6. Add a formal-only lifecycle-owned stderr drain for each persistent and Examiner process. Drain continuously with a
   bounded overlap buffer that detects a sentinel split across chunks; retain counts/booleans only and never raw stderr
   or key digest. A match marks credential cleanup failed, while drain lifecycle failure becomes typed Runtime failure.
   Preserve non-formal behavior.
7. Add deterministic tests for exact six-package tuple/digest/TOCTOU, credential-file metadata and parsing, zero-side-
   effect preflight, proxy auth replacement and streaming, method/path/body rejection, early upstream failure,
   persistent/Examiner config and env, partial-start unwind, idempotent stop, and real-key sentinel absence across
   argv/TOML/auth/shell snapshot/session/SQLite/WAL/SHM/log/evidence/stderr. Include split-chunk stderr matches,
   nonmatching high-volume drain/backpressure, no raw/digest output, persistent/Examiner teardown, and non-formal
   compatibility. Re-run formal and non-formal regression suites, Ruff, compile/diff, GitNexus, restart, and health.
8. After independent deterministic PASS and secure operator installation of the credential file, execute exactly one
   bounded formal Coordinator empty-business smoke. It cannot use source/platform/Runner/StartLedger/Examiner or
   semantic modeling and cannot retry. Matching terminal plus zero secret/residue passes the provider gate; otherwise
   retain a typed Runtime result and keep start73 paused.

The user approved this rollback and the local proxy boundary on 2026-08-10. The plaintext credential supplied in chat
must never be copied into repository files, delivery documents, tool commands, logs, or test fixtures. Credential
installation is an operator step through a non-echoing local channel.

Implementation and Independent Round 25 passed. The initial live attempt exposed and preserved one formal TOML
duplicate-scalar startup defect; the repair retained one exact tuple and added parser/unwind coverage. The subsequent
single live empty Coordinator smoke received matching `turn/completed` through the proxy with upstream 2xx and zero
secret/residue. The DeepSeek Runtime/provider gate is complete; start73 may proceed from the committed rollback, while
semantic acceptance remains a separate live requirement.

## Start74 cleanup-audit ordering repair

1. Extend artifact/process scanning with safe `scan_complete` and `scan_error_count` fields; treat unreadable
   filesystem and live `/proc` surfaces as incomplete without changing the true secret-match count.
2. For formal runs only, split Adapter stop into resource teardown/private-file removal followed by one final
   run-wide audit while the provider key remains available for comparison. Project one digest-free
   `aggregate_secret_audit` onto all persistent-role cleanup booleans.
3. Make child/role/proxy cleanup best-effort but fail-closed: continue remaining teardown, preserve fixed reason/count
   evidence, keep child residue visible, verify proxy thread/socket closure, and wipe the key in an outer `finally`.
4. Lock and cache the first lifecycle cleanup projection. Repeated stop/read is immutable; a later roster resets only
   after proving the prior lifecycle owns no active resource. Preserve non-formal/R2.3-002 behavior and schema.
5. Add regressions for the Protocol temporary-config ordering defect, real retained secret, incomplete scan, child
   residue, proxy shutdown/join/socket failure, key wipe, idempotence, lifecycle reset and non-formal compatibility.
   Run focused, R2.3-005, full modeling-team, Ruff/compile/diff/GitNexus and independent restart/health checks. Do not
   run a provider smoke or semantic model, mutate start74 evidence, or append ledger state during this repair.

Development and Independent Round 28 passed these deterministic gates. Start74 remains an immutable overall failure;
the repair establishes the cleanup contract for a future authorized run only.
