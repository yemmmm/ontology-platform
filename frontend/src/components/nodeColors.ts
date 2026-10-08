// Tableau 10 categorical palette. Colors distinguish nodes, not semantic categories.
const PALETTE = [
  "#4e79a7", "#f28e2c", "#e15759", "#76b7b2", "#59a14f",
  "#edc949", "#af7aa1", "#ff9da7", "#9c755f", "#bab0ab",
];

function hashId(id: string): number {
  let hash = 2166136261;
  for (let i = 0; i < id.length; i += 1) hash = Math.imul(hash ^ id.charCodeAt(i), 16777619);
  return hash >>> 0;
}

export function assignNodeColors(
  nodeIds: string[], edges: { source: string; target: string }[],
): Map<string, string> {
  const neighbors = new Map(nodeIds.map(id => [id, new Set<string>()]));
  for (const edge of edges) {
    if (edge.source === edge.target) continue;
    neighbors.get(edge.source)!.add(edge.target);
    neighbors.get(edge.target)!.add(edge.source);
  }
  const ordered = [...nodeIds].sort((a, b) => neighbors.get(b)!.size - neighbors.get(a)!.size
    || (a < b ? -1 : a > b ? 1 : 0));
  const assigned = new Map<string, number>();
  const usage = PALETTE.map(() => 0);
  for (const id of ordered) {
    const conflicts = PALETTE.map(() => 0);
    for (const neighbor of neighbors.get(id)!) {
      const color = assigned.get(neighbor);
      if (color !== undefined) conflicts[color] += 1;
    }
    const start = hashId(id) % PALETTE.length;
    const candidates = PALETTE.map((_, index) => (start + index) % PALETTE.length);
    candidates.sort((a, b) => conflicts[a] - conflicts[b] || usage[a] - usage[b]);
    assigned.set(id, candidates[0]);
    usage[candidates[0]] += 1;
  }
  return new Map([...assigned].map(([id, index]) => [id, PALETTE[index]]));
}
