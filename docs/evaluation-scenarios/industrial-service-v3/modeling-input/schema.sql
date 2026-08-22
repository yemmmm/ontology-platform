-- Industrial service v3 evaluation schema.
-- This file is deliberately independent of platform migrations and stores no RDF.
-- The guard is repeated here so a standalone psql invocation is fail-closed too.
DO $$
DECLARE
    existing_owner text;
    existing_marker text;
BEGIN
    SELECT pg_get_userbyid(n.nspowner), obj_description(n.oid, 'pg_namespace')
      INTO existing_owner, existing_marker
      FROM pg_namespace AS n
     WHERE n.nspname = 'industrial_service_v3';

    IF FOUND THEN
        IF existing_owner <> current_user
           OR existing_marker <> 'ontology-platform:v3-industrial-service-fixture' THEN
            RAISE EXCEPTION 'refusing to replace schema industrial_service_v3: owner or fixture marker mismatch';
        END IF;
        DROP SCHEMA industrial_service_v3 CASCADE;
    END IF;
END
$$;

CREATE SCHEMA industrial_service_v3;
COMMENT ON SCHEMA industrial_service_v3 IS 'ontology-platform:v3-industrial-service-fixture';
SET search_path TO industrial_service_v3, pg_catalog;

CREATE TABLE service_regions (
    region_id text PRIMARY KEY,
    region_code text NOT NULL UNIQUE,
    region_name text NOT NULL,
    timezone text NOT NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE customers (
    customer_id text PRIMARY KEY,
    customer_code text NOT NULL UNIQUE,
    customer_name text NOT NULL,
    region_id text NOT NULL REFERENCES service_regions (region_id),
    status text NOT NULL CHECK (status IN ('ACTIVE', 'SUSPENDED')),
    created_at timestamptz NOT NULL
);

CREATE TABLE service_sites (
    site_id text PRIMARY KEY,
    customer_id text NOT NULL REFERENCES customers (customer_id),
    region_id text NOT NULL REFERENCES service_regions (region_id),
    site_code text NOT NULL UNIQUE,
    site_name text NOT NULL,
    city text NOT NULL,
    timezone text NOT NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE equipment_models (
    model_id text PRIMARY KEY,
    model_code text NOT NULL UNIQUE,
    model_name text NOT NULL,
    manufacturer text NOT NULL,
    support_tier text NOT NULL CHECK (support_tier IN ('STANDARD', 'PREMIUM')),
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE assets (
    asset_id text PRIMARY KEY,
    asset_tag text NOT NULL UNIQUE,
    site_id text NOT NULL REFERENCES service_sites (site_id),
    model_id text NOT NULL REFERENCES equipment_models (model_id),
    serial_number text NOT NULL UNIQUE,
    installed_at date NOT NULL,
    warranty_end_date date,
    status text NOT NULL CHECK (status IN ('ACTIVE', 'RETIRED'))
);

CREATE TABLE sla_policies (
    sla_policy_id text PRIMARY KEY,
    policy_code text NOT NULL UNIQUE,
    policy_name text NOT NULL,
    description text,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE sla_targets (
    sla_target_id text PRIMARY KEY,
    sla_policy_id text NOT NULL REFERENCES sla_policies (sla_policy_id),
    severity text NOT NULL CHECK (severity IN ('P1', 'P2', 'P3', 'P4')),
    response_minutes integer NOT NULL CHECK (response_minutes > 0),
    resolution_minutes integer NOT NULL CHECK (resolution_minutes > 0),
    UNIQUE (sla_policy_id, severity)
);

CREATE TABLE service_contracts (
    contract_id text PRIMARY KEY,
    contract_number text NOT NULL UNIQUE,
    customer_id text NOT NULL REFERENCES customers (customer_id),
    sla_policy_id text NOT NULL REFERENCES sla_policies (sla_policy_id),
    start_date date NOT NULL,
    end_date date NOT NULL,
    status text NOT NULL CHECK (status IN ('ACTIVE', 'EXPIRED', 'SUSPENDED')),
    CHECK (end_date >= start_date)
);

CREATE TABLE contract_assets (
    contract_asset_id text PRIMARY KEY,
    contract_id text NOT NULL REFERENCES service_contracts (contract_id),
    asset_id text NOT NULL REFERENCES assets (asset_id),
    coverage_start_date date NOT NULL,
    coverage_end_date date,
    coverage_status text NOT NULL CHECK (coverage_status IN ('COVERED', 'EXPIRED')),
    UNIQUE (contract_id, asset_id, coverage_start_date),
    CHECK (coverage_end_date IS NULL OR coverage_end_date >= coverage_start_date)
);

CREATE TABLE incidents (
    incident_id text PRIMARY KEY,
    incident_number text NOT NULL UNIQUE,
    asset_id text NOT NULL REFERENCES assets (asset_id),
    reported_at timestamptz NOT NULL,
    occurred_at timestamptz NOT NULL,
    severity text NOT NULL CHECK (severity IN ('P1', 'P2', 'P3', 'P4')),
    failure_code text,
    symptom text,
    status text NOT NULL CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CANCELLED')),
    closed_at timestamptz,
    CHECK (reported_at >= occurred_at),
    CHECK (closed_at IS NULL OR closed_at >= reported_at)
);

CREATE TABLE work_orders (
    work_order_id text PRIMARY KEY,
    work_order_number text NOT NULL UNIQUE,
    incident_id text NOT NULL UNIQUE REFERENCES incidents (incident_id),
    opened_at timestamptz NOT NULL,
    responded_at timestamptz,
    onsite_at timestamptz,
    restored_at timestamptz,
    resolved_at timestamptz,
    status text NOT NULL CHECK (status IN ('OPEN', 'ASSIGNED', 'IN_PROGRESS', 'WAITING_PARTS', 'RESOLVED', 'CANCELLED')),
    resolution_code text,
    created_by text NOT NULL,
    CHECK (responded_at IS NULL OR responded_at >= opened_at),
    CHECK (onsite_at IS NULL OR responded_at IS NOT NULL AND onsite_at >= responded_at),
    CHECK (restored_at IS NULL OR onsite_at IS NOT NULL AND restored_at >= onsite_at),
    CHECK (resolved_at IS NULL OR restored_at IS NOT NULL AND resolved_at >= restored_at)
);

CREATE TABLE work_order_status_events (
    status_event_id text PRIMARY KEY,
    work_order_id text NOT NULL REFERENCES work_orders (work_order_id),
    event_at timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('OPEN', 'ASSIGNED', 'IN_PROGRESS', 'WAITING_PARTS', 'RESOLVED', 'CANCELLED')),
    note text,
    UNIQUE (work_order_id, event_at, status)
);

CREATE TABLE technicians (
    technician_id text PRIMARY KEY,
    technician_code text NOT NULL UNIQUE,
    technician_name text NOT NULL,
    region_id text NOT NULL REFERENCES service_regions (region_id),
    skill_level text NOT NULL CHECK (skill_level IN ('JUNIOR', 'SENIOR', 'SPECIALIST')),
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE work_order_assignments (
    assignment_id text PRIMARY KEY,
    work_order_id text NOT NULL REFERENCES work_orders (work_order_id),
    technician_id text NOT NULL REFERENCES technicians (technician_id),
    assigned_at timestamptz NOT NULL,
    unassigned_at timestamptz,
    assignment_role text NOT NULL CHECK (assignment_role IN ('PRIMARY', 'BACKUP')),
    CHECK (unassigned_at IS NULL OR unassigned_at >= assigned_at)
);

CREATE TABLE work_order_delay_events (
    delay_event_id text PRIMARY KEY,
    work_order_id text NOT NULL REFERENCES work_orders (work_order_id),
    delay_start_at timestamptz NOT NULL,
    delay_end_at timestamptz,
    cause_code text NOT NULL CHECK (cause_code IN ('PART_SHORTAGE', 'DISPATCH_CAPACITY', 'CUSTOMER_ACCESS', 'OTHER', 'UNKNOWN')),
    note text,
    CHECK (delay_end_at IS NULL OR delay_end_at >= delay_start_at)
);

CREATE TABLE spare_parts (
    part_id text PRIMARY KEY,
    part_number text NOT NULL UNIQUE,
    part_name text NOT NULL,
    standard_cost numeric(12, 2) NOT NULL CHECK (standard_cost >= 0),
    currency char(3) NOT NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE part_compatibilities (
    compatibility_id text PRIMARY KEY,
    part_id text NOT NULL REFERENCES spare_parts (part_id),
    model_id text NOT NULL REFERENCES equipment_models (model_id),
    compatibility_type text NOT NULL CHECK (compatibility_type IN ('REQUIRED', 'OPTIONAL')),
    UNIQUE (part_id, model_id)
);

CREATE TABLE warehouses (
    warehouse_id text PRIMARY KEY,
    warehouse_code text NOT NULL UNIQUE,
    region_id text NOT NULL REFERENCES service_regions (region_id),
    warehouse_name text NOT NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE inventory_movements (
    inventory_movement_id text PRIMARY KEY,
    warehouse_id text NOT NULL REFERENCES warehouses (warehouse_id),
    part_id text NOT NULL REFERENCES spare_parts (part_id),
    movement_at timestamptz NOT NULL,
    movement_type text NOT NULL CHECK (movement_type IN ('RECEIPT', 'RESERVATION', 'SHIPMENT', 'ADJUSTMENT')),
    quantity integer NOT NULL CHECK (quantity > 0),
    reference_type text,
    reference_id text,
    note text,
    CHECK ((reference_type IS NULL AND reference_id IS NULL) OR (reference_type IS NOT NULL AND reference_id IS NOT NULL))
);

CREATE TABLE part_requests (
    part_request_id text PRIMARY KEY,
    request_number text NOT NULL UNIQUE,
    work_order_id text NOT NULL REFERENCES work_orders (work_order_id),
    part_id text NOT NULL REFERENCES spare_parts (part_id),
    requested_quantity integer NOT NULL CHECK (requested_quantity > 0),
    approved_quantity integer NOT NULL CHECK (approved_quantity >= 0 AND approved_quantity <= requested_quantity),
    requested_at timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('REQUESTED', 'APPROVED', 'PARTIAL', 'FULFILLED', 'CANCELLED')),
    UNIQUE (work_order_id, part_id)
);

CREATE TABLE part_shipments (
    part_shipment_id text PRIMARY KEY,
    shipment_number text NOT NULL UNIQUE,
    part_request_id text NOT NULL REFERENCES part_requests (part_request_id),
    warehouse_id text NOT NULL REFERENCES warehouses (warehouse_id),
    shipped_at timestamptz,
    shipped_quantity integer NOT NULL CHECK (shipped_quantity > 0),
    status text NOT NULL CHECK (status IN ('ALLOCATED', 'SHIPPED', 'PARTIAL', 'CANCELLED')),
    tracking_number text
);

CREATE INDEX idx_customers_region_id ON customers (region_id);
CREATE INDEX idx_sites_customer_id ON service_sites (customer_id);
CREATE INDEX idx_sites_region_id ON service_sites (region_id);
CREATE INDEX idx_assets_site_id ON assets (site_id);
CREATE INDEX idx_assets_model_id ON assets (model_id);
CREATE INDEX idx_sla_targets_policy_severity ON sla_targets (sla_policy_id, severity);
CREATE INDEX idx_contracts_customer_id ON service_contracts (customer_id);
CREATE INDEX idx_contract_assets_asset_dates ON contract_assets (asset_id, coverage_start_date, coverage_end_date);
CREATE INDEX idx_incidents_asset_occurred_at ON incidents (asset_id, occurred_at);
CREATE INDEX idx_work_orders_status ON work_orders (status);
CREATE INDEX idx_status_events_work_order_event_at ON work_order_status_events (work_order_id, event_at);
CREATE INDEX idx_technicians_region_id ON technicians (region_id);
CREATE INDEX idx_assignments_work_order_assigned_at ON work_order_assignments (work_order_id, assigned_at);
CREATE INDEX idx_delays_work_order_start_at ON work_order_delay_events (work_order_id, delay_start_at);
CREATE INDEX idx_compatibilities_model_id ON part_compatibilities (model_id);
CREATE INDEX idx_inventory_part_warehouse_time ON inventory_movements (part_id, warehouse_id, movement_at);
CREATE INDEX idx_requests_work_order_id ON part_requests (work_order_id);
CREATE INDEX idx_shipments_request_id ON part_shipments (part_request_id);
