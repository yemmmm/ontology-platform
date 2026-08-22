#!/usr/bin/env bash
set -euo pipefail

# Recreate only the controlled evaluation schema. This script is deliberately not a product
# migration and contains no password, connector, authorization, or query-rewrite behavior.
readonly target_schema="industrial_service_v3"
readonly fixture_marker="ontology-platform:v3-industrial-service-fixture"
readonly compose_service="postgres"
readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "${script_dir}/.." && pwd)"
readonly schema_sql="${repo_root}/docs/evaluation-scenarios/industrial-service-v3/modeling-input/schema.sql"
readonly sample_sql="${repo_root}/docs/evaluation-scenarios/industrial-service-v3/modeling-input/sample-data.sql"

cd -- "${repo_root}"

if [[ "${target_schema}" != "industrial_service_v3" ]]; then
    printf 'refusing unexpected target schema: %s\n' "${target_schema}" >&2
    exit 1
fi
if [[ ! -f "${schema_sql}" || ! -f "${sample_sql}" ]]; then
    printf 'missing fixture SQL under the expected repository path\n' >&2
    exit 1
fi

mapfile -t compose_services < <(docker compose config --services)
if ! printf '%s\n' "${compose_services[@]}" | grep -Fxq "${compose_service}"; then
    printf 'Compose service %s is not defined\n' "${compose_service}" >&2
    exit 1
fi
if ! docker compose ps --status running --services | grep -Fxq "${compose_service}"; then
    printf 'Compose service %s is not running\n' "${compose_service}" >&2
    exit 1
fi

mapfile -t runtime_config < <(
    docker compose exec -T "${compose_service}" sh -lc 'printf "%s\n%s\n" "$POSTGRES_USER" "$POSTGRES_DB"' | tr -d '\r'
)
if [[ "${#runtime_config[@]}" -ne 2 ]]; then
    printf 'container did not expose exactly POSTGRES_USER and POSTGRES_DB\n' >&2
    exit 1
fi
readonly pg_user="${runtime_config[0]}"
readonly pg_database="${runtime_config[1]}"
if [[ ! "${pg_user}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ || ! "${pg_database}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    printf 'refusing unsafe database identity from the container environment\n' >&2
    exit 1
fi

psql_target() {
    docker compose exec -T "${compose_service}" psql -X -v ON_ERROR_STOP=1 -U "${pg_user}" -d "${pg_database}" "$@"
}

scalar_query() {
    psql_target -Atqc "$1" | tr -d '\r'
}

readonly schema_state_sql="SELECT COALESCE((SELECT CASE WHEN pg_get_userbyid(n.nspowner) = current_user AND obj_description(n.oid, 'pg_namespace') = '${fixture_marker}' THEN 'fixture' ELSE 'refuse' END FROM pg_namespace AS n WHERE n.nspname = '${target_schema}'), 'absent');"
readonly schema_state="$(scalar_query "${schema_state_sql}")"
if [[ "${schema_state}" == "refuse" ]]; then
    printf 'refusing to replace existing schema %s: owner or fixture marker mismatch\n' "${target_schema}" >&2
    exit 1
fi
if [[ "${schema_state}" != "absent" && "${schema_state}" != "fixture" ]]; then
    printf 'unexpected schema state: %s\n' "${schema_state}" >&2
    exit 1
fi

readonly sentinel_sql="SELECT md5(COALESCE(string_agg(entry, E'\\n' ORDER BY entry), '')) FROM (SELECT 'schema|' || n.nspname || '|' || pg_get_userbyid(n.nspowner) AS entry FROM pg_namespace AS n WHERE n.nspname <> '${target_schema}' AND n.nspname <> 'information_schema' AND n.nspname NOT LIKE 'pg_%' UNION ALL SELECT 'relation|' || n.nspname || '|' || c.relname || '|' || c.relkind::text || '|' || pg_get_userbyid(c.relowner) AS entry FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace WHERE n.nspname <> '${target_schema}' AND n.nspname <> 'information_schema' AND n.nspname NOT LIKE 'pg_%') AS entries;"
readonly sentinel_before="$(scalar_query "${sentinel_sql}")"

printf 'target database: %s\n' "${pg_database}"
printf 'target schema: %s\n' "${target_schema}"
printf 'fixture marker: %s\n' "${fixture_marker}"
printf 'existing target state: %s\n' "${schema_state}"
printf 'non-target relation sentinel before: %s\n' "${sentinel_before}"

psql_target --single-transaction -f - < "${schema_sql}"
psql_target --single-transaction -f - < "${sample_sql}"

readonly sentinel_after="$(scalar_query "${sentinel_sql}")"
printf 'non-target relation sentinel after: %s\n' "${sentinel_after}"
if [[ "${sentinel_before}" != "${sentinel_after}" ]]; then
    printf 'non-target relation sentinel changed; refusing successful result\n' >&2
    exit 1
fi

readonly table_count="$(scalar_query "SELECT count(*) FROM information_schema.tables WHERE table_schema = '${target_schema}' AND table_type = 'BASE TABLE';")"
if [[ "${table_count}" != "21" ]]; then
    printf 'expected 21 fixture tables, found %s\n' "${table_count}" >&2
    exit 1
fi
printf 'loaded fixture tables: %s\n' "${table_count}"
