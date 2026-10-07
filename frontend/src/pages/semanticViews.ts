export const semanticViews = [
  ["object", "对象"], ["behavior", "行为"], ["rule", "规则"], ["business_role", "角色"],
  ["process", "流程"], ["data_mapping", "数据映射"], ["interface_mapping", "接口映射"],
] as const;
// The scenario-map contract calls its responsibility viewpoint role.
export const scenarioViews = semanticViews.map(([role,label]) => [role === "business_role" ? "role" : role,label] as const);
