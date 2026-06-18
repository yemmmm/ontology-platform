import type { JsonObject } from "./types";

export const propertyTypes = ["string", "number", "boolean", "date", "enum", "reference", "json"] as const;

export function classNames(...names: Array<string | false | null | undefined>) {
  return names.filter(Boolean).join(" ");
}

export function splitCsv(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function csv(value: string[]) {
  return value.join(", ");
}

export function parseJsonObject(value: string): JsonObject {
  if (!value.trim()) return {};
  const parsed = JSON.parse(value);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("JSON must be an object");
  }
  return parsed as JsonObject;
}

export function prettyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

export function compactId(id: string | null | undefined) {
  if (!id) return "None";
  return id.length > 10 ? `${id.slice(0, 8)}...` : id;
}

export function nameFor<T extends { id: string; name?: string }>(
  items: T[],
  id: string | null | undefined,
) {
  if (!id) return "None";
  return items.find((item) => item.id === id)?.name ?? compactId(id);
}

export function formatDate(value?: string) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
