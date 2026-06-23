import { useCallback, useEffect, useRef, useState } from "react";

export type AsyncResourceState<T> = {
  data: T | null;
  error: Error | null;
  loading: boolean;
  refreshing: boolean;
};

export type AsyncResource<T> = AsyncResourceState<T> & {
  refresh: () => Promise<T | undefined>;
  cancel: () => void;
};

function toError(reason: unknown): Error {
  return reason instanceof Error ? reason : new Error(String(reason));
}

export function useAsyncResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  dependencies: readonly unknown[] = [],
  enabled = true,
): AsyncResource<T> {
  const loadRef = useRef(load);
  loadRef.current = load;
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const [state, setState] = useState<AsyncResourceState<T>>({
    data: null,
    error: null,
    loading: enabled,
    refreshing: false,
  });

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  const refresh = useCallback(async () => {
    cancel();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((current) => ({
      ...current,
      error: null,
      loading: current.data === null,
      refreshing: current.data !== null,
    }));
    try {
      const data = await loadRef.current(controller.signal);
      if (!controller.signal.aborted && mountedRef.current) {
        setState({ data, error: null, loading: false, refreshing: false });
      }
      return data;
    } catch (reason) {
      if (!controller.signal.aborted && mountedRef.current) {
        setState((current) => ({
          ...current,
          error: toError(reason),
          loading: false,
          refreshing: false,
        }));
      }
      return undefined;
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  }, [cancel]);

  useEffect(() => {
    mountedRef.current = true;
    if (enabled) void refresh();
    else setState((current) => ({ ...current, loading: false, refreshing: false }));
    return () => {
      mountedRef.current = false;
      cancel();
    };
    // The dependency list is intentionally supplied by the caller, like useEffect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, refresh, cancel, ...dependencies]);

  return { ...state, refresh, cancel };
}
