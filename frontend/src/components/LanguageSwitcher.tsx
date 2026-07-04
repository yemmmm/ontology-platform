import { Tooltip } from "antd";
import { Globe } from "lucide-react";
import { LANGUAGE_LABELS, LANGUAGES, useI18n } from "../i18n";

export function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();
  const nextIndex = (LANGUAGES.indexOf(lang) + 1) % LANGUAGES.length;
  const nextLang = LANGUAGES[nextIndex];

  return (
    <Tooltip title={t("Switch language")}>
      <button
        className="iconButton languageSwitcher"
        onClick={() => setLang(nextLang)}
        type="button"
        aria-label={t("Switch language")}
      >
        <Globe size={16} />
        <span className="languageSwitcherLabel">{LANGUAGE_LABELS[lang]}</span>
      </button>
    </Tooltip>
  );
}
