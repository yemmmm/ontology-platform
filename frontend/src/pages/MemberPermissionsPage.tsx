import { useEffect, useState } from "react";
import { useT } from "../i18n";
import { workspaceApi } from "../workspaceApi";
import type { AccessRole, Project } from "../workspaceTypes";
export function MemberPermissionsPage({ project }: { project: Project }) {
  const t = useT();
  const [roles, setRoles] = useState<AccessRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    workspaceApi.roles(project.id).then(items => { if (active) setRoles(items); }).catch(reason => { if (active) setError(String(reason)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [project.id]);
  return <section className="panel" aria-label={t("Member permissions")}><h2>{t("Permission roles and Grants")}</h2>
    {loading ? <p role="status">{t("Loading…")}</p> : error ? <p className="errorMessage" role="alert">{t("Permission roles could not be read")}: {error}</p> : !roles.length ? <p>{t("No permission roles")}</p> : <div className="tableScroll"><table><thead><tr><th>{t("Role name")}</th><th>{t("Description")}</th><th>Grant</th></tr></thead><tbody>{roles.map(role => <tr key={role.id}><td>{role.name}</td><td>{role.description || t("Not recorded")}</td><td>{role.grants.length ? role.grants.map(grant => <span className="tag" key={grant}>{grant}</span>) : t("No Grant configured")}</td></tr>)}</tbody></table></div>}
  </section>;
}
