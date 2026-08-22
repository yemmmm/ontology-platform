-- Deterministic representative rows for industrial-service-v3.
-- Business answers and case labels intentionally live outside this file.
SET search_path TO industrial_service_v3, pg_catalog;

INSERT INTO service_regions (region_id, region_code, region_name, timezone, active) VALUES
    ('REG-E', 'EAST', 'East Service Region', 'Asia/Shanghai', true),
    ('REG-W', 'WEST', 'West Service Region', 'Asia/Shanghai', true),
    ('REG-N', 'NORTH', 'North Service Region', 'Asia/Shanghai', true);

INSERT INTO customers (customer_id, customer_code, customer_name, region_id, status, created_at) VALUES
    ('CUS-001', 'CUST-E-001', 'Haiyue Precision', 'REG-E', 'ACTIVE', '2023-01-15 09:00:00+08'),
    ('CUS-002', 'CUST-W-001', 'Lanxin Manufacturing', 'REG-W', 'ACTIVE', '2023-03-20 09:00:00+08'),
    ('CUS-003', 'CUST-N-001', 'Beichen Energy', 'REG-N', 'ACTIVE', '2023-06-10 09:00:00+08');

INSERT INTO service_sites (site_id, customer_id, region_id, site_code, site_name, city, timezone, active) VALUES
    ('SITE-001', 'CUS-001', 'REG-E', 'SITE-E-001', 'Haiyue Shanghai Plant', 'Shanghai', 'Asia/Shanghai', true),
    ('SITE-002', 'CUS-001', 'REG-E', 'SITE-E-002', 'Haiyue Suzhou Plant', 'Suzhou', 'Asia/Shanghai', true),
    ('SITE-003', 'CUS-002', 'REG-W', 'SITE-W-001', 'Lanxin Chengdu Plant', 'Chengdu', 'Asia/Shanghai', true),
    ('SITE-004', 'CUS-002', 'REG-W', 'SITE-W-002', 'Lanxin Chongqing Plant', 'Chongqing', 'Asia/Shanghai', true),
    ('SITE-005', 'CUS-003', 'REG-N', 'SITE-N-001', 'Beichen Beijing Station', 'Beijing', 'Asia/Shanghai', true);

INSERT INTO equipment_models (model_id, model_code, model_name, manufacturer, support_tier, active) VALUES
    ('MOD-AX100', 'AX100', 'AX100 Process Pump', 'Aster Industrial', 'STANDARD', true),
    ('MOD-AX200', 'AX200', 'AX200 Process Pump', 'Aster Industrial', 'PREMIUM', true),
    ('MOD-BX300', 'BX300', 'BX300 Compressor', 'Boreal Systems', 'STANDARD', true),
    ('MOD-CX500', 'CX500', 'CX500 Controller', 'Cobalt Works', 'PREMIUM', true);

INSERT INTO assets (asset_id, asset_tag, site_id, model_id, serial_number, installed_at, warranty_end_date, status) VALUES
    ('AST-001', 'ASSET-E-001', 'SITE-001', 'MOD-AX100', 'AX100-0001', '2022-01-10', '2025-12-31', 'ACTIVE'),
    ('AST-002', 'ASSET-E-002', 'SITE-001', 'MOD-AX200', 'AX200-0002', '2022-02-14', '2026-12-31', 'ACTIVE'),
    ('AST-003', 'ASSET-E-003', 'SITE-002', 'MOD-BX300', 'BX300-0003', '2022-04-18', '2026-12-31', 'ACTIVE'),
    ('AST-004', 'ASSET-E-004', 'SITE-002', 'MOD-CX500', 'CX500-0004', '2022-05-22', '2026-12-31', 'ACTIVE'),
    ('AST-005', 'ASSET-W-001', 'SITE-003', 'MOD-AX100', 'AX100-0005', '2021-08-11', '2024-12-31', 'ACTIVE'),
    ('AST-006', 'ASSET-W-002', 'SITE-003', 'MOD-AX200', 'AX200-0006', '2021-09-30', '2025-12-31', 'ACTIVE'),
    ('AST-007', 'ASSET-W-003', 'SITE-004', 'MOD-BX300', 'BX300-0007', '2022-07-01', '2026-12-31', 'ACTIVE'),
    ('AST-008', 'ASSET-W-004', 'SITE-004', 'MOD-CX500', 'CX500-0008', '2022-07-15', '2026-12-31', 'ACTIVE'),
    ('AST-009', 'ASSET-N-001', 'SITE-005', 'MOD-AX100', 'AX100-0009', '2020-11-03', '2023-11-03', 'ACTIVE'),
    ('AST-010', 'ASSET-N-002', 'SITE-005', 'MOD-AX200', 'AX200-0010', '2021-12-12', NULL, 'ACTIVE');

INSERT INTO sla_policies (sla_policy_id, policy_code, policy_name, description, active) VALUES
    ('SLA-PREM', 'PREMIUM-24X7', 'Premium 24x7 Response', 'Short response and resolution targets for critical assets', true),
    ('SLA-STD', 'STANDARD-BUSINESS', 'Standard Business Support', 'Business-hours support targets', true);

INSERT INTO sla_targets (sla_target_id, sla_policy_id, severity, response_minutes, resolution_minutes) VALUES
    ('TARGET-PREM-P1', 'SLA-PREM', 'P1', 30, 240),
    ('TARGET-PREM-P2', 'SLA-PREM', 'P2', 120, 960),
    ('TARGET-PREM-P3', 'SLA-PREM', 'P3', 240, 1920),
    ('TARGET-PREM-P4', 'SLA-PREM', 'P4', 480, 2880),
    ('TARGET-STD-P1', 'SLA-STD', 'P1', 60, 480),
    ('TARGET-STD-P2', 'SLA-STD', 'P2', 240, 1440),
    ('TARGET-STD-P3', 'SLA-STD', 'P3', 480, 2880),
    ('TARGET-STD-P4', 'SLA-STD', 'P4', 720, 4320);

INSERT INTO service_contracts (contract_id, contract_number, customer_id, sla_policy_id, start_date, end_date, status) VALUES
    ('CTR-001', 'CONTRACT-E-001', 'CUS-001', 'SLA-PREM', '2025-01-01', '2026-12-31', 'ACTIVE'),
    ('CTR-002', 'CONTRACT-W-001', 'CUS-002', 'SLA-STD', '2025-01-01', '2026-12-31', 'ACTIVE'),
    ('CTR-003', 'CONTRACT-N-001', 'CUS-003', 'SLA-STD', '2024-01-01', '2025-12-31', 'EXPIRED'),
    ('CTR-004', 'CONTRACT-N-002', 'CUS-003', 'SLA-PREM', '2026-01-01', '2026-06-30', 'SUSPENDED');

INSERT INTO contract_assets (contract_asset_id, contract_id, asset_id, coverage_start_date, coverage_end_date, coverage_status) VALUES
    ('COV-001', 'CTR-001', 'AST-001', '2025-01-01', NULL, 'COVERED'),
    ('COV-002', 'CTR-001', 'AST-002', '2025-01-01', NULL, 'COVERED'),
    ('COV-003', 'CTR-001', 'AST-003', '2025-01-01', NULL, 'COVERED'),
    ('COV-004', 'CTR-001', 'AST-004', '2025-01-01', NULL, 'COVERED'),
    ('COV-005', 'CTR-002', 'AST-005', '2025-01-01', NULL, 'COVERED'),
    ('COV-006', 'CTR-002', 'AST-006', '2025-01-01', NULL, 'COVERED'),
    ('COV-007', 'CTR-002', 'AST-007', '2025-01-01', NULL, 'COVERED'),
    ('COV-008', 'CTR-002', 'AST-008', '2025-01-01', NULL, 'COVERED'),
    ('COV-009', 'CTR-003', 'AST-009', '2024-01-01', '2025-12-31', 'EXPIRED'),
    ('COV-010', 'CTR-004', 'AST-010', '2026-01-01', '2026-06-30', 'EXPIRED');

INSERT INTO incidents (incident_id, incident_number, asset_id, reported_at, occurred_at, severity, failure_code, symptom, status, closed_at) VALUES
    ('INC-1001', 'INCIDENT-1001', 'AST-001', '2026-02-10 08:00:00+08', '2026-02-10 07:50:00+08', 'P1', 'F-SEAL', 'Pressure loss at pump seal', 'RESOLVED', '2026-02-10 18:00:00+08'),
    ('INC-1002', 'INCIDENT-1002', 'AST-002', '2026-02-12 09:00:00+08', '2026-02-12 08:50:00+08', 'P1', 'F-POWER', 'Pump controller will not start', 'RESOLVED', '2026-02-12 18:00:00+08'),
    ('INC-1003', 'INCIDENT-1003', 'AST-003', '2026-02-13 09:00:00+08', '2026-02-13 08:45:00+08', 'P2', 'F-BEARING', 'Vibration above normal', 'RESOLVED', '2026-02-13 16:00:00+08'),
    ('INC-1004', 'INCIDENT-1004', 'AST-004', '2026-02-14 09:00:00+08', '2026-02-14 08:50:00+08', 'P2', 'F-SENSOR', 'Intermittent sensor alert', 'RESOLVED', '2026-02-15 00:00:00+08'),
    ('INC-1005', 'INCIDENT-1005', 'AST-009', '2026-02-15 08:00:00+08', '2026-02-15 07:45:00+08', 'P1', 'F-SEAL', 'Fluid leak at old unit', 'RESOLVED', '2026-02-15 10:30:00+08'),
    ('INC-1006', 'INCIDENT-1006', 'AST-006', '2026-02-16 09:05:00+08', '2026-02-16 09:00:00+08', 'P3', 'F-OVERHEAT', 'Motor temperature high', 'RESOLVED', '2026-02-16 13:00:00+08'),
    ('INC-1007', 'INCIDENT-1007', 'AST-006', '2026-03-01 10:15:00+08', '2026-03-01 10:00:00+08', 'P3', 'F-OVERHEAT', 'Motor temperature high again', 'RESOLVED', '2026-03-01 14:00:00+08'),
    ('INC-1008', 'INCIDENT-1008', 'AST-007', '2026-02-17 09:00:00+08', '2026-02-17 08:45:00+08', 'P1', 'F-CONTROL', 'Controller replacement required', 'IN_PROGRESS', NULL),
    ('INC-1009', 'INCIDENT-1009', 'AST-008', '2026-02-18 09:00:00+08', '2026-02-18 08:45:00+08', 'P2', 'F-FIRMWARE', 'Firmware alarm', 'RESOLVED', '2026-02-18 13:00:00+08'),
    ('INC-1010', 'INCIDENT-1010', 'AST-010', '2026-07-01 08:10:00+08', '2026-07-01 08:00:00+08', 'P2', NULL, NULL, 'OPEN', NULL),
    ('INC-1011', 'INCIDENT-1011', 'AST-005', '2026-03-05 08:20:00+08', '2026-03-05 08:00:00+08', 'P3', 'F-FLOW', 'Reduced flow', 'RESOLVED', '2026-03-05 13:00:00+08'),
    ('INC-1012', 'INCIDENT-1012', 'AST-003', '2026-03-10 08:10:00+08', '2026-03-10 08:00:00+08', 'P2', 'F-VALVE', 'Valve response slow', 'RESOLVED', '2026-03-10 13:00:00+08');

INSERT INTO work_orders (work_order_id, work_order_number, incident_id, opened_at, responded_at, onsite_at, restored_at, resolved_at, status, resolution_code, created_by) VALUES
    ('WO-1001', 'WO-1001', 'INC-1001', '2026-02-10 08:00:00+08', '2026-02-10 08:20:00+08', '2026-02-10 09:00:00+08', '2026-02-10 16:00:00+08', '2026-02-10 18:00:00+08', 'RESOLVED', 'PART_REPLACED', 'dispatcher-east'),
    ('WO-1002', 'WO-1002', 'INC-1002', '2026-02-12 09:00:00+08', '2026-02-12 12:00:00+08', '2026-02-12 12:30:00+08', '2026-02-12 17:30:00+08', '2026-02-12 18:00:00+08', 'RESOLVED', 'RESET_CONTROLLER', 'dispatcher-east'),
    ('WO-1003', 'WO-1003', 'INC-1003', '2026-02-13 09:00:00+08', '2026-02-13 09:30:00+08', '2026-02-13 10:00:00+08', '2026-02-13 15:00:00+08', '2026-02-13 16:00:00+08', 'RESOLVED', 'BEARING_REPLACED', 'dispatcher-east'),
    ('WO-1004', 'WO-1004', 'INC-1004', '2026-02-14 09:00:00+08', '2026-02-14 10:00:00+08', '2026-02-14 11:00:00+08', '2026-02-14 20:00:00+08', '2026-02-15 00:00:00+08', 'RESOLVED', 'SENSOR_REPLACED', 'dispatcher-east'),
    ('WO-1005', 'WO-1005', 'INC-1005', '2026-02-15 08:00:00+08', '2026-02-15 08:30:00+08', '2026-02-15 09:00:00+08', '2026-02-15 10:00:00+08', '2026-02-15 10:30:00+08', 'RESOLVED', 'SEAL_REPLACED', 'dispatcher-north'),
    ('WO-1006', 'WO-1006', 'INC-1006', '2026-02-16 09:05:00+08', '2026-02-16 09:20:00+08', '2026-02-16 10:00:00+08', '2026-02-16 12:00:00+08', '2026-02-16 13:00:00+08', 'RESOLVED', 'COOLED_AND_TESTED', 'dispatcher-west'),
    ('WO-1007', 'WO-1007', 'INC-1007', '2026-03-01 10:15:00+08', '2026-03-01 10:30:00+08', '2026-03-01 11:00:00+08', '2026-03-01 13:00:00+08', '2026-03-01 14:00:00+08', 'RESOLVED', 'COOLED_AND_TESTED', 'dispatcher-west'),
    ('WO-1008', 'WO-1008', 'INC-1008', '2026-02-17 09:00:00+08', '2026-02-17 09:20:00+08', '2026-02-17 10:00:00+08', NULL, NULL, 'WAITING_PARTS', NULL, 'dispatcher-west'),
    ('WO-1009', 'WO-1009', 'INC-1009', '2026-02-18 09:00:00+08', '2026-02-18 09:30:00+08', '2026-02-18 10:00:00+08', '2026-02-18 12:00:00+08', '2026-02-18 13:00:00+08', 'RESOLVED', 'FIRMWARE_UPDATED', 'dispatcher-west'),
    ('WO-1010', 'WO-1010', 'INC-1010', '2026-07-01 08:10:00+08', NULL, NULL, NULL, NULL, 'OPEN', NULL, 'dispatcher-north'),
    ('WO-1011', 'WO-1011', 'INC-1011', '2026-03-05 08:20:00+08', '2026-03-05 09:00:00+08', '2026-03-05 10:00:00+08', '2026-03-05 12:00:00+08', '2026-03-05 13:00:00+08', 'RESOLVED', 'FLOW_ADJUSTED', 'dispatcher-west'),
    ('WO-1012', 'WO-1012', 'INC-1012', '2026-03-10 08:10:00+08', '2026-03-10 08:30:00+08', '2026-03-10 09:00:00+08', '2026-03-10 12:00:00+08', '2026-03-10 13:00:00+08', 'RESOLVED', 'VALVE_REPLACED', 'dispatcher-east');

INSERT INTO work_order_status_events (status_event_id, work_order_id, event_at, status, note) VALUES
    ('EVT-1001-1', 'WO-1001', '2026-02-10 08:00:00+08', 'OPEN', 'Incident accepted'),
    ('EVT-1001-2', 'WO-1001', '2026-02-10 08:20:00+08', 'ASSIGNED', 'Engineer accepted'),
    ('EVT-1001-3', 'WO-1001', '2026-02-10 09:00:00+08', 'IN_PROGRESS', 'On site'),
    ('EVT-1001-4', 'WO-1001', '2026-02-10 18:00:00+08', 'RESOLVED', 'Repair verified'),
    ('EVT-1002-1', 'WO-1002', '2026-02-12 09:00:00+08', 'OPEN', 'Incident accepted'),
    ('EVT-1002-2', 'WO-1002', '2026-02-12 12:00:00+08', 'ASSIGNED', 'Dispatch queue'),
    ('EVT-1002-3', 'WO-1002', '2026-02-12 18:00:00+08', 'RESOLVED', 'Repair verified'),
    ('EVT-1003-1', 'WO-1003', '2026-02-13 09:00:00+08', 'OPEN', 'Incident accepted'),
    ('EVT-1003-2', 'WO-1003', '2026-02-13 09:30:00+08', 'ASSIGNED', 'Engineer accepted'),
    ('EVT-1003-3', 'WO-1003', '2026-02-13 16:00:00+08', 'RESOLVED', 'Repair verified'),
    ('EVT-1004-1', 'WO-1004', '2026-02-14 09:00:00+08', 'OPEN', 'Incident accepted'),
    ('EVT-1004-2', 'WO-1004', '2026-02-14 10:00:00+08', 'ASSIGNED', 'Engineer accepted'),
    ('EVT-1004-3', 'WO-1004', '2026-02-15 00:00:00+08', 'RESOLVED', 'Repair verified'),
    ('EVT-1005-1', 'WO-1005', '2026-02-15 08:00:00+08', 'OPEN', 'Incident accepted'),
    ('EVT-1005-2', 'WO-1005', '2026-02-15 08:30:00+08', 'ASSIGNED', 'Engineer accepted'),
    ('EVT-1005-3', 'WO-1005', '2026-02-15 10:30:00+08', 'RESOLVED', 'Repair verified'),
    ('EVT-1006-1', 'WO-1006', '2026-02-16 09:05:00+08', 'OPEN', 'Incident accepted'),
    ('EVT-1006-2', 'WO-1006', '2026-02-16 09:20:00+08', 'ASSIGNED', 'Engineer accepted'),
    ('EVT-1006-3', 'WO-1006', '2026-02-16 13:00:00+08', 'RESOLVED', 'Repair verified'),
    ('EVT-1007-1', 'WO-1007', '2026-03-01 10:15:00+08', 'OPEN', 'Incident accepted'),
    ('EVT-1007-2', 'WO-1007', '2026-03-01 10:30:00+08', 'ASSIGNED', 'Engineer accepted'),
    ('EVT-1007-3', 'WO-1007', '2026-03-01 14:00:00+08', 'RESOLVED', 'Repair verified'),
    ('EVT-1008-1', 'WO-1008', '2026-02-17 09:00:00+08', 'OPEN', 'Incident accepted'),
    ('EVT-1008-2', 'WO-1008', '2026-02-17 09:20:00+08', 'ASSIGNED', 'Engineer accepted'),
    ('EVT-1008-3', 'WO-1008', '2026-02-17 10:30:00+08', 'WAITING_PARTS', 'Awaiting controller'),
    ('EVT-1009-1', 'WO-1009', '2026-02-18 09:00:00+08', 'OPEN', 'Incident accepted'),
    ('EVT-1009-2', 'WO-1009', '2026-02-18 09:30:00+08', 'ASSIGNED', 'Engineer accepted'),
    ('EVT-1009-3', 'WO-1009', '2026-02-18 13:00:00+08', 'RESOLVED', 'Repair verified'),
    ('EVT-1010-1', 'WO-1010', '2026-07-01 08:10:00+08', 'OPEN', 'Awaiting contract review'),
    ('EVT-1011-1', 'WO-1011', '2026-03-05 08:20:00+08', 'OPEN', 'Incident accepted'),
    ('EVT-1011-2', 'WO-1011', '2026-03-05 09:00:00+08', 'ASSIGNED', 'Engineer accepted'),
    ('EVT-1011-3', 'WO-1011', '2026-03-05 13:00:00+08', 'RESOLVED', 'Repair verified'),
    ('EVT-1012-1', 'WO-1012', '2026-03-10 08:10:00+08', 'OPEN', 'Incident accepted'),
    ('EVT-1012-2', 'WO-1012', '2026-03-10 08:30:00+08', 'ASSIGNED', 'Engineer accepted'),
    ('EVT-1012-3', 'WO-1012', '2026-03-10 13:00:00+08', 'RESOLVED', 'Repair verified');

INSERT INTO technicians (technician_id, technician_code, technician_name, region_id, skill_level, active) VALUES
    ('TECH-001', 'TECH-E-001', 'Lin Wei', 'REG-E', 'SENIOR', true),
    ('TECH-002', 'TECH-E-002', 'Qiao Min', 'REG-E', 'SPECIALIST', true),
    ('TECH-003', 'TECH-W-001', 'Zhou Han', 'REG-W', 'SENIOR', true),
    ('TECH-004', 'TECH-W-002', 'Du Rong', 'REG-W', 'JUNIOR', true),
    ('TECH-005', 'TECH-N-001', 'Gao Lu', 'REG-N', 'SENIOR', true);

INSERT INTO work_order_assignments (assignment_id, work_order_id, technician_id, assigned_at, unassigned_at, assignment_role) VALUES
    ('ASN-1001', 'WO-1001', 'TECH-001', '2026-02-10 08:20:00+08', NULL, 'PRIMARY'),
    ('ASN-1002', 'WO-1002', 'TECH-002', '2026-02-12 12:00:00+08', NULL, 'PRIMARY'),
    ('ASN-1003', 'WO-1003', 'TECH-001', '2026-02-13 09:30:00+08', NULL, 'PRIMARY'),
    ('ASN-1004', 'WO-1004', 'TECH-002', '2026-02-14 10:00:00+08', NULL, 'PRIMARY'),
    ('ASN-1005', 'WO-1005', 'TECH-005', '2026-02-15 08:30:00+08', NULL, 'PRIMARY'),
    ('ASN-1006', 'WO-1006', 'TECH-003', '2026-02-16 09:20:00+08', NULL, 'PRIMARY'),
    ('ASN-1007', 'WO-1007', 'TECH-003', '2026-03-01 10:30:00+08', NULL, 'PRIMARY'),
    ('ASN-1008', 'WO-1008', 'TECH-004', '2026-02-17 09:20:00+08', NULL, 'PRIMARY'),
    ('ASN-1009', 'WO-1009', 'TECH-004', '2026-02-18 09:30:00+08', NULL, 'PRIMARY'),
    ('ASN-1011', 'WO-1011', 'TECH-003', '2026-03-05 09:00:00+08', NULL, 'PRIMARY'),
    ('ASN-1012', 'WO-1012', 'TECH-001', '2026-03-10 08:30:00+08', NULL, 'PRIMARY');

INSERT INTO work_order_delay_events (delay_event_id, work_order_id, delay_start_at, delay_end_at, cause_code, note) VALUES
    ('DELAY-1001', 'WO-1001', '2026-02-10 09:00:00+08', '2026-02-10 15:00:00+08', 'PART_SHORTAGE', 'Seal kit unavailable at first request'),
    ('DELAY-1002', 'WO-1002', '2026-02-12 09:30:00+08', '2026-02-12 12:00:00+08', 'DISPATCH_CAPACITY', 'No technician available in dispatch queue'),
    ('DELAY-1004', 'WO-1004', '2026-02-14 11:00:00+08', '2026-02-14 13:00:00+08', 'UNKNOWN', 'Cause not confirmed'),
    ('DELAY-1008', 'WO-1008', '2026-02-17 10:30:00+08', NULL, 'PART_SHORTAGE', 'Controller shipment incomplete'),
    ('DELAY-1010', 'WO-1010', '2026-07-01 08:10:00+08', '2026-07-01 12:00:00+08', 'CUSTOMER_ACCESS', 'Site access not confirmed'),
    ('DELAY-1011', 'WO-1011', '2026-03-05 09:30:00+08', '2026-03-05 10:00:00+08', 'CUSTOMER_ACCESS', 'Safety induction at site');

INSERT INTO spare_parts (part_id, part_number, part_name, standard_cost, currency, active) VALUES
    ('PART-001', 'SP-SEAL-AX', 'AX pump seal kit', 120.00, 'CNY', true),
    ('PART-002', 'SP-BEAR-BX', 'BX compressor bearing', 680.00, 'CNY', true),
    ('PART-003', 'SP-CTRL-BX', 'BX controller', 1450.00, 'CNY', true),
    ('PART-004', 'SP-SENSOR-CX', 'CX sensor module', 320.00, 'CNY', true),
    ('PART-005', 'SP-FILTER-AX', 'AX filter element', 85.00, 'CNY', true),
    ('PART-006', 'SP-VALVE-BX', 'BX valve assembly', 510.00, 'CNY', true);

INSERT INTO part_compatibilities (compatibility_id, part_id, model_id, compatibility_type) VALUES
    ('COMP-001', 'PART-001', 'MOD-AX100', 'REQUIRED'),
    ('COMP-002', 'PART-001', 'MOD-AX200', 'OPTIONAL'),
    ('COMP-003', 'PART-002', 'MOD-BX300', 'REQUIRED'),
    ('COMP-004', 'PART-003', 'MOD-BX300', 'REQUIRED'),
    ('COMP-005', 'PART-004', 'MOD-CX500', 'REQUIRED'),
    ('COMP-006', 'PART-005', 'MOD-AX100', 'OPTIONAL'),
    ('COMP-007', 'PART-005', 'MOD-AX200', 'OPTIONAL'),
    ('COMP-008', 'PART-006', 'MOD-BX300', 'OPTIONAL');

INSERT INTO warehouses (warehouse_id, warehouse_code, region_id, warehouse_name, active) VALUES
    ('WH-E-01', 'WH-EAST-01', 'REG-E', 'East Central Warehouse', true),
    ('WH-W-01', 'WH-WEST-01', 'REG-W', 'West Central Warehouse', true),
    ('WH-N-01', 'WH-NORTH-01', 'REG-N', 'North Central Warehouse', true);

INSERT INTO inventory_movements (inventory_movement_id, warehouse_id, part_id, movement_at, movement_type, quantity, reference_type, reference_id, note) VALUES
    ('MOV-001', 'WH-E-01', 'PART-001', '2026-01-20 09:00:00+08', 'RECEIPT', 10, 'PURCHASE', 'PO-001', 'Opening receipt'),
    ('MOV-002', 'WH-E-01', 'PART-001', '2026-02-10 09:10:00+08', 'RESERVATION', 8, 'PART_REQUEST', 'REQ-1001', 'Reserved for active requests'),
    ('MOV-003', 'WH-E-01', 'PART-001', '2026-02-10 15:30:00+08', 'SHIPMENT', 2, 'PART_SHIPMENT', 'SHIP-1001', 'Shipment for pump repair'),
    ('MOV-004', 'WH-E-01', 'PART-002', '2026-01-20 09:00:00+08', 'RECEIPT', 10, 'PURCHASE', 'PO-002', 'Opening receipt'),
    ('MOV-005', 'WH-E-01', 'PART-002', '2026-02-13 09:10:00+08', 'RESERVATION', 1, 'PART_REQUEST', 'REQ-1002', 'Reserved for bearing repair'),
    ('MOV-006', 'WH-E-01', 'PART-002', '2026-02-13 11:00:00+08', 'SHIPMENT', 1, 'PART_SHIPMENT', 'SHIP-1002', 'Shipment for compressor repair'),
    ('MOV-007', 'WH-W-01', 'PART-003', '2026-01-20 09:00:00+08', 'RECEIPT', 5, 'PURCHASE', 'PO-003', 'Opening receipt'),
    ('MOV-008', 'WH-W-01', 'PART-003', '2026-02-17 10:20:00+08', 'RESERVATION', 4, 'PART_REQUEST', 'REQ-1003', 'Reserved for controller repair'),
    ('MOV-009', 'WH-W-01', 'PART-003', '2026-02-17 13:00:00+08', 'SHIPMENT', 2, 'PART_SHIPMENT', 'SHIP-1003', 'Partial shipment'),
    ('MOV-010', 'WH-N-01', 'PART-004', '2026-01-20 09:00:00+08', 'RECEIPT', 6, 'PURCHASE', 'PO-004', 'Opening receipt'),
    ('MOV-011', 'WH-W-01', 'PART-005', '2026-01-20 09:00:00+08', 'RECEIPT', 12, 'PURCHASE', 'PO-005', 'Opening receipt'),
    ('MOV-012', 'WH-E-01', 'PART-006', '2026-01-20 09:00:00+08', 'RECEIPT', 8, 'PURCHASE', 'PO-006', 'Opening receipt');

INSERT INTO part_requests (part_request_id, request_number, work_order_id, part_id, requested_quantity, approved_quantity, requested_at, status) VALUES
    ('REQ-1001', 'REQ-1001', 'WO-1001', 'PART-001', 2, 2, '2026-02-10 09:10:00+08', 'FULFILLED'),
    ('REQ-1002', 'REQ-1002', 'WO-1003', 'PART-002', 1, 1, '2026-02-13 09:10:00+08', 'FULFILLED'),
    ('REQ-1003', 'REQ-1003', 'WO-1008', 'PART-003', 4, 4, '2026-02-17 10:20:00+08', 'PARTIAL'),
    ('REQ-1004', 'REQ-1004', 'WO-1011', 'PART-005', 1, 1, '2026-03-05 10:10:00+08', 'FULFILLED');

INSERT INTO part_shipments (part_shipment_id, shipment_number, part_request_id, warehouse_id, shipped_at, shipped_quantity, status, tracking_number) VALUES
    ('SHIP-1001', 'SHIP-1001', 'REQ-1001', 'WH-E-01', '2026-02-10 15:30:00+08', 2, 'SHIPPED', 'TRACK-E-1001'),
    ('SHIP-1002', 'SHIP-1002', 'REQ-1002', 'WH-E-01', '2026-02-13 11:00:00+08', 1, 'SHIPPED', 'TRACK-E-1002'),
    ('SHIP-1003', 'SHIP-1003', 'REQ-1003', 'WH-W-01', '2026-02-17 13:00:00+08', 2, 'PARTIAL', 'TRACK-W-1003'),
    ('SHIP-1004', 'SHIP-1004', 'REQ-1004', 'WH-W-01', '2026-03-05 11:00:00+08', 1, 'SHIPPED', 'TRACK-W-1004');
