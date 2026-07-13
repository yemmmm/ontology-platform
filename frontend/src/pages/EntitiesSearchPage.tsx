/**
 * Stage 4 §7.1 — EntitiesSearchPage.
 *
 * Searches entities across the active graph set through the new
 * ``entity-search`` read model. Rows are decorated with
 * ``assertion_kind`` / ``source_graph_iri`` / ``is_stale`` / ``graph_set_id``
 * so the user can see projection state alongside the label.
 *
 * The page itself performs no writes. Clicking a row expands an inline
 * details panel (IRI, class, comment, provenance, literal facts) instead
 * of navigating away, so recall review stays in context.
 */

import { Alert, Button, Card, Input, Select, Skeleton, Tag } from "antd";
import { ChevronDown, ChevronRight, Database, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useT } from "../i18n";
import { readModel, type SemanticRequester } from "../semanticApi";

type AssertionKindFilter = "all" | "asserted" | "owl_inferred" | "rule_derived";

type EntitySearchRow = {
  iri: string;
  label: string | null;
  comment: string | null;
  class_iri: string | null;
  class_label: string | null;
  assertion_kind: "asserted" | "owl_inferred" | "rule_derived";
  source_graph_iri: string;
  source_signature: string | null;
  evidence_status: string | null;
  is_stale: boolean;
  graph_set_id: string;
};

type EntitySearchEnvelope = {
  graph_set_id: string;
  model_name: string;
  projection_version: string;
  items: EntitySearchRow[];
};

type EntityLiteralFactRow = {
  id: string;
  subject_iri: string;
  predicate_iri: string;
  predicate_label: string | null;
  object_value: unknown;
  object_label?: string | null;
  assertion_kind: string;
  stale?: boolean;
};

type EntityLiteralFactsEnvelope = {
  graph_set_id: string;
  warnings?: Array<{ code: string; message?: string }>;
  items: EntityLiteralFactRow[];
};

type EntitiesSearchPageProps = {
  graphSetId: string;
  ontologyId: string;
  readOnly: boolean;
  request: SemanticRequester;
};

const DEBOUNCE_MS = 200;

export function EntitiesSearchPage({
  graphSetId,
  ontologyId,
  readOnly,
  request,
}: EntitiesSearchPageProps) {
  // ontologyId is part of the Stage 4 §7.1 prop contract; it is reserved
  // for the future "open entity in editor" deep link. The current MVP only
  // surfaces the read-model results, so the value is intentionally unused
  // at runtime but kept on the prop signature for symmetry with sibling
  // pages (ClassesPage / EntitiesPage) that already accept it.
  void ontologyId;

  const t = useT();
  const [rawInput, setRawInput] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [classIri, setClassIri] = useState<string>("");
  const [scope, setScope] = useState<AssertionKindFilter>("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<EntitySearchEnvelope | null>(null);
  const [expandedIri, setExpandedIri] = useState<string | null>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      setDebouncedQuery(rawInput.trim());
    }, DEBOUNCE_MS);
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, [rawInput]);

  const load = useCallback(async () => {
    // No input → no recall. The page stays in the "type to search" empty
    // state until the user actually enters a query; we never fire the
    // unfiltered listing call that previously returned the whole graph.
    if (!debouncedQuery) {
      setResult(null);
      setError("");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const envelope = await readModel<EntitySearchEnvelope>(
        request,
        graphSetId,
        "entity-search",
        {
          q: debouncedQuery,
          classIri: classIri || undefined,
          include: "asserted",
          fieldSet: "summary",
          limit: 50,
        },
      );
      setResult(envelope);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery, classIri, graphSetId, request]);

  useEffect(() => {
    void load();
  }, [load]);

  // Collapsing the expanded row when the query changes keeps the detail
  // panel from pointing at a row that is no longer in the result set.
  useEffect(() => {
    setExpandedIri(null);
  }, [debouncedQuery, classIri, scope]);

  const filteredItems = useMemo(() => {
    const items = result?.items ?? [];
    if (scope === "all") return items;
    return items.filter((row) => row.assertion_kind === scope);
  }, [result, scope]);

  const distinctClasses = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of result?.items ?? []) {
      if (row.class_iri && !map.has(row.class_iri)) {
        map.set(row.class_iri, row.class_label ?? row.class_iri);
      }
    }
    return Array.from(map.entries()).map(([value, label]) => ({ value, label }));
  }, [result]);

  return (
    <section className="entitiesSearchPage stage4" aria-label="entities-search-page">
      <header className="topBar">
        <div>
          <span className="eyebrow">{t("Stage 4 · graph-derived")}</span>
          <h1>{t("Search entities")}</h1>
          <div className="crumbTrail">
            <span>{t("Graph set")}: <code>{graphSetId}</code></span>
          </div>
        </div>
        <Button
          icon={<RefreshCw size={15} />}
          onClick={() => void load()}
          disabled={loading || !debouncedQuery}
        >
          {t("Refresh")}
        </Button>
      </header>

      {error && (
        <Alert
          type="error"
          showIcon
          message={error}
          closable
          action={
            <Button size="small" onClick={() => void load()}>
              {t("Retry")}
            </Button>
          }
          onClose={() => setError("")}
        />
      )}

      <Card size="small" title={t("Search")}>
        <div className="entitiesSearchControls">
          <Input
            allowClear
            prefix={<Search size={14} />}
            placeholder={t("Search entities across the active graph set")}
            value={rawInput}
            onChange={(event) => setRawInput(event.target.value)}
            aria-label="entities-search-input"
          />
          <Select
            allowClear
            placeholder={t("All classes")}
            value={classIri || undefined}
            onChange={(value) => setClassIri(value ?? "")}
            options={distinctClasses}
            style={{ minWidth: 220 }}
            aria-label="entities-search-class"
          />
          <Select
            value={scope}
            onChange={(value) => setScope(value as AssertionKindFilter)}
            options={[
              { value: "all", label: t("All scopes") },
              { value: "asserted", label: t("Asserted") },
              { value: "owl_inferred", label: t("OWL inferred") },
              { value: "rule_derived", label: t("Rule derived") },
            ]}
            style={{ minWidth: 160 }}
            aria-label="entities-search-scope"
          />
        </div>
      </Card>

      <Card
        size="small"
        title={t("{count} results · sorted by label", { count: filteredItems.length })}
      >
        {loading ? (
          <Skeleton active />
        ) : filteredItems.length === 0 ? (
          <div className="emptyState" aria-label="entities-search-empty">
            <Database size={22} />
            <span>
              {debouncedQuery
                ? t("No entities matched. Try a broader query.")
                : t("Type to search across the active graph set.")}
            </span>
          </div>
        ) : (
          <ul className="entitySearchList" aria-label="entities-search-results">
            {filteredItems.map((row) => {
              const expanded = expandedIri === row.iri;
              return (
                <li key={row.iri} className="entitySearchRow">
                  <button
                    type="button"
                    className="entitySearchMain"
                    onClick={() => setExpandedIri(expanded ? null : row.iri)}
                    aria-label={`entity-search-row-${row.iri}`}
                    aria-expanded={expanded}
                  >
                    <span className="entitySearchChevron">
                      {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </span>
                    <strong>{row.label ?? compactIri(row.iri)}</strong>
                    {row.class_label && <Tag color="blue">{row.class_label}</Tag>}
                    <AssertionKindTag kind={row.assertion_kind} />
                  </button>
                  {expanded && (
                    <EntityDetailPanel
                      row={row}
                      graphSetId={graphSetId}
                      request={request}
                    />
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {readOnly && (
        <Alert type="info" showIcon message={t("Data graph is locked. Search is read-only.")} />
      )}
    </section>
  );
}

function EntityDetailPanel({
  row,
  graphSetId,
  request,
}: {
  row: EntitySearchRow;
  graphSetId: string;
  request: SemanticRequester;
}) {
  const t = useT();
  const [facts, setFacts] = useState<EntityLiteralFactRow[]>([]);
  const [factsLoading, setFactsLoading] = useState(false);
  const [factsError, setFactsError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setFactsLoading(true);
    setFactsError("");
    void readModel<EntityLiteralFactsEnvelope>(request, graphSetId, "entity-literal-facts", {
      include: "asserted",
      entity: row.iri,
      limit: 50,
    })
      .then((envelope) => {
        if (!cancelled) setFacts(envelope.items ?? []);
      })
      .catch((cause) => {
        if (!cancelled) {
          setFacts([]);
          setFactsError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .finally(() => {
        if (!cancelled) setFactsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [request, graphSetId, row.iri]);

  return (
    <div className="entitySearchDetail" aria-label={`entity-search-detail-${row.iri}`}>
      <dl className="entitySearchDetailGrid">
        <div>
          <dt>{t("Label")}</dt>
          <dd>{row.label ?? compactIri(row.iri)}</dd>
        </div>
        <div>
          <dt>{t("IRI")}</dt>
          <dd><code>{row.iri}</code></dd>
        </div>
        <div>
          <dt>{t("Class")}</dt>
          <dd>
            {row.class_label ?? (row.class_iri ? compactIri(row.class_iri) : "—")}
            {row.class_iri && <code className="entitySearchDetailIri">{row.class_iri}</code>}
          </dd>
        </div>
        <div>
          <dt>{t("Assertion")}</dt>
          <dd>
            <AssertionKindTag kind={row.assertion_kind} />
            {row.is_stale && <Tag color="warning">⚠ {t("stale")}</Tag>}
          </dd>
        </div>
        <div>
          <dt>{t("Evidence status")}</dt>
          <dd>{row.evidence_status ?? "—"}</dd>
        </div>
        <div>
          <dt>{t("Source graph")}</dt>
          <dd><code>{row.source_graph_iri}</code></dd>
        </div>
        <div>
          <dt>{t("Source signature")}</dt>
          <dd><code>{row.source_signature ?? "—"}</code></dd>
        </div>
        <div>
          <dt>{t("Graph set")}</dt>
          <dd><code>{row.graph_set_id}</code></dd>
        </div>
        {row.comment && (
          <div className="entitySearchDetailFull">
            <dt>{t("Description")}</dt>
            <dd>{row.comment}</dd>
          </div>
        )}
      </dl>

      <section className="entitySearchDetailFacts" aria-label={`entity-search-detail-facts-${row.iri}`}>
        <header>
          <strong>{t("Literal facts")}</strong>
        </header>
        {factsLoading ? (
          <Skeleton active paragraph={{ rows: 3 }} title={false} />
        ) : factsError ? (
          <Alert type="warning" showIcon message={factsError} />
        ) : facts.length === 0 ? (
          <p className="entitySearchDetailFactsEmpty">
            {t("No literal facts for this entity in the current layer.")}
          </p>
        ) : (
          <div className="entityLiteralFactList">
            {facts.map((fact) => (
              <article key={fact.id} className="entityLiteralFact">
                <div>
                  <span>{fact.predicate_label ?? compactIri(fact.predicate_iri)}</span>
                  <Tag>{assertionKindLabel(fact.assertion_kind, t)}{fact.stale ? ` · ${t("stale")}` : ""}</Tag>
                </div>
                <p>{literalFactValue(fact)}</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function AssertionKindTag({
  kind,
}: {
  kind: "asserted" | "owl_inferred" | "rule_derived";
}) {
  const t = useT();
  const color = kind === "asserted" ? "green" : kind === "owl_inferred" ? "geekblue" : "purple";
  const label =
    kind === "asserted"
      ? t("Asserted")
      : kind === "owl_inferred"
        ? t("OWL inferred")
        : t("Rule derived");
  return (
    <Tag color={color} aria-label={`entity-search-assertion-${kind}`}>
      {label}
    </Tag>
  );
}

function compactIri(value: string) {
  const hash = value.lastIndexOf("#");
  const slash = value.lastIndexOf("/");
  const idx = Math.max(hash, slash);
  return idx >= 0 ? value.slice(idx + 1) : value;
}

function assertionKindLabel(kind: string, t: ReturnType<typeof useT>) {
  const normalized = (kind || "asserted").toLowerCase().replace(/[-\s]/g, "_");
  if (normalized === "asserted") return t("Asserted");
  if (normalized === "owl_inferred" || normalized === "inferred") return t("OWL inferred");
  if (normalized === "rule_derived") return t("Rule derived");
  return t("Asserted");
}

function literalFactValue(fact: EntityLiteralFactRow) {
  if (fact.object_label != null && fact.object_label !== "") return String(fact.object_label);
  if (fact.object_value == null) return "";
  if (typeof fact.object_value === "string") return fact.object_value;
  return JSON.stringify(fact.object_value);
}

export type { EntitiesSearchPageProps };
