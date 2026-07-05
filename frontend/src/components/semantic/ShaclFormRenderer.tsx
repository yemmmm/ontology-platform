import { InfoCircledIcon } from "./radixIcons";
import { useT } from "../../i18n";
import type { SemanticJsonObject } from "../../types";

export type ShaclFieldConstraint = {
  path?: string;
  name?: string;
  label?: string;
  datatype?: string;
  minCount?: number;
  maxCount?: number;
  pattern?: string;
  enumeration?: unknown[];
  description?: string;
  class_iri?: string;
  required?: boolean;
};

export type ShaclFormGuidance = {
  target_class?: string;
  target_class_label?: string;
  shape_iri?: string;
  fields?: ShaclFieldConstraint[];
};

export function parseShaclGuidance(value: SemanticJsonObject | null | undefined): ShaclFormGuidance | null {
  if (!value || typeof value !== "object") return null;
  const guidance = value as ShaclFormGuidance & Record<string, unknown>;
  if (!guidance.fields && !guidance.shape_iri && !guidance.target_class) {
    return null;
  }
  return guidance;
}

export function ShaclFormRenderer({
  guidance,
  values,
  onChange,
  readOnly,
}: {
  guidance: ShaclFormGuidance | null;
  values: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  readOnly?: boolean;
}) {
  const t = useT();

  if (!guidance || !guidance.fields || guidance.fields.length === 0) {
    return (
      <section className="shaclFormRenderer empty" aria-label="shacl-form-empty">
        <div className="emptyState">
          <InfoCircledIcon />
          <span>{t("No SHACL form guidance available")}</span>
        </div>
      </section>
    );
  }

  return (
    <section className="shaclFormRenderer" aria-label="shacl-form-renderer">
      <header>
        {guidance.shape_iri && (
          <span className="shaclShapeIri">
            <code>{guidance.shape_iri}</code>
          </span>
        )}
        {guidance.target_class_label && (
          <span className="shaclTargetLabel">{guidance.target_class_label}</span>
        )}
      </header>
      <div className="stackForm">
        {guidance.fields.map((field, idx) => (
          <ShaclFieldRow
            key={`${field.path ?? idx}-${idx}`}
            field={field}
            onChange={(next) => {
              const updated = { ...values };
              if (next === undefined || next === "") {
                delete updated[field.path ?? field.name ?? `field-${idx}`];
              } else {
                updated[field.path ?? field.name ?? `field-${idx}`] = next;
              }
              onChange(updated);
            }}
            readOnly={readOnly}
            value={values[field.path ?? field.name ?? `field-${idx}`]}
          />
        ))}
      </div>
    </section>
  );
}

function ShaclFieldRow({
  field,
  value,
  onChange,
  readOnly,
}: {
  field: ShaclFieldConstraint;
  value: unknown;
  onChange: (next: unknown) => void;
  readOnly?: boolean;
}) {
  const t = useT();
  const required = field.required || (typeof field.minCount === "number" && field.minCount > 0);
  const multi = typeof field.maxCount === "number" ? field.maxCount > 1 : true;
  const label = field.label ?? field.name ?? field.path;
  const hasEnum = Array.isArray(field.enumeration) && field.enumeration.length > 0;
  const isBoolean = field.datatype === "xsd:boolean" || field.datatype === "boolean";

  return (
    <label className="shaclField">
      <span className="shaclFieldLabel">
        {label}
        {required && <em>· {t("required")}</em>}
        {multi && !hasEnum && !isBoolean && <small>· {t("multi-valued")}</small>}
      </span>
      {field.description && <small className="shaclFieldDescription">{field.description}</small>}
      {hasEnum ? (
        <select
          disabled={readOnly}
          multiple={multi}
          onChange={(event) => {
            if (multi) {
              const selected = Array.from(event.target.selectedOptions).map((option) => option.value);
              onChange(selected);
            } else {
              onChange(event.target.value);
            }
          }}
          value={Array.isArray(value) ? (value as string[]) : value ? [String(value)] : []}
        >
          {(field.enumeration ?? []).map((option) => (
            <option key={String(option)} value={String(option)}>
              {String(option)}
            </option>
          ))}
        </select>
      ) : isBoolean ? (
        <select
          disabled={readOnly}
          onChange={(event) => onChange(event.target.value === "true")}
          value={typeof value === "boolean" ? String(value) : ""}
        >
          <option value="">{t("Unset")}</option>
          <option value="true">{t("True")}</option>
          <option value="false">{t("False")}</option>
        </select>
      ) : (
        <input
          disabled={readOnly}
          onChange={(event) => onChange(event.target.value)}
          pattern={field.pattern}
          placeholder={field.datatype ?? label}
          required={required}
          value={(value as string | number | undefined)?.toString() ?? ""}
        />
      )}
    </label>
  );
}
