/**
 * Stage 4 §7.3 — McpToolsPage rewrite.
 *
 * Replaces the hard-coded tool list with a runtime enumeration fetched
 * from the new ``GET /api/mcp/tools`` endpoint. The endpoint introspects
 * the FastMCP tool registry and bucketizes tools by source filename
 * (``system`` / ``interview`` / ``semantic``); the page renders one panel
 * per category with one row per tool.
 */

import { Alert, Card, Skeleton, Tag, Typography } from "antd";
import { Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { useT } from "../i18n";

type McpToolRow = {
  name: string;
  description: string | null;
  input_schema_summary: {
    properties: string[];
    required: string[];
    title?: string | null;
  };
  source_file: string;
  category: "system" | "interview" | "semantic" | "uncategorized";
};

type McpToolsEnvelope = {
  tools: McpToolRow[];
  total: number;
  by_category: Record<string, number>;
};

type McpToolsPageProps = {
  request: <T,>(path: string, options?: RequestInit) => Promise<T>;
};

const CATEGORY_ORDER: McpToolRow["category"][] = [
  "system",
  "interview",
  "semantic",
  "uncategorized",
];

export function McpToolsPage({ request }: McpToolsPageProps) {
  const t = useT();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [envelope, setEnvelope] = useState<McpToolsEnvelope | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    request<McpToolsEnvelope>("/mcp/tools")
      .then((data) => {
        if (!cancelled) setEnvelope(data);
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [request]);

  return (
    <section className="mcpToolsPage stage4" aria-label="mcp-tools-page">
      <Panel
        title={t("MCP tools")}
        icon={<Wrench size={17} />}
        actions={
          envelope ? (
            <Typography.Text type="secondary" aria-label="mcp-tools-summary">
              {t("{total} tools across {categories} categories", {
                total: envelope.total,
                categories: Object.keys(envelope.by_category).length,
              })}
            </Typography.Text>
          ) : null
        }
      >
        {error ? (
          <Alert
            type="error"
            showIcon
            message={t("Failed to load MCP tools catalog")}
            description={error}
          />
        ) : loading ? (
          <Skeleton active />
        ) : envelope ? (
          <div className="mcpCatalog" aria-label="mcp-tools-catalog">
            {CATEGORY_ORDER.filter((cat) => envelope.by_category[cat] > 0).map(
              (category) => {
                const tools = envelope.tools.filter(
                  (tool) => tool.category === category,
                );
                return (
                  <Card
                    key={category}
                    size="small"
                    title={
                      <span aria-label={`mcp-tools-category-${category}`}>
                        {t(categoryLabel(category))} · {tools.length}
                      </span>
                    }
                    style={{ marginTop: 12 }}
                  >
                    <ul className="toolList">
                      {tools.map((tool) => (
                        <li
                          key={tool.name}
                          className="toolRow"
                          aria-label={`mcp-tool-${tool.name}`}
                        >
                          <div className="toolRowMain">
                            <strong>{tool.name}</strong>
                            {tool.description && (
                              <span className="toolDescription">
                                {tool.description}
                              </span>
                            )}
                            {tool.input_schema_summary.required.length > 0 && (
                              <span className="toolRequired">
                                {t("Required")}:{" "}
                                {tool.input_schema_summary.required.join(", ")}
                              </span>
                            )}
                            {tool.input_schema_summary.properties.length > 0 && (
                              <span className="toolProperties">
                                {t("Properties")}:{" "}
                                {tool.input_schema_summary.properties.join(", ")}
                              </span>
                            )}
                          </div>
                          <Tag aria-label={`mcp-tool-source-${tool.source_file}`}>
                            {tool.source_file}
                          </Tag>
                        </li>
                      ))}
                    </ul>
                  </Card>
                );
              },
            )}
          </div>
        ) : null}
      </Panel>
    </section>
  );
}

function Panel({
  title,
  icon,
  actions,
  children,
}: {
  title: string;
  icon: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card
      title={
        <div className="panelHeaderTitle" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {icon}
          <h2 style={{ margin: 0, fontSize: 16 }}>{title}</h2>
          {actions && <span style={{ marginLeft: "auto" }}>{actions}</span>}
        </div>
      }
      variant="borderless"
    >
      {children}
    </Card>
  );
}

function categoryLabel(category: McpToolRow["category"]): string {
  switch (category) {
    case "system":
      return "System tools";
    case "interview":
      return "Interview tools";
    case "semantic":
      return "Semantic tools";
    default:
      return "Uncategorized tools";
  }
}

export type { McpToolsPageProps };
