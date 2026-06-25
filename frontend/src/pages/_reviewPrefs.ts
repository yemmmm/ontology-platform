import { useCallback, useState } from "react";

export type ReviewPrefKey = "autoApplyOnApprove";

export function useReviewPref(key: ReviewPrefKey, fallback: boolean): [boolean, (next: boolean) => void] {
  const storageKey = `ontology-platform-ui-review-${key}`;
  const [value, setValue] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      return stored === null ? fallback : stored === "true";
    } catch {
      return fallback;
    }
  });

  const update = useCallback((next: boolean) => {
    setValue(next);
    try {
      localStorage.setItem(storageKey, String(next));
    } catch {
      // Local storage is optional in embedded previews.
    }
  }, [storageKey]);

  return [value, update];
}
