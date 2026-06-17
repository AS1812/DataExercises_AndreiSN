-- Test 3: flow_006_raw in Snowflake.
-- Type-mapped from the Postgres DDL (test2_postgres/schema.sql):
--   uuid -> VARCHAR(36)        (Snowflake has no native uuid type)
--   double precision -> FLOAT
--   timestamp -> TIMESTAMP_NTZ
--   gen_random_uuid() -> UUID_STRING(),  now() -> CURRENT_TIMESTAMP()
--   bigint/integer/smallint/numeric(p,s)/varchar(n)/char(n)/date -> unchanged
-- Note: Snowflake enforces NOT NULL but treats PRIMARY KEY as informational
-- (not unique-enforced) -- so idempotency relies on the MERGE key, not the PK.
CREATE SCHEMA IF NOT EXISTS pipeline;

CREATE TABLE IF NOT EXISTS pipeline.flow_006_raw (
    flow_uuid varchar(36) NOT NULL DEFAULT uuid_string(),
    date_cycle_id bigint NULL,
    nomination_id varchar(36) NULL,
    metadata_id varchar(30) NULL,
    tsp varchar(15) NULL,
    tsp_short char(3) NULL,
    tsp_name varchar(100) NULL,
    cycle_id smallint NULL,
    hourly_cycle_id integer NULL,
    cycle_num smallint NULL,
    cycle_desc varchar(30) NULL,
    eff_gas_day date NULL,
    eff_gas_day_time varchar(15) NULL,
    end_eff_gas_day date NULL,
    end_eff_gas_day_time varchar(15) NULL,
    post_date date NULL,
    post_time varchar(25) NULL,
    cap_type_desc varchar(75) NULL,
    loc varchar(15) NULL,
    loc_prop varchar(15) NULL,
    loc_name varchar(150) NULL,
    loc_segment varchar(25) NULL,
    loc_zone varchar(25) NULL,
    flow_id smallint NULL,
    flow_short varchar(25) NULL,
    loc_purp_desc varchar(50) NULL,
    loc_qti_id smallint NULL,
    loc_qti_short char(3) NULL,
    loc_qti varchar(10) NULL,
    loc_qti_desc varchar(75) NULL,
    meas_basis_desc varchar(75) NULL,
    it_id smallint NULL,
    it_num smallint NULL,
    it_desc varchar(75) NULL,
    design_capacity float NULL,
    operating_capacity float NULL,
    scheduled_quantity float NULL,
    operationally_available float NULL,
    unsubscribed_capacity float NULL,
    no_notice_quantity float NULL,
    storage_capacity float NULL,
    storage_quantity float NULL,
    storage_pct_full numeric(3,2) NULL,
    design_description varchar(25) NULL,
    bidirectional varchar(25) NULL,
    source_type_id integer NULL,
    scrape_date timestamp_ntz NULL,
    loc_key varchar(20) NULL,
    file_name varchar(255) NULL,
    tsq_sign smallint NULL,
    load_date timestamp_ntz NULL DEFAULT current_timestamp(),
    CONSTRAINT pk_flow_006_raw PRIMARY KEY(flow_uuid)
);
