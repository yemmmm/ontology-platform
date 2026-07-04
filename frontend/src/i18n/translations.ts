export type Language = "en" | "zh";

export type TranslationMap = Record<string, string>;

export const LANGUAGES: Language[] = ["zh", "en"];

export const LANGUAGE_LABELS: Record<Language, string> = {
  zh: "中文",
  en: "English",
};

export const STORAGE_KEY = "ontology-platform-ui-lang";

export function detectInitialLanguage(): Language {
  if (typeof window === "undefined") return "zh";
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "zh") return stored;
  } catch {
    // localStorage unavailable
  }
  const navLang = typeof navigator !== "undefined" ? navigator.language : "";
  return navLang && navLang.toLowerCase().startsWith("en") ? "en" : "zh";
}

export function formatTemplate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    const value = params[key];
    return value === undefined || value === null ? match : String(value);
  });
}
