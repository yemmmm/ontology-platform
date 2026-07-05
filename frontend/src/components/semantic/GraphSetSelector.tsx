import { useMemo } from "react";
import { Layers } from "lucide-react";
import type { SemanticGraphSetRead } from "../../types";
import { useT } from "../../i18n";

export function GraphSetSelector({
  graphSets,
  value,
  onChange,
  disabled,
}: {
  graphSets: SemanticGraphSetRead[];
  value: string | null;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const t = useT();
  const ordered = useMemo(() => {
    return [...graphSets].sort((a, b) => b.name.localeCompare(a.name)).reverse();
  }, [graphSets]);

  return (
    <label className="graphSetSelector" aria-label="graph-set-selector">
      <Layers size={14} />
      <span>{t("Graph set")}</span>
      <select
        disabled={disabled || !ordered.length}
        onChange={(event) => onChange(event.target.value)}
        value={value ?? ""}
      >
        {!ordered.length && <option value="">{t("No graph sets")}</option>}
        {ordered.map((graphSet) => (
          <option key={graphSet.id} value={graphSet.id}>
            {graphSet.name} · {graphSet.scope_type}
          </option>
        ))}
      </select>
    </label>
  );
}
