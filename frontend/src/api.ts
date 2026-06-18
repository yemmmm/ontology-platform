import type { Notice } from "./types";

declare global {
  interface ImportMetaEnv {
    readonly VITE_API_BASE_URL?: string;
  }

  interface ImportMeta {
    readonly env: ImportMetaEnv;
  }
}

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "");
export const TOKEN_KEY = "ontology-platform-admin-token";

export async function apiRequest<T>(
  path: string,
  token: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token.trim()) headers.set("Authorization", `Bearer ${token.trim()}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  const text = await response.text();
  let payload: unknown = null;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? JSON.stringify((payload as { detail: unknown }).detail)
        : typeof payload === "string"
          ? payload
          : response.statusText;
    throw new Error(`${response.status} ${detail}`);
  }

  return payload as T;
}

export function errorNotice(error: unknown): Notice {
  return { kind: "error", message: error instanceof Error ? error.message : String(error) };
}
