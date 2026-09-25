-- TenderWatch: local copy of simap.ch publications (Swiss public procurement)
--
-- Principle: store the RAW API response (jsonb) and derive everything else
-- through views. Changing an analysis never requires downloading again.

-- A procurement project, as returned by the search endpoint.
CREATE TABLE IF NOT EXISTS projects (
    id                      UUID PRIMARY KEY,
    project_number          TEXT NOT NULL,
    newest_publication_date DATE,
    search_json             JSONB NOT NULL,
    first_seen              TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen               TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- id of the newest publication whose history has been read: when the
    -- project gets a new publication, its history is read again.
    history_for             UUID
);

-- A publication (tender, award, direct award, abandonment…).
-- A project split into lots publishes one award PER lot: lot_id tells them apart.
CREATE TABLE IF NOT EXISTS publications (
    id                  UUID PRIMARY KEY,
    project_id          UUID NOT NULL REFERENCES projects(id),
    lot_id              UUID,
    lot_number          INTEGER,
    publication_number  TEXT,
    pub_type            TEXT,
    publication_date    DATE,
    corrected           BOOLEAN,
    detail              JSONB,          -- NULL until the detail is downloaded
    content_hash        TEXT,
    detail_fetched_at   TIMESTAMPTZ,
    detail_error        TEXT,           -- last failure, so as not to loop on it
    first_seen          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS publications_project ON publications(project_id);
CREATE INDEX IF NOT EXISTS publications_pending ON publications(id) WHERE detail IS NULL;

-- A replaced version is never overwritten: if simap edits or withdraws a
-- publication, the previous answer stays here.
CREATE TABLE IF NOT EXISTS publication_history (
    publication_id  UUID NOT NULL REFERENCES publications(id),
    content_hash    TEXT NOT NULL,
    detail          JSONB NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL,
    replaced_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (publication_id, content_hash)
);

-- Public profile of a vendor registered on simap: this is what carries the UID.
CREATE TABLE IF NOT EXISTS vendors (
    id          UUID PRIMARY KEY,
    uid         TEXT,               -- normalised Swiss UID "CHE-123.456.789", NULL if absent
    name        TEXT,
    detail      JSONB,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    error       TEXT
);
CREATE INDEX IF NOT EXISTS vendors_uid ON vendors(uid);

-- Zefix (commercial register) record per UID.
CREATE TABLE IF NOT EXISTS zefix_companies (
    uid         TEXT PRIMARY KEY,   -- same format as vendors.uid
    name        TEXT,
    status      TEXT,               -- ACTIVE, CANCELLED, BEING_CANCELLED…
    legal_form  TEXT,
    legal_seat  TEXT,
    canton      TEXT,
    detail      JSONB,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    error       TEXT                -- 'not_found': UID not in the register (association, public body, foreign…)
);

-- Multilingual simap text {de,fr,it,en} → one value: the first language
-- filled in, French first. Publications are often filled in only in their
-- creation language, in which case this returns the original text.
CREATE OR REPLACE FUNCTION ml(j JSONB) RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT COALESCE(j->>'fr', j->>'de', j->>'it', j->>'en')
$$;

-- One row per (award publication, winner).
--
-- Known pitfalls, see docs/methodology.md:
--   * members of a bidding consortium are only named in the free-text note:
--     only the lead vendor gets a row here;
--   * the price is the *published* price: VAT included or not depending on
--     vat_type, and sometimes a framework-agreement ceiling rather than spending;
--   * a corrected award appears several times: v_awards_current keeps only the
--     latest publication of each lot.
CREATE OR REPLACE VIEW v_awards AS
SELECT
    p.id                                            AS publication_id,
    p.project_id,
    pr.project_number,
    p.publication_number,
    p.lot_id,
    p.lot_number,
    p.pub_type,
    p.publication_date,
    p.corrected,
    p.detail->'base'->>'processType'                AS process_type,
    p.detail->'procurement'->>'orderType'           AS order_type,
    ml(p.detail->'base'->'title')                   AS title,
    (p.detail->'base'->>'procOfficeId')::uuid       AS proc_office_id,
    ml(p.detail->'project-info'->'procOfficeAddress'->'name') AS proc_office_name,
    p.detail->'project-info'->'procOfficeAddress'->>'cantonId' AS proc_office_canton,
    (p.detail->'decision'->>'awardDecisionDate')::date AS award_date,
    (p.detail->'decision'->>'numberOfSubmissions')::int AS n_submissions,
    ml(p.detail->'decision'->'awardDecisionJustification') AS justification,
    (v->>'vendorId')::uuid                          AS vendor_id,
    v->>'vendorName'                                AS vendor_name,
    v->'vendorAddress'->>'countryId'                AS vendor_country,
    v->'vendorAddress'->>'cantonId'                 AS vendor_canton,
    (v->'price'->>'price')::numeric                 AS price,
    v->'price'->>'currency'                         AS currency,
    v->'price'->>'vatType'                          AS vat_type,
    ml(v->'note')                                   AS vendor_note,
    vd.uid
FROM publications p
JOIN projects pr ON pr.id = p.project_id
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(p.detail->'decision'->'vendors', '[]'::jsonb)) v
LEFT JOIN vendors vd ON vd.id = (v->>'vendorId')::uuid
WHERE p.detail IS NOT NULL
  AND p.pub_type IN ('award', 'direct_award');

-- Latest award publication of each (project, lot): drops earlier versions of
-- a corrected award.
CREATE OR REPLACE VIEW v_awards_current AS
WITH last AS (
    SELECT DISTINCT ON (project_id, COALESCE(lot_number, 0)) id
    FROM publications
    WHERE pub_type IN ('award', 'direct_award') AND detail IS NOT NULL
    ORDER BY project_id, COALESCE(lot_number, 0), publication_date DESC, publication_number DESC
)
SELECT a.* FROM v_awards a JOIN last ON last.id = a.publication_id;
