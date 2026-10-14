---
name: competency-question-authoring
description: Draft source-grounded competency questions, answer points and evidence for a business scenario or approved logical slice. Use as the Competency Question role before user review and public/hidden freezing.
---

# Competency Question Authoring

Create questions that test what the semantic model should make understandable. Your role
instructions and mounted CQ contract govern draft fields, review, visibility and handoff. This
skill supplies the authoring method; it does not authorize approval, freezing or model production.

## Establish the business question

Read only approved business inputs and confirmed user answers. Separate business statements from
database/schema/sample evidence. A column name, status code or a few rows can suggest an ambiguity;
they cannot establish the business definition, lifecycle or metric rule.

For panorama questions, look for end-to-end outcomes, shared terms, important process dependencies
and cross-slice relationships. For slice questions, use the approved slice boundary and test its
meaningful concepts, relations, conditions, values or mappings. Do not choose Ontology topology or
require Classes, predicates or implementation details in a user's question.

Choose questions whose answers materially depend on modeled semantics. Prefer a precise question
about a business distinction, rule or relationship over a broad request to list everything. Separate
independent questions when bundling them would hide which meaning is supported. Avoid rewording one
question repeatedly just to reach a count; the task's suggested counts are guidance, not quotas.

## Write an answer that can be judged

For each question, identify the necessary answer points and bind them to exact approved source or
confirmed-interview references. State conditions, exclusions, units, lifecycle states, time bounds
and mapping assumptions only where the evidence supports them. Do not fill a plausible missing rule
from general knowledge or sample data.

A reference answer is a set of required business meanings, not wording that a consumer must copy.
Different wording with the same supported meaning should be acceptable. Preserve explicitly unknown
parts and their affected scope; a properly evidenced unknown can be the correct answer.

If the question has multiple materially different readings, clarify it before publishing or name
the ambiguity explicitly for review. If the approved inputs cannot support the proposed answer,
ask through your permitted direct user channel or retain an explicit unknown. Do not manufacture a
confident reference answer to make the question look complete.

Distinguish semantic support from SQL execution. A question can test whether meaning, joins and
metric rules support a query; claims about actual database results require the separately authorized
execution evidence and must not be inferred from the ontology alone.

## Check every required answer point before review

After generating both public and hidden questions, and before panorama-review or slice-review,
check every answer point against three criteria: an approved source supports it within the current
Task's authorized output scope; the question
explicitly asks for it or a correct answer necessarily needs it; omitting it changes the business
judgment or violates the question's stated answer scope. Merely appearing in the source does not
make a statement required in every answer. Preserve necessary implicit conditions, such as an
approval prerequisite, even when they are not repeated in the question.

Use the existing draft `note` to record the question ID and one-based answer-point position,
source locator, question-scope correspondence, and retain/modify/remove-from-this-question
decision with its reason. Cover every required point; points sharing a basis may be grouped.
This is a human-readable explanation, not a new field, scoring rule, or machine marker.

Remove unrelated obligations from this question's scoring scope. If an independent aspect still
needs testing, clarify the question or propose a separate question within the approved coverage;
do not silently discard required coverage or put the correct answer into the question. Platform
constraints, such as not executing external APIs, need not be recited in unrelated business
answers. Keep business effects, conditions, result identity and authorization/execution boundaries
when they affect the conclusion. An answer that actively contradicts a boundary is still wrong.

Content corrections use the existing review/version lifecycle, not `note` to override frozen
text. Self-checking does not approve a question. After reordering points, locate them within the
new content version. Keep all hidden check reasons private with the draft and review records.

In the same check note, distinguish confirmed business meaning, declared source-structure evidence
and a supported unknown. A physical declaration does not confirm customer meaning or business
cardinality; unknown business meaning does not erase the declaration. Excluding executable
SQL/API mappings does not automatically exclude source evidence relevant to the approved chain.
If Task output scope and a proposed required point disagree, clarify that point through review
before freezing; do not silently expand the Task or tailor obligations to a prior model failure.
The reviewed question/points must state the intended distinction clearly enough to judge from
the frozen approved basis, without production context or a new packet field.

## Check coverage and independence

Before publishing, compare the draft against the scenario or approved slice: which important
business outcomes and relationships are covered, which remain untested, and which questions are
redundant? Do not silently expand the approved business scope to close a gap.

Draft public and potentially hidden questions from the same approved source basis, while respecting
the frozen visibility contract. Any question or answer already shown to a production role remains
public. Do not create a nominally hidden rewording whose answer is simply revealed by a public
question; aim for a distinct application of the supported semantics. Do not use tester-only truth,
prior model results or guessed future failures to tailor the hidden set.

Question generation does not authorize sending private drafts or answer points to Coordinator,
Modeling or Protocol. Only the Runner-published public projection is shared with production roles.
Do not grade the finished model or revise a reference answer to fit an Examiner's response.

## Submit for review

Publish using the exact mounted draft contract with stable question IDs, answer points, evidence,
unknowns and scope. Report a concrete coverage gap or unsupported answer to the user. User decisions
control approval, revision and grouping; elapsed time, a suggested count or this skill is not an
approval. Correct rejected fields through the existing feedback and preserve version bindings.

## Bind the checked content to its reviewed version (R4.0-013)

Locate your self-check by question ID, current `content_version` and one-based answer-point
position. After a content correction, redo the check against the corrected question and point
order; an earlier note does not validate the successor. Publish the actual corrected content
through the existing review lifecycle. The Delivery host independently compares the final frozen
question, points, review identity and version against the approved modification; a note alone
cannot change the frozen answer scope or preserve an unreviewed point.
