# Minimal service-site installation scenario

Source ID: checkpoint-minimal-source-v1

This is an artificial scenario authored for the user-requested R3.0-015 flow test.
It is not an excerpt from the industrial-service-v3 customer/work-order corpus.
The following definitions are the complete business source for this scenario.

## Business definitions

1. A Service Site is a physical location at which equipment is installed for service.
2. An Installed Asset is an individual piece of equipment installed for service.
3. An Installed Asset is installed at a Service Site. The relationship is directed
   from Installed Asset to Service Site and means physical installation location.
4. Service Site and Installed Asset are distinct concepts. A site is not equipment,
   and an asset is not a location. The relationship does not mean ownership.

## Scope and unknowns

Only these two concepts, their meanings, and the installation-location relationship
are in scope. The source supplies no named assets or sites, instance rows,
cardinality constraint, equipment models, customers, work orders, lifecycle states,
metrics, SQL mappings, controlled value sets, or business access policy.
Do not infer any of those. Their absence does not prevent completing the defined
concept-and-relationship scope. Platform access checks still apply.

The source is available as evidence for these definitions and their relationship.
It may be cited by source ID, file path, and numbered definition. There are no
additional business documents required to interpret this artificial scenario.
