---
name: minimal-chain-modeling
description: Model the two-concept installation-location scope in the R4.3-026 Team task using direct submission and governed self-checks. Use with its paired compact role package, not for larger scenario or checkpoint experiments.
---

# Minimal chain modeling

Read the complete sole business source and distinguish supplied meanings from absent facts.
Express the two concepts, their distinction, installation direction/meaning and supported
unknowns faithfully. Technical node/property counts are representation choices, not new
business scope. Do not create named equipment/location instances, cardinality or mappings
from assumptions. Choose representation by semantic level: the current entity/create_entity
path creates an owl:NamedIndividual even without a Class; a generic label does not turn it
into a concept definition. An asserted relation between these individuals states an instance
fact. A concept-only source must not acquire such facts merely to draw its directed chain.
Use existing Class/relation_type definitions when they fit the source, or another explicitly
supported concept-level representation; do not invent Classes to satisfy compilation.

Use the compact mounted candidate schema and R4.3-025 value/reference rules. Keep item IDs
neutral, candidate revisions immutable and the current complete graph available. Give each
concept its supported definition. The installation predicate's definition must retain its
meaning and exclusions; the directed relation refers to actual candidate item IDs and the
predicate's definition_ref when expressing a supplied instance relationship. The seven
unified candidate kinds do not include Class/relation_type: create those definitions with
item_id=null, target_ref=null and their semantic fields in an explicit change request;
candidate_ref=null is supported when no candidate items are selected. Publish this complete
immutable request as the semantic delivery. Create needed Classes first, then refer to their
actual retained receipt entries using existing_resource_ref to define the relation_type. The
retained MCP response is an envelope: a read-model resource item is addressed under
`/structuredContent/data/items/N`, while an
applied batch item is addressed at that same complete item path and exposes the platform
identity in its `resource_outputs` object, including both `resource_id` and `resource_iri`.
For `source_class_id`/`target_class_id`, bind the intended concept to the complete applied
receipt item by selecting the returned `resource_bindings` member by `change_id`/`item_id`.
Copy that member's `existing_resource_ref` unchanged into the field's
`existing_resource_ref` wrapper. Request order and `resource_bindings` order can differ from
the raw receipt `items` order: never turn a binding's array index into a receipt JSON Pointer.
For an older result without that reference, read the actual retained receipt, find the intended
definition's `client_item_id`, and use its actual item path. Before relation submission, match
each source/target concept to the named change and actual resource identity and compare the
direction with the approved definition. The compiler must receive the UUID from that exact
receipt item. A read-model `id`/`iri`/`class_iri` is a semantic IRI and must stay in an IRI slot;
never URL-decode it, derive a UUID from it, or use it as a resource ID. If a later applied batch
has advanced the current revision, retain the exact earlier applied receipt and let the governed
current read confirm that its exact resource IRI and label are still visible before reusing its
UUID. Do not use fields-only change IDs as candidate `definition_ref` or guess platform IDs.
If the receipt metadata, label, and IRI do not agree, stop and reread the complete receipt and
current model; do not swap endpoints by position.
Do not put required meaning only in a handoff or invent relation
annotation fields. Preserve supplied unknowns in supported semantic_definition fields and
report candidate-only unknowns as delivery gaps when they are not retrievable.

After Coordinator confirms the business scope/topology and Host confirms CQ freeze,
submit explicit intended changes using modeling_submit_model_changes. Retain actual slice
IDs verbatim; do not normalize hyphens or underscores. Before freeze you may prepare the
delivery and keep this session waiting. `cq_freeze_pending` is ordinary upstream dependency
waiting, not a blocked/terminal result, business clarification, or runtime issue: notify
Coordinator once and continue the same session after the existing Host confirmation instead
of reporting `status=blocked` or terminating the role. Retain all actual results
and correct only identified gaps. Protocol conversion, translation approval and
model dry-run are absent from this path. An applied receipt proves application, not semantic
quality. Read the current authorized model with public business questions; expand real IRI
anchors when needed to check full meanings and direction. Check the installation chain and
unknown handling without using private questions or asserting global completeness from a
page flag. Compare retrieved resource kinds/types and asserted statements against the source,
not only their labels or definition text. Source absence of named instances must agree with
the applied graph, and relationship definitions must not become asserted instance facts.
A complete association scan checks structure; it does not make this semantic decision. After
an applied relation, inspect the actual relation `sourceClassId`/`targetClassId` values and the
`rdfs:domain`/`rdfs:range` endpoint IRIs, expand each endpoint to its authorized Class label
and type, and compare them one by one with the approved direction and definition. Do not claim
the direction is confirmed or assert handoff semantic readiness from your own summary, labels alone,
or an association `COMPLETE` result. Host technical locators may identify artifacts and paths
but do not choose the business endpoints.
An endpoint change after this applied-model self-check is a new substantive repair round,
even if only the pointers change and the original textual definition stays the same. Report
the mismatch to Coordinator and await confirmation of a repair round under the existing user
authorization. If no rounds remain, retain the defect, finish permitted read-only checks and
resource closure, and hand off without correcting the model. Do not equate the ongoing initial
round's ordinary batching/format corrections with a new semantic repair after self-check.
Close the association self-check and owned resources before reporting handoff
readiness; preserve missing evidence rather than treating it as PASS.
