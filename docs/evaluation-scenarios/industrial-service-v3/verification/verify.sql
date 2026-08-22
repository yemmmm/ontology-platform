\set ON_ERROR_STOP on
SET search_path TO industrial_service_v3, pg_catalog;
SET TIME ZONE 'Asia/Shanghai';

-- One stable JSON document is emitted so an independent tester can compare it with
-- expected-results.json without interpreting psql's table formatting.
WITH
schema_info AS (
    SELECT jsonb_build_object(
        'schema', current_schema(),
        'marker', obj_description('industrial_service_v3'::regnamespace, 'pg_namespace'),
        'table_count', (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'industrial_service_v3' AND table_type = 'BASE TABLE'),
        'table_names', (SELECT jsonb_agg(table_name ORDER BY table_name) FROM information_schema.tables WHERE table_schema = 'industrial_service_v3' AND table_type = 'BASE TABLE'),
        'column_count', (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'industrial_service_v3'),
        'constraint_count', (SELECT count(*) FROM pg_constraint c JOIN pg_class r ON r.oid = c.conrelid JOIN pg_namespace n ON n.oid = r.relnamespace WHERE n.nspname = 'industrial_service_v3'),
        'index_count', (SELECT count(*) FROM pg_indexes WHERE schemaname = 'industrial_service_v3')
    ) AS value
),
row_counts AS (
    SELECT jsonb_object_agg(table_name, row_count ORDER BY table_name) AS value
    FROM (
        SELECT 'assets' AS table_name, count(*) AS row_count FROM assets
        UNION ALL SELECT 'contract_assets', count(*) FROM contract_assets
        UNION ALL SELECT 'customers', count(*) FROM customers
        UNION ALL SELECT 'equipment_models', count(*) FROM equipment_models
        UNION ALL SELECT 'incidents', count(*) FROM incidents
        UNION ALL SELECT 'inventory_movements', count(*) FROM inventory_movements
        UNION ALL SELECT 'part_compatibilities', count(*) FROM part_compatibilities
        UNION ALL SELECT 'part_requests', count(*) FROM part_requests
        UNION ALL SELECT 'part_shipments', count(*) FROM part_shipments
        UNION ALL SELECT 'service_contracts', count(*) FROM service_contracts
        UNION ALL SELECT 'service_regions', count(*) FROM service_regions
        UNION ALL SELECT 'service_sites', count(*) FROM service_sites
        UNION ALL SELECT 'sla_policies', count(*) FROM sla_policies
        UNION ALL SELECT 'sla_targets', count(*) FROM sla_targets
        UNION ALL SELECT 'spare_parts', count(*) FROM spare_parts
        UNION ALL SELECT 'technicians', count(*) FROM technicians
        UNION ALL SELECT 'warehouses', count(*) FROM warehouses
        UNION ALL SELECT 'work_order_assignments', count(*) FROM work_order_assignments
        UNION ALL SELECT 'work_order_delay_events', count(*) FROM work_order_delay_events
        UNION ALL SELECT 'work_order_status_events', count(*) FROM work_order_status_events
        UNION ALL SELECT 'work_orders', count(*) FROM work_orders
    ) counts
),
case_results AS (
    SELECT jsonb_build_object(
        'C01', (SELECT jsonb_build_object(
            'incident_id', i.incident_id,
            'work_order_id', w.work_order_id,
            'asset_id', i.asset_id,
            'response_minutes', floor(extract(epoch FROM (w.responded_at - i.reported_at)) / 60)::integer,
            'resolution_minutes', floor(extract(epoch FROM (w.resolved_at - i.reported_at)) / 60)::integer,
            'target_response_minutes', st.response_minutes,
            'target_resolution_minutes', st.resolution_minutes,
            'resolution_overage_minutes', floor(extract(epoch FROM (w.resolved_at - i.reported_at)) / 60)::integer - st.resolution_minutes,
            'delay_cause', d.cause_code,
            'part_request_id', pr.part_request_id,
            'shipment_id', ps.part_shipment_id
        ) FROM incidents i JOIN work_orders w ON w.incident_id = i.incident_id
          JOIN assets a ON a.asset_id = i.asset_id
          JOIN contract_assets ca ON ca.asset_id = a.asset_id AND ca.coverage_start_date <= i.occurred_at::date AND (ca.coverage_end_date IS NULL OR ca.coverage_end_date >= i.occurred_at::date)
          JOIN service_contracts sc ON sc.contract_id = ca.contract_id AND sc.status = 'ACTIVE' AND sc.start_date <= i.occurred_at::date AND sc.end_date >= i.occurred_at::date
          JOIN sla_targets st ON st.sla_policy_id = sc.sla_policy_id AND st.severity = i.severity
          JOIN work_order_delay_events d ON d.work_order_id = w.work_order_id AND d.cause_code = 'PART_SHORTAGE'
          JOIN part_requests pr ON pr.work_order_id = w.work_order_id
          JOIN part_shipments ps ON ps.part_request_id = pr.part_request_id
         WHERE i.incident_id = 'INC-1001'),
        'C02', (SELECT jsonb_build_object(
            'incident_id', i.incident_id,
            'work_order_id', w.work_order_id,
            'response_minutes', floor(extract(epoch FROM (w.responded_at - i.reported_at)) / 60)::integer,
            'resolution_minutes', floor(extract(epoch FROM (w.resolved_at - i.reported_at)) / 60)::integer,
            'target_response_minutes', st.response_minutes,
            'target_resolution_minutes', st.resolution_minutes,
            'response_overage_minutes', floor(extract(epoch FROM (w.responded_at - i.reported_at)) / 60)::integer - st.response_minutes,
            'resolution_overage_minutes', floor(extract(epoch FROM (w.resolved_at - i.reported_at)) / 60)::integer - st.resolution_minutes,
            'delay_cause', d.cause_code,
            'part_request_count', (SELECT count(*) FROM part_requests pr WHERE pr.work_order_id = w.work_order_id)
        ) FROM incidents i JOIN work_orders w ON w.incident_id = i.incident_id
          JOIN contract_assets ca ON ca.asset_id = i.asset_id AND ca.coverage_start_date <= i.occurred_at::date AND (ca.coverage_end_date IS NULL OR ca.coverage_end_date >= i.occurred_at::date)
          JOIN service_contracts sc ON sc.contract_id = ca.contract_id AND sc.status = 'ACTIVE' AND sc.start_date <= i.occurred_at::date AND sc.end_date >= i.occurred_at::date
          JOIN sla_targets st ON st.sla_policy_id = sc.sla_policy_id AND st.severity = i.severity
          JOIN work_order_delay_events d ON d.work_order_id = w.work_order_id
         WHERE i.incident_id = 'INC-1002'),
        'C03', (SELECT jsonb_build_object(
            'incident_id', i.incident_id,
            'work_order_id', w.work_order_id,
            'response_minutes', floor(extract(epoch FROM (w.responded_at - i.reported_at)) / 60)::integer,
            'resolution_minutes', floor(extract(epoch FROM (w.resolved_at - i.reported_at)) / 60)::integer,
            'target_resolution_minutes', st.resolution_minutes,
            'resolution_within_target', (w.resolved_at - i.reported_at) <= make_interval(mins => st.resolution_minutes),
            'part_request_id', pr.part_request_id,
            'shipment_id', ps.part_shipment_id,
            'shipment_status', ps.status
        ) FROM incidents i JOIN work_orders w ON w.incident_id = i.incident_id
          JOIN contract_assets ca ON ca.asset_id = i.asset_id AND ca.coverage_start_date <= i.occurred_at::date AND (ca.coverage_end_date IS NULL OR ca.coverage_end_date >= i.occurred_at::date)
          JOIN service_contracts sc ON sc.contract_id = ca.contract_id AND sc.status = 'ACTIVE' AND sc.start_date <= i.occurred_at::date AND sc.end_date >= i.occurred_at::date
          JOIN sla_targets st ON st.sla_policy_id = sc.sla_policy_id AND st.severity = i.severity
          JOIN part_requests pr ON pr.work_order_id = w.work_order_id
          JOIN part_shipments ps ON ps.part_request_id = pr.part_request_id
         WHERE i.incident_id = 'INC-1003'),
        'C04', (SELECT jsonb_build_object(
            'incident_id', i.incident_id,
            'work_order_id', w.work_order_id,
            'delay_cause', d.cause_code,
            'resolution_minutes', floor(extract(epoch FROM (w.resolved_at - i.reported_at)) / 60)::integer,
            'target_resolution_minutes', st.resolution_minutes
        ) FROM incidents i JOIN work_orders w ON w.incident_id = i.incident_id
          JOIN contract_assets ca ON ca.asset_id = i.asset_id AND ca.coverage_start_date <= i.occurred_at::date AND (ca.coverage_end_date IS NULL OR ca.coverage_end_date >= i.occurred_at::date)
          JOIN service_contracts sc ON sc.contract_id = ca.contract_id AND sc.status = 'ACTIVE' AND sc.start_date <= i.occurred_at::date AND sc.end_date >= i.occurred_at::date
          JOIN sla_targets st ON st.sla_policy_id = sc.sla_policy_id AND st.severity = i.severity
          JOIN work_order_delay_events d ON d.work_order_id = w.work_order_id
         WHERE i.incident_id = 'INC-1004'),
        'C05', (SELECT jsonb_build_object(
            'incident_id', i.incident_id,
            'work_order_id', w.work_order_id,
            'asset_id', i.asset_id,
            'valid_coverage_count', (SELECT count(*) FROM contract_assets ca JOIN service_contracts sc ON sc.contract_id = ca.contract_id AND sc.status = 'ACTIVE' WHERE ca.asset_id = i.asset_id AND ca.coverage_start_date <= i.occurred_at::date AND (ca.coverage_end_date IS NULL OR ca.coverage_end_date >= i.occurred_at::date) AND sc.start_date <= i.occurred_at::date AND sc.end_date >= i.occurred_at::date),
            'sla_applicable', false,
            'resolution_minutes', floor(extract(epoch FROM (w.resolved_at - i.reported_at)) / 60)::integer
        ) FROM incidents i JOIN work_orders w ON w.incident_id = i.incident_id WHERE i.incident_id = 'INC-1005'),
        'C06', (SELECT jsonb_build_object(
            'asset_id', i1.asset_id,
            'failure_code', i1.failure_code,
            'first_incident_id', i1.incident_id,
            'second_incident_id', i2.incident_id,
            'days_apart', (i2.occurred_at::date - i1.occurred_at::date)
        ) FROM incidents i1 JOIN incidents i2 ON i2.asset_id = i1.asset_id AND i2.failure_code = i1.failure_code AND i2.incident_id > i1.incident_id AND i2.occurred_at::date - i1.occurred_at::date <= 30 WHERE i1.incident_id = 'INC-1006' AND i2.incident_id = 'INC-1007'),
        'C07', (SELECT jsonb_build_object(
            'incident_id', i.incident_id,
            'work_order_id', w.work_order_id,
            'part_request_id', pr.part_request_id,
            'requested_quantity', pr.requested_quantity,
            'shipped_quantity', (SELECT coalesce(sum(ps.shipped_quantity), 0) FROM part_shipments ps WHERE ps.part_request_id = pr.part_request_id),
            'request_status', pr.status,
            'work_order_status', w.status,
            'resolved_at_is_null', (w.resolved_at IS NULL)
        ) FROM incidents i JOIN work_orders w ON w.incident_id = i.incident_id JOIN part_requests pr ON pr.work_order_id = w.work_order_id WHERE i.incident_id = 'INC-1008'),
        'C08', (SELECT jsonb_build_object(
            'incident_id', i.incident_id,
            'work_order_id', w.work_order_id,
            'response_minutes', floor(extract(epoch FROM (w.responded_at - i.reported_at)) / 60)::integer,
            'resolution_minutes', floor(extract(epoch FROM (w.resolved_at - i.reported_at)) / 60)::integer,
            'target_response_minutes', st.response_minutes,
            'target_resolution_minutes', st.resolution_minutes,
            'part_request_count', (SELECT count(*) FROM part_requests pr WHERE pr.work_order_id = w.work_order_id),
            'assignment_count', (SELECT count(*) FROM work_order_assignments a WHERE a.work_order_id = w.work_order_id)
        ) FROM incidents i JOIN work_orders w ON w.incident_id = i.incident_id
          JOIN contract_assets ca ON ca.asset_id = i.asset_id AND ca.coverage_start_date <= i.occurred_at::date AND (ca.coverage_end_date IS NULL OR ca.coverage_end_date >= i.occurred_at::date)
          JOIN service_contracts sc ON sc.contract_id = ca.contract_id AND sc.status = 'ACTIVE' AND sc.start_date <= i.occurred_at::date AND sc.end_date >= i.occurred_at::date
          JOIN sla_targets st ON st.sla_policy_id = sc.sla_policy_id AND st.severity = i.severity
         WHERE i.incident_id = 'INC-1009')
    ) AS value
),
null_empty AS (
    SELECT jsonb_build_object(
        'null_counts', jsonb_build_object(
            'assets_warranty_end_date', (SELECT count(*) FROM assets WHERE warranty_end_date IS NULL),
            'incidents_failure_code', (SELECT count(*) FROM incidents WHERE failure_code IS NULL),
            'incidents_symptom', (SELECT count(*) FROM incidents WHERE symptom IS NULL),
            'work_orders_responded_at', (SELECT count(*) FROM work_orders WHERE responded_at IS NULL),
            'work_orders_resolved_at', (SELECT count(*) FROM work_orders WHERE resolved_at IS NULL),
            'delay_end_at', (SELECT count(*) FROM work_order_delay_events WHERE delay_end_at IS NULL)
        ),
        'work_orders_without_part_requests', (SELECT jsonb_agg(work_order_id ORDER BY work_order_id) FROM work_orders w WHERE NOT EXISTS (SELECT 1 FROM part_requests p WHERE p.work_order_id = w.work_order_id)),
        'empty_work_order_count', (SELECT count(*) FROM work_orders w WHERE NOT EXISTS (SELECT 1 FROM part_requests p WHERE p.work_order_id = w.work_order_id))
    ) AS value
),
fk_orphans AS (
    SELECT jsonb_build_object(
        'orphan_count', (
            SELECT count(*) FROM (
                SELECT c.customer_id FROM customers c LEFT JOIN service_regions r ON r.region_id = c.region_id WHERE r.region_id IS NULL
                UNION ALL SELECT s.site_id FROM service_sites s LEFT JOIN customers c ON c.customer_id = s.customer_id WHERE c.customer_id IS NULL
                UNION ALL SELECT s.site_id FROM service_sites s LEFT JOIN service_regions r ON r.region_id = s.region_id WHERE r.region_id IS NULL
                UNION ALL SELECT a.asset_id FROM assets a LEFT JOIN service_sites s ON s.site_id = a.site_id WHERE s.site_id IS NULL
                UNION ALL SELECT a.asset_id FROM assets a LEFT JOIN equipment_models m ON m.model_id = a.model_id WHERE m.model_id IS NULL
                UNION ALL SELECT t.sla_target_id FROM sla_targets t LEFT JOIN sla_policies p ON p.sla_policy_id = t.sla_policy_id WHERE p.sla_policy_id IS NULL
                UNION ALL SELECT c.contract_id FROM service_contracts c LEFT JOIN customers u ON u.customer_id = c.customer_id WHERE u.customer_id IS NULL
                UNION ALL SELECT c.contract_id FROM service_contracts c LEFT JOIN sla_policies p ON p.sla_policy_id = c.sla_policy_id WHERE p.sla_policy_id IS NULL
                UNION ALL SELECT ca.contract_asset_id FROM contract_assets ca LEFT JOIN service_contracts c ON c.contract_id = ca.contract_id WHERE c.contract_id IS NULL
                UNION ALL SELECT ca.contract_asset_id FROM contract_assets ca LEFT JOIN assets a ON a.asset_id = ca.asset_id WHERE a.asset_id IS NULL
                UNION ALL SELECT i.incident_id FROM incidents i LEFT JOIN assets a ON a.asset_id = i.asset_id WHERE a.asset_id IS NULL
                UNION ALL SELECT w.work_order_id FROM work_orders w LEFT JOIN incidents i ON i.incident_id = w.incident_id WHERE i.incident_id IS NULL
                UNION ALL SELECT e.status_event_id FROM work_order_status_events e LEFT JOIN work_orders w ON w.work_order_id = e.work_order_id WHERE w.work_order_id IS NULL
                UNION ALL SELECT t.technician_id FROM technicians t LEFT JOIN service_regions r ON r.region_id = t.region_id WHERE r.region_id IS NULL
                UNION ALL SELECT a.assignment_id FROM work_order_assignments a LEFT JOIN work_orders w ON w.work_order_id = a.work_order_id WHERE w.work_order_id IS NULL
                UNION ALL SELECT a.assignment_id FROM work_order_assignments a LEFT JOIN technicians t ON t.technician_id = a.technician_id WHERE t.technician_id IS NULL
                UNION ALL SELECT d.delay_event_id FROM work_order_delay_events d LEFT JOIN work_orders w ON w.work_order_id = d.work_order_id WHERE w.work_order_id IS NULL
                UNION ALL SELECT c.compatibility_id FROM part_compatibilities c LEFT JOIN spare_parts p ON p.part_id = c.part_id WHERE p.part_id IS NULL
                UNION ALL SELECT c.compatibility_id FROM part_compatibilities c LEFT JOIN equipment_models m ON m.model_id = c.model_id WHERE m.model_id IS NULL
                UNION ALL SELECT w.warehouse_id FROM warehouses w LEFT JOIN service_regions r ON r.region_id = w.region_id WHERE r.region_id IS NULL
                UNION ALL SELECT m.inventory_movement_id FROM inventory_movements m LEFT JOIN warehouses w ON w.warehouse_id = m.warehouse_id WHERE w.warehouse_id IS NULL
                UNION ALL SELECT m.inventory_movement_id FROM inventory_movements m LEFT JOIN spare_parts p ON p.part_id = m.part_id WHERE p.part_id IS NULL
                UNION ALL SELECT p.part_request_id FROM part_requests p LEFT JOIN work_orders w ON w.work_order_id = p.work_order_id WHERE w.work_order_id IS NULL
                UNION ALL SELECT p.part_request_id FROM part_requests p LEFT JOIN spare_parts s ON s.part_id = p.part_id WHERE s.part_id IS NULL
                UNION ALL SELECT s.part_shipment_id FROM part_shipments s LEFT JOIN part_requests p ON p.part_request_id = s.part_request_id WHERE p.part_request_id IS NULL
                UNION ALL SELECT s.part_shipment_id FROM part_shipments s LEFT JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.warehouse_id IS NULL
            ) orphan_ids
        )
    ) AS value
),
content_digests AS (
    SELECT jsonb_object_agg(table_name, digest ORDER BY table_name) AS value
    FROM (
        SELECT 'assets' AS table_name, md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.asset_id), '')) AS digest FROM assets t
        UNION ALL SELECT 'contract_assets', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.contract_asset_id), '')) FROM contract_assets t
        UNION ALL SELECT 'customers', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.customer_id), '')) FROM customers t
        UNION ALL SELECT 'equipment_models', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.model_id), '')) FROM equipment_models t
        UNION ALL SELECT 'incidents', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.incident_id), '')) FROM incidents t
        UNION ALL SELECT 'inventory_movements', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.inventory_movement_id), '')) FROM inventory_movements t
        UNION ALL SELECT 'part_compatibilities', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.compatibility_id), '')) FROM part_compatibilities t
        UNION ALL SELECT 'part_requests', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.part_request_id), '')) FROM part_requests t
        UNION ALL SELECT 'part_shipments', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.part_shipment_id), '')) FROM part_shipments t
        UNION ALL SELECT 'service_contracts', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.contract_id), '')) FROM service_contracts t
        UNION ALL SELECT 'service_regions', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.region_id), '')) FROM service_regions t
        UNION ALL SELECT 'service_sites', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.site_id), '')) FROM service_sites t
        UNION ALL SELECT 'sla_policies', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.sla_policy_id), '')) FROM sla_policies t
        UNION ALL SELECT 'sla_targets', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.sla_target_id), '')) FROM sla_targets t
        UNION ALL SELECT 'spare_parts', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.part_id), '')) FROM spare_parts t
        UNION ALL SELECT 'technicians', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.technician_id), '')) FROM technicians t
        UNION ALL SELECT 'warehouses', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.warehouse_id), '')) FROM warehouses t
        UNION ALL SELECT 'work_order_assignments', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.assignment_id), '')) FROM work_order_assignments t
        UNION ALL SELECT 'work_order_delay_events', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.delay_event_id), '')) FROM work_order_delay_events t
        UNION ALL SELECT 'work_order_status_events', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.status_event_id), '')) FROM work_order_status_events t
        UNION ALL SELECT 'work_orders', md5(coalesce(string_agg(to_jsonb(t)::text, E'\n' ORDER BY t.work_order_id), '')) FROM work_orders t
    ) digests
)
SELECT jsonb_build_object(
    'schema', (SELECT value FROM schema_info),
    'row_counts', (SELECT value FROM row_counts),
    'cases', (SELECT value FROM case_results),
    'null_empty', (SELECT value FROM null_empty),
    'foreign_key_check', (SELECT value FROM fk_orphans),
    'content_digests', (SELECT value FROM content_digests)
)::text;
