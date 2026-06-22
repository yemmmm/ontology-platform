import { ArrowRight, X } from "lucide-react";
import type { Entity, Relation } from "../types";
import { classNames, compactId, prettyJson } from "../utils";

type EntityDetailDrawerProps = {
  entity: Entity | null;
  relations: Relation[];
  entities: Entity[];
  onClose: () => void;
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
            <button className="iconButton" onClick={onClose} type="button" aria-label="Close detail">
              <X size={16} />
            </button>
          </header>

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

          <footer className="entityDrawerFooter">
            <span className="entityDrawerId">ID: {compactId(entity.id)}</span>
          </footer>
        </div>
      )}
    </aside>
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
