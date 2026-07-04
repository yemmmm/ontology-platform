import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { zh } from "./zh";
import {
  detectInitialLanguage,
  formatTemplate,
  LANGUAGE_LABELS,
  LANGUAGES,
  STORAGE_KEY,
  type Language,
} from "./translations";

type I18nContextValue = {
  lang: Language;
  setLang: (lang: Language) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>(() => detectInitialLanguage());

  const setLang = useCallback((next: Language) => {
    setLangState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // localStorage unavailable
    }
  }, []);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = lang;
    }
  }, [lang]);

  const t = useCallback(
    (key: string, params?: Record<string, string | number>) => {
      if (lang === "en") return formatTemplate(key, params);
      const value = zh[key];
      if (value === undefined) return formatTemplate(key, params);
      return formatTemplate(value, params);
    },
    [lang],
  );

  const value = useMemo<I18nContextValue>(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <LanguageProvider>");
  return ctx;
}

export function useT() {
  return useI18n().t;
}

export { LANGUAGE_LABELS, LANGUAGES };
export type { Language };
