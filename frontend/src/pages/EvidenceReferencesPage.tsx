import { Alert, Button, Card, Input, Skeleton, Tag, Tooltip } from "antd";
import {
  BookMarked,
  Check,
  Copy,
  FileText,
  Link2,
  Plus,
  Quote,
  RefreshCw,
  Search,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useT } from "../i18n";
import { compactId, formatDate } from "../utils";
import type { WorkbenchRequest } from "./workbenchTypes";

type EvidenceReference = {
  id: string;
  project_id: string;
  document_name: string;
  excerpt: string;
  excerpt_hash: string;
  created_by: string | null;
  created_at: string;
  association_count: number;
};

type EvidenceAssociation = {
  id: string;
  ontology_id: string;
  graph_set_id: string | null;
  target_type: string;
  target_id: string;
  client_item_id: string | null;
  edit_audit_id: string | null;
  created_at: string;
};

type EvidenceReferencesPageProps = {
  projectId: string;
  ontologyId: string;
  readOnly: boolean;
  request: WorkbenchRequest;
};

export function EvidenceReferencesPage({
  projectId,
  ontologyId,
  readOnly,
  request,
}: EvidenceReferencesPageProps) {
  const t = useT();
  const [items, setItems] = useState<EvidenceReference[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [associations, setAssociations] = useState<EvidenceAssociation[]>([]);
  const [search, setSearch] = useState("");
  const [documentName, setDocumentName] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [createdMessage, setCreatedMessage] = useState("");
  const [copied, setCopied] = useState(false);

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) ?? null,
    [items, selectedId],
  );
  const currentOntologyAssociations = useMemo(
    () => associations.filter((item) => item.ontology_id === ontologyId),
    [associations, ontologyId],
  );

  const load = useCallback(async (query: string) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (query.trim()) params.set("search", query.trim());
      const result = await request<{ items: EvidenceReference[]; total: number }>(
        `/projects/${projectId}/evidence-references?${params.toString()}`,
      );
      setItems(result.items);
      setSelectedId((current) =>
        result.items.some((item) => item.id === current) ? current : result.items[0]?.id ?? null,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [projectId, request]);

  useEffect(() => {
    void load("");
  }, [load]);

  useEffect(() => {
    if (!selectedId) {
      setAssociations([]);
      return;
    }
    request<{ items: EvidenceAssociation[] }>(
      `/evidence-references/${selectedId}/associations`,
    )
      .then((result) => setAssociations(result.items))
      .catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
  }, [request, selectedId]);

  async function createReference() {
    if (!documentName.trim() || !excerpt.trim()) return;
    setSaving(true);
    setError("");
    setCreatedMessage("");
    try {
      const result = await request<EvidenceReference & { created: boolean }>(
        `/projects/${projectId}/evidence-references`,
        {
          method: "POST",
          body: JSON.stringify({ document_name: documentName, excerpt }),
        },
      );
      setDocumentName("");
      setExcerpt("");
      setCreatedMessage(result.created ? t("Evidence reference saved") : t("Existing evidence reference reused"));
      await load(search);
      setSelectedId(result.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  }

  async function copyExcerpt() {
    if (!selected) return;
    await navigator.clipboard.writeText(selected.excerpt);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <section className="evidenceLedger" aria-label="evidence-references-page">
      <header className="pageSubHeader evidenceLedgerHeader">
        <div>
          <span className="eyebrow">{t("Project evidence")}</span>
          <h2>{t("Evidence references")}</h2>
          <p>{t("Keep the exact excerpts an external modeling agent used. References are shared by every ontology in this project.")}</p>
        </div>
        <div className="headerActions">
          <Tag color="blue" icon={<BookMarked size={13} />}>{t("Shared by project")}</Tag>
          <Button icon={<RefreshCw size={15} />} onClick={() => void load(search)} disabled={loading}>
            {t("Refresh")}
          </Button>
        </div>
      </header>

      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError("")} />}
      {createdMessage && <Alert type="success" showIcon message={createdMessage} closable onClose={() => setCreatedMessage("")} />}

      <Card className="evidenceComposer" bordered={false}>
        <div className="evidenceComposerIntro">
          <span className="evidenceComposerIcon"><Quote size={19} /></span>
          <div>
            <strong>{t("Save a cited passage")}</strong>
            <span>{t("Only the document name and exact excerpt are stored. The full source file is not uploaded.")}</span>
          </div>
        </div>
        <div className="evidenceComposerFields">
          <label>
            <span>{t("Document name")}</span>
            <Input
              value={documentName}
              onChange={(event) => setDocumentName(event.target.value)}
              placeholder={t("Example: Dify API Guide")}
              disabled={readOnly || saving}
              maxLength={255}
            />
          </label>
          <label className="evidenceExcerptField">
            <span>{t("Exact document excerpt")}</span>
            <Input.TextArea
              value={excerpt}
              onChange={(event) => setExcerpt(event.target.value)}
              placeholder={t("Paste the exact passage that supports a class, relation, entity, or fact...")}
              disabled={readOnly || saving}
              autoSize={{ minRows: 3, maxRows: 8 }}
            />
          </label>
          <Button
            type="primary"
            icon={<Plus size={15} />}
            onClick={() => void createReference()}
            loading={saving}
            disabled={readOnly || !documentName.trim() || !excerpt.trim()}
          >
            {t("Save reference")}
          </Button>
        </div>
      </Card>

      <div className="evidenceLedgerGrid">
        <Card className="evidenceIndex" bordered={false}>
          <div className="evidenceIndexToolbar">
            <div>
              <strong>{t("Reference ledger")}</strong>
              <span>{t("{count} project references", { count: items.length })}</span>
            </div>
            <Input
              allowClear
              prefix={<Search size={14} />}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onPressEnter={() => void load(search)}
              placeholder={t("Search document or excerpt")}
            />
          </div>
          {loading ? (
            <Skeleton active paragraph={{ rows: 6 }} />
          ) : items.length === 0 ? (
            <div className="evidenceEmpty">
              <FileText size={24} />
              <strong>{t("No evidence references yet")}</strong>
              <span>{t("Save the first excerpt used by a modeling agent.")}</span>
            </div>
          ) : (
            <div className="evidenceReferenceList" role="list">
              {items.map((item) => (
                <button
                  className={item.id === selectedId ? "evidenceReferenceRow active" : "evidenceReferenceRow"}
                  key={item.id}
                  onClick={() => setSelectedId(item.id)}
                  type="button"
                >
                  <span className="evidenceDocumentGlyph"><FileText size={16} /></span>
                  <span className="evidenceReferenceCopy">
                    <strong>{item.document_name}</strong>
                    <small>{item.excerpt}</small>
                    <span>
                      <Link2 size={11} /> {t("{count} associations", { count: item.association_count })}
                      <span aria-hidden="true">·</span>{formatDate(item.created_at)}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </Card>

        <Card className="evidenceDetail" bordered={false}>
          {!selected ? (
            <div className="evidenceEmpty">
              <Quote size={24} />
              <strong>{t("Select a reference")}</strong>
              <span>{t("Inspect its exact excerpt and modeling associations.")}</span>
            </div>
          ) : (
            <>
              <div className="evidenceDetailHeader">
                <div>
                  <span className="eyebrow">{t("Cited source")}</span>
                  <h3>{selected.document_name}</h3>
                </div>
                <Tooltip title={copied ? t("Copied") : t("Copy excerpt")}>
                  <Button icon={copied ? <Check size={14} /> : <Copy size={14} />} onClick={() => void copyExcerpt()} />
                </Tooltip>
              </div>
              <blockquote>{selected.excerpt}</blockquote>
              <dl className="evidenceMetadata">
                <div><dt>{t("Reference ID")}</dt><dd><code>{compactId(selected.id)}</code></dd></div>
                <div><dt>{t("Excerpt hash")}</dt><dd><code title={selected.excerpt_hash}>{compactId(selected.excerpt_hash)}</code></dd></div>
                <div><dt>{t("Created")}</dt><dd>{formatDate(selected.created_at)}</dd></div>
                <div><dt>{t("Created by")}</dt><dd>{selected.created_by || t("Not recorded")}</dd></div>
              </dl>
              <div className="evidenceAssociationSection">
                <div className="evidenceAssociationHeading">
                  <div><strong>{t("Modeling associations")}</strong><span>{t("Concrete results supported by this excerpt")}</span></div>
                  <Tag>{associations.length}</Tag>
                </div>
                {associations.length === 0 ? (
                  <div className="evidenceAssociationEmpty">{t("Not associated with a modeling result yet")}</div>
                ) : (
                  <div className="evidenceAssociationList">
                    {associations.map((association) => (
                      <div className="evidenceAssociationRow" key={association.id}>
                        <span className={association.ontology_id === ontologyId ? "associationDot current" : "associationDot"} />
                        <div>
                          <strong>{association.target_type.replace(/_/g, " ")}</strong>
                          <code title={association.target_id}>{association.target_id}</code>
                          <span>
                            {association.ontology_id === ontologyId ? t("Current ontology") : t("Another project ontology")}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {currentOntologyAssociations.length > 0 && (
                  <p className="evidenceCurrentScopeNote">
                    {t("{count} associations belong to the ontology currently open", { count: currentOntologyAssociations.length })}
                  </p>
                )}
              </div>
            </>
          )}
        </Card>
      </div>
    </section>
  );
}
