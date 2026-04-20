# Template Registry Persistence Plan

Status: In progress (Postgres adapter and CI gate implemented).
Owner: Backend Platform
Date: 2026-04-20

## Why
The current registry implementation is in-memory and process-local. On restart, template definitions are lost.
This is acceptable for development, but not acceptable for production cutover.

## Required End State
A durable backing store must be active before retiring the legacy pipeline.
One of these paths is required:
1. Postgres-backed registry with transactional versioning and integrity checks.
2. S3-backed registry with immutable version objects and metadata index.

## Baseline Requirements
- Persist template payload: page_layout, styles, header_footer, checksum, deprecated flag.
- Preserve semantic version uniqueness per template_id.
- Enforce immutability after publish.
- Keep checksum verification on read.
- Support latest_non_deprecated_version lookup.
- Support rollback by selecting prior immutable version.

## Proposed Delivery Steps
1. [x] Introduce storage interface in generation_v2 template registry.
2. [x] Implement Postgres adapter (primary production path).
3. [ ] Implement optional S3 adapter for static distribution workloads.
4. [ ] Add migration script to export current in-memory fixtures into persistent store.
5. [ ] Add startup health check: fail fast if persistent registry is unavailable in production mode.
6. [x] Add integration tests against adapter-backed registry (CI job with Postgres service).

## Implemented So Far
- Added pluggable registry storage with environment selection:
	- `GENV2_TEMPLATE_REGISTRY_BACKEND=memory|postgres`
	- `GENV2_TEMPLATE_REGISTRY_DSN` (or `DATABASE_URL`) for Postgres backend
- Added Postgres-backed store in generation_v2 registry module.
- Added schema SQL asset:
	- `services/generation_v2/sql/001_create_templates.sql`
- Added CI workflow gate:
	- `.github/workflows/generation-v2-production-gates.yml`

## Retirement Gate
Legacy pipeline retirement is blocked until:
- Persistent adapter is enabled in deployment config.
- Integration tests for registry persistence pass in CI.
- Backfill/migration is completed and verified.

## Suggested Schemas
### Postgres
- templates(template_id, version, deprecated, checksum, payload_jsonb, created_at)
- primary key(template_id, version)
- index(template_id, deprecated, version)

### S3
- s3://bucket/templates/{template_id}/{version}.json
- object metadata: checksum, deprecated, created_at
- index file or DynamoDB table for latest lookup
