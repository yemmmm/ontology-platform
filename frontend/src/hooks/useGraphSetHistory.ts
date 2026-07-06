import { useCallback, useEffect, useRef, useState } from "react";

import { readModel } from "../semanticApi";
import type { WorkbenchRequest } from "../pages/workbenchTypes";

/**
 * Stage 3 §4.2 — graph-set history list row.
 *
 * The backend composer is `_compose_graph_set_history_list` in
 * `backend/app/services/semantic_read_model.py`. The envelope wraps the
 * payload in `items[]` (one entry), and that entry is itself
 * `{ graph_sets: [...], total: N }`. The composer ignores the anchor
 * `graph_set_id` for membership and queries by `(scope_type, scope_id)`,
 * so any set in scope is a valid anchor.
 *
 * Unlike `useGraphSetReadiness` this hook does NOT poll: history lists
 * change rarely and the page exposes a Refresh button.
 */
export type GraphSetHistoryStatus = "editable" | "locked" | "superseded";

export type GraphSetHistoryEntry = {
  graph_set_id: string;
  status: GraphSetHistoryStatus;
  created_at: string;
  locked_at: string | null;
  source_signature: string;
  member_count: number;
  latest_derived_pointer_at: string | null;
  ready: boolean | null;
};

export type GraphSetHistoryPayload = {
  graph_sets: GraphSetHistoryEntry[];
  total: number;
};

export type GraphSetHistoryEnvelope = {
  graph_set_id: string;
  model_name: "graph-set-history-list";
  projection_version: string;
  items: GraphSetHistoryPayload[];
};

export type UseGraphSetHistoryResult = {
  data: GraphSetHistoryEntry[] | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  reload: () => Promise<void>;
};

function messageFrom(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

export function useGraphSetHistory(
  request: WorkbenchRequest,
  graphSetId: string | null,
): UseGraphSetHistoryResult {
  const [data, setData] = useState<GraphSetHistoryEntry[] | null>(null);
  const [loading, setLoading] = useState<boolean>(!!graphSetId);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track the in-flight request so a slow response can't overwrite a fresher
  // reload (e.g. user clicks Refresh while a fetch is mid-air).
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
      const env = await readModel<GraphSetHistoryEnvelope>(
        request,
        graphSetId,
        "graph-set-history-list",
        { fieldSet: "summary" },
      );
      if (requestId !== requestIdRef.current) return;
      const payload = env.items?.[0] ?? { graph_sets: [], total: 0 };
      setData(payload.graph_sets);
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

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, loading, refreshing, error, reload };
}
