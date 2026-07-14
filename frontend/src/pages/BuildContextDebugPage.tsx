import {
  Activity,
  AlertTriangle,
  Bot,
  Braces,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Database,
  FileText,
  Layers3,
  Loader2,
  RefreshCw,
  ServerCog,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useT } from "../i18n";
import type {
  BuildCheckpoint,
  BuildContext,
  BuildContextOntology,
  BuildSessionDetail,
  BuildSessionSummary,
} from "../types";
import { classNames, compactId, formatDate, prettyJson } from "../utils";

type Requester = <T,>(path: string, options?: RequestInit) => Promise<T>;

type Diagnostic = {
  id: string;
  tone: "warning" | "error";
  title: string;
  detail: string;
};

export function BuildContextDebugPage(props: { projectId: string; request: Requester }) {
  const t = useT();
  const [context, setContext] = useState<BuildContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [sessionDetail, setSessionDetail] = useState<BuildSessionDetail | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sessionError, setSessionError] = useState("");

  const loadContext = useCallback(async () => {
    setLoading(true);
    setError("");
    setSelectedSessionId("");
    setSessionDetail(null);
    try {
      const data = await props.request<BuildContext>(
        `/projects/${props.projectId}/build-context?recent_session_limit=10&recent_session_cursor=0`,
      );
      setContext(data);
    } catch (requestError) {
      setContext(null);
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, [props.projectId, props.request]);

  useEffect(() => {
    void loadContext();
  }, [loadContext]);

  async function loadMoreSessions() {
    const cursor = context?.agent_state.recent_sessions_next_cursor;
    if (cursor === null || cursor === undefined || loadingMore) return;
    setLoadingMore(true);
    setError("");
    try {
      const page = await props.request<BuildContext>(
        `/projects/${props.projectId}/build-context?recent_session_limit=10&recent_session_cursor=${cursor}`,
      );
      setContext((current) => {
        if (!current) return page;
        const known = new Set(current.agent_state.recent_sessions.map((item) => item.id));
        const additions = page.agent_state.recent_sessions.filter((item) => !known.has(item.id));
        return {
          ...current,
          generated_at: page.generated_at,
          agent_state: {
            ...current.agent_state,
            recent_sessions: [...current.agent_state.recent_sessions, ...additions],
            recent_sessions_next_cursor: page.agent_state.recent_sessions_next_cursor,
            unresolved_items: unique([
              ...current.agent_state.unresolved_items,
              ...page.agent_state.unresolved_items,
            ]),
          },
        };
      });
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoadingMore(false);
    }
  }

  async function inspectSession(sessionId: string) {
    if (selectedSessionId === sessionId && sessionDetail) {
      setSelectedSessionId("");
      setSessionDetail(null);
      return;
    }
    setSelectedSessionId(sessionId);
    setSessionDetail(null);
    setSessionError("");
    setSessionLoading(true);
    try {
      setSessionDetail(await props.request<BuildSessionDetail>(`/build-sessions/${sessionId}`));
    } catch (requestError) {
      setSessionError(errorMessage(requestError));
    } finally {
      setSessionLoading(false);
    }
  }

  const diagnostics = useMemo(() => (context ? collectDiagnostics(context, t) : []), [context, t]);

  if (loading && !context) {
    return (
      <CenteredState icon={<Loader2 className="spin" size={22} />} title={t("Loading Build Context")} />
    );
  }

  if (!context) {
    return (
      <CenteredState
        icon={<AlertTriangle size={22} />}
        title={t("Build Context could not be loaded")}
        detail={error}
        action={
          <button className="primaryButton" onClick={() => void loadContext()} type="button">
            <RefreshCw size={15} /> {t("Retry")}
          </button>
        }
      />
    );
  }

  const { platform_state: platform, agent_state: agent } = context;

  return (
    <section className="buildContextPage" aria-label="build-context-debug-page">
      <header className="buildContextHero">
        <div>
          <span className="buildContextKicker"><ServerCog size={14} /> {t("Read-only project recovery view")}</span>
          <h2>{context.project.name}</h2>
          <p>
            {t("Platform facts and Agent reports stay separate. Reading this page does not update last activity.")}
          </p>
        </div>
        <div className="buildContextHeroActions">
          <span><Clock3 size={14} /> {t("Generated")} {formatDate(context.generated_at)}</span>
          <button className="primaryButton" disabled={loading} onClick={() => void loadContext()} type="button">
            {loading ? <Loader2 className="spin" size={15} /> : <RefreshCw size={15} />}
            {t("Refresh")}
          </button>
        </div>
      </header>

      {error && <div className="inlineError">{error}</div>}

      <section className="buildContextDiagnostics" aria-label={t("Diagnostics")}>
        <div className="buildContextSectionHeading">
          <div><AlertTriangle size={17} /><h3>{t("Diagnostics")}</h3></div>
          <span>{t("{count} deterministic findings", { count: diagnostics.length })}</span>
        </div>
        {diagnostics.length ? (
          <div className="diagnosticList">
            {diagnostics.map((item) => (
              <article className={classNames("diagnosticItem", item.tone)} key={item.id}>
                <AlertTriangle size={16} />
                <div><strong>{item.title}</strong><span>{item.detail}</span></div>
              </article>
            ))}
          </div>
        ) : (
          <div className="diagnosticClear"><CheckCircle2 size={16} /> {t("No deterministic warning found")}</div>
        )}
      </section>

      <div className="buildContextColumns">
        <section className="buildContextLane platform" aria-label="platform-state">
          <div className="buildContextLaneTitle">
            <div className="buildContextLaneIcon"><Database size={18} /></div>
            <div><span>{t("Server observed")}</span><h3>{t("Platform State")}</h3></div>
          </div>

          <div className="contextMetricGrid">
            <ContextMetric label={t("Brief completeness")} value={`${Math.round(platform.project_brief.completeness * 100)}%`} />
            <ContextMetric label={t("Evidence references")} value={platform.evidence_reference_count} />
            <ContextMetric label={t("Ontologies")} value={platform.ontologies.length} />
            <ContextMetric label={t("Modeling batches")} value={platform.modeling_batches.length} />
          </div>

          <ContextBlock title={t("Project Brief")} icon={<FileText size={15} />}>
            {platform.project_brief.missing_fields.length ? (
              <TagList items={platform.project_brief.missing_fields} emptyLabel={t("No missing fields")} />
            ) : <p className="contextEmptyLine">{t("No missing fields")}</p>}
          </ContextBlock>

          <ContextBlock title={t("Competency Questions")} icon={<Activity size={15} />}>
            {Object.keys(platform.competency_question_counts).length ? (
              <div className="countList">
                {Object.entries(platform.competency_question_counts).map(([status, count]) => (
                  <div key={status}><span>{status}</span><strong>{count}</strong></div>
                ))}
              </div>
            ) : <p className="contextEmptyLine">{t("No competency questions observed")}</p>}
          </ContextBlock>

          <ContextBlock title={t("Ontology Workspaces")} icon={<Layers3 size={15} />}>
            {platform.ontologies.length ? (
              <div className="workspaceStateList">
                {platform.ontologies.map((ontology) => <WorkspaceState key={ontology.id} ontology={ontology} />)}
              </div>
            ) : <p className="contextEmptyLine">{t("No ontologies in this project")}</p>}
          </ContextBlock>

          <ContextBlock title={t("Modeling Batches")} icon={<Database size={15} />}>
            {platform.modeling_batches.length ? (
              <SafeBatchSummaries batches={platform.modeling_batches} />
            ) : <p className="contextEmptyLine">{t("No modeling batches observed")}</p>}
          </ContextBlock>
        </section>

        <section className="buildContextLane agent" aria-label="agent-state">
          <div className="buildContextLaneTitle">
            <div className="buildContextLaneIcon"><Bot size={18} /></div>
            <div><span>{t("Externally reported")}</span><h3>{t("Agent State")}</h3></div>
          </div>

          <div className="contextMetricGrid agentMetrics">
            <ContextMetric label={t("Active sessions")} value={agent.active_sessions.length} />
            <ContextMetric label={t("Recent sessions")} value={agent.recent_sessions.length} />
            <ContextMetric label={t("Unresolved items")} value={agent.unresolved_items.length} />
          </div>

          <ContextBlock title={t("Active Sessions")} icon={<Activity size={15} />}>
            <SessionList
              empty={t("No active build sessions")}
              inspectSession={inspectSession}
              selectedSessionId={selectedSessionId}
              sessions={agent.active_sessions}
            />
          </ContextBlock>

          <ContextBlock title={t("Recent Sessions")} icon={<Clock3 size={15} />}>
            <SessionList
              empty={t("No completed or cancelled sessions")}
              inspectSession={inspectSession}
              selectedSessionId={selectedSessionId}
              sessions={agent.recent_sessions}
            />
            {agent.recent_sessions_next_cursor !== null && (
              <button className="secondaryButton contextLoadMore" disabled={loadingMore} onClick={() => void loadMoreSessions()} type="button">
                {loadingMore ? <Loader2 className="spin" size={14} /> : <ChevronDown size={14} />}
                {t("Load more sessions")}
              </button>
            )}
          </ContextBlock>

          {selectedSessionId && (
            <ContextBlock title={t("Session Detail")} icon={<Braces size={15} />}>
              {sessionLoading && <p className="contextEmptyLine"><Loader2 className="spin" size={14} /> {t("Loading session detail")}</p>}
              {sessionError && <div className="inlineError">{sessionError}</div>}
              {sessionDetail && <SessionDetail detail={sessionDetail} />}
            </ContextBlock>
          )}
        </section>
      </div>

      <details className="buildContextRaw">
        <summary><Braces size={16} /> {t("Raw merged response")}<span>{t("REST contract view")}</span></summary>
        <pre className="jsonBlock tall">{prettyJson(safeDebugPayload(context))}</pre>
      </details>
    </section>
  );
}

function ContextMetric(props: { label: string; value: string | number }) {
  return <div className="contextMetric"><span>{props.label}</span><strong>{props.value}</strong></div>;
}

function ContextBlock(props: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="contextBlock">
      <header>{props.icon}<h4>{props.title}</h4></header>
      {props.children}
    </section>
  );
}

function WorkspaceState({ ontology }: { ontology: BuildContextOntology }) {
  const t = useT();
  return (
    <article className="workspaceStateItem">
      <div className="workspaceStateHeader">
        <div><strong>{ontology.name}</strong><code>{compactId(ontology.id)}</code></div>
        <span className={classNames("contextStatus", ontology.workspace.editable ? "ready" : "blocked")}>
          {ontology.workspace.editable ? t("Editable") : t("Not editable")}
        </span>
      </div>
      <dl>
        <dt>{t("Ontology status")}</dt><dd>{ontology.status}</dd>
        <dt>{t("Workspace state")}</dt><dd>{ontology.workspace.state}</dd>
        <dt>{t("Workspace version")}</dt><dd><code>{ontology.workspace.workspace_version ?? t("Not available")}</code></dd>
      </dl>
      {ontology.workspace.issues.length > 0 && <TagList items={ontology.workspace.issues} emptyLabel="" />}
    </article>
  );
}

function SessionList(props: {
  sessions: BuildSessionSummary[];
  empty: string;
  selectedSessionId: string;
  inspectSession: (id: string) => void;
}) {
  if (!props.sessions.length) return <p className="contextEmptyLine">{props.empty}</p>;
  return (
    <div className="sessionList">
      {props.sessions.map((session) => (
        <SessionItem
          key={session.id}
          onClick={() => void props.inspectSession(session.id)}
          selected={props.selectedSessionId === session.id}
          session={session}
        />
      ))}
    </div>
  );
}

function SessionItem(props: { session: BuildSessionSummary; selected: boolean; onClick: () => void }) {
  const t = useT();
  const checkpoint = props.session.latest_checkpoint;
  return (
    <button className={classNames("sessionItem", props.selected && "selected")} onClick={props.onClick} type="button">
      <div className="sessionItemTop">
        <div><strong>{compactId(props.session.id)}</strong><span>{t("Revision {revision}", { revision: props.session.revision })}</span></div>
        <span className={classNames("contextStatus", props.session.status)}>{props.session.status}</span>
      </div>
      {checkpoint ? <CheckpointSummary checkpoint={checkpoint} /> : <span className="sessionMuted">{t("No checkpoint reported")}</span>}
      {props.session.completion_summary && <span>{props.session.completion_summary}</span>}
      {props.session.cancel_reason && <span>{t("Cancelled: {reason}", { reason: props.session.cancel_reason })}</span>}
      {props.session.unresolved_items.length > 0 && <TagList items={props.session.unresolved_items} emptyLabel="" />}
      <div className="sessionItemFooter"><Clock3 size={12} /> {formatDate(props.session.last_activity_at)} <ChevronRight size={14} /></div>
    </button>
  );
}

function CheckpointSummary({ checkpoint }: { checkpoint: BuildCheckpoint }) {
  const t = useT();
  return (
    <div className="checkpointSummary">
      <span className="checkpointPhase">{checkpoint.phase}</span>
      <strong>{checkpoint.current_step}</strong>
      {checkpoint.ontology_id && (
        <span className="checkpointOntology">{t("Focus ontology")}: <code>{checkpoint.ontology_id}</code></span>
      )}
      {checkpoint.next_step && <span>{checkpoint.next_step}</span>}
      {checkpoint.blockers.length > 0 && <TagList items={checkpoint.blockers} emptyLabel="" />}
      {checkpoint.failure && <span className="checkpointFailure">{checkpoint.failure.code}: {checkpoint.failure.message}</span>}
    </div>
  );
}

function SessionDetail({ detail }: { detail: BuildSessionDetail }) {
  const t = useT();
  const evidenceReferences = Array.isArray(detail.evidence.references) ? detail.evidence.references : [];
  const evidenceNextCursor = detail.evidence.next_cursor;
  return (
    <div className="sessionDetail">
      <DetailSection title={t("Involved ontologies")} count={detail.involved_ontology_ids.length}>
        {detail.involved_ontology_ids.length ? (
          <div className="detailIdentifierList">
            {detail.involved_ontology_ids.map((ontologyId) => <code key={ontologyId}>{ontologyId}</code>)}
          </div>
        ) : <p className="contextEmptyLine">{t("No involved ontologies recorded")}</p>}
      </DetailSection>

      <DetailSection title={t("Lease summaries")} count={detail.leases.length}>
        {detail.leases.length ? (
          <div className="leaseSummaryList">
            {detail.leases.map((lease) => (
              <article key={`${lease.ontology_id}-${lease.lease_revision}`}>
                <div><code>{lease.ontology_id}</code><span className={classNames("contextStatus", lease.state)}>{lease.state}</span></div>
                <dl>
                  <dt>{t("Lease revision")}</dt><dd>{lease.lease_revision}</dd>
                  <dt>{t("Expires at")}</dt><dd>{formatDate(lease.expires_at)}</dd>
                  <dt>{t("Acquired at")}</dt><dd>{formatDate(lease.acquired_at)}</dd>
                  {lease.renewed_at && <><dt>{t("Renewed at")}</dt><dd>{formatDate(lease.renewed_at)}</dd></>}
                  {lease.released_at && <><dt>{t("Released at")}</dt><dd>{formatDate(lease.released_at)}</dd></>}
                </dl>
              </article>
            ))}
          </div>
        ) : <p className="contextEmptyLine">{t("No leases recorded")}</p>}
      </DetailSection>

      <DetailSection title={t("Modeling batch summaries")} count={detail.modeling_batches.length}>
        {detail.modeling_batches.length ? (
          <SafeBatchSummaries batches={detail.modeling_batches} />
        ) : <p className="contextEmptyLine">{t("No modeling batches linked to this session")}</p>}
      </DetailSection>

      <DetailSection title={t("Evidence references")} count={evidenceReferences.length}>
        {evidenceReferences.length ? (
          <div className="safeSummaryList">
            {evidenceReferences.map((reference, index) => (
              <pre key={evidenceReferenceKey(reference, index)}>{prettyJson(safeRecordSummary(reference, [
                "id", "document_name", "excerpt", "excerpt_hash", "created_at",
              ]))}</pre>
            ))}
          </div>
        ) : <p className="contextEmptyLine">{t("No evidence references linked to this session")}</p>}
        <p className="detailReadOnlyHint">
          {t("Read-only evidence entries are identified by the stable references returned by this recovery response.")}
          <span>{t("Next cursor")}: {formatScalar(evidenceNextCursor, t("None"))}</span>
        </p>
      </DetailSection>

      <DetailSection title={t("Recent activity")} count={detail.recent_activity.length}>
        {detail.recent_activity.length ? (
          <div className="activitySummaryList">
            {detail.recent_activity.map((activity, index) => (
              <article key={`${String(activity.type ?? "activity")}-${String(activity.at ?? index)}`}>
                <span>{humanizeActivityType(activity.type)}</span>
                <time>{formatScalar(activity.at, t("Time not recorded"), true)}</time>
                {activity.ontology_id != null && <code>{String(activity.ontology_id)}</code>}
                {activity.checkpoint_id != null && <small>{t("Checkpoint")}: {String(activity.checkpoint_id)}</small>}
              </article>
            ))}
          </div>
        ) : <p className="contextEmptyLine">{t("No recent activity recorded")}</p>}
      </DetailSection>

      <h5>{t("Checkpoint history")} <span>{detail.checkpoints.length}</span></h5>
      {detail.checkpoints.length ? (
        <div className="checkpointTimeline">
          {detail.checkpoints.map((checkpoint) => (
            <article key={checkpoint.id}>
              <span>#{checkpoint.sequence}</span>
              <CheckpointSummary checkpoint={checkpoint} />
              <time>{formatDate(checkpoint.created_at)}</time>
            </article>
          ))}
        </div>
      ) : <p className="contextEmptyLine">{t("No checkpoints in this session")}</p>}
      <details className="sessionRaw"><summary>{t("Raw session response")}</summary><pre className="jsonBlock">{prettyJson(safeDebugPayload(detail))}</pre></details>
    </div>
  );
}

function DetailSection(props: { title: string; count: number; children: ReactNode }) {
  return (
    <section className="sessionDetailSection">
      <h5>{props.title}<span>{props.count}</span></h5>
      {props.children}
    </section>
  );
}

function SafeBatchSummaries({ batches }: { batches: Array<Record<string, unknown>> }) {
  return (
    <div className="safeSummaryList">
      {batches.map((batch, index) => (
        <pre key={String(batch.id ?? index)}>{prettyJson(safeRecordSummary(batch, [
          "id", "ontology_id", "status", "result", "error", "created_at", "updated_at",
        ]))}</pre>
      ))}
    </div>
  );
}

function safeRecordSummary(value: unknown, allowedKeys: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return { value: String(value ?? "") };
  const record = value as Record<string, unknown>;
  const summary = Object.fromEntries(
    allowedKeys
      .filter((key) => key in record)
      .map((key) => [key, safeDebugPayload(record[key])]),
  );
  return Object.keys(summary).length ? summary : { summary: "No public summary fields returned" };
}

function evidenceReferenceKey(value: unknown, index: number) {
  if (value && typeof value === "object" && !Array.isArray(value) && "id" in value) {
    return String((value as Record<string, unknown>).id);
  }
  return `evidence-${index}`;
}

function humanizeActivityType(value: unknown) {
  return typeof value === "string" ? value.replace(/_/g, " ") : "activity";
}

function formatScalar(value: unknown, fallback: string, date = false) {
  if (value === null || value === undefined || value === "") return fallback;
  return date && typeof value === "string" ? formatDate(value) : String(value);
}

function safeDebugPayload(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(safeDebugPayload);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !isInternalDebugKey(key))
      .map(([key, child]) => [key, safeDebugPayload(child)]),
  );
}

function isInternalDebugKey(key: string) {
  const normalized = key.toLowerCase().replace(/[-\s]/g, "_");
  return /lease_?token/.test(normalized)
    || /graph.*iri/.test(normalized)
    || normalized.includes("graph_set")
    || normalized.includes("graphset");
}

function TagList(props: { items: string[]; emptyLabel: string }) {
  if (!props.items.length) return props.emptyLabel ? <p className="contextEmptyLine">{props.emptyLabel}</p> : null;
  return <div className="contextTags">{props.items.map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}</div>;
}

function CenteredState(props: { icon: ReactNode; title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="buildContextCentered">
      {props.icon}<strong>{props.title}</strong>
      {props.detail && <span>{props.detail}</span>}
      {props.action}
    </div>
  );
}

function collectDiagnostics(context: BuildContext, t: ReturnType<typeof useT>): Diagnostic[] {
  const findings: Diagnostic[] = [];
  const sessions = [...context.agent_state.active_sessions, ...context.agent_state.recent_sessions];
  for (const session of sessions) {
    const checkpoint = session.latest_checkpoint;
    if (checkpoint?.blockers.length) {
      findings.push({
        id: `${session.id}-blockers`, tone: "warning", title: t("Checkpoint has blockers"),
        detail: `${compactId(session.id)} · ${checkpoint.blockers.join(" · ")}`,
      });
    }
    if (checkpoint?.failure) {
      findings.push({
        id: `${session.id}-failure`, tone: "error", title: t("Checkpoint reports a failure"),
        detail: `${checkpoint.failure.code}: ${checkpoint.failure.message}`,
      });
    }
    if (session.status === "completed" && session.unresolved_items.length) {
      findings.push({
        id: `${session.id}-unresolved`, tone: "warning", title: t("Completed session has unresolved items"),
        detail: session.unresolved_items.join(" · "),
      });
    }
    if (checkpoint?.phase === "handoff" && context.platform_state.modeling_batches.length === 0) {
      findings.push({
        id: `${session.id}-handoff`, tone: "warning", title: t("Handoff has no observed modeling batch"),
        detail: t("The Agent reports handoff, while the platform has not observed a modeling batch."),
      });
    }
  }
  for (const ontology of context.platform_state.ontologies) {
    if (!ontology.workspace.editable || ontology.workspace.issues.length) {
      findings.push({
        id: `${ontology.id}-workspace`, tone: "warning", title: t("Ontology workspace needs attention"),
        detail: `${ontology.name} · ${ontology.workspace.issues.join(" · ") || t("Not editable")}`,
      });
    }
  }
  return findings;
}

function unique(items: string[]) {
  return [...new Set(items)];
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
