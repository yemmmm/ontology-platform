import { Alert, Button, Card, Descriptions, Empty, Input, Select, Space, Spin, Tag, Typography } from "antd";
import { LocateFixed, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { Evidence, SourceChunk, SourceDocument } from "../types";
import type { Requester } from "./governanceTypes";
import { messageFrom } from "./governanceTypes";

type EvidenceExplorerProps = {
  request: Requester;
  evidenceIds?: string[];
  proposalId?: string;
  itemKey?: string;
  documentId?: string;
  evidence?: Evidence[];
  compact?: boolean;
};

type EvidenceContext = {
  evidence: Evidence;
  document: SourceDocument | null;
  chunk: SourceChunk | null;
  traceWarning: string | null;
};

function HighlightedChunk({ context }: { context: EvidenceContext }) {
  const { evidence, chunk } = context;
  if (!chunk) return <Alert type="warning" showIcon message="Original chunk is unavailable; only the stored quote can be shown." />;
  if (evidence.char_start === null || evidence.char_end === null) return <pre style={{ whiteSpace: "pre-wrap" }}>{chunk.text}</pre>;
  const start = evidence.char_start - chunk.char_start;
  const end = evidence.char_end - chunk.char_start;
  if (start < 0 || end > chunk.text.length || start >= end) {
    return <Alert type="warning" showIcon message="Stored character offsets do not fit the current chunk. Location is not inferred." description={<pre style={{ whiteSpace: "pre-wrap" }}>{chunk.text}</pre>} />;
  }
  return <pre style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{chunk.text.slice(0, start)}<mark id={`evidence-${evidence.id}`}>{chunk.text.slice(start, end)}</mark>{chunk.text.slice(end)}</pre>;
}

export function EvidenceExplorer({
  request,
  evidenceIds = [],
  proposalId,
  itemKey,
  documentId,
  evidence: providedEvidence,
  compact = false,
}: EvidenceExplorerProps) {
  const [evidence, setEvidence] = useState<Evidence[]>(providedEvidence ?? []);
  const [contexts, setContexts] = useState<EvidenceContext[]>([]);
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState(documentId ?? "all");
  const [idQuery, setIdQuery] = useState(evidenceIds.join(", "));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const hydrate = useCallback(async (items: Evidence[]) => {
    const documentIds = [...new Set(items.map((item) => item.document_id).filter((id): id is string => Boolean(id)))];
    const documentPairs = await Promise.all(documentIds.map(async (id) => {
      const [document, chunks] = await Promise.all([
        request<SourceDocument>(`/source-documents/${id}`),
        request<SourceChunk[]>(`/source-documents/${id}/chunks`),
      ]);
      return { document, chunks };
    }));
    const documentMap = new Map(documentPairs.map((pair) => [pair.document.id, pair]));
    setDocuments(documentPairs.map((pair) => pair.document));
    setContexts(items.map((item) => {
      const pair = item.document_id ? documentMap.get(item.document_id) : undefined;
      const chunk = pair?.chunks.find((candidate) => candidate.id === item.chunk_id) ?? null;
      const hashMismatch = chunk && item.content_hash !== chunk.content_hash;
      return {
        evidence: item,
        document: pair?.document ?? null,
        chunk,
        traceWarning: hashMismatch ? "The stored evidence hash differs from the current source chunk hash." : null,
      };
    }));
  }, [request]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      let items = providedEvidence ?? [];
      if (proposalId && itemKey) {
        items = await request<Evidence[]>(`/proposals/${proposalId}/items/${encodeURIComponent(itemKey)}/sources`);
      } else if (!providedEvidence && evidenceIds.length > 0) {
        setEvidence([]);
        setContexts([]);
        return;
      }
      setEvidence(items);
      await hydrate(items);
    } catch (loadError) {
      setError(messageFrom(loadError));
    } finally {
      setLoading(false);
    }
  }, [evidenceIds.length, hydrate, itemKey, proposalId, providedEvidence, request]);

  useEffect(() => { void load(); }, [load]);

  const requestedIds = useMemo(() => idQuery.split(",").map((value) => value.trim()).filter(Boolean), [idQuery]);
  const filtered = contexts.filter((context) => selectedDocumentId === "all" || context.evidence.document_id === selectedDocumentId);
  const unresolvedIds = requestedIds.filter((id) => !evidence.some((item) => item.id === id));

  return (
    <Space direction="vertical" size={compact ? 8 : 16} style={{ width: "100%" }}>
      {!compact && <div className="topBar"><div><span className="eyebrow">Traceability / source truth</span><h1>Evidence Explorer</h1><div className="crumbTrail">Document, conversation and user-statement evidence</div></div><Button icon={<RefreshCw size={15} />} onClick={() => void load()} loading={loading}>Refresh</Button></div>}
      {error && <Alert type="error" showIcon message={error} />}
      {!compact && <Card title="Evidence lookup">
        <Space wrap style={{ width: "100%" }}>
          <Input prefix={<Search size={14} />} value={idQuery} onChange={(event) => setIdQuery(event.target.value)} placeholder="Evidence IDs, comma separated" style={{ maxWidth: 440 }} />
          <Select value={selectedDocumentId} onChange={setSelectedDocumentId} style={{ width: 240 }} options={[{ value: "all", label: "All source documents" }, ...documents.map((item) => ({ value: item.id, label: item.filename }))]} />
        </Space>
      </Card>}
      {loading && <Spin tip="Loading evidence and source chunks…" />}
      {unresolvedIds.length > 0 && !proposalId && !providedEvidence && (
        <Alert type="warning" showIcon message="Evidence IDs cannot be resolved by the current backend API." description={`Unresolved: ${unresolvedIds.join(", ")}. The backend exposes evidence through proposal item sources only; Fact Claims do not include proposal/item linkage. No source location has been fabricated.`} />
      )}
      {documentId && !proposalId && !providedEvidence && (
        <Alert type="warning" showIcon message="Document-wide evidence lookup is not available." description="The backend can list document proposals and proposal-item evidence, but it cannot list evidence records for a document directly. Supply a proposal ID and item key to resolve exact sources." />
      )}
      {!loading && filtered.length === 0 && unresolvedIds.length === 0 && <Empty description="No evidence sources found" />}
      {filtered.length > 0 && <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(${compact ? "280px" : "360px"}, 1fr))`, gap: 12 }}>
        {filtered.map((context) => (
          <Card key={context.evidence.id} size="small" title={<Space wrap><Tag>{context.evidence.source_type}</Tag><span>{context.document?.filename ?? "Non-document source"}</span></Space>} extra={<Button type="text" icon={<LocateFixed size={15} />} disabled={!context.chunk} onClick={() => document.getElementById(`evidence-${context.evidence.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" })} aria-label="Locate original text" />}>
            <Space direction="vertical" size={10} style={{ width: "100%" }}>
              {context.traceWarning && <Alert type="warning" showIcon message={context.traceWarning} />}
              <Descriptions size="small" column={1} items={[
                { key: "id", label: "Evidence ID", children: context.evidence.id },
                { key: "page", label: "Page / chunk", children: `${context.evidence.page_number ?? "—"} / ${context.evidence.chunk_id ?? "—"}` },
                { key: "range", label: "Character range", children: context.evidence.char_start === null ? "—" : `${context.evidence.char_start}–${context.evidence.char_end}` },
                { key: "hash", label: "Content hash", children: <Typography.Text copyable code>{context.evidence.content_hash}</Typography.Text> },
              ]} />
              <blockquote style={{ margin: 0, borderLeft: "3px solid #6c4df6", paddingLeft: 12 }}>{context.evidence.quote}</blockquote>
              <HighlightedChunk context={context} />
            </Space>
          </Card>
        ))}
      </div>}
    </Space>
  );
}
