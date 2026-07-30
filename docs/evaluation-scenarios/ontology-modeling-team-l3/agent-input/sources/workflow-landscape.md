# Workflow landscape

The content platform contains three independently managed workflows: C evaluates
generated content, B generates content and invokes C as a published Tool before
returning its result, and A publishes B's result. Operational diagrams describe the
dependency path as C -> B -> A. B identifies C by workflow identity, not release ID.
Each workflow has a separate draft and publication lifecycle.
