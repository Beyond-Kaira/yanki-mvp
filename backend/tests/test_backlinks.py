"""Backlink Intelligence (Phase 8) — the delta engine's honesty, mostly.

Almost every test here is about a claim the product must NOT make. A backlink
tool's reputation is destroyed by one confident wrong number — "you lost 4,000
links" on a day nothing happened — and every plausible link-diff implementation
produces exactly that at least once. So the assertions are mostly negative:
no losses from a truncated pull, no births from a returning link, no phantom
churn from a rewritten URL.

Everything runs on the deterministic mock at $0. The mock is a pure function of
``(domain, cycle)`` — there is no clock and no RNG anywhere in the module — so
"run cycle 0 then cycle 2" produces the same profile evolution on every machine,
which is what makes a multi-refresh assertion possible at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.backlink.authority import compute_authority, velocity
from app.backlink.base import BacklinkPage, BacklinkRow, BacklinkSourceUnavailable
from app.backlink.delta import MISSES_BEFORE_LOST, is_measurable, run_import
from app.backlink.gap import anchor_distribution, link_gap, unlinked_mentions
from app.backlink.mock import EPOCH, MockBacklinkSource
from app.backlink.normalize import classify_anchor, domain_key, subnet_24, url_key
from app.backlink.pricing import page_cost
from app.backlink.registry import get_backlink_source
from app.backlink.toxicity import assess_project, band_for, disavow_file
from app.db.models import (
    Backlink,
    BacklinkImport,
    CreditLedgerEntry,
    LinkEvent,
    Organization,
    Plan,
    Project,
    ReferringDomainRollup,
    Subscription,
    Workspace,
)

SUBJECT = "acme.example"


@pytest.fixture()
def project(db_session):
    org = Organization(name="Acme", slug="acme", kind="company")
    db_session.add(org)
    db_session.flush()
    workspace = Workspace(org_id=org.id, name="Default", slug="default", is_default=True)
    db_session.add(workspace)
    db_session.flush()
    project = Project(
        org_id=org.id,
        workspace_id=workspace.id,
        name="Acme",
        domain=f"https://{SUBJECT}/",
        domain_key=SUBJECT,
    )
    db_session.add(project)
    db_session.commit()
    return project


def _run(db_session, project, cycle: int, *, day: int = 0):
    outcome = run_import(
        db_session,
        source=MockBacklinkSource(cycle=cycle),
        org_id=project.org_id,
        project_id=project.id,
        subject_domain=SUBJECT,
        brand="acme",
        now=datetime(2026, 6, 1, tzinfo=UTC) + timedelta(days=day),
        meter=False,
    )
    db_session.commit()
    return outcome


# --------------------------------------------------------------------------
# Identity — the rules that stop cosmetic churn reading as real churn
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("https://blog.example/post", "http://blog.example/post"),
        ("https://blog.example/post", "https://www.blog.example/post/"),
        ("https://blog.example/post", "https://blog.example/post?utm_source=x"),
        ("https://blog.example/post", "https://blog.example/post#section"),
    ],
)
def test_cosmetic_url_differences_are_the_same_link(a, b):
    """Each of these pairs, treated as distinct, is a phantom new+lost pair."""

    assert url_key(a) == url_key(b)


def test_genuinely_different_pages_keep_different_keys():
    assert url_key("https://blog.example/a") != url_key("https://blog.example/b")
    assert url_key("https://a.example/p") != url_key("https://b.example/p")


def test_a_meaningful_query_parameter_survives():
    """Only tracking parameters are stripped — ?id=7 identifies a page."""

    assert url_key("https://x.example/p?id=7") != url_key("https://x.example/p")


def test_domain_key_normalizes_hosts():
    assert domain_key("https://WWW.Example.com:443/path") == "example.com"
    assert domain_key("sub.example.co.uk") == "sub.example.co.uk"


def test_subnet_24_groups_ipv4_and_ignores_the_rest():
    assert subnet_24("192.0.2.44") == "192.0.2.0/24"
    assert subnet_24("2001:db8::1") is None
    assert subnet_24(None) is None
    assert subnet_24("not-an-ip") is None


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        ("", "empty"),
        ("Acme", "brand"),
        ("click here", "generic"),
        ("https://acme.example/", "naked"),
        ("best cheap widgets", "partial"),
    ],
)
def test_anchor_classification(anchor, expected):
    assert classify_anchor(anchor, brand="acme", target_domain="https://acme.example/") == expected


# --------------------------------------------------------------------------
# Cost — an unpriceable call must never be recorded as free
# --------------------------------------------------------------------------


def test_the_mock_is_free_and_says_so():
    assert page_cost("mock", 5000) == Decimal("0")


def test_an_unknown_vendor_raises_rather_than_costing_zero():
    """The openrouter.py mistake, refused at the seam (ADR-34, #58)."""

    with pytest.raises(BacklinkSourceUnavailable):
        page_cost("some-vendor-we-never-priced", 100)


def test_a_priced_vendor_charges_per_row_with_a_floor():
    assert page_cost("dataforseo", 1000) == Decimal("0.600000")
    # A tiny page still pays the per-request floor rather than rounding to free.
    assert page_cost("dataforseo", 1) > Decimal("0")


# --------------------------------------------------------------------------
# The registry — DRY_RUN cannot reach a paid index
# --------------------------------------------------------------------------


def test_the_module_is_off_by_default():
    from types import SimpleNamespace

    assert get_backlink_source(SimpleNamespace(backlinks_enabled=False, dry_run=True)) is None


def test_dry_run_forces_the_mock_even_with_a_vendor_configured():
    from types import SimpleNamespace

    source = get_backlink_source(
        SimpleNamespace(backlinks_enabled=True, dry_run=True, backlink_vendor="dataforseo")
    )
    assert isinstance(source, MockBacklinkSource)


def test_an_unrecognised_vendor_is_not_measured_rather_than_mocked():
    """Falling back to fixtures here would look exactly like real data."""

    from types import SimpleNamespace

    assert (
        get_backlink_source(
            SimpleNamespace(backlinks_enabled=True, dry_run=False, backlink_vendor="acme-links")
        )
        is None
    )


# --------------------------------------------------------------------------
# Measurability — the gate in front of every absence claim
# --------------------------------------------------------------------------


def _page(rows: int, coverage: str = "complete") -> BacklinkPage:
    return BacklinkPage(
        subject_domain=SUBJECT,
        rows=tuple(
            BacklinkRow(
                source_url=f"https://s{i}.example/p",
                source_domain=f"s{i}.example",
                target_url=f"https://{SUBJECT}/",
            )
            for i in range(rows)
        ),
        coverage_status=coverage,  # type: ignore[arg-type]
    )


def test_a_truncated_page_is_never_measurable():
    assert is_measurable(_page(100, "partial"), previous_rows=100) is False
    assert is_measurable(_page(0, "empty"), previous_rows=100) is False
    assert is_measurable(_page(0, "failed"), previous_rows=100) is False


def test_a_collapsed_page_is_not_measurable_even_when_the_vendor_calls_it_complete():
    """A vendor's 'complete' is a claim. A 90% drop is better explained by a bug."""

    assert is_measurable(_page(10), previous_rows=100) is False


def test_a_first_import_is_measurable_with_nothing_to_compare_against():
    assert is_measurable(_page(10), previous_rows=None) is True


def test_a_small_but_stable_profile_stays_measurable():
    assert is_measurable(_page(9), previous_rows=10) is True


# --------------------------------------------------------------------------
# The delta engine, across cycles
# --------------------------------------------------------------------------


def test_first_import_records_everything_as_new(db_session, project):
    outcome = _run(db_session, project, cycle=0)

    assert outcome.measurable is True
    assert outcome.new_links == outcome.rows_ingested > 0
    assert outcome.lost_links == 0
    assert outcome.cost_usd == Decimal("0")

    stored = db_session.scalars(sa.select(Backlink)).all()
    assert len(stored) == outcome.rows_ingested
    assert all(link.status == "active" for link in stored)


def test_link_birth_uses_the_vendors_first_seen_not_our_storage_date(db_session, project):
    """Otherwise a plan-cap change re-mints every link as 'new'."""

    _run(db_session, project, cycle=0)
    link = db_session.scalars(sa.select(Backlink)).first()
    assert link is not None
    # SQLite drops tzinfo on round-trip, so compare naive-to-naive rather than
    # asserting something about the storage layer we do not mean to assert.
    first_seen = link.first_seen_at.replace(tzinfo=None)
    # EPOCH-derived, from the mock's vendor_first_seen — not the import moment.
    assert first_seen < datetime(2026, 6, 1)
    assert first_seen >= EPOCH.replace(tzinfo=None)


def test_a_second_import_adds_births_without_re_minting_the_old_ones(db_session, project):
    _run(db_session, project, cycle=0)
    outcome = _run(db_session, project, cycle=1, day=7)

    assert outcome.new_links == 2, "the two links the mock adds at cycle 1"
    # The dropped one is only provisional after a single miss.
    assert outcome.lost_links == 0

    missing = db_session.scalars(
        sa.select(Backlink).where(Backlink.status == "missing_pending")
    ).all()
    assert len(missing) == 1
    assert missing[0].source_domain == "forum.example"


def test_a_link_is_only_lost_after_repeated_misses(db_session, project):
    _run(db_session, project, cycle=0)
    _run(db_session, project, cycle=1, day=7)
    outcome = _run(db_session, project, cycle=1, day=14)

    assert MISSES_BEFORE_LOST == 2
    assert outcome.lost_links == 1
    lost = db_session.scalars(sa.select(Backlink).where(Backlink.status == "lost")).all()
    assert [link.source_domain for link in lost] == ["forum.example"]
    assert lost[0].lost_reason == "absent_from_index"


def test_a_returning_link_is_regained_not_born_again(db_session, project):
    _run(db_session, project, cycle=0)
    _run(db_session, project, cycle=1, day=7)
    outcome = _run(db_session, project, cycle=2, day=14)

    assert outcome.regained_links == 1
    events = db_session.scalars(sa.select(LinkEvent).where(LinkEvent.kind == "regained")).all()
    assert len(events) == 1
    assert events[0].source_domain == "forum.example"

    # And crucially: it did NOT also count as a birth.
    births = db_session.scalars(
        sa.select(LinkEvent).where(
            LinkEvent.kind == "new", LinkEvent.source_domain == "forum.example"
        )
    ).all()
    assert len(births) == 1, "only the original cycle-0 birth"


def test_an_anchor_rewrite_is_a_change_not_a_replacement(db_session, project):
    _run(db_session, project, cycle=0)
    _run(db_session, project, cycle=1, day=7)
    outcome = _run(db_session, project, cycle=2, day=14)

    assert outcome.changed_links >= 1
    change = db_session.scalars(sa.select(LinkEvent).where(LinkEvent.kind == "changed")).first()
    assert change is not None
    assert change.detail["field"] == "anchor"
    assert change.detail["from"] != change.detail["to"]


def test_a_truncated_refresh_records_what_it_saw_and_claims_no_losses(db_session, project):
    """The headline test: a bad pull must never look like a catastrophe."""

    _run(db_session, project, cycle=0)
    before = db_session.scalars(
        sa.select(sa.func.count()).select_from(Backlink).where(Backlink.status == "active")
    ).one()

    outcome = _run(db_session, project, cycle=3, day=7)

    assert outcome.coverage_status == "partial"
    assert outcome.measurable is False
    assert outcome.lost_links == 0

    still_active = db_session.scalars(
        sa.select(sa.func.count()).select_from(Backlink).where(Backlink.status == "active")
    ).one()
    assert still_active == before, "no link was demoted by an untrustworthy pull"
    assert (
        db_session.scalars(
            sa.select(sa.func.count()).select_from(LinkEvent).where(LinkEvent.kind == "lost")
        ).one()
        == 0
    )


def test_an_unavailable_index_degrades_the_refresh_instead_of_failing(db_session, project):
    class _Broken:
        name = "mock"

        def fetch_backlinks(self, subject_domain, *, cursor=None):
            raise BacklinkSourceUnavailable("index down")

        def price_estimate(self, subject_domain):
            return Decimal("0")

    outcome = run_import(
        db_session,
        source=_Broken(),
        org_id=project.org_id,
        project_id=project.id,
        subject_domain=SUBJECT,
        meter=False,
    )
    db_session.commit()

    assert outcome.measurable is False
    assert outcome.coverage_status == "failed"
    assert outcome.lost_links == 0
    record = db_session.get(BacklinkImport, outcome.import_id)
    assert record.status == "failed" and record.error


def test_every_import_records_its_provenance(db_session, project):
    outcome = _run(db_session, project, cycle=0)
    record = db_session.get(BacklinkImport, outcome.import_id)
    assert record.provenance["vendor"] == "mock"
    assert "fetched_at" in record.provenance
    assert record.provenance["coverage_note"]


# --------------------------------------------------------------------------
# Rollups, authority, velocity
# --------------------------------------------------------------------------


def test_rollups_group_links_by_referring_domain(db_session, project):
    _run(db_session, project, cycle=0)
    rollups = db_session.scalars(sa.select(ReferringDomainRollup)).all()
    assert rollups
    assert all(r.subject_domain == SUBJECT for r in rollups)
    assert (
        sum(r.links_count for r in rollups)
        == db_session.scalars(sa.select(sa.func.count()).select_from(Backlink)).one()
    )


def test_authority_is_bounded_and_decomposes(db_session, project):
    _run(db_session, project, cycle=0)
    score = compute_authority(db_session, project_id=project.id, subject_domain=SUBJECT)

    assert 0 <= score.value <= 100
    assert score.version == "1.0"
    for term in ("reach", "quality", "trust", "diversity"):
        assert term in score.components
        assert "points" in score.components[term]
        assert score.components[term]["explains"]
    # The points must actually add up to the score the user is shown.
    total = sum(score.components[t]["points"] for t in ("reach", "quality", "trust", "diversity"))
    assert abs(total - score.value) <= 1.0
    assert score.components["caveats"], "a published formula states its limits"


def test_an_empty_profile_scores_zero_rather_than_erroring(db_session, project):
    score = compute_authority(db_session, project_id=project.id, subject_domain=SUBJECT)
    assert score.value == 0


def test_velocity_reads_the_import_snapshots(db_session, project):
    _run(db_session, project, cycle=0)
    _run(db_session, project, cycle=1, day=7)
    series = velocity(db_session, project_id=project.id, subject_domain=SUBJECT)

    assert len(series) == 2
    assert series[-1]["new"] == 2
    assert all("measurable" in point for point in series)


# --------------------------------------------------------------------------
# Toxicity — advisory, and every flag decomposes
# --------------------------------------------------------------------------


def test_band_thresholds():
    assert band_for(0) == "low"
    assert band_for(45) == "medium"
    assert band_for(85) == "high"


def test_the_link_farm_in_the_fixture_is_flagged_with_reasons(db_session, project):
    _run(db_session, project, cycle=0)
    assess_project(db_session, project_id=project.id, subject_domain=SUBJECT)
    db_session.commit()

    flagged = db_session.scalars(
        sa.select(ReferringDomainRollup).where(
            ReferringDomainRollup.toxicity_band.in_(("medium", "high"))
        )
    ).all()
    assert flagged, "the seeded /24 link farm should surface"
    for rollup in flagged:
        assert rollup.toxicity_reasons, "a band without reasons is a bug"
        for reason in rollup.toxicity_reasons:
            assert reason["code"] and reason["label"] and reason["evidence"]
        assert rollup.toxicity_score == min(
            100, sum(r["weight"] for r in rollup.toxicity_reasons)
        ), "the reasons must sum to the number shown"


def test_a_reputable_domain_is_not_flagged(db_session, project):
    _run(db_session, project, cycle=0)
    assess_project(db_session, project_id=project.id, subject_domain=SUBJECT)
    db_session.commit()

    reputable = db_session.scalars(
        sa.select(ReferringDomainRollup).where(ReferringDomainRollup.domain_authority >= 60)
    ).all()
    assert reputable
    assert all(r.toxicity_band == "low" for r in reputable)


def test_the_disavow_file_is_valid_google_format_and_carries_its_reasoning(db_session, project):
    _run(db_session, project, cycle=0)
    assess_project(db_session, project_id=project.id, subject_domain=SUBJECT)
    db_session.commit()

    text = disavow_file(
        db_session, project_id=project.id, subject_domain=SUBJECT, minimum_band="medium"
    )

    assert "REVIEW BEFORE SUBMITTING" in text
    assert "has not submitted anything on your behalf" in text
    domains = [line for line in text.splitlines() if line.startswith("domain:")]
    assert domains, "the fixture contains flaggable domains"
    for line in text.splitlines():
        # Google's format: comments or domain:/url entries, nothing else.
        assert line == "" or line.startswith("#") or line.startswith("domain:")


def test_a_clean_profile_produces_an_empty_but_explicit_disavow_file(db_session, project):
    text = disavow_file(db_session, project_id=project.id, subject_domain=SUBJECT)
    assert "Nothing to disavow" in text
    assert not [line for line in text.splitlines() if line.startswith("domain:")]


# --------------------------------------------------------------------------
# Gap analysis and the citation-derived opportunity list
# --------------------------------------------------------------------------


def test_gap_lists_domains_that_link_to_rivals_but_not_to_us(db_session, project):
    _run(db_session, project, cycle=0)

    # A competitor's profile, stored rollup-only exactly as the design says.
    db_session.add_all(
        [
            ReferringDomainRollup(
                org_id=project.org_id,
                project_id=project.id,
                subject_domain="rival.example",
                subject_kind="competitor",
                referring_domain="bigmag.example",
                links_count=3,
                follow_links=3,
                domain_authority=88.0,
            ),
            # ...and one that already links to us, which must NOT be a gap.
            ReferringDomainRollup(
                org_id=project.org_id,
                project_id=project.id,
                subject_domain="rival.example",
                subject_kind="competitor",
                referring_domain="directory.example",
                links_count=1,
                follow_links=1,
                domain_authority=31.0,
            ),
        ]
    )
    db_session.commit()

    rows = link_gap(db_session, project_id=project.id, own_domain=SUBJECT)
    names = [row.referring_domain for row in rows]

    assert "bigmag.example" in names
    assert "directory.example" not in names, "it already links to us"
    assert rows[0].referring_domain == "bigmag.example", "ranked by competitors × authority"


def test_unlinked_mentions_come_from_citation_evidence_with_no_vendor_call(db_session, project):
    """The differentiator: a page that named the brand but never linked to it."""

    from app.db.models import Analysis, GeoRecord, Prompt, Response, SerpCheck

    analysis = Analysis(url=f"https://{SUBJECT}/", status="done")
    db_session.add(analysis)
    db_session.flush()
    prompt = Prompt(analysis_id=analysis.id, text="best widgets", category="rec")
    db_session.add(prompt)
    db_session.flush()
    response = Response(
        analysis_id=analysis.id,
        prompt_id=prompt.id,
        engine="measured",
        model="mock",
        raw_text="Acme is good.",
    )
    db_session.add(response)
    db_session.flush()
    db_session.add_all(
        [
            GeoRecord(
                analysis_id=analysis.id,
                response_id=response.id,
                brand="Acme",
                prompt="best widgets",
                citations=[
                    {
                        "url": "https://reviewsite.example/roundup",
                        "source_domain": "reviewsite.example",
                        "source_title": "Widget roundup 2026",
                    },
                    # Already links to us in the fixture — must be excluded.
                    {
                        "url": "https://directory.example/listing",
                        "source_domain": "directory.example",
                        "source_title": "Directory",
                    },
                ],
            ),
            SerpCheck(
                analysis_id=analysis.id,
                query="acme reviews",
                source="mock",
                hit=True,
                matched_url="https://newsblog.example/acme-story",
                matched_snippet="Acme announced...",
                matched_via="text",
            ),
        ]
    )
    db_session.commit()

    _run(db_session, project, cycle=0)

    mentions = unlinked_mentions(db_session, project_id=project.id, own_domain=SUBJECT)
    domains = {m.source_domain for m in mentions}

    assert "reviewsite.example" in domains, "cited in an AI answer, never linked"
    assert "newsblog.example" in domains, "named in search results, never linked"
    assert "directory.example" not in domains, "already links to us"
    assert {m.seen_via for m in mentions} <= {"ai_citation", "search_result"}


def test_anchor_distribution_is_computed_on_read(db_session, project):
    _run(db_session, project, cycle=0)
    distribution = anchor_distribution(db_session, project_id=project.id, subject_domain=SUBJECT)
    assert distribution["total"] > 0
    assert sum(distribution["counts"].values()) == distribution["total"]
    assert abs(sum(distribution["shares"].values()) - 1.0) < 0.001


# --------------------------------------------------------------------------
# Tenant isolation — the M1 gate applies to this module too
# --------------------------------------------------------------------------


def test_every_backlink_row_carries_its_org(db_session, project):
    _run(db_session, project, cycle=0)
    for model in (Backlink, BacklinkImport, LinkEvent, ReferringDomainRollup):
        rows = db_session.scalars(sa.select(model)).all()
        assert rows, model.__name__
        assert all(row.org_id == project.org_id for row in rows), model.__name__


def test_one_projects_links_are_invisible_to_another(db_session, project):
    _run(db_session, project, cycle=0)

    other_org = Organization(name="Other", slug="other", kind="company")
    db_session.add(other_org)
    db_session.flush()
    other_ws = Workspace(org_id=other_org.id, name="D", slug="default", is_default=True)
    db_session.add(other_ws)
    db_session.flush()
    other = Project(
        org_id=other_org.id,
        workspace_id=other_ws.id,
        name="Other",
        domain="https://other.example/",
        domain_key="other.example",
    )
    db_session.add(other)
    db_session.commit()

    assert (
        db_session.scalars(
            sa.select(sa.func.count()).select_from(Backlink).where(Backlink.project_id == other.id)
        ).one()
        == 0
    )
    assert compute_authority(db_session, project_id=other.id, subject_domain=SUBJECT).value == 0
    assert link_gap(db_session, project_id=other.id, own_domain="other.example") == []


# --------------------------------------------------------------------------
# Metering — no path reaches a paid index without a reservation (P7.6)
# --------------------------------------------------------------------------


def test_a_metered_import_reserves_quota_and_settles_the_real_cost(db_session, project):
    from app.services import billing

    billing.seed_plans(db_session)
    plan = db_session.scalar(sa.select(Plan).where(Plan.key == "pro"))
    db_session.add(Subscription(org_id=project.org_id, plan_id=plan.id, status="active"))
    billing.grant_credit(db_session, project.org_id, Decimal("10"))
    db_session.commit()

    outcome = run_import(
        db_session,
        source=MockBacklinkSource(cycle=0),
        org_id=project.org_id,
        project_id=project.id,
        subject_domain=SUBJECT,
        now=datetime(2026, 6, 1, tzinfo=UTC),
    )
    db_session.commit()

    assert (
        billing.usage(
            db_session,
            project.org_id,
            billing.METRIC_BACKLINK_REFRESHES,
            now=datetime(2026, 6, 1, tzinfo=UTC),
        )
        == 1
    )
    # The mock is free — and the ledger says so explicitly rather than by
    # having no row at all.
    entry = db_session.scalars(
        sa.select(CreditLedgerEntry).order_by(CreditLedgerEntry.created_at.desc())
    ).first()
    assert entry is not None
    assert entry.source_type == "backlink_import"
    assert entry.source_id == outcome.import_id
    assert entry.delta_usd == Decimal("0")


def test_a_plan_without_backlinks_cannot_start_an_import_at_all(db_session, project):
    """Free has 0 refreshes — the refusal happens before the vendor is called."""

    from app.services import billing

    billing.seed_plans(db_session)
    plan = db_session.scalar(sa.select(Plan).where(Plan.key == "free"))
    db_session.add(Subscription(org_id=project.org_id, plan_id=plan.id, status="active"))
    db_session.commit()

    with pytest.raises(billing.QuotaExceeded):
        run_import(
            db_session,
            source=MockBacklinkSource(cycle=0),
            org_id=project.org_id,
            project_id=project.id,
            subject_domain=SUBJECT,
            now=datetime(2026, 6, 1, tzinfo=UTC),
        )


def test_a_failed_import_still_settles_so_the_attempt_is_visible(db_session, project):
    from app.services import billing

    billing.seed_plans(db_session)
    plan = db_session.scalar(sa.select(Plan).where(Plan.key == "pro"))
    db_session.add(Subscription(org_id=project.org_id, plan_id=plan.id, status="active"))
    db_session.commit()

    class _Broken:
        name = "mock"

        def fetch_backlinks(self, subject_domain, *, cursor=None):
            raise BacklinkSourceUnavailable("index down")

        def price_estimate(self, subject_domain):
            return Decimal("0")

    run_import(
        db_session,
        source=_Broken(),
        org_id=project.org_id,
        project_id=project.id,
        subject_domain=SUBJECT,
        now=datetime(2026, 6, 1, tzinfo=UTC),
    )
    db_session.commit()

    assert db_session.scalar(sa.select(sa.func.count()).select_from(CreditLedgerEntry)) == 1
