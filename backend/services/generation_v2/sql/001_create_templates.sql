CREATE TABLE IF NOT EXISTS generation_v2_templates (
    template_id TEXT NOT NULL,
    version TEXT NOT NULL,
    deprecated BOOLEAN NOT NULL DEFAULT FALSE,
    checksum TEXT NOT NULL,
    page_layout_json JSONB NOT NULL,
    styles_json JSONB NOT NULL,
    header_footer_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (template_id, version)
);

CREATE INDEX IF NOT EXISTS idx_generation_v2_templates_lookup
ON generation_v2_templates (template_id, deprecated, version);
