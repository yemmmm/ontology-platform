# Review and publication rules

Agent-permitted actions:

- Read durable state and audit records.
- Save interview answers and confirmed brief mappings.
- Create idempotent draft proposals backed by evidence.
- Run deterministic validation and readiness checks.
- Summarize review batches and return their platform deep links.

Human-only governance actions:

- Approve or reject a proposal or proposal item.
- Edit/merge approved knowledge, resolve conflicts, or approve an entity merge.
- Approve/reject Fact Claims.
- Waive validation or publication gates.
- Apply governed changes when the workbench requires it.
- Publish or deprecate a version.

Never translate conversational consent into a governance call. Wait until a subsequent read proves the
platform status changed. For a pending batch, show its stable ID, counts, summary, validation outcome,
and exact deep link. For publication, show every gate and require explicit confirmation in the workbench.
