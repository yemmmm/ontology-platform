# Modeling guidelines

## Core boundary

Ontology is the stable semantic model of a domain. It is not a copy of database schema.

- Use Ontology Schema for reusable concepts, stable relations, constraints, and inference paths.
- Use Entity Graph for concrete entities and concrete facts.
- Use Semantic Mapping for links between ontology concepts, entity identities, and external fields.
- Use Data Catalog for data location, sensitivity, owner, access policy, join key, and freshness.
- Use Connector for governed access to external databases or APIs.

Never put table names, physical column names, SQL joins, credentials, or access policy rules into the
published ontology schema unless they are genuine domain concepts.

## Ontology partitioning

Do not put every concept into one ontology. Partition by semantic stability, governance boundary,
reuse scope, and change frequency, not by database table or UI module.

- Use Core ontologies for stable cross-domain concepts such as `Entity`, `Agent`, `Organization`,
  `Person`, `Location`, `Event`, `TimeInterval`, `Identifier`, and `Provenance`.
- Use Domain ontologies for business-domain semantics such as `Customer`, `Contract`, `Product`,
  `Risk`, `Student`, `Course`, or `Assessment`.
- Use Application ontologies for application-specific workflow, dashboard, report, import, or
  integration concepts that should not pollute shared domain meaning.
- Split ontologies when different teams own definition, approval, release cadence, or stewardship.
- Split high-change vocabularies, status lists, categories, and classifications into Taxonomy or
  controlled vocabulary resources instead of changing stable ontology schema.
- Keep Ontology, Taxonomy, Semantic Mapping, Data Catalog, and Connector concerns separate. Mappings
  explain how external fields align to semantic concepts; they do not define domain meaning.
- Use bounded context judgment. If `Customer` means different things in CRM, billing, legal, and
  support contexts, preserve the context-specific concepts and bridge them with Mapping or a small
  bridge ontology. Avoid strong equivalence unless the identity and meaning are genuinely the same.
- Use import relationships for reuse. Application ontologies import Domain ontologies; Domain
  ontologies import Core ontologies and relevant Taxonomies. Do not copy shared classes into each
  ontology.

Split an ontology when releases require unrelated reviewers, concepts share no competency questions,
stable schema is blocked by fast-changing categories, naming conflicts become frequent, or external
system fields start appearing as first-class ontology concepts.

Example structure:

```text
core/entity
core/agent
core/time
core/provenance
domains/customer
domains/product
domains/contract
domains/risk
taxonomies/industry
taxonomies/geography
taxonomies/product-category
mappings/crm
mappings/erp
applications/catalog-ui
applications/analytics
```

## Class, Entity, Property, Relation

- Use a Class for a reusable category with stable meaning, identity rules, and lifecycle.
- Use an Entity for an identifiable instance.
- Use a Property for intrinsic literal values that do not need independent traversal.
- Use a RelationType when both endpoints have identity, independent meaning, evidence, or traversal value.
- Model events, policies, periods, projects, and rules as Classes when participants, time, status, scope,
  or exceptions must attach to them.
- Give every class a description, aliases, parent references, and evidence.
- Give every property a domain class, value type, required/multi-value flags, enum values, and constraints.
- Give every relation a source Class, target Class, inverse name when meaningful, and optional parent.

## Avoid copying database schema

Ask these questions before creating a Class or Property:

1. Would this concept still exist if the database table or field were renamed?
2. Would a domain user naturally mention it?
3. Does it have a stable identity or lifecycle?
4. Does it help answer an approved competency question?
5. Does it participate in traversal, explanation, inference, or pattern discovery?

If the answer is mostly no, keep it in Mapping or Catalog, not Ontology Schema.

Example:

```text
Do not model: student_table, score_table, student_pii.id_card_number
Model: Student, Assessment, AssessmentResult
Map: AssessmentResult.score -> external grade system field
Catalog: student_pii.id_card_number is PII with restricted access
```

## Relation design

Relations are first-class semantic links, not disguised fields.

- Use a relation when the target should be traversed, filtered, explained, audited, or reused.
- Use a property when the value is a literal attribute of the source and has no independent identity.
- Do not collapse meaningful relationships into JSON blobs or text fields.
- Do not create inheritance unless the child is substitutable for the parent.

Example:

```text
Student --HAS_RESULT--> AssessmentResult --FOR_ASSESSMENT--> Assessment --BELONGS_TO--> Course
```

This is better than storing `grade` as a flat `Student` property when course, exam, time, and source
matter.

## Class-level and Entity-level relations

Class-level RelationType expresses a stable domain pattern:

```text
CourseOffering --CONFLICTS_WITH--> CourseOffering
```

Entity-level Relation expresses a concrete instance fact:

```text
2026春-高数周三1-2节 --CONFLICTS_WITH--> 2026春-物理周三1-2节
```

Rules:

- Entity-level relations do not automatically become Class-level schema.
- Mark instance-only relations with `scope=instance` or equivalent metadata.
- Promote a repeated entity-level pattern to schema only after review.
- Define relation semantics such as symmetric, transitive, inverse, status, and validity window.
- `CONFLICTS_WITH` is normally symmetric and non-transitive.

## Knowledge facts from natural language

Many “unstructured” statements are structured facts written in natural language. Convert them into
entities, properties, and relations when they need query, explanation, or linkage.

Example:

```text
寝室十一点门禁
```

Model:

```text
(:Dormitory {name: "学生寝室"})
(:AccessPolicy {name: "寝室门禁规定", cutoff_time: "23:00"})
(:AccessPolicy)-[:APPLIES_TO]->(:Dormitory)
```

Do not reduce it to `Dormitory.access_time = "23:00"` if policy scope, effective dates, exceptions,
or future revisions may matter.

Other examples:

- `16周是考试周` -> `AcademicWeek --DESIGNATED_AS--> ExamPeriod`
- `考试周不用上课` -> `ExamPeriod --SUSPENDS--> RegularClass`
- `2号图书馆明年建成` -> `ConstructionProject --BUILDS--> LibraryNo2` with expected completion date
- `端午节学校放假三天` -> `Holiday --APPLIES_TO--> School` and optionally `Holiday --SUSPENDS--> RegularClass`

Resolve relative dates such as “明年” against the source date when the fact is captured.

## 入图判断

Do not use the graph as a catch-all knowledge dump. For weakly related knowledge, ask:

1. Will users or agents query it through this platform?
2. Does it affect existing entities, schedules, policies, availability, eligibility, or explanations?
3. Can the platform keep it fresh and govern its changes?

If at least two answers are yes, model it in the Entity Graph. If not, keep it in documents, an
external system, or a future topic graph.

## External data and sensitive fields

- Large entity count is not a reason to avoid graph storage. Use graph storage when the data participates
  in traversal or reasoning.
- Sensitive or operational fields may remain outside the graph.
- Store external identifiers and join keys only through approved Mapping/Catalog structures.
- Agent must query external data through governed platform tools, not direct SQL or credentials.
- Cross-system one-to-one matches produce mapping candidates or Merge Proposals. They do not directly
  create `SAME_AS`.

## Minimum schema usability

Broad extraction may start only when:

- every extracted entity kind has a reviewed Class;
- proposed edges have reviewed RelationTypes or approved Entity-level relation types;
- Mapping/Catalog candidates exist for external facts needed by competency questions;
- no blocking schema validation errors remain.

Represent uncertainty in confidence and review status, not by weakening deterministic constraints.
