import { useState } from "react";
import { useAuth } from "../AuthGate";
import { LANGUAGE_LABELS, LANGUAGES, useI18n, type Language } from "../i18n";
export function SettingsPage() {
  const { principal, logout } = useAuth();
  const { lang, setLang, t } = useI18n();
  const [error, setError] = useState("");
  return <section className="panel settingsPanel" aria-label={t("Settings")}>
    <label>{t("Language preference")}<select aria-label={t("Language preference")} value={lang} onChange={event => setLang(event.target.value as Language)}>{LANGUAGES.map(language => <option key={language} value={language}>{LANGUAGE_LABELS[language]}</option>)}</select></label>
    <div><h2>{t("Current account")}</h2><p>{principal.actor}</p></div>
    <button className="primaryButton" onClick={() => void logout().catch(reason => setError(String(reason)))}>{t("Sign out")}</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}
