/**
 * Stage 4 §7.2 — AgentTestPage rewrite.
 *
 * The new ``AgentTestService.run_agent_test`` returns a structured
 * ``graph_context`` envelope (entries + generated_at + scope) instead of
 * an opaque JSON object. This page surfaces each entry with an
 * AssertionKind chip and a stale warning, alongside the answer, tool
 * calls timeline, prompt preview, warnings, and errors.
 *
 * Spec §7.2 ASCII mock layout.
 */

import { Alert, Button, Card, Input, Space, Tag, Typography } from "antd";
import { Clipboard, Play, Send } from "lucide-react";
import { useState } from "react";

import { useT } from "../i18n";
import type {
  AgentTestGraphContextEntry,
  AgentTestResponse,
  JsonObject,
  Ontology,
} from "../types";
import { prettyJson } from "../utils";

type AgentTestPageProps = {
  ontology: Ontology;
  graphSetId: string;
  request: <T,>(path: string, options?: RequestInit) => Promise<T>;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
};

export function AgentTestPage({ ontology, graphSetId, request, mutate }: AgentTestPageProps) {
  const t = useT();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AgentTestResponse | null>(null);

  function run(event: React.FormEvent) {
    event.preventDefault();
    mutate(async () => {
      const response = await request<AgentTestResponse>("/agent-test/run", {
        method: "POST",
        body: JSON.stringify({
          ontology_id: ontology.id,
          graph_set_id: graphSetId,
          question,
        }),
      });
      setResult(response);
    }, t("Agent test completed"));
  }

  return (
    <section className="agentLayout stage4" aria-label="agent-test-page">
      <Card title={t("Agent test")} size="small">
        <form className="stackForm" onSubmit={run}>
          <Input.TextArea
            className="questionBox"
            required
            placeholder={t("Ask a question against the active graph set")}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            autoSize={{ minRows: 3, maxRows: 8 }}
            aria-label="agent-test-question"
          />
          <Space>
            <Button
              type="primary"
              htmlType="submit"
              icon={<Play size={15} />}
              aria-label="agent-test-run"
            >
              {t("Run")}
            </Button>
            {result && (
              <Button
                icon={<Clipboard size={15} />}
                onClick={() =>
                  navigator.clipboard.writeText(prettyJson(result))
                }
              >
                {t("Copy result")}
              </Button>
            )}
          </Space>
        </form>
      </Card>

      {!result ? (
        <Card title={t("Run output")} size="small">
          <div className="emptyState" aria-label="agent-test-empty">
            <Send size={22} />
            <span>{t("No run output yet")}</span>
          </div>
        </Card>
      ) : (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          {result.errors.length > 0 && (
            <Alert
              type="error"
              showIcon
              message={t("Run produced errors")}
              description={
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {result.errors.map((err, idx) => (
                    <li key={`err-${idx}`}>{err}</li>
                  ))}
                </ul>
              }
            />
          )}
          {result.warnings.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message={t("Run produced warnings")}
              description={
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {result.warnings.map((warn, idx) => (
                    <li key={`warn-${idx}`}>{warn}</li>
                  ))}
                </ul>
              }
            />
          )}

          <Card title={t("Answer")} size="small">
            <pre className="agentAnswer" aria-label="agent-test-answer">
              {result.answer || t("(empty answer)")}
            </pre>
          </Card>

          <Card
            title={t("Graph context · {n} entries", {
              n: result.graph_context.entries.length,
            })}
            size="small"
          >
            <dl className="agentContextMeta">
              <div>
                <dt>{t("Generated at")}</dt>
                <dd>{result.graph_context.generated_at}</dd>
              </div>
              <div>
                <dt>{t("Scope")}</dt>
                <dd>
                  <code>
                    {result.graph_context.scope.graph_set_id} /{" "}
                    {result.graph_context.scope.ontology_id}
                  </code>
                </dd>
              </div>
            </dl>
            {result.graph_context.entries.length === 0 ? (
              <Typography.Text type="secondary">
                {t("No graph context matched the question.")}
              </Typography.Text>
            ) : (
              <ul className="agentContextList" aria-label="agent-test-graph-context">
                {result.graph_context.entries.map((entry) => (
                  <GraphContextEntryRow key={entry.iri} entry={entry} />
                ))}
              </ul>
            )}
          </Card>

          <Card title={t("Tool calls")} size="small">
            <Timeline items={result.tool_calls} />
          </Card>

          <Card title={t("Prompt preview")} size="small">
            <pre className="jsonBlock" aria-label="agent-test-prompt">
              {result.prompt_preview}
            </pre>
          </Card>
        </Space>
      )}
    </section>
  );
}

function GraphContextEntryRow({ entry }: { entry: AgentTestGraphContextEntry }) {
  const t = useT();
  const color =
    entry.assertion_kind === "asserted"
      ? "green"
      : entry.assertion_kind === "owl_inferred"
        ? "geekblue"
        : "purple";
  const label =
    entry.assertion_kind === "asserted"
      ? t("Asserted")
      : entry.assertion_kind === "owl_inferred"
        ? t("OWL inferred")
        : t("Rule derived");
  return (
    <li className="agentContextRow" aria-label={`agent-test-context-${entry.iri}`}>
      <div className="agentContextRowMain">
        <strong>{entry.label ?? entry.iri}</strong>
        {entry.class_label && <Tag color="blue">{entry.class_label}</Tag>}
        {entry.is_stale && <Tag color="warning">⚠ {t("stale")}</Tag>}
        <Tag color={color}>{label}</Tag>
      </div>
      <code className="agentContextRowSource">{entry.source_graph_iri}</code>
    </li>
  );
}

function Timeline({ items }: { items: JsonObject[] }) {
  const t = useT();
  if (!items.length) {
    return <Typography.Text type="secondary">{t("No tool calls")}</Typography.Text>;
  }
  return (
    <div className="timeline">
      {items.map((item, index) => (
        <div
          className="timelineItem"
          key={`call-${index}-${JSON.stringify(item).slice(0, 24)}`}
        >
          <span>{index + 1}</span>
          <pre>{prettyJson(item)}</pre>
        </div>
      ))}
    </div>
  );
}

export type { AgentTestPageProps };
