import { useState } from "react";
import { Braces, ChevronDown, ChevronRight, Plus, Minus } from "lucide-react";
import { useT } from "../../i18n";
import { GraphIriLabel } from "./badges";

export type GraphDelta = {
  added_quads?: Array<{ graph?: string; subject?: string; predicate?: string; object?: string } | string>;
  removed_quads?: Array<{ graph?: string; subject?: string; predicate?: string; object?: string } | string>;
  affected_graph_iris?: string[];
  added_statements?: Array<Record<string, unknown>>;
  removed_statements?: Array<Record<string, unknown>>;
  added?: Array<Record<string, unknown>>;
  removed?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

export function GraphDeltaViewer({ delta, defaultExpanded = false }: { delta: GraphDelta; defaultExpanded?: boolean }) {
  const t = useT();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [raw, setRaw] = useState(false);
  const added = collectStatements(delta, "added");
  const removed = collectStatements(delta, "removed");
  const affected = delta.affected_graph_iris ?? [];

  if (!added.length && !removed.length && !affected.length) {
    return (
      <div className="graphDeltaEmpty" aria-label="empty-graph-delta">
        {t("No graph changes")}
      </div>
    );
  }

  return (
    <section className="graphDeltaViewer" aria-label="graph-delta-viewer">
      <header className="graphDeltaHeader">
        <button className="ghostButton" onClick={() => setExpanded((v) => !v)} type="button">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <Braces size={14} />
        <span>
          {t("Added {added} · Removed {removed}", { added: added.length, removed: removed.length })}
        </span>
        <button
          aria-pressed={raw}
          className={raw ? "toggleButton active" : "toggleButton"}
          onClick={() => setRaw((v) => !v)}
          type="button"
        >
          {raw ? t("Compact view") : t("Raw view")}
        </button>
      </header>
      {expanded && (
        <div className="graphDeltaBody">
          {affected.length > 0 && (
            <div className="deltaAffectedGraphs" aria-label="affected-graphs">
              <strong>{t("Affected graphs")}</strong>
              <ul>
                {affected.map((graphIri) => (
                  <li key={graphIri}>
                    <GraphIriLabel iri={graphIri} />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {raw ? (
            <pre className="jsonBlock deltaRaw">{JSON.stringify(delta, null, 2)}</pre>
          ) : (
            <div className="deltaStatementList">
              {added.length > 0 && (
                <DeltaGroup icon={<Plus size={12} />} label={t("Added")} items={added} tone="added" />
              )}
              {removed.length > 0 && (
                <DeltaGroup icon={<Minus size={12} />} label={t("Removed")} items={removed} tone="removed" />
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function DeltaGroup({
  icon,
  label,
  items,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  items: Array<Record<string, unknown> | string>;
  tone: "added" | "removed";
}) {
  return (
    <div className={`deltaGroup ${tone}`} aria-label={`delta-group-${tone}`}>
      <header>
        {icon}
        <strong>{label}</strong>
        <span>{items.length}</span>
      </header>
      <ul>
        {items.map((item, idx) => {
          const text = typeof item === "string" ? item : describeStatement(item);
          return <li key={idx} className={tone}><code>{text}</code></li>;
        })}
      </ul>
    </div>
  );
}

function describeStatement(item: Record<string, unknown>): string {
  const subject = item.subject ?? item.s ?? "";
  const predicate = item.predicate ?? item.p ?? "";
  const object = item.object ?? item.o ?? "";
  const graph = item.graph ?? item.g;
  const compact = [subject, predicate, object]
    .map((value) => (typeof value === "string" ? shortenForDisplay(value) : JSON.stringify(value)))
    .join(" ");
  return graph ? `${compact}    [${shortenForDisplay(String(graph))}]` : compact;
}

function shortenForDisplay(value: string): string {
  if (!value) return "";
  if (value.length <= 80) return value;
  const hash = value.lastIndexOf("#");
  const slash = value.lastIndexOf("/");
  const cut = Math.max(hash, slash);
  if (cut >= 0 && value.length - cut - 1 <= 60) {
    return `…${value.slice(cut)}`;
  }
  return `${value.slice(0, 78)}…`;
}

function collectStatements(delta: GraphDelta, side: "added" | "removed"): Array<Record<string, unknown> | string> {
  const out: Array<Record<string, unknown> | string> = [];
  if (side === "added") {
    pushAll(out, delta.added_quads);
    pushAll(out, delta.added_statements);
    pushAll(out, delta.added);
  } else {
    pushAll(out, delta.removed_quads);
    pushAll(out, delta.removed_statements);
    pushAll(out, delta.removed);
  }
  return out;
}

function pushAll(
  out: Array<Record<string, unknown> | string>,
  source: Array<{ graph?: string; subject?: string; predicate?: string; object?: string } | string> | undefined,
) {
  if (!source) return;
  for (const item of source) {
    if (typeof item === "string") {
      out.push(item);
    } else {
      out.push(item as Record<string, unknown>);
    }
  }
}
