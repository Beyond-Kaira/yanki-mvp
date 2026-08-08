#!/usr/bin/env python
"""Put one organization on one plan — the operator's key to the quota cage.

P7.6 made plan limits real (ADR-45). There is no Stripe lifecycle yet and no
platform back office (P7.7), so without this script the only way to move an
organization off Free is hand-written SQL against production — which is how a
tier change becomes an incident.

Read-only by default. Nothing is written until ``--set`` names a plan.

    # what is everyone on right now?
    docker exec yanki-prod-api-1 python /app/scripts/set_org_plan.py --list

    # move one organization to a tier
    docker exec yanki-prod-api-1 python /app/scripts/set_org_plan.py \
        --org <uuid-or-slug> --set enterprise

The organization may be named by id or by slug, because an operator reading the
admin panel has the slug and an operator reading a log line has the id.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

# Runnable as `python scripts/set_org_plan.py` from the repo root as well as
# from inside the container, where the backend package sits at /app.
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if _BACKEND.is_dir():
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select  # noqa: E402

from app.db.models import Organization, Plan, Subscription  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import billing  # noqa: E402


def _resolve_org(session, needle: str) -> Organization:
    try:
        org_id = uuid.UUID(needle)
    except ValueError:
        org = session.scalar(select(Organization).where(Organization.slug == needle))
    else:
        org = session.get(Organization, org_id)
    if org is None:
        raise SystemExit(f"no organization matches {needle!r} (tried id, then slug)")
    return org


def _describe(session, org: Organization) -> str:
    plan = billing.plan_for_org(session, org.id)
    # "free (implied)" and "free" are different states worth telling apart: the
    # first has no subscription row and is falling back, the second was chosen.
    tier = f"{plan.key}" if plan is not None else "free (implied — no subscription row)"
    return f"{org.slug:<28} {str(org.id):<38} {tier}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", help="organization id or slug")
    parser.add_argument("--set", dest="plan_key", help="plan key to assign (see --plans)")
    parser.add_argument("--list", action="store_true", help="list organizations and their plans")
    parser.add_argument("--plans", action="store_true", help="list the plan catalog")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.plans or not (args.list or args.org):
            plans = list(session.scalars(select(Plan).order_by(Plan.monthly_price_usd)))
            if not plans:
                print("PLAN CATALOG IS EMPTY — quota checks will 503 until 0016_seed_plans runs.")
            for plan in plans:
                print(f"{plan.key:<12} {plan.name:<12} {plan.limits}")
            if not args.list and not args.org:
                return 0

        if args.list:
            for org in session.scalars(select(Organization).order_by(Organization.created_at)):
                print(_describe(session, org))
            return 0

        org = _resolve_org(session, args.org)
        if not args.plan_key:
            print(_describe(session, org))
            return 0

        try:
            subscription = billing.assign_plan(session, org.id, args.plan_key)
        except LookupError as exc:
            raise SystemExit(str(exc)) from exc
        session.commit()

        plan = session.get(Plan, subscription.plan_id)
        assert plan is not None  # just assigned
        print(f"{org.slug} → {plan.key} ({plan.name})")
        print(f"  limits: {plan.limits}")
        superseded = session.scalars(
            select(Subscription).where(
                Subscription.org_id == org.id, Subscription.status == "superseded"
            )
        ).all()
        if superseded:
            print(f"  {len(superseded)} previous subscription(s) marked superseded, not deleted")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
