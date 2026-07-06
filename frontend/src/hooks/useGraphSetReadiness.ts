import { useCallback, useEffect, useRef, useState } from "react";

import { readModel } from "../semanticApi";
import type { WorkbenchRequest } from "../pages/workbenchTypes";

/**
 * Stage 3 §4.1 — publication readiness row.
 *
 * The backend composer is `_compose_publication_readiness` in
 * `backend/app/services/semantic_read_model.py`. The envelope wraps the row
 * in `items[]` (one row per graph set). The summary field_set drops gates
 * and editable_graphs; we always request `detail` here.
 */
export type PublicationGateStatus = "passed" | "warning" | "blocked";

export type PublicationGate = {
  gate: string;
  status: PublicationGateStatus;
  details: Record<string, unknown>;
  label: string;
};

export type EditableGraphEntry = {
  graph_iri: string;
  role: string;
};

export type PublicationReadinessRow = {
  graph_set_id: string;
  ready: boolean;
  gates: PublicationGate[];
  blockers: string[];
  warnings: string[];
  editable_graph_count: number;
  editable_graphs: EditableGraphEntry[];
  last_published_at: string | null;
};

export type PublicationReadinessEnvelope = {
  graph_set_id: string;
  projection_name: "publication-readiness";
  projection_version: string;
  field_set: "summary" | "detail";
  items: PublicationReadinessRow[];
};

export type UseGraphSetReadinessResult = {
  data: PublicationReadinessRow | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  reload: () => Promise<void>;
};

const POLL_INTERVAL_MS = 30_000;

function messageFrom(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

/**
 * Polls `/semantic/graph-sets/{graphSetId}/read-models/publication-readiness`
 * every 30 seconds while the document is visible. Stops polling on unmount or
 * when the tab is hidden (reload fires on next focus).
 */
export function useGraphSetReadiness(
  request: WorkbenchRequest,
  graphSetId: string | null,
): UseGraphSetReadinessResult {
  const [data, setData] = useState<PublicationReadinessRow | null>(null);
  const [loading, setLoading] = useState<boolean>(!!graphSetId);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track the in-flight request so a slow response can't overwrite a fresher
  // reload (e.g. user clicks Refresh while the interval fetch is mid-air).
  const requestIdRef = useRef(0);

  const reload = useCallback(async () => {
    if (!graphSetId) {
      setData(null);
      setLoading(false);
      setRefreshing(false);
      setError(null);
      return;
    }
    const requestId = ++requestIdRef.current;
    if (data === null) setLoading(true);
    else setRefreshing(true);
    try {
      const env = await readModel<PublicationReadinessEnvelope>(
        request,
        graphSetId,
        "publication-readiness",
        { fieldSet: "detail" },
      );
      if (requestId !== requestIdRef.current) return;
      const row = env.items?.[0] ?? null;
      setData(row);
      setError(null);
    } catch (reason) {
      if (requestId !== requestIdRef.current) return;
      setError(messageFrom(reason));
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [request, graphSetId, data]);

  // Initial + dependency-change fetch.
  useEffect(() => {
    void reload();
  }, [reload]);

  // 30s polling while the tab is visible. Clear on unmount.
  useEffect(() => {
    if (!graphSetId) return;
    const trigger = () => {
      if (typeof document === "undefined" || document.visibilityState === "visible") {
        void reload();
      }
    };
    const intervalId = window.setInterval(trigger, POLL_INTERVAL_MS);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void reload();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [graphSetId, reload]);

  return { data, loading, refreshing, error, reload };
}
