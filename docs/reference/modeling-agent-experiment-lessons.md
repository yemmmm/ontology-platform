# External Modeling Agent Experiment Lessons

## Status and authority

This document collects practical experience from external and multi-Agent ontology-modeling
experiments, including R2.2-001 L3.

It is **reference-only and non-normative**. It provides examples, heuristics, failure patterns, and
diagnostic tactics. It does not create completion gates and cannot override:

1. an authoritative requirement;
2. `AGENTS.md`;
3. an accepted design or test plan; or
4. an explicit user instruction.

Use only the parts relevant to the current stage and demonstrated risk. Do not copy every historical
control into a new experiment.

## General experience extracted from prior repository guidance

### Start with modeling, not a generalized runtime

- The first useful experiment is normally one bounded corpus, one fresh modeling scope, one
  deterministic dry-run/application path, validation, and one governed query.
- Run only the minimum Runtime checks needed to begin real modeling. Consumer suites, mutation
  matrices, repeated-success measurement, generalized recovery, polished management UI, and
  production security are later-stage concerns unless the current experiment demonstrates a need.
- A limited attempt budget is useful because it makes the modeling direction observable. It should
  not be spent on broad preflight work designed mainly to avoid learning from a real attempt.
- Keep design, review, documentation, and regression work proportional to the current gate.

### Reuse accepted execution paths

- Inventory the closest accepted scenario, launcher/script, prompt, role configuration, protocol
  helper, evidence reader, and tests before designing a replacement.
- A Runtime change should usually alter only launch, input assembly, tool bridging, event
  normalization, and terminal-state detection. Rebuilding isolation, resource lifecycle, Batch,
  validation, query, cleanup, and acceptance around each Runtime creates avoidable drift.
- Preserve the earlier path as a regression oracle. If reuse is genuinely incompatible, record the
  exact incompatibility and review the replacement before implementation.

### Keep semantic and mechanical responsibilities separate

- Deterministic code is a good owner for UUIDs, canonical JSON, filenames, atomic publication,
  schemas, lease timing, checkpoint bodies, retry identity, and response parsing.
- Modeling Agents should spend reasoning on business meaning, Classes, Properties, Shapes,
  relations, evidence, gaps, and explicit unknowns.
- A Delivery-Agent execution script can manage temporary resources and collect mechanical evidence,
  but it is not a separate Host layer and should not decide semantic quality.

### Prefer the smallest safe credential and isolation path

- For a local modeling-quality experiment, direct provider access with a short-lived credential is
  often the smallest workable path.
- Add a model proxy, network sandbox, stronger credential isolation, or a generalized broker only
  when required by the accepted stage or a demonstrated risk.
- A useful practice is to retain exact cleanup evidence for uniquely owned keys, Projects,
  processes, and temporary homes without retaining plaintext credentials.

### Make failures observable and scoped

- Expose progress milestones and distinguish first-response waits from terminal waits.
- Preserve the real failing layer instead of relabeling infrastructure trouble as model quality.
- A runtime or transport failure should lead to a narrow runtime repair, not a new ontology
  workflow, Consumer, mutation suite, or governance subsystem.
- Track semantic-modeling time separately from infrastructure, harness, review, and documentation.
  A low semantic share is a signal to reduce the path.

### Coordinate parallel work explicitly

- Parallelism is not itself a failure cause.
- Freeze each task contract first, then assign non-overlapping files, ports, Project/Ontology IDs,
  runtime directories, cleanup responsibility, and shared-document ownership.
- Use one shared test plan with append-only rounds. Give the delivery record one owner.

## R2.2-001 L3 failed attempts and corrections

### Collaboration evidence was read from the wrong source

**Observed:** the outer `codex exec --json` transcript did not list the nested Modeling Agent, so
three runs were initially summarized as if no child Agent existed.

**Actual evidence:** raw coordinator rollouts contained `spawn_agent`; linked child rollouts and
grounded questions existed. One run was still a valid negative case because it omitted
`agent_type=modeling_agent`; later runs contained the required role and `fork_turns=none`.

**Correction:** use the accepted L0/L1 raw-rollout reader and correlate coordinator
`thread.started`, `spawn_agent`, `sub_agent_activity`, and child `session_meta`.

**Experience:** summary streams are useful for progress, not authoritative identity proof.

### The first-modeling deadline was enforced twice

**Observed:** the coordinator and Modeling Agent had already run, but a second deadline check during
delegation recording appended a halt and marked the retained run paused.

**Correction:** enforce the first-modeling clock at the first valid modeling delegation and recover
the raw state with an append-only, hash-bound correction.

**Experience:** a gate should have one owner and one transition. Reapplying it later can invalidate
work that already satisfied it.

### Recovery initially assumed only one question

**Observed:** the first implementation used one fixed pending-question snapshot. A legitimate
second question collided with that snapshot, and later answer release recomputed an older
correction.

**Correction:** represent question/answer transitions as ordered append-only cycles. Bind the
canonical question, exact frozen answer, coordinator, origin transcript, prior cycle, and prior
correction. Validate the complete chain on status and continuation.

**Experience:** resumable interviews are event sequences, not a mutable single-slot record.

### The resume command could not write `/work`

**Observed:** the retained coordinator Session resumed, but its parent `codex exec` invocation was
read-only and could not publish the next question or candidate.

**Correction:** place sandbox and working-directory options on the parent command before `resume`;
probe `/work` as writable, `/opt` as read-only, and repository/tester-only paths as absent.

**Experience:** a Runtime check that proves read access at L0 does not prove later continuation-write
requirements. Probe the exact contract needed by the next stage.

### The Protocol interpreter mount reused the wrong directory

**Observed:** MCP initialization failed before the Protocol Agent started because the backend source
parent was mounted instead of the verified virtual-environment runtime root. That broader mount also
risked exposing `.env`.

**Correction:** reuse the L1-proven resolved interpreter runtime mount and expose only explicitly
required script files.

**Experience:** reuse the exact accepted mount shape, not a path that merely looks adjacent.

### The keyed Protocol Agent repeated the no-key probe

**Observed:** after the Delivery Agent had injected a temporary key, the Protocol Agent repeated an
authentication-rejection probe and canceled its otherwise valid Build Session.

**Correction:** perform the no-key rejection before key creation, stage a redacted proof, inject the
temporary key, and explicitly tell the Protocol Agent not to repeat the probe.

**Experience:** lifecycle proofs should have one owner. Repeating a precondition after the state
transition can invalidate the active workflow.

### Relation IRI validation happened too late

**Observed:** dry-run accepted relation client IDs that were not absolute RDF IRIs. Atomic apply
then failed at RDF persistence and fenced the Ontology.

**Correction:** validate source, predicate, and target as absolute RDF IRIs before producing any RDF
delta. Negative tests prove zero workspace change, zero RDF delta, and no fence.

**Experience:** dry-run must validate every precondition enforced by downstream persistence, not
just the request schema.

### One Batch was not enough for platform-issued relation IRIs

**Observed:** relations need absolute resource IRIs, but entity client IDs are not those IRIs.

**Correction:** apply bounded schema and entity Batches first, reread the platform-issued IRIs, then
construct the relation Batch.

**Experience:** split Batches at identity-resolution boundaries rather than teaching the model to
guess persistence identifiers.

### The generic terminal timeout rejected valid progress

**Observed:** a Protocol Agent that had already applied its schema and Shape was stopped by the
generic 300-second terminal timeout while materializing instances and relations.

**Correction:** keep first-response and normal coordinator/resume limits unchanged, but give the
demonstrably longer Protocol role its own bounded terminal budget.

**Experience:** use role-specific timing based on observed work. Do not globally increase every
timeout.

### Mechanical audit assumed exactly one applied Batch

**Observed:** a Protocol execution completed four valid Batches, rejected its negative dry-run,
completed the Build Session, and wrote a valid result. The Delivery Agent's script rejected it
because the old result contract expected one `applied` object instead of a list.

**Correction:** require a non-empty applied-Batch list and reread every listed Batch during
mechanical evidence validation.

**Experience:** acceptance contracts must reflect the actual bounded workflow and should not encode
an obsolete single-Batch implementation assumption.

### An independent inspection command mutated evidence

**Observed:** a status inspection appended a deterministic recovery correction while an independent
round intended to remain read-only.

**Correction:** later independent acceptance read the final snapshot, correction chain,
transcripts, receipts, and cleanup artifacts directly and modified only the shared test plan.

**Experience:** verify whether an apparently diagnostic command writes ledgers or caches before
using it in an independent evidence review.

## Reusable testing heuristics

- Keep modeling-start accounting separate from Protocol retries. A retry may reuse the same approved
  candidate and Agent Sessions, but it needs its own failure receipt and cleanup proof.
- Test collaboration identity from raw rollouts, including positive role/fork cases and a negative
  missing-role case.
- For recovery chains, test question/answer tampering, coordinator substitution, origin-transcript
  drift, prior-cycle drift, and prior-correction drift.
- For resume isolation, test both allowed writes and forbidden reads.
- For dry-run defects, assert absence of side effects, not only the returned error.
- For multi-Batch results, compare every reported receipt with platform facts.
- Let an independent tester evaluate the retained semantic evidence without creating or continuing
  the live run.
- Preserve failed rounds and failed attempts. A later PASS supersedes their conclusion but does not
  erase the evidence or lesson.
