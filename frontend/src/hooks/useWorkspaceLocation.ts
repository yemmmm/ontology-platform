import { useCallback, useEffect, useState } from "react";

export const workspaceLocationKeys = [
  "project",
  "ontology",
  "version",
  "tab",
  "batch",
  "proposal",
  "claim",
] as const;

export type WorkspaceLocationKey = (typeof workspaceLocationKeys)[number];
export type WorkspaceLocation = Record<WorkspaceLocationKey, string | null>;
export type WorkspaceLocationUpdate = Partial<Record<WorkspaceLocationKey, string | null>>;

const storagePrefix = "ontology-platform-ui-location-";

function readLocation(): WorkspaceLocation {
  const query = new URLSearchParams(window.location.search);
  return Object.fromEntries(
    workspaceLocationKeys.map((key) => {
      const queryValue = query.get(key);
      if (queryValue !== null) return [key, queryValue || null];
      try {
        return [key, localStorage.getItem(`${storagePrefix}${key}`)];
      } catch {
        return [key, null];
      }
    }),
  ) as WorkspaceLocation;
}

function persistLocation(location: WorkspaceLocation): void {
  for (const key of workspaceLocationKeys) {
    try {
      if (location[key]) localStorage.setItem(`${storagePrefix}${key}`, location[key]);
      else localStorage.removeItem(`${storagePrefix}${key}`);
    } catch {
      // Storage is optional; URL state remains authoritative.
    }
  }
}

export function useWorkspaceLocation() {
  const [location, setLocationState] = useState<WorkspaceLocation>(readLocation);

  useEffect(() => {
    persistLocation(location);
  }, [location]);

  useEffect(() => {
    const handlePopState = () => setLocationState(readLocation());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const setLocation = useCallback((update: WorkspaceLocationUpdate, replace = false) => {
    const url = new URL(window.location.href);
    for (const key of workspaceLocationKeys) {
      if (!(key in update)) continue;
      const value = update[key];
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    window.history[replace ? "replaceState" : "pushState"]({}, "", url);
    const next = { ...readLocation(), ...update };
    setLocationState(next);
    persistLocation(next);
  }, []);

  const clearLocation = useCallback(
    (keys: readonly WorkspaceLocationKey[], replace = false) => {
      setLocation(Object.fromEntries(keys.map((key) => [key, null])), replace);
    },
    [setLocation],
  );

  return { location, setLocation, clearLocation } as const;
}
