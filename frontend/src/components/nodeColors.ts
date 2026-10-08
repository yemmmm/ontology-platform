const VIEWPOINT_HUES = {
  object: 212,
  behavior: 28,
  rule: 0,
  business_role: 45,
  process: 263,
  data_mapping: 133,
  interface_mapping: 188,
};
export type NodeColorFamily = keyof typeof VIEWPOINT_HUES | "unclassified";

// Strength uses the same bounded connection-degree mapping as node size.
export function connectionColor(family: NodeColorFamily, strength: number): string {
  if (family === "unclassified") return `hsl(220, 0%, ${68 - strength * 24}%)`;
  return `hsl(${VIEWPOINT_HUES[family]}, ${35 + strength * 40}%, 55%)`;
}

export const VIEWPOINT_COLORS = Object.fromEntries(
  Object.keys(VIEWPOINT_HUES).map(role => [role,
    [0, 0.5, 1].map(strength => connectionColor(role as keyof typeof VIEWPOINT_HUES, strength)),
  ]),
) as Record<keyof typeof VIEWPOINT_HUES, string[]>;
export const UNCLASSIFIED_COLORS = [0, 0.5, 1].map(strength => connectionColor("unclassified", strength));

export function assignNodeColorFamilies(
  nodes: { id: string; roles: unknown[] }[],
): Map<string, NodeColorFamily> {
  return new Map(nodes.map(node => {
    const roles = [...new Set(node.roles.filter((role): role is string => typeof role === "string" && role.length > 0))];
    const role = roles.length === 1 ? roles[0] : "";
    const family = Object.prototype.hasOwnProperty.call(VIEWPOINT_HUES, role)
      ? role as keyof typeof VIEWPOINT_HUES : "unclassified";
    return [node.id, family];
  }));
}
