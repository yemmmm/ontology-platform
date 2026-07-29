# L0 coordination task

You are the modeling coordinator for an L0 runtime probe. Work only with `/opt` and `/work`.

1. Spawn exactly `modeling_agent` and `platform_protocol_agent` with explicit
   `agent_type` and `fork_turns="none"`.
2. Ask the modeling agent for the fixed non-answer modeling description from
   `/opt/modeling-source.md`.
3. Ask the protocol agent to call `ontology_platform.check_platform_health`
   exactly once and return only its normalized status.
4. Do not call an ontology-platform MCP tool yourself. Do not read paths outside
   `/opt` and `/work`, and do not reveal credentials.
5. Once both children return, output exactly one block:

```text
L0_NEEDS_ANSWER
question_id=l0-confirm-modeling-intent
question=Confirm that the bounded modeling intent may be accepted.
```

When resumed, route the raw answer to `modeling_agent` using the same explicit
role contract and finish with exactly one block:

```text
L0_COMPLETE
session_reused=true
routed_to=modeling_agent
conclusion=<short non-secret confirmation>
```
