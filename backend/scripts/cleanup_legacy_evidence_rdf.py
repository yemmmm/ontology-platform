"""One-shot cleanup: remove all legacy evidence-related RDF triples.

Run this once after deploying the new PG-backed evidence system.

Background
----------
Before the refactor, evidence was stored as RDF triples:

  - ``?fact prov:wasDerivedFrom ?chunk`` edges linking facts to text chunks
  - 5 literal properties per chunk IRI (sourceDocument, sequence, charStart,
    charEnd, text)
  - ``?s op:evidenceStatus ?o`` markers ("missing_evidence" /
    "evidence_bound")
  - ``op:FactClaim`` reified assertion instances and their properties

After the refactor, evidence lives in the ``fact_evidence_bindings`` Postgres
table keyed by ``fact_id`` (sha256(s,p,o,g)). The RDF triples above are dead
data: nothing reads them, and leaving them around pollutes exports. This
script removes them.

Two modes
---------
``--dry-run``  Print the planned SPARQL UPDATEs without executing them.
``--print``    Just print the SPARQL UPDATEs (for manual paste into the
               Oxigraph /update endpoint or a SPARQL workbench). Does not
               require app settings or DB access.
default       Execute the UPDATEs via the app's ``RdfStoreRepository``
               against the configured ``oxigraph_url``.

Usage
-----
::

    uv run python scripts/cleanup_legacy_evidence_rdf.py --help
    uv run python scripts/cleanup_legacy_evidence_rdf.py --dry-run
    uv run python scripts/cleanup_legacy_evidence_rdf.py --print
    uv run python scripts/cleanup_legacy_evidence_rdf.py

Notes
-----
- SPARQL ``DELETE WHERE { GRAPH ?g { ... } }`` matches every named graph in
  the store, which is what we want here (legacy evidence triples may be
  scattered across multiple ``asserted_data`` graphs). There is no
  ``--graph-set-id`` flag because graph_set membership is a PG-side concept
  the SPARQL layer cannot see; if you need to scope by graph_set, list the
  member ``asserted_data`` graph IRIs and replace ``?g`` with
  ``VALUES ?g { <iri1> <iri2> ... }`` in each UPDATE before pasting.
- ``op:FactClaim`` cleanup deletes both the ``?s a op:FactClaim`` typing
  triple and all of ``?s``'s outgoing property triples, in a single
  nested ``DELETE WHERE``. (Oxigraph implements SPARQL 1.1 Update, so
  deleting the same variables in one statement is well-defined.)
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Iterable

logger = logging.getLogger("cleanup_legacy_evidence_rdf")

PROV_WAS_DERIVED_FROM = "http://www.w3.org/ns/prov#wasDerivedFrom"
OP_NAMESPACE = "http://ontology-platform.local/semantic/op/"
TAG_NAMESPACE = "tag:ontology-platform.internal,2026:"

# Each entry: (description, SPARQL UPDATE string).
# Every UPDATE uses ``GRAPH ?g`` to span all named graphs.
CLEANUP_OPERATIONS: list[tuple[str, str]] = [
    (
        "prov:wasDerivedFrom edges",
        f"DELETE WHERE {{ GRAPH ?g {{ ?s <{PROV_WAS_DERIVED_FROM}> ?o . }} }}",
    ),
    (
        "op:evidenceStatus literals",
        f"DELETE WHERE {{ GRAPH ?g {{ ?s <{OP_NAMESPACE}evidenceStatus> ?o . }} }}",
    ),
    (
        "chunk literal properties (sourceDocument, sequence, charStart, charEnd, text)",
        (
            f"DELETE WHERE {{ GRAPH ?g {{ ?chunk ?p ?o . "
            f"VALUES ?p {{ "
            f"<{TAG_NAMESPACE}sourceDocument> "
            f"<{TAG_NAMESPACE}sequence> "
            f"<{TAG_NAMESPACE}charStart> "
            f"<{TAG_NAMESPACE}charEnd> "
            f"<{TAG_NAMESPACE}text> "
            f"}} }} }}"
        ),
    ),
    (
        "op:FactClaim instances and their properties",
        (
            f"DELETE WHERE {{ GRAPH ?g {{ "
            f"?s a <{OP_NAMESPACE}FactClaim> . "
            f"?s ?p ?o . }} }}"
        ),
    ),
]


def iter_operations() -> Iterable[tuple[str, str]]:
    yield from CLEANUP_OPERATIONS


def run_print() -> int:
    """Print SPARQL UPDATEs for manual paste into a SPARQL endpoint."""
    print("# Legacy evidence RDF cleanup -- SPARQL UPDATE statements.")
    print("# Paste each into your Oxigraph /update endpoint (or SPARQL workbench).")
    print("# Back up the store first.\n")
    for description, sparql in iter_operations():
        print(f"# --- {description}")
        print(sparql)
        print()
    return 0


def run_dry_run() -> int:
    """Log the planned UPDATEs without executing them."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger.info("DRY-RUN: %d SPARQL UPDATE(s) would be executed",
                len(CLEANUP_OPERATIONS))
    for description, sparql in iter_operations():
        logger.info("Would run: %s", description)
        logger.debug("  SPARQL: %s", sparql)
    logger.info("Dry-run complete. Re-run without --dry-run to apply.")
    return 0


def run_apply() -> int:
    """Execute the UPDATEs via the app's RdfStoreRepository."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from app.api.deps import build_rdf_store
    from app.core.config import Settings

    settings = Settings()
    repo = build_rdf_store(settings)

    logger.info("Applying %d SPARQL UPDATE(s) to RDF store...",
                len(CLEANUP_OPERATIONS))
    for description, sparql in iter_operations():
        try:
            repo.update_sparql(sparql)
        except Exception as exc:
            logger.error("[FAIL] %s: %s", description, exc)
            return 1
        logger.info("[OK] Cleaned: %s", description)
    logger.info("Done.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="See module docstring for the full background and migration notes.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned UPDATEs without executing them",
    )
    mode.add_argument(
        "--print",
        action="store_true",
        help="Print SPARQL UPDATEs for manual paste into a SPARQL endpoint",
    )
    args = parser.parse_args()

    if args.print:
        return run_print()
    if args.dry_run:
        return run_dry_run()
    return run_apply()


if __name__ == "__main__":
    sys.exit(main())
