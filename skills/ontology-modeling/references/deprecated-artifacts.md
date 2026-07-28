# Deprecated modeling artifacts

The following assets are retained only to explain historical deliveries. Do not invoke, install,
copy, or use them as workflow dependencies for new modeling work.

## Skills

- `skills/ontology-builder/`
- `skills/ontology-business-organizer/`
- `skills/ontology-model-reviewer/`
- `skills/ontology-retrieval-evaluator/`
- `skills/ontology-work-unit-modeler/`
- the former global ClaudeCode `ontology-builder` skill

Their Coverage Matrix, Business Knowledge Pack, fixed role gates, Local/Formal profiles, work-unit
handoffs, and role-specific evals are not completion requirements of `ontology-modeling`.

## ClaudeCode and repo-local Harness

- `.codex/hooks/modeling_harness.py` and `.codex/hooks.json`
- `.codex/modeling-harness.md`
- `.codex/fast_local_launcher.py`
- `.codex/local_modeling_adapter.py`
- `.codex/modeling_profiles.py`
- `.codex/shared_modeling_directory.py`
- `.codex/modeling_handoff.py`
- `.claude/modeling-harness.md`
- `.claude/local-modeling.md`
- `.claude/settings.json`
- `.claude/agents/ontology-*.md`
- `.claude/agents/simulated-user.md`
- `.claude/agents/source-extractor.md`
- `.claude/agents/semantic-analyst.md`

Do not reactivate the two-top-level-Claude session experiment, mailbox, Hook recorder, fixed role
team, local adapter, or shared-directory orchestration. A new run uses the current skill directly
with a single modeling Agent and an optional fresh read-only consumer.

Historical requirements, designs, test plans, delivery records, traces, and workspaces may still
describe these components. Treat their PASS status as evidence about the historical version, not as
authorization to use it now.
