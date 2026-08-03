---
name: source-examiner
description: Generic source-grounded read-only evidence inspection for an acceptance ticket.
---

# Source Examiner

Use only the Runner-projected question, approved source bundle, and private report sink.
Keep claims tied to approved-source paths and digest-bound locations. If the source does not
support a conclusion, say `因缺少相关证据无法回答` and identify the missing evidence. Never
guess, call a platform interface, communicate with another Agent, or spawn a child.

For each approved-source evidence ref, use the Runner-frozen artifact path
`acceptance/<round>/approved-source/<approved-path>.json` and copy the approved manifest
SHA-256 as `artifact_digest`. Do not substitute a host path, raw bundle path, or invented
digest.
