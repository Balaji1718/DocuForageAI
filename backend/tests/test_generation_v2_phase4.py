from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.generation_v2.errors import DeprecatedTemplateError, IntegrityError
from services.generation_v2.template_registry import TemplateRegistry, check_registry_backend_health


def _sample_layout() -> dict:
    return {
        "size": {"width_in": 8.5, "height_in": 11.0},
        "margins": {"top_in": 1.0, "right_in": 1.0, "bottom_in": 1.0, "left_in": 1.0},
    }


def _sample_styles(size: int) -> dict:
    return {
        "Normal": {"font_name": "Calibri", "font_size_pt": size, "line_spacing": 1.15},
        "Heading1": {"font_name": "Calibri", "font_size_pt": size + 2, "line_spacing": 1.2},
    }


def _sample_header_footer(text: str) -> dict:
    return {"header": {"text": text}, "footer": {"text": "Page {n}"}}


def test_two_versions_stored_independently():
    reg = TemplateRegistry()

    reg.register(
        template_id="thesis",
        version="1.0.0",
        page_layout=_sample_layout(),
        styles=_sample_styles(11),
        header_footer=_sample_header_footer("Institute"),
    )
    reg.register(
        template_id="thesis",
        version="1.1.0",
        page_layout=_sample_layout(),
        styles=_sample_styles(12),
        header_footer=_sample_header_footer("Institute"),
    )

    t1 = reg.get("thesis", "1.0.0")
    t2 = reg.get("thesis", "1.1.0")

    assert t1.styles["Normal"]["font_size_pt"] == 11
    assert t2.styles["Normal"]["font_size_pt"] == 12


def test_mutating_stored_template_triggers_integrity_error():
    reg = TemplateRegistry()
    template = reg.register(
        template_id="proposal",
        version="2.0.0",
        page_layout=_sample_layout(),
        styles=_sample_styles(11),
        header_footer=_sample_header_footer("Dept"),
    )

    # Build a new mutable payload and monkey-patch storage to emulate corruption.
    reg._store._templates[("proposal", "2.0.0")] = type(template)(
        template_id=template.template_id,
        version=template.version,
        page_layout={**_sample_layout()},
        styles={**_sample_styles(11)},
        header_footer={**_sample_header_footer("Dept")},
        deprecated=False,
    )

    # Corrupt post-register by mutating private attrs via object.__setattr__.
    corrupted = reg._store._templates[("proposal", "2.0.0")]
    object.__setattr__(corrupted, "styles", {"Normal": {"font_size_pt": 99}})

    with pytest.raises(IntegrityError, match="Checksum mismatch"):
        reg.get("proposal", "2.0.0")


def test_deprecated_version_raises_with_migration_hint():
    reg = TemplateRegistry()
    reg.register(
        template_id="invoice",
        version="1.0.0",
        page_layout=_sample_layout(),
        styles=_sample_styles(10),
        header_footer=_sample_header_footer("Org"),
        deprecated=True,
    )
    reg.register(
        template_id="invoice",
        version="1.1.0",
        page_layout=_sample_layout(),
        styles=_sample_styles(11),
        header_footer=_sample_header_footer("Org"),
        deprecated=False,
    )

    with pytest.raises(DeprecatedTemplateError, match="Please migrate to invoice@1.1.0"):
        reg.get("invoice", "1.0.0")


def test_registry_from_environment_memory_backend(monkeypatch):
    monkeypatch.setenv("GENV2_TEMPLATE_REGISTRY_BACKEND", "memory")
    reg = TemplateRegistry.from_environment()

    reg.register(
        template_id="env-test",
        version="1.0.0",
        page_layout=_sample_layout(),
        styles=_sample_styles(10),
        header_footer=_sample_header_footer("Org"),
        deprecated=False,
    )
    assert reg.exists("env-test", "1.0.0") is True


def test_registry_from_environment_postgres_requires_dsn(monkeypatch):
    monkeypatch.setenv("GENV2_TEMPLATE_REGISTRY_BACKEND", "postgres")
    monkeypatch.delenv("GENV2_TEMPLATE_REGISTRY_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="requires GENV2_TEMPLATE_REGISTRY_DSN or DATABASE_URL"):
        TemplateRegistry.from_environment()


def test_health_check_missing_dsn_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("GENV2_TEMPLATE_REGISTRY_BACKEND", "postgres")
    monkeypatch.delenv("GENV2_TEMPLATE_REGISTRY_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="GENV2_TEMPLATE_REGISTRY_DSN must be set when GENV2_TEMPLATE_REGISTRY_BACKEND=postgres"):
        check_registry_backend_health()


def test_health_check_unreachable_postgres_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("GENV2_TEMPLATE_REGISTRY_BACKEND", "postgres")
    monkeypatch.setenv("GENV2_TEMPLATE_REGISTRY_DSN", "postgresql://bad-host:5432/genv2")

    fake_psycopg = SimpleNamespace(connect=lambda _dsn: (_ for _ in ()).throw(OSError("connection refused")))
    with patch.dict("sys.modules", {"psycopg": fake_psycopg}):
        with pytest.raises(RuntimeError, match="unreachable"):
            check_registry_backend_health()


def test_health_check_missing_table_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("GENV2_TEMPLATE_REGISTRY_BACKEND", "postgres")
    monkeypatch.setenv("GENV2_TEMPLATE_REGISTRY_DSN", "postgresql://localhost:5432/genv2")

    class _Cursor:
        def __init__(self):
            self._step = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _query):
            self._step += 1

        def fetchone(self):
            if self._step == 1:
                return (1,)
            return None

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _Cursor()

    fake_psycopg = SimpleNamespace(connect=lambda _dsn: _Conn())
    with patch.dict("sys.modules", {"psycopg": fake_psycopg}):
        with pytest.raises(RuntimeError, match="migration"):
            check_registry_backend_health()
