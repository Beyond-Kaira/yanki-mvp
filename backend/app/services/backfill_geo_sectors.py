"""Fill missing GEO sector keys. Preview by default; pass --apply to persist.

Run after the schema migration and before enabling indexed sector readers.
Only NULL keys are filled; existing keys and original labels are preserved.
"""

import argparse
from typing import cast

from sqlalchemy import Connection, Table, select, update

from app.db.models import GeoRecord
from app.services.sectors import normalize_sector


def backfill_sector_keys(
    connection: Connection, *, apply: bool = False, batch_size: int = 500
) -> int:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    records = cast(Table, GeoRecord.__table__)
    last_id = None
    count = 0
    while True:
        query = (
            select(records.c.id, records.c.sector)
            .where(records.c.sector_key.is_(None))
            .order_by(records.c.id)
            .limit(batch_size)
        )
        if last_id is not None:
            query = query.where(records.c.id > last_id)
        rows = connection.execute(query).all()
        if not rows:
            break
        for row in rows:
            key = normalize_sector(row.sector) or None
            if key is None:
                continue
            if apply:
                # Avoid overwriting a concurrent writer's newer sector/key.
                result = connection.execute(
                    update(records)
                    .where(
                        records.c.id == row.id,
                        records.c.sector_key.is_(None),
                        records.c.sector == row.sector,
                    )
                    .values(sector_key=key)
                )
                count += result.rowcount
            else:
                count += 1
        last_id = rows[-1].id
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist missing sector keys")
    args = parser.parse_args()
    from app.db.session import engine

    with engine.begin() as connection:
        count = backfill_sector_keys(connection, apply=args.apply)
    print(f"{'Updated' if args.apply else 'Would update'} {count} GEO sector keys.")


if __name__ == "__main__":
    main()
