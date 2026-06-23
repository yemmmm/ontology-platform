# Project interview fields

Persist the user's original answer before mapping it into fields. Confirmed fields should cite one or
more saved answer IDs.

Required for a usable brief:

- `domain_name`: the domain's unambiguous name.
- `business_goal`: decisions or outcomes the graph must support.
- `scope`: included processes, objects, events, and users.
- `core_concepts`: central actors, objects, events, and terms.
- `expected_granularity`: instance and event detail required.
- `data_sources`: available documents or user declarations and their trust priority.

Clarify when material:

- `exclusions`: explicit non-goals.
- `time_boundary`, `region_boundary`, and `version_boundary`.
- `terminology`: aliases, controlled terms, and languages.
- `allowed_inference`: whether and how derived facts may be proposed.

Ask no more than three questions per turn. Prefer questions whose answers unblock schema design or a
high-priority competency question. An optional skip is a confirmed state, not a missing state; report
its quality impact and do not ask it again unless the user reopens it.
