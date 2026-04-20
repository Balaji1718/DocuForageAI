from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from .errors import DeprecatedTemplateError, IntegrityError

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze_value(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(v) for v in value)
    return value


def _thaw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _thaw_value(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(v) for v in value]
    return value


def _payload_checksum(page_layout: Mapping[str, Any], styles: Mapping[str, Any], header_footer: Mapping[str, Any]) -> str:
    payload = {
        "page_layout": _thaw_value(page_layout),
        "styles": _thaw_value(styles),
        "header_footer": _thaw_value(header_footer),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TemplateVersion:
    template_id: str
    version: str
    page_layout: Mapping[str, Any]
    styles: Mapping[str, Any]
    header_footer: Mapping[str, Any]
    deprecated: bool = False
    checksum: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.template_id.strip():
            raise ValueError("template_id must be non-empty")
        if not _SEMVER_RE.match(self.version):
            raise ValueError(f"Invalid semver version: {self.version}")

        frozen_layout = _freeze_value(self.page_layout)
        frozen_styles = _freeze_value(self.styles)
        frozen_header_footer = _freeze_value(self.header_footer)

        object.__setattr__(self, "page_layout", frozen_layout)
        object.__setattr__(self, "styles", frozen_styles)
        object.__setattr__(self, "header_footer", frozen_header_footer)

        checksum = _payload_checksum(self.page_layout, self.styles, self.header_footer)
        object.__setattr__(self, "checksum", checksum)


class TemplateRegistryStore(Protocol):
    def insert(self, template: TemplateVersion) -> None:
        ...

    def get(self, template_id: str, version: str) -> TemplateVersion:
        ...

    def exists(self, template_id: str, version: str) -> bool:
        ...

    def list_versions(self, template_id: str) -> list[TemplateVersion]:
        ...


def check_registry_backend_health() -> None:
    backend = (os.getenv("GENV2_TEMPLATE_REGISTRY_BACKEND") or "memory").strip().lower()
    if backend not in {"postgres", "postgresql"}:
        return

    dsn = os.getenv("GENV2_TEMPLATE_REGISTRY_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "GENV2_TEMPLATE_REGISTRY_DSN must be set when GENV2_TEMPLATE_REGISTRY_BACKEND=postgres"
        )

    try:
        import psycopg

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'generation_v2_templates'
                    """
                )
                table_exists = cur.fetchone() is not None
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Template registry Postgres backend is unreachable: {exc}") from exc

    if not table_exists:
        raise RuntimeError("Template registry table not found - run SQL migration 001_create_templates.sql")


class InMemoryTemplateStore:
    def __init__(self) -> None:
        self._templates: dict[tuple[str, str], TemplateVersion] = {}

    def insert(self, template: TemplateVersion) -> None:
        key = (template.template_id, template.version)
        if key in self._templates:
            raise ValueError(f"Template already exists: {template.template_id}@{template.version}")
        self._templates[key] = template

    def get(self, template_id: str, version: str) -> TemplateVersion:
        key = (template_id, version)
        if key not in self._templates:
            raise KeyError(f"Template not found: {template_id}@{version}")
        return self._templates[key]

    def exists(self, template_id: str, version: str) -> bool:
        return (template_id, version) in self._templates

    def list_versions(self, template_id: str) -> list[TemplateVersion]:
        return [template for (tid, _), template in self._templates.items() if tid == template_id]


class PostgresTemplateStore:
    def __init__(self, dsn: str) -> None:
        if not dsn.strip():
            raise ValueError("Postgres DSN must be non-empty")
        self._dsn = dsn
        self._ensure_schema()

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("psycopg is required for PostgresTemplateStore") from exc
        return psycopg.connect(self._dsn)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
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
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_generation_v2_templates_lookup
                    ON generation_v2_templates (template_id, deprecated, version)
                    """
                )
            conn.commit()

    @staticmethod
    def _row_to_template(row: tuple[Any, ...]) -> TemplateVersion:
        template_id, version, deprecated, checksum, page_layout_json, styles_json, header_footer_json = row
        template = TemplateVersion(
            template_id=str(template_id),
            version=str(version),
            page_layout=page_layout_json,
            styles=styles_json,
            header_footer=header_footer_json,
            deprecated=bool(deprecated),
        )
        if template.checksum != str(checksum):
            raise IntegrityError(
                f"Checksum mismatch for template {template.template_id}@{template.version}: "
                f"expected {template.checksum}, got {checksum}"
            )
        return template

    def insert(self, template: TemplateVersion) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO generation_v2_templates
                    (template_id, version, deprecated, checksum, page_layout_json, styles_json, header_footer_json)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                    """,
                    (
                        template.template_id,
                        template.version,
                        template.deprecated,
                        template.checksum,
                        json.dumps(_thaw_value(template.page_layout), separators=(",", ":"), sort_keys=True),
                        json.dumps(_thaw_value(template.styles), separators=(",", ":"), sort_keys=True),
                        json.dumps(_thaw_value(template.header_footer), separators=(",", ":"), sort_keys=True),
                    ),
                )
            conn.commit()

    def get(self, template_id: str, version: str) -> TemplateVersion:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT template_id, version, deprecated, checksum, page_layout_json, styles_json, header_footer_json
                    FROM generation_v2_templates
                    WHERE template_id = %s AND version = %s
                    """,
                    (template_id, version),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError(f"Template not found: {template_id}@{version}")
        return self._row_to_template(row)

    def exists(self, template_id: str, version: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM generation_v2_templates
                    WHERE template_id = %s AND version = %s
                    """,
                    (template_id, version),
                )
                row = cur.fetchone()
        return row is not None

    def list_versions(self, template_id: str) -> list[TemplateVersion]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT template_id, version, deprecated, checksum, page_layout_json, styles_json, header_footer_json
                    FROM generation_v2_templates
                    WHERE template_id = %s
                    """,
                    (template_id,),
                )
                rows = cur.fetchall()
        return [self._row_to_template(row) for row in rows]


class TemplateRegistry:
    def __init__(self, store: TemplateRegistryStore | None = None) -> None:
        self._store: TemplateRegistryStore = store or InMemoryTemplateStore()

    @classmethod
    def from_environment(cls) -> "TemplateRegistry":
        backend = (os.getenv("GENV2_TEMPLATE_REGISTRY_BACKEND") or "memory").strip().lower()
        if backend in {"memory", "inmemory"}:
            return cls(store=InMemoryTemplateStore())
        if backend in {"postgres", "postgresql"}:
            dsn = os.getenv("GENV2_TEMPLATE_REGISTRY_DSN") or os.getenv("DATABASE_URL")
            if not dsn:
                raise RuntimeError(
                    "GENV2_TEMPLATE_REGISTRY_BACKEND=postgres requires GENV2_TEMPLATE_REGISTRY_DSN or DATABASE_URL"
                )
            return cls(store=PostgresTemplateStore(dsn=dsn))
        raise RuntimeError(f"Unsupported GENV2_TEMPLATE_REGISTRY_BACKEND: {backend}")

    def register(
        self,
        *,
        template_id: str,
        version: str,
        page_layout: Mapping[str, Any],
        styles: Mapping[str, Any],
        header_footer: Mapping[str, Any],
        deprecated: bool = False,
    ) -> TemplateVersion:
        template = TemplateVersion(
            template_id=template_id,
            version=version,
            page_layout=page_layout,
            styles=styles,
            header_footer=header_footer,
            deprecated=deprecated,
        )
        self._store.insert(template)
        return template

    def latest_non_deprecated_version(self, template_id: str) -> str | None:
        versions = [
            template.version
            for template in self._store.list_versions(template_id)
            if not template.deprecated
        ]
        if not versions:
            return None
        return sorted(versions, key=_semver_key)[-1]

    def get(self, template_id: str, version: str) -> TemplateVersion:
        template = self._store.get(template_id, version)

        current_checksum = _payload_checksum(template.page_layout, template.styles, template.header_footer)
        if current_checksum != template.checksum:
            raise IntegrityError(
                f"Checksum mismatch for template {template_id}@{version}: "
                f"expected {template.checksum}, got {current_checksum}"
            )

        if template.deprecated:
            latest = self.latest_non_deprecated_version(template_id)
            hint = f" Please migrate to {template_id}@{latest}." if latest else " No non-deprecated version is available."
            raise DeprecatedTemplateError(
                f"Template {template_id}@{version} is deprecated.{hint}"
            )

        return template

    def exists(self, template_id: str, version: str) -> bool:
        return self._store.exists(template_id, version)


def _semver_key(version: str) -> tuple[int, int, int]:
    match = _SEMVER_RE.match(version)
    if not match:
        raise ValueError(f"Invalid semver version: {version}")
    return tuple(int(v) for v in match.groups())
