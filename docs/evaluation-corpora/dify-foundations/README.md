# Dify Foundations Evaluation Corpus

This directory is the versioned, repository-local input for the Dify foundations modeling scenario in
R1.1-004. It is not a general document-ingestion feature and it is not a promise that the included
documentation is current.

## Pinned snapshot

- Snapshot: `dify-foundations-2026-07-18-5396c1a`
- Official repository: `langgenius/dify-docs`
- Commit: `5396c1a1afbea0dee3d089abfabdf6dac91d30d5`
- Commit time: `2026-07-17T19:52:12+08:00`
- Manifest SHA-256: `9bc401fde174c4a0023ab9f2605fde2c5c9de0702b069a21f891904ca04a5f3f`

English pages are the authoritative content source. Official Chinese pages present at the same commit
are included for Chinese modeling and user confirmation; `official_same_commit` records provenance, not
a guarantee of semantic parity or freshness. The project does not create translated corpus pages.

The snapshot covers product positioning, application types, Workflow and Chatflow, workflow creation,
canvas orchestration, variables, testing and publishing, application reuse and DSL, Start/User Input,
LLM, IF/ELSE, Iteration, Jinja2 Template, Output, and the official Multi-platform content generator quick
start. It deliberately excludes complete API reference, plugin development, deployment operations,
advanced knowledge features, monitoring/logs, images, scripts, and tracking assets. `docs.json` is the
pinned official navigation index; live `llms.txt` is only a freshness-discovery entry and is never needed
for offline verification or rebuilding the selected file list.

## Attribution and license

The files under `snapshots/*/official/` are Dify documentation by LangGenius, retrieved from the official
repository and used under the Creative Commons Attribution 4.0 International license. The exact license
text is preserved as `official/LICENSE`; the manifest records official page and repository locations for
every file. The corpus metadata, verification tool, and tests are part of this project.

## Commands

Run the offline checks from the repository root:

```bash
python docs/evaluation-corpora/dify-foundations/tools/corpus.py verify \
  docs/evaluation-corpora/dify-foundations/snapshots/dify-foundations-2026-07-18-5396c1a
python -m unittest discover \
  -s docs/evaluation-corpora/dify-foundations/tests -p 'test_*.py' -v
python docs/evaluation-corpora/dify-foundations/tools/corpus.py locate \
  docs/evaluation-corpora/dify-foundations/snapshots/dify-foundations-2026-07-18-5396c1a \
  --topic jinja2-template
```

To reproduce official bytes, use a new or empty destination whose final directory name is the snapshot
ID:

```bash
python docs/evaluation-corpora/dify-foundations/tools/corpus.py rebuild \
  docs/evaluation-corpora/dify-foundations/snapshots/dify-foundations-2026-07-18-5396c1a \
  --destination /tmp/dify-corpus-check/dify-foundations-2026-07-18-5396c1a
```

`rebuild` constructs URLs only from the pinned commit and official raw GitHub host, rejects redirects,
sends no authentication headers, verifies every downloaded hash, and never overwrites a non-empty
destination. CI runs `verify` and the unit tests without network access; a real network rebuild is an
explicit release/acceptance check.

## Modeling and evidence use

Business Knowledge Packs should record the snapshot ID, manifest hash, selected paths, and file hashes.
Coverage Matrices assign `MODELED`, `DEFERRED`, `AMBIGUOUS`, `UNSUPPORTED`, or `MISSING` outside the
immutable snapshot. Platform Evidence References still contain the exact excerpt actually used; a local
file is not itself an Evidence Reference. Keep official quotations separate from summaries and Agent
inferences.

Two useful disambiguation anchors in the English source are:

- `official/en/cloud/use-dify/workspace/app-management.mdx` describes application duplication/templates
  and DSL import/export for application reuse.
- `official/en/cloud/use-dify/nodes/template.mdx` defines the Template workflow node as a Jinja2 data
  transformation mechanism. It is not an application template.

The quick start's `Multi-platform content generator` is in `official/en/quick-start.mdx`. Always report
the manifest entry's path and SHA-256 with a quotation so another role can reproduce the lookup.

## Auditable offline role checks

Acceptance uses three fresh role sandboxes, each started with:

```bash
codex exec --ephemeral --sandbox read-only --json -C <snapshot-dir> '<role prompt>'
```

The role's first shell call must attempt
`socket.create_connection(("docs.dify.ai", 443), 2)` and stop if the connection succeeds. Preserve the
complete JSONL stream in a uniquely named system-temporary acceptance directory. A tester must verify the
canary failed due to the sandbox, subsequent tool events only read local files, every reported path/hash/
excerpt matches the snapshot, and all roles used the same manifest hash. A prompt that merely says
"offline" is not evidence. Missing canary output, incomplete event logs, any Web/MCP network call, or a
successful canary makes the role gate fail or block.

## Updating without destroying history

Never edit an existing snapshot in place. Create a new snapshot ID and manifest, set
`previous_snapshot` to the prior ID, rebuild into a new directory, run `diff` between manifests, and keep
both versions in Git. A Build Session uses one snapshot ID throughout; a freshness check may report that
official repository HEAD moved, but it must not silently mix new content into the active session.
