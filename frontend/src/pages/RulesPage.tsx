import { Alert, Button, Card, Input, Modal, Select, Skeleton, Tag } from "antd";
import { Edit3, Plus, RefreshCw, Trash2, Workflow } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useT } from "../i18n";
import {
  createRuleDefinition,
  deleteRuleDefinition,
  listRuleDefinitions,
  updateRuleDefinition,
} from "../semanticApi";
import type { SemanticJsonObject, SemanticRuleDefinitionRead } from "../types";
import { prettyJson } from "../utils";
import type { WorkbenchRequest } from "./workbenchTypes";

type RulesPageProps = {
  readOnly: boolean;
  request: WorkbenchRequest;
};

type RuleFormState = {
  ruleIri: string;
  name: string;
  language: "platform_dsl" | "sparql_construct" | "workflow_state_machine";
  bodyText: string;
  inputRolesText: string;
  status: "draft" | "active" | "retired" | "rejected";
  priority: string;
};

const DEFAULT_DSL_BODY = {
  when: [{ s: "?s", p: "<http://example.test/predicate>", o: "?o" }],
  then: [{ s: "?s", p: "<http://example.test/derived>", o: "?o" }],
};

const EMPTY_FORM: RuleFormState = {
  ruleIri: "",
  name: "",
  language: "platform_dsl",
  bodyText: JSON.stringify(DEFAULT_DSL_BODY, null, 2),
  inputRolesText: "asserted_data",
  status: "draft",
  priority: "0",
};

export function RulesPage({ readOnly, request }: RulesPageProps) {
  const t = useT();
  const [rules, setRules] = useState<SemanticRuleDefinitionRead[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<RuleFormState>(EMPTY_FORM);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await listRuleDefinitions(request, { limit: 500 });
      setRules(result.rules);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedId && rules.length) {
      setSelectedId(rules[0]!.id);
      return;
    }
    if (selectedId && !rules.some((rule) => rule.id === selectedId)) {
      setSelectedId(rules[0]?.id ?? null);
    }
  }, [rules, selectedId]);

  const selectedRule = useMemo(
    () => rules.find((rule) => rule.id === selectedId) ?? null,
    [rules, selectedId],
  );

  function openCreate() {
    setForm({
      ...EMPTY_FORM,
      ruleIri: `http://ontology-platform.local/semantic/rule/${Date.now()}`,
    });
    setCreating(true);
  }

  function openEdit(rule: SemanticRuleDefinitionRead) {
    setForm({
      ruleIri: rule.rule_iri,
      name: rule.name,
      language: rule.language as RuleFormState["language"],
      bodyText: JSON.stringify(rule.body, null, 2),
      inputRolesText: rule.input_roles.join(", "),
      status: rule.status as RuleFormState["status"],
      priority: String(rule.priority),
    });
    setEditing(true);
  }

  async function submitCreate() {
    const parsed = parseCreateForm(form);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const created = await createRuleDefinition(request, parsed.payload);
      setCreating(false);
      setSelectedId(created.id);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }

  async function submitEdit() {
    if (!selectedRule) return;
    const priority = Number.parseInt(form.priority, 10);
    if (!form.name.trim()) {
      setError(t("Rule name is required"));
      return;
    }
    if (Number.isNaN(priority)) {
      setError(t("Priority must be a number"));
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const updated = await updateRuleDefinition(request, selectedRule.id, {
        name: form.name.trim(),
        status: form.status,
        priority,
      });
      setEditing(false);
      setSelectedId(updated.id);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }

  async function removeRule(rule: SemanticRuleDefinitionRead) {
    if (!window.confirm(t("Delete this rule definition?"))) return;
    setSubmitting(true);
    setError("");
    try {
      await deleteRuleDefinition(request, rule.id);
      if (selectedId === rule.id) setSelectedId(null);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="rulesPage" aria-label="rules-page">
      <header className="pageSubHeader">
        <div>
          <span className="eyebrow">{t("Modeling")}</span>
          <h2>{t("Rules")}</h2>
          <p>{t("View and maintain lightweight semantic rule definitions.")}</p>
        </div>
        <div className="headerActions">
          <Button icon={<RefreshCw size={15} />} onClick={() => void load()} disabled={loading}>
            {t("Refresh")}
          </Button>
          <Button type="primary" icon={<Plus size={15} />} onClick={openCreate} disabled={readOnly}>
            {t("New rule")}
          </Button>
        </div>
      </header>

      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}

      <div className="rulesPageGrid">
        <Card
          title={
            <div className="reportPanelHeader">
              <Workflow size={15} />
              <span>{t("Rule definitions")}</span>
              <Tag>{rules.length}</Tag>
            </div>
          }
        >
          {loading ? (
            <Skeleton active paragraph={{ rows: 8 }} />
          ) : rules.length === 0 ? (
            <div className="emptyState">{t("No rules yet")}</div>
          ) : (
            <table className="namedGraphTable" aria-label="rule-definition-table">
              <thead>
                <tr>
                  <th>{t("Name")}</th>
                  <th>{t("Language")}</th>
                  <th>{t("Status")}</th>
                  <th>{t("Priority")}</th>
                  <th>{t("Actions")}</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => (
                  <tr key={rule.id} className={rule.id === selectedId ? "selectedTableRow" : undefined}>
                    <td>
                      <button className="ghostButton" type="button" onClick={() => setSelectedId(rule.id)}>
                        {rule.name}
                      </button>
                      <div className="mutedCode">{rule.rule_iri}</div>
                    </td>
                    <td><code>{rule.language}</code></td>
                    <td><RuleStatusTag status={rule.status} /></td>
                    <td>{rule.priority}</td>
                    <td>
                      <div className="tableActions">
                        <Button size="small" icon={<Edit3 size={13} />} onClick={() => openEdit(rule)} disabled={readOnly}>
                          {t("Edit")}
                        </Button>
                        <Button size="small" danger icon={<Trash2 size={13} />} onClick={() => void removeRule(rule)} disabled={readOnly || submitting}>
                          {t("Delete")}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title={t("Rule detail")}>
          {!selectedRule ? (
            <div className="emptyState">{t("Select a rule to view details")}</div>
          ) : (
            <dl className="semanticGraphDetailList ruleDetailList">
              <div><dt>{t("ID")}</dt><dd><code>{selectedRule.id}</code></dd></div>
              <div><dt>{t("IRI")}</dt><dd><code>{selectedRule.rule_iri}</code></dd></div>
              <div><dt>{t("Version")}</dt><dd><code>{selectedRule.version}</code></dd></div>
              <div><dt>{t("Input roles")}</dt><dd>{selectedRule.input_roles.join(", ")}</dd></div>
              <div><dt>{t("Output kind")}</dt><dd>{selectedRule.output_kind}</dd></div>
              <div><dt>{t("Uses inferred facts")}</dt><dd>{selectedRule.uses_inferred_facts ? t("Yes") : t("No")}</dd></div>
              <div><dt>{t("Requires review")}</dt><dd>{selectedRule.requires_review ? t("Yes") : t("No")}</dd></div>
              <div><dt>{t("Body")}</dt><dd><pre className="jsonBlock">{prettyJson(selectedRule.body)}</pre></dd></div>
            </dl>
          )}
        </Card>
      </div>

      <RuleModal
        mode="create"
        open={creating}
        form={form}
        busy={submitting}
        onChange={setForm}
        onCancel={() => setCreating(false)}
        onSubmit={() => void submitCreate()}
      />
      <RuleModal
        mode="edit"
        open={editing}
        form={form}
        busy={submitting}
        onChange={setForm}
        onCancel={() => setEditing(false)}
        onSubmit={() => void submitEdit()}
      />
    </section>
  );
}

function RuleStatusTag({ status }: { status: string }) {
  const color = status === "active" ? "green" : status === "rejected" ? "red" : status === "retired" ? "orange" : "default";
  return <Tag color={color}>{status}</Tag>;
}

function RuleModal({
  mode,
  open,
  form,
  busy,
  onChange,
  onCancel,
  onSubmit,
}: {
  mode: "create" | "edit";
  open: boolean;
  form: RuleFormState;
  busy: boolean;
  onChange: (form: RuleFormState) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  const t = useT();
  const createMode = mode === "create";
  return (
    <Modal
      title={createMode ? t("Create rule") : t("Edit rule")}
      open={open}
      onCancel={onCancel}
      onOk={onSubmit}
      confirmLoading={busy}
      okText={createMode ? t("Create rule") : t("Save")}
      width={760}
      okButtonProps={{ disabled: !form.name.trim() || (createMode && !form.ruleIri.trim()) }}
    >
      <div className="ruleModalForm">
        <label>
          <span>{t("Name")}</span>
          <Input value={form.name} onChange={(event) => onChange({ ...form, name: event.target.value })} />
        </label>
        <label>
          <span>{t("Rule IRI")}</span>
          <Input
            value={form.ruleIri}
            disabled={!createMode}
            onChange={(event) => onChange({ ...form, ruleIri: event.target.value })}
          />
        </label>
        <div className="ruleModalRow">
          <label>
            <span>{t("Language")}</span>
            <Select
              value={form.language}
              disabled={!createMode}
              onChange={(value) => onChange({ ...form, language: value })}
              options={[
                { value: "platform_dsl", label: "platform_dsl" },
                { value: "sparql_construct", label: "sparql_construct" },
                { value: "workflow_state_machine", label: "workflow_state_machine" },
              ]}
            />
          </label>
          <label>
            <span>{t("Status")}</span>
            <Select
              value={form.status}
              onChange={(value) => onChange({ ...form, status: value })}
              options={[
                { value: "draft", label: "draft" },
                { value: "active", label: "active" },
                { value: "retired", label: "retired" },
                { value: "rejected", label: "rejected" },
              ]}
            />
          </label>
          <label>
            <span>{t("Priority")}</span>
            <Input value={form.priority} onChange={(event) => onChange({ ...form, priority: event.target.value })} />
          </label>
        </div>
        <label>
          <span>{t("Input roles")}</span>
          <Input
            value={form.inputRolesText}
            disabled={!createMode}
            onChange={(event) => onChange({ ...form, inputRolesText: event.target.value })}
          />
        </label>
        <label>
          <span>{t("Body JSON")}</span>
          <Input.TextArea
            value={form.bodyText}
            disabled={!createMode}
            onChange={(event) => onChange({ ...form, bodyText: event.target.value })}
            rows={10}
          />
        </label>
        {!createMode && (
          <Alert
            type="info"
            showIcon
            message={t("Rule body and language are versioned. Create a new rule version to change executable logic.")}
          />
        )}
      </div>
    </Modal>
  );
}

function parseCreateForm(form: RuleFormState):
  | {
      payload: Parameters<typeof createRuleDefinition>[1];
    }
  | { error: string } {
  if (!form.name.trim()) return { error: "Rule name is required" };
  if (!form.ruleIri.trim()) return { error: "Rule IRI is required" };
  const priority = Number.parseInt(form.priority, 10);
  if (Number.isNaN(priority)) return { error: "Priority must be a number" };
  let body: SemanticJsonObject;
  try {
    const parsed = JSON.parse(form.bodyText) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { error: "Body JSON must be an object" };
    }
    body = parsed as SemanticJsonObject;
  } catch {
    return { error: "Body JSON is invalid" };
  }
  const inputRoles = form.inputRolesText
    .split(",")
    .map((role) => role.trim())
    .filter(Boolean);
  if (!inputRoles.length) return { error: "At least one input role is required" };
  return {
    payload: {
      ruleIri: form.ruleIri.trim(),
      name: form.name.trim(),
      language: form.language,
      body,
      inputRoles,
      status: form.status,
      priority,
    },
  };
}

export type { RulesPageProps };
