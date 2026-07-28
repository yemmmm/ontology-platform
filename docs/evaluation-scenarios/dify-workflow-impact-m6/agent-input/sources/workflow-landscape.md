# Workflow landscape

The content platform contains three independently managed workflows:

- Workflow C evaluates generated content and returns a scoring result.
- Workflow B generates content and invokes Workflow C as a published Tool before returning its result.
- Workflow A publishes the result produced by Workflow B.

Operational diagrams describe the dependency path as C -> B -> A. B's checked-in tool configuration
identifies the callee as `workflow-c-quality-evaluator`; it does not contain a release identifier.
Each workflow has its own draft and publication lifecycle.
