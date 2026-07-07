/**
 * Stage 4 §7.1 — EntitiesSearchPage.
 *
 * Searches entities across the active graph set through the new
 * ``entity-search`` read model. Rows are decorated with
 * ``assertion_kind`` / ``source_graph_iri`` / ``is_stale`` / ``graph_set_id``
 * so the user can see projection state alongside the label.
 *
 * The page itself performs no writes. Clicking a row navigates to the
 * existing ``EntitiesPage`` workspace tab with the entity preselected.
 */

import { Alert, Button, Card, Input, Select, Skeleton, Tag } from "antd";
import { Database, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useT } from "../i18n";
import { readModel, type SemanticRequester } from "../semanticApi";
import type { WorkbenchNavigate } from "./workbenchTypes";

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

type EntitiesSearchPageProps = {
  graphSetId: string;
  ontologyId: string;
  readOnly: boolean;
  request: SemanticRequester;
  navigate?: WorkbenchNavigate;
};

const DEBOUNCE_MS = 200;

export function EntitiesSearchPage({
  graphSetId,
  ontologyId,
  readOnly,
  request,
  navigate,
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
    setLoading(true);
    setError("");
    try {
      const envelope = await readModel<EntitySearchEnvelope>(
        request,
        graphSetId,
        "entity-search",
        {
          q: debouncedQuery || undefined,
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
        <Button icon={<RefreshCw size={15} />} onClick={() => void load()} disabled={loading}>
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
            {filteredItems.map((row) => (
              <li key={row.iri} className="entitySearchRow">
                <button
                  type="button"
                  className="entitySearchMain"
                  onClick={() => navigate?.("entities", { graphSet: graphSetId })}
                  aria-label={`entity-search-row-${row.iri}`}
                >
                  <strong>{row.label ?? row.iri}</strong>
                  {row.class_label && <Tag color="blue">{row.class_label}</Tag>}
                  {row.comment && <span className="entitySearchComment">{row.comment}</span>}
                  <code className="entitySearchIri">{row.iri}</code>
                </button>
                <div className="entitySearchMeta">
                  <AssertionKindTag kind={row.assertion_kind} />
                  {row.is_stale && <Tag color="warning">⚠ {t("stale")}</Tag>}
                  <code className="entitySearchSource">{row.source_graph_iri}</code>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {readOnly && (
        <Alert type="info" showIcon message={t("Data graph is locked. Search is read-only.")} />
      )}
    </section>
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

export type { EntitiesSearchPageProps };
