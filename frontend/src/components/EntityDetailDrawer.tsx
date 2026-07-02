import { AlertCircle, ArrowRight, BookOpen, FileText, GitBranch, Pencil, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { Entity, EntityKnowledgeContext, EntityKnowledgeItem, EntityKnowledgeRule, Relation } from "../types";
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
        setKnowledgeError(error instanceof Error ? error.message : "Failed to load knowledge context");
      }
    }).finally(() => {
      if (!cancelled) setLoadingKnowledge(false);
    });
    return () => {
      cancelled = true;
    };
  }, [entity?.id, props.request, props.versionId]);

  return (
    <aside
      className={classNames("entityDrawer", open && "open")}
      aria-hidden={!open}
      aria-label="Entity detail"
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
                <Pencil size={14} /> Edit
              </button>
              <button
                aria-label={`Delete ${entity.name}`}
                className="iconButton danger"
                onClick={() => setConfirmingDelete(true)}
                title="Delete entity"
                type="button"
              >
                <Trash2 size={15} />
              </button>
              <button className="iconButton" onClick={onClose} type="button" aria-label="Close detail">
                <X size={16} />
              </button>
            </div>
          </header>

          <nav className="entityDrawerTabs" aria-label="Entity detail sections">
            {[
              ["overview", "Overview"],
              ["knowledge", "Knowledge"],
              ["rules", "Rules"],
              ["raw", "Raw"],
            ].map(([id, label]) => (
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
                <strong>Delete this entity?</strong>
                <span>
                  {relationCount > 0
                    ? `This entity has ${relationCount} connected ${relationCount === 1 ? "relation" : "relations"}. Remove them before deleting the entity.`
                    : "This action cannot be undone."}
                </span>
              </div>
              <div className="entityDeleteConfirmActions">
                <button className="secondaryButton" onClick={() => setConfirmingDelete(false)} type="button">
                  Cancel
                </button>
                <button
                  className="secondaryButton dangerText"
                  disabled={relationCount > 0}
                  onClick={props.onDelete}
                  type="button"
                >
                  <Trash2 size={14} /> Delete entity
                </button>
              </div>
            </div>
          )}

          {activeTab === "overview" && (
            <>
              <section className="entityDrawerSection">
                <h3>Description</h3>
                {descriptionValue ? (
                  <p className="entityDrawerDesc">{descriptionValue}</p>
                ) : (
                  <p className="entityDrawerEmpty">No description.</p>
                )}
              </section>

              <DrawerRelations entity={entity} relations={props.relations} entities={props.entities} />

              <section className="entityDrawerSection">
                <h3>Properties</h3>
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
              <h3>Raw context</h3>
              {loadingKnowledge ? (
                <p className="entityDrawerEmpty">Loading knowledge context...</p>
              ) : knowledgeError ? (
                <DrawerAlert message={knowledgeError} />
              ) : (
                <pre className="jsonBlock entityDrawerProps">{prettyJson(knowledge ?? entity)}</pre>
              )}
            </section>
          )}

          <footer className="entityDrawerFooter">
            <span className="entityDrawerId">ID: {compactId(entity.id)}</span>
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
  if (props.loading) return <DrawerLoading />;
  if (props.error) return <DrawerAlert message={props.error} />;
  if (!props.context) return <p className="entityDrawerEmpty">No knowledge context loaded.</p>;
  return (
    <>
      <KnowledgeGroup
        title="Entity assertions"
        icon={<BookOpen size={14} />}
        items={props.context.entity_assertions}
        empty="No direct entity assertions."
        onOpenFact={props.onOpenFact}
      />
      <KnowledgeGroup
        title="Inherited class knowledge"
        icon={<GitBranch size={14} />}
        items={props.context.inherited_class_assertions}
        empty="No inherited class assertions."
        onOpenFact={props.onOpenFact}
      />
      <KnowledgeGroup
        title="Relation assertions"
        icon={<ArrowRight size={14} />}
        items={props.context.relation_assertions}
        empty="No relation assertions."
        onOpenFact={props.onOpenFact}
      />
      <KnowledgeGroup
        title="Rule-derived assertions"
        icon={<FileText size={14} />}
        items={props.context.rule_assertions}
        empty="No rule-derived assertions."
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
  if (props.loading) return <DrawerLoading />;
  if (props.error) return <DrawerAlert message={props.error} />;
  if (!props.context) return <p className="entityDrawerEmpty">No rule context loaded.</p>;
  if (props.context.rules.length === 0 && props.context.rule_assertions.length === 0) {
    return <p className="entityDrawerEmpty">No rules matched this entity.</p>;
  }
  return (
    <>
      {props.context.rules.map((rule) => (
        <RuleCard key={rule.id} rule={rule} />
      ))}
      <KnowledgeGroup
        title="Produced assertions"
        icon={<FileText size={14} />}
        items={props.context.rule_assertions}
        empty="No produced assertions."
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
          {item.inherited_from_class_id && <span>class {compactId(item.inherited_from_class_id)}</span>}
          {item.relation_id && <span>rel {compactId(item.relation_id)}</span>}
          {item.rule_id && <span>rule {compactId(item.rule_id)}</span>}
        </div>
      </header>
      <pre className="jsonBlock entityKnowledgeValue">{prettyJson(item.value)}</pre>
      <footer>
        <span>{item.redacted ? "Redacted" : `confidence ${Math.round((item.confidence ?? 0) * 100)}%`}</span>
        {item.claim_id && (
          <button type="button" onClick={() => props.onOpenFact(item.claim_id!)}>
            Open fact
          </button>
        )}
      </footer>
    </article>
  );
}

function RuleCard(props: { rule: EntityKnowledgeRule }) {
  return (
    <section className="entityDrawerSection">
      <article className="entityRuleCard">
        <header>
          <div>
            <strong>{props.rule.rule_type}</strong>
            <span>{compactId(props.rule.id)} · {props.rule.status} · priority {props.rule.priority}</span>
          </div>
          <span>v{props.rule.version}</span>
        </header>
        <div className="entityRuleGrid">
          <div>
            <span>Scope</span>
            <pre className="jsonBlock">{prettyJson(props.rule.scope)}</pre>
          </div>
          <div>
            <span>Conclusion</span>
            <pre className="jsonBlock">{prettyJson(props.rule.conclusion)}</pre>
          </div>
        </div>
      </article>
    </section>
  );
}

function DrawerLoading() {
  return <p className="entityDrawerEmpty">Loading knowledge context...</p>;
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
  const { outgoing, incoming } = relationsFor(props.entity, props.relations);

  if (outgoing.length === 0 && incoming.length === 0) {
    return (
      <section className="entityDrawerSection">
        <h3>Relations</h3>
        <p className="entityDrawerEmpty">No relations.</p>
      </section>
    );
  }

  return (
    <section className="entityDrawerSection">
      <h3>Relations</h3>
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
