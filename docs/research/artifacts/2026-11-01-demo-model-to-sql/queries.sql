-- Actual governed model: Ontology 755f1e0e-cf5d-47f2-a2a3-95220f4cba96, revision 4.
-- Q3/Q4 require key_enabled_value; the model does not specify this encoding.
-- Q7/Q8/Q9 have no emitted executable SQL; see assessment.json.

-- Q1 [SUPPORTED] 各模型成功新调用次数、历史实际扣额总量和平均扣额是多少？包含暂无调用的模型。
-- Evidence: C_CALL, T_MODELS, T_CALLS, J_CALL_MODELS
SELECT m.id AS model_id, m.name AS model_name,
       COUNT(c.id) AS successful_new_calls,
       COALESCE(SUM(c.charged_units), 0) AS historical_charged_units,
       AVG(c.charged_units) AS average_charged_units
FROM models AS m
LEFT JOIN calls AS c ON c.model_id = m.id
GROUP BY m.id, m.name
ORDER BY m.id;

-- Q2 [SUPPORTED] 每个凭证授权了多少个模型、成功调用多少次、实际扣额多少、当前余额多少？包含零调用凭证。
-- Evidence: C_KEY, C_CALL, T_KEYS, T_GRANTS, T_CALLS, J_GRANTS, J_KEY_CALLS
WITH grant_totals AS (
    SELECT key_id, COUNT(*) AS authorized_models
    FROM model_grants
    GROUP BY key_id
), call_totals AS (
    SELECT key_id, COUNT(*) AS successful_new_calls,
           SUM(charged_units) AS historical_charged_units
    FROM calls
    GROUP BY key_id
)
SELECT k.id AS key_id, k.name AS key_name,
       COALESCE(g.authorized_models, 0) AS authorized_models,
       COALESCE(c.successful_new_calls, 0) AS successful_new_calls,
       COALESCE(c.historical_charged_units, 0) AS historical_charged_units,
       k.remaining_quota
FROM api_keys AS k
LEFT JOIN grant_totals AS g ON g.key_id = k.id
LEFT JOIN call_totals AS c ON c.key_id = k.id
ORDER BY k.id;

-- Q3 [CONDITIONAL] 按凭证状态、授权、模型状态和额度条件，哪些凭证—模型组合满足一次新调用的准入条件？
-- Evidence: C_MODEL, C_KEY, C_CALL, T_MODELS, T_KEYS, T_GRANTS, J_GRANTS
SELECT k.id AS key_id, k.name AS key_name,
       m.id AS model_id, m.name AS model_name,
       k.remaining_quota, m.quota_cost,
       k.remaining_quota - m.quota_cost AS quota_after_one_new_call
FROM api_keys AS k
JOIN model_grants AS g ON g.key_id = k.id
JOIN models AS m ON m.id = g.model_id
WHERE k.enabled = :key_enabled_value
  AND m.enabled = 1
  AND k.remaining_quota >= m.quota_cost
ORDER BY k.id, m.id;

-- Q4 [CONDITIONAL] 哪些启用凭证还有正余额，却不足以调用其已授权且启用的模型？
-- Evidence: C_MODEL, C_KEY, C_CALL, T_MODELS, T_KEYS, T_GRANTS, J_GRANTS
SELECT k.id AS key_id, k.name AS key_name,
       m.id AS model_id, m.name AS model_name,
       k.remaining_quota, m.quota_cost,
       m.quota_cost - k.remaining_quota AS missing_units
FROM api_keys AS k
JOIN model_grants AS g ON g.key_id = k.id
JOIN models AS m ON m.id = g.model_id
WHERE k.enabled = :key_enabled_value
  AND m.enabled = 1
  AND k.remaining_quota > 0
  AND k.remaining_quota < m.quota_cost
ORDER BY k.id, m.id;

-- Q5 [SUPPORTED] 哪些模型存在历史实际扣额与当前扣额配置不同的成功调用？有多少次、实际扣额合计多少？
-- Evidence: C_MODEL, C_CALL, T_MODELS, T_CALLS, J_CALL_MODELS
SELECT m.id AS model_id, m.name AS model_name,
       m.quota_cost AS current_quota_cost,
       COUNT(c.id) AS calls_with_different_historical_charge,
       SUM(c.charged_units) AS historical_charged_units
FROM models AS m
JOIN calls AS c ON c.model_id = m.id
WHERE c.charged_units <> m.quota_cost
GROUP BY m.id, m.name, m.quota_cost
ORDER BY m.id;

-- Q6 [SUPPORTED] 哪些请求标识曾被两个或更多不同凭证成功使用？
-- Evidence: C_CALL, T_CALLS
SELECT request_id, COUNT(DISTINCT key_id) AS credential_count,
       COUNT(*) AS successful_records
FROM calls
GROUP BY request_id
HAVING COUNT(DISTINCT key_id) >= 2
ORDER BY request_id;

