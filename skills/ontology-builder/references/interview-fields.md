# Project interview fields

Interview the user in their domain language before mapping anything into platform fields. Persist the
user's original answer before mapping it into fields. Confirmed fields should cite one or more saved
answer IDs.

## Interview posture

Start by understanding the current system and business context, not by asking the user to design an
ontology or schema. Users may not know platform concepts and can introduce misleading structure if
asked for classes, relations, operations, or platform features too early.

Prefer questions like:

- What work or decision does the current system support today?
- Who uses it, and what do they need to know or decide?
- What things, events, documents, policies, or records do people talk about?
- Where does the information live now, and which sources are authoritative?
- What questions are hard to answer today?
- What exceptions, lifecycle states, time windows, or regional/version boundaries matter?

Avoid early questions like:

- What ontology classes do you want?
- What schema should I create?
- What relation types should exist?
- Which RDF graph or internal batch structure do you need?
- What feature should this ontology implement?

Use platform terms only when reporting internal work or when the user already uses them accurately.
When confirmation is needed, present candidates in domain language with a short example instead of
asking the user to manipulate internal concepts.

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

## Conversation flow

1. Recover existing platform state and saved answers.
2. Ask broad background questions about the existing system and workflow.
3. Drill into actors, objects, events, decisions, policies, evidence, and pain points.
4. Translate answers internally into the required fields and save that mapping.
5. Summarize the business understanding in user-facing language.
6. Derive competency questions from the summary and ask the user to confirm or correct them.
7. Only after confirmation, derive schema, relation, fact, rule, and Operation candidates.

Ask no more than three questions per turn. Prefer questions whose answers unblock schema design or a
high-priority competency question. An optional skip is a confirmed state, not a missing state; report
its quality impact and do not ask it again unless the user reopens it.

Before schema discovery, require either a confirmed summary or an explicit user instruction to proceed
with uncertainty. If proceeding with uncertainty, record the uncertain fields and keep resulting
candidates lower confidence.
