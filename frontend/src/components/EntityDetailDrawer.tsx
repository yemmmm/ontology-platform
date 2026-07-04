import { AlertCircle, ArrowRight, BookOpen, FileText, GitBranch, Pencil, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { Entity, EntityKnowledgeContext, EntityKnowledgeItem, EntityKnowledgeRule, Relation } from "../types";
import { useT } from "../i18n";
import { classNames, compactId, prettyJson } from "../utils";

type Requester = <T,>(path: string, options?: RequestInit) => Promise<T>;
type EntityDrawerTab = "overview" | "knowledge" | "rules" | "raw";

type EntityDetailDrawerProps = {
  entity: Entity | null;
  relations: Relation[];
  entities: Entity[];
  versionId: string;
  request: Requester;
  onClose: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onOpenFact: (claimId: string) => void;
};

function relationsFor(entity: Entity, relations: Relation[]) {
  const outgoing = relations.filter((relation) => relation.source_entity_id === entity.id);
  const incoming = relations.filter((relation) => relation.target_entity_id === entity.id);
  return { outgoing, incoming };
}

function entityName(entities: Entity[], id: string) {
  return entities.find((entity) => entity.id === id)?.name ?? compactId(id);
}

export function EntityDetailDrawer(props: EntityDetailDrawerProps) {
  const t = useT();
  const { entity, onClose } = props;
  const open = entity !== null;
  const descriptionValue = entity ? readDescription(entity.properties) : "";
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [activeTab, setActiveTab] = useState<EntityDrawerTab>("overview");
  const [knowledge, setKnowledge] = useState<EntityKnowledgeContext | null>(null);
  const [loadingKnowledge, setLoadingKnowledge] = useState(false);
  const [knowledgeError, setKnowledgeError] = useState("");
  const relationCount = entity
    ? props.relations.filter(
        (relation) =>
          relation.source_entity_id === entity.id || relation.target_entity_id === entity.id,
      ).length
    : 0;

  useEffect(() => {
    setConfirmingDelete(false);
    setActiveTab("overview");
  }, [entity?.id]);

  useEffect(() => {
    if (!entity) {
      setKnowledge(null);
      setKnowledgeError("");
      setLoadingKnowledge(false);
      return;
    }
    let cancelled = false;
    setLoadingKnowledge(true);
    setKnowledgeError("");
    props.request<EntityKnowledgeContext>(
      `/versions/${props.versionId}/entities/${entity.id}/knowledge-context`,
    ).then((data) => {
      if (!cancelled) setKnowledge(data);
    }).catch((error: unknown) => {
      if (!cancelled) {
        setKnowledge(null);
        setKnowledgeError(error instanceof Error ? error.message : t("Failed to load knowledge context"));
      }
    }).finally(() => {
      if (!cancelled) setLoadingKnowledge(false);
    });
    return () => {
      cancelled = true;
    };
  }, [entity?.id, props.request, props.versionId, t]);

  return (
    <aside
      className={classNames("entityDrawer", open && "open")}
      aria-hidden={!open}
      aria-label={t("Entity detail")}
    >
      {entity && (
        <div className="entityDrawerInner">
          <header className="entityDrawerHeader">
            <div className="entityDrawerHeaderMain">
              <span className="entityDrawerClassBadge">{entity.class_label}</span>
              <h2>{entity.name}</h2>
              {entity.aliases.length > 0 && (
                <div className="entityDrawerAliases">
                  {entity.aliases.map((alias, idx) => (
                    <span key={`${alias}-${idx}`} className="aliasChip">
                      {alias}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="entityDrawerHeaderActions">
              <button className="secondaryButton entityDrawerEdit" onClick={props.onEdit} type="button">
                <Pencil size={14} /> {t("Edit")}
              </button>
              <button
                aria-label={t("Delete {name}", { name: entity.name })}
                className="iconButton danger"
                onClick={() => setConfirmingDelete(true)}
                title={t("Delete entity")}
                type="button"
              >
                <Trash2 size={15} />
              </button>
              <button className="iconButton" onClick={onClose} type="button" aria-label={t("Close detail")}>
                <X size={16} />
              </button>
            </div>
          </header>

          <nav className="entityDrawerTabs" aria-label={t("Entity detail sections")}>
            {([
              ["overview", t("Overview")],
              ["knowledge", t("Knowledge")],
              ["rules", t("Rules")],
              ["raw", t("Raw")],
            ] as const).map(([id, label]) => (
              <button
                aria-pressed={activeTab === id}
                className={classNames(activeTab === id && "active")}
                key={id}
                onClick={() => setActiveTab(id as EntityDrawerTab)}
                type="button"
              >
                {label}
              </button>
            ))}
          </nav>

          {confirmingDelete && (
            <div className="entityDeleteConfirm" role="alert">
              <div>
                <strong>{t("Delete this entity?")}</strong>
                <span>
                  {relationCount > 0
                    ? t("This entity has {n} connected relations. Remove them before deleting the entity.", { n: relationCount })
                    : t("This action cannot be undone.")}
                </span>
              </div>
              <div className="entityDeleteConfirmActions">
                <button className="secondaryButton" onClick={() => setConfirmingDelete(false)} type="button">
                  {t("Cancel")}
                </button>
                <button
                  className="secondaryButton dangerText"
                  disabled={relationCount > 0}
                  onClick={props.onDelete}
                  type="button"
                >
                  <Trash2 size={14} /> {t("Delete entity")}
                </button>
              </div>
            </div>
          )}

          {activeTab === "overview" && (
            <>
              <section className="entityDrawerSection">
                <h3>{t("Description")}</h3>
                {descriptionValue ? (
                  <p className="entityDrawerDesc">{descriptionValue}</p>
                ) : (
                  <p className="entityDrawerEmpty">{t("No description.")}</p>
                )}
              </section>

              <DrawerRelations entity={entity} relations={props.relations} entities={props.entities} />

              <section className="entityDrawerSection">
                <h3>{t("Properties")}</h3>
                <pre className="jsonBlock entityDrawerProps">{prettyJson(entity.properties)}</pre>
              </section>
            </>
          )}

          {activeTab === "knowledge" && (
            <KnowledgeTab
              context={knowledge}
              error={knowledgeError}
              loading={loadingKnowledge}
              onOpenFact={props.onOpenFact}
            />
          )}

          {activeTab === "rules" && (
            <RulesTab
              context={knowledge}
              error={knowledgeError}
              loading={loadingKnowledge}
              onOpenFact={props.onOpenFact}
            />
          )}

          {activeTab === "raw" && (
            <section className="entityDrawerSection">
              <h3>{t("Raw context")}</h3>
              {loadingKnowledge ? (
                <p className="entityDrawerEmpty">{t("Loading knowledge context...")}</p>
              ) : knowledgeError ? (
                <DrawerAlert message={knowledgeError} />
              ) : (
                <pre className="jsonBlock entityDrawerProps">{prettyJson(knowledge ?? entity)}</pre>
              )}
            </section>
          )}

          <footer className="entityDrawerFooter">
            <span className="entityDrawerId">{t("ID")}: {compactId(entity.id)}</span>
          </footer>
        </div>
      )}
    </aside>
  );
}

function KnowledgeTab(props: {
  context: EntityKnowledgeContext | null;
  loading: boolean;
  error: string;
  onOpenFact: (claimId: string) => void;
}) {
  const t = useT();
  if (props.loading) return <DrawerLoading />;
  if (props.error) return <DrawerAlert message={props.error} />;
  if (!props.context) return <p className="entityDrawerEmpty">{t("No knowledge context loaded.")}</p>;
  return (
    <>
      <KnowledgeGroup
        title={t("Entity assertions")}
        icon={<BookOpen size={14} />}
        items={props.context.entity_assertions}
        empty={t("No direct entity assertions.")}
        onOpenFact={props.onOpenFact}
      />
      <KnowledgeGroup
        title={t("Inherited class knowledge")}
        icon={<GitBranch size={14} />}
        items={props.context.inherited_class_assertions}
        empty={t("No inherited class assertions.")}
        onOpenFact={props.onOpenFact}
      />
      <KnowledgeGroup
        title={t("Relation assertions")}
        icon={<ArrowRight size={14} />}
        items={props.context.relation_assertions}
        empty={t("No relation assertions.")}
        onOpenFact={props.onOpenFact}
      />
      <KnowledgeGroup
        title={t("Rule-derived assertions")}
        icon={<FileText size={14} />}
        items={props.context.rule_assertions}
        empty={t("No rule-derived assertions.")}
        onOpenFact={props.onOpenFact}
      />
    </>
  );
}

function RulesTab(props: {
  context: EntityKnowledgeContext | null;
  loading: boolean;
  error: string;
  onOpenFact: (claimId: string) => void;
}) {
  const t = useT();
  if (props.loading) return <DrawerLoading />;
  if (props.error) return <DrawerAlert message={props.error} />;
  if (!props.context) return <p className="entityDrawerEmpty">{t("No rule context loaded.")}</p>;
  if (props.context.rules.length === 0 && props.context.rule_assertions.length === 0) {
    return <p className="entityDrawerEmpty">{t("No rules matched this entity.")}</p>;
  }
  return (
    <>
      {props.context.rules.map((rule) => (
        <RuleCard key={rule.id} rule={rule} />
      ))}
      <KnowledgeGroup
        title={t("Produced assertions")}
        icon={<FileText size={14} />}
        items={props.context.rule_assertions}
        empty={t("No produced assertions.")}
        onOpenFact={props.onOpenFact}
      />
    </>
  );
}

function KnowledgeGroup(props: {
  title: string;
  icon: ReactNode;
  items: EntityKnowledgeItem[];
  empty: string;
  onOpenFact: (claimId: string) => void;
}) {
  return (
    <section className="entityDrawerSection">
      <h3 className="entityKnowledgeHeading">{props.icon}{props.title}</h3>
      {props.items.length === 0 ? (
        <p className="entityDrawerEmpty">{props.empty}</p>
      ) : (
        <div className="entityKnowledgeList">
          {props.items.map((item) => (
            <KnowledgeItem key={item.claim_id ?? `${item.source_type}-${item.predicate}`} item={item} onOpenFact={props.onOpenFact} />
          ))}
        </div>
      )}
    </section>
  );
}

function KnowledgeItem(props: { item: EntityKnowledgeItem; onOpenFact: (claimId: string) => void }) {
  const t = useT();
  const { item } = props;
  return (
    <article className={classNames("entityKnowledgeItem", item.overridden && "overridden")}>
      <header>
        <div>
          <strong>{item.predicate}</strong>
          <span>{item.source_type}{item.layer ? ` · ${item.layer}` : ""}</span>
        </div>
        <div className="entityKnowledgeBadges">
          {item.audit_status && <span>{item.audit_status}</span>}
          {item.inherited_from_class_id && <span>{t("class {id}", { id: compactId(item.inherited_from_class_id) })}</span>}
          {item.relation_id && <span>{t("rel {id}", { id: compactId(item.relation_id) })}</span>}
          {item.rule_id && <span>{t("rule {id}", { id: compactId(item.rule_id) })}</span>}
        </div>
      </header>
      <pre className="jsonBlock entityKnowledgeValue">{prettyJson(item.value)}</pre>
      <footer>
        <span>{item.redacted ? t("Redacted") : t("confidence {pct}%", { pct: Math.round((item.confidence ?? 0) * 100) })}</span>
        {item.claim_id && (
          <button type="button" onClick={() => props.onOpenFact(item.claim_id!)}>
            {t("Open fact")}
          </button>
        )}
      </footer>
    </article>
  );
}

function RuleCard(props: { rule: EntityKnowledgeRule }) {
  const t = useT();
  return (
    <section className="entityDrawerSection">
      <article className="entityRuleCard">
        <header>
          <div>
            <strong>{props.rule.rule_type}</strong>
            <span>{compactId(props.rule.id)} · {props.rule.status} · {t("priority")} {props.rule.priority}</span>
          </div>
          <span>v{props.rule.version}</span>
        </header>
        <div className="entityRuleGrid">
          <div>
            <span>{t("Scope")}</span>
            <pre className="jsonBlock">{prettyJson(props.rule.scope)}</pre>
          </div>
          <div>
            <span>{t("Conclusion")}</span>
            <pre className="jsonBlock">{prettyJson(props.rule.conclusion)}</pre>
          </div>
        </div>
      </article>
    </section>
  );
}

function DrawerLoading() {
  const t = useT();
  return <p className="entityDrawerEmpty">{t("Loading knowledge context...")}</p>;
}

function DrawerAlert(props: { message: string }) {
  return (
    <div className="entityDrawerAlert" role="alert">
      <AlertCircle size={15} />
      <span>{props.message}</span>
    </div>
  );
}

function DrawerRelations(props: {
  entity: Entity;
  relations: Relation[];
  entities: Entity[];
}) {
  const t = useT();
  const { outgoing, incoming } = relationsFor(props.entity, props.relations);

  if (outgoing.length === 0 && incoming.length === 0) {
    return (
      <section className="entityDrawerSection">
        <h3>{t("Relations")}</h3>
        <p className="entityDrawerEmpty">{t("No relations.")}</p>
      </section>
    );
  }

  return (
    <section className="entityDrawerSection">
      <h3>{t("Relations")}</h3>
      <div className="entityDrawerRelations">
        {outgoing.map((relation) => (
          <div className="entityDrawerRelItem" key={`out-${relation.id}`}>
            <span className="entityDrawerRelType">{relation.relation_type}</span>
            <ArrowRight size={12} className="entityDrawerRelArrow" />
            <span className="entityDrawerRelTarget">
              {entityName(props.entities, relation.target_entity_id)}
            </span>
          </div>
        ))}
        {incoming.map((relation) => (
          <div className="entityDrawerRelItem entityDrawerRelItemIncoming" key={`in-${relation.id}`}>
            <span className="entityDrawerRelTarget">
              {entityName(props.entities, relation.source_entity_id)}
            </span>
            <ArrowRight size={12} className="entityDrawerRelArrow" />
            <span className="entityDrawerRelType">{relation.relation_type}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function readDescription(properties: Entity["properties"]): string {
  const value = properties?.description;
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}
