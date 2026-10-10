"""Sector identity and isolated migration backfill, with no application DB writes."""

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.pipeline.geo_records import geo_record_from_audit
from app.services.backfill_geo_sectors import backfill_sector_keys
from app.services.sectors import normalize_sector


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, ""),
        (" \t ", ""),
        (" E Commerce ", "e-commerce"),
        ("ECOMMERCE", "e-commerce"),
        ("ｅ－ｃｏｍｍｅｒｃｅ", "e-commerce"),
        ("Artificial\u00a0 Intelligence", "artificial intelligence"),
        ("AI", "ai"),
        ("Machine Learning", "machine learning"),
        ("FinTech", "fintech"),
        ("Financial Technology", "financial technology"),
    ],
)
def test_sector_normalization(raw, expected):
    assert normalize_sector(raw) == expected


def test_backfill_batches_preserve_labels_and_downgrade(monkeypatch):
    path = Path(__file__).parents[1] / "alembic/versions/0026_geo_sector_key.py"
    spec = importlib.util.spec_from_file_location("sector_key_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    labels = [None, " ", " ECOMMERCE ", "ｅ－ｃｏｍｍｅｒｃｅ", "AI", "Artificial Intelligence"]
    original = [{"id": uuid.UUID(int=i + 1), "sector": label} for i, label in enumerate(labels)]
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            metadata = sa.MetaData()
            table = sa.Table(
                "geo_records",
                metadata,
                sa.Column("id", sa.Uuid(), primary_key=True),
                sa.Column("sector", sa.Text()),
            )
            metadata.create_all(connection)
            connection.execute(table.insert(), original)
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            migrated = sa.Table("geo_records", sa.MetaData(), autoload_with=connection)
            assert backfill_sector_keys(connection, batch_size=2) == 4
            assert (
                connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(migrated)
                    .where(migrated.c.sector_key.is_not(None))
                )
                == 0
            )
            assert backfill_sector_keys(connection, apply=True, batch_size=2) == 4
            assert backfill_sector_keys(connection, apply=True, batch_size=2) == 0
            rows = connection.execute(sa.select(migrated).order_by(migrated.c.id)).mappings().all()
            assert [row["sector"] for row in rows] == labels
            assert [row["sector_key"] for row in rows] == [
                normalize_sector(v) or None for v in labels
            ]
            indexes = sa.inspect(connection).get_indexes("geo_records")
            assert any(index["name"] == "ix_geo_records_sector_key" for index in indexes)
            migration.downgrade()
            assert "sector_key" not in {
                c["name"] for c in sa.inspect(connection).get_columns("geo_records")
            }
            assert [
                dict(row)
                for row in connection.execute(sa.select(table).order_by(table.c.id)).mappings()
            ] == original
    finally:
        engine.dispose()


def test_writer_derives_key_and_tracks_sector_changes():
    record = geo_record_from_audit(
        {"sector": " E Commerce ", "brand": "test", "prompt": "test"},
        analysis_id=uuid.uuid4(),
        response_id=uuid.uuid4(),
    )
    assert record.sector == " E Commerce "
    assert record.sector_key == "e-commerce"
    record.sector = "Artificial Intelligence"
    assert record.sector_key == "artificial intelligence"
    record.sector = None
    assert record.sector_key is None
