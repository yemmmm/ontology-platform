// A fixed hue per declared viewpoint, with three identity-based shades per hue.
export const VIEWPOINT_COLORS = {
  object: ["#2f6fba", "#4c86c6", "#76a3d5"],
  behavior: ["#c2691d", "#da8138", "#e9a568"],
  rule: ["#be4e4e", "#d36d6d", "#df9696"],
  business_role: ["#9b7c21", "#b5963e", "#cbb16b"],
  process: ["#7450af", "#9071c2", "#ac95d2"],
  data_mapping: ["#37824d", "#559968", "#83b38f"],
  interface_mapping: ["#227b89", "#4096a3", "#75b4bd"],
};
export const UNCLASSIFIED_COLORS = ["#737b88", "#9098a3", "#adb3bd"];

function hashId(id: string): number {
  let hash = 2166136261;
  for (let i = 0; i < id.length; i += 1) hash = Math.imul(hash ^ id.charCodeAt(i), 16777619);
  return hash >>> 0;
}

export function assignNodeColors(
  nodes: { id: string; roles: unknown[] }[],
): Map<string, string> {
  return new Map(nodes.map(node => {
    const roles = [...new Set(node.roles.filter((role): role is string => typeof role === "string" && role.length > 0))];
    const role = roles.length === 1 ? roles[0] : "";
    const palette = Object.prototype.hasOwnProperty.call(VIEWPOINT_COLORS, role)
      ? VIEWPOINT_COLORS[role as keyof typeof VIEWPOINT_COLORS] : UNCLASSIFIED_COLORS;
    return [node.id, palette[hashId(node.id) % palette.length]];
  }));
}
