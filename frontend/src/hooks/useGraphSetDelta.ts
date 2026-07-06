import { useCallback, useRef, useState } from "react";

import { readModel } from "../semanticApi";
import type { WorkbenchRequest } from "../pages/workbenchTypes";

/**
 * Stage 3 §4.3 — graph-set delta (RDF diff between two graph sets).
 *
 * The backend composer is `_compose_graph_set_delta` in
 * `backend/app/services/semantic_read_model.py`. The envelope wraps the
 * payload in `items[]` (one entry); the entry is
 * `{ base_graph_set_id, target_graph_set_id, roles: [...], truncated }`.
 *
 * This hook is LAZY: nothing fires until the caller invokes
 * `compute(baseId, targetId)`. No polling.
 */
export type TripleDelta = {
  subject: string;
  predicate: string;
  object: string;
};

export type RoleDelta = {
  role: string;
  base_graph_iri: string | null;
  target_graph_iri: string | null;
  added: TripleDelta[];
  removed: TripleDelta[];
  counts: { added: number; removed: number };
};

export type GraphSetDeltaPayload = {
  base_graph_set_id: string;
  target_graph_set_id: string;
  roles: RoleDelta[];
  truncated?: boolean;
};

export type GraphSetDeltaEnvelope = {
  graph_set_id: string;
  model_name: "graph-set-delta";
  projection_version: string;
  items: GraphSetDeltaPayload[];
};

export type UseGraphSetDeltaResult = {
  data: GraphSetDeltaPayload | null;
  loading: boolean;
  error: string | null;
  compute: (baseId: string, targetId: string) => Promise<void>;
  reset: () => void;
};

function messageFrom(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

export function useGraphSetDelta(
  request: WorkbenchRequest,
): UseGraphSetDeltaResult {
  const [data, setData] = useState<GraphSetDeltaPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track the in-flight request so a stale slow response can't overwrite a
  // newer compute's result.
  const requestIdRef = useRef(0);

  const compute = useCallback(
    async (baseId: string, targetId: string) => {
      if (!baseId || !targetId || baseId === targetId) return;
      const requestId = ++requestIdRef.current;
      setLoading(true);
      setError(null);
      try {
        const env = await readModel<GraphSetDeltaEnvelope>(
          request,
          baseId,
          "graph-set-delta",
          { fieldSet: "detail", target: targetId },
        );
        if (requestId !== requestIdRef.current) return;
        setData(env.items?.[0] ?? null);
      } catch (reason) {
        if (requestId !== requestIdRef.current) return;
        setError(messageFrom(reason));
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [request],
  );

  const reset = useCallback(() => {
    requestIdRef.current += 1;
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return { data, loading, error, compute, reset };
}
