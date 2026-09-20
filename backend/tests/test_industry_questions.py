import json
import uuid

import pytest
from sqlalchemy import select

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import AuditEvent, Membership, UsageCounter
from app.industry_citations import routes
from app.providers.base import ProviderResult

PATH = "/api/v1/industry-citations/questions"
BODY = {"industry": "Running shoes", "country": "Türkiye", "language": "tr"}
QUESTIONS = [
    f"Türkiye'de koşu ayakkabısı seçiminde {index} numaralı kriter nedir?" for index in range(10)
]


class FakeLLM:
    model = "test/model"

    def __init__(self, text=None):
        self.text = text or json.dumps({"questions": QUESTIONS})
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return ProviderResult(text=self.text, model=self.model, cost_usd=0.001)


@pytest.fixture()
def llm(monkeypatch):
    fake = FakeLLM()
    app.dependency_overrides[get_settings] = lambda: Settings(dry_run=False, open_router_key="test")
    monkeypatch.setattr(routes, "get_measured_llm", lambda settings: fake)
    yield fake
    app.dependency_overrides.pop(get_settings, None)


def test_auth_required(client, llm):
    assert client.post(PATH, json=BODY).status_code == 401
    assert not llm.calls


def test_generates_questions_with_market_and_language(client, signed_in, llm, db_session):
    signed_in()
    response = client.post(PATH, json={**BODY, "industry": " Running shoes "})
    assert response.status_code == 200
    assert response.json() == {
        **BODY,
        "questions": QUESTIONS,
        "model": "test/model",
        "cost_usd": 0.001,
    }
    messages, options = llm.calls[0]
    assert json.loads(messages[1]["content"]) == BODY
    assert options["max_tokens"] == 3000
    assert options["json_object"] is True
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "industry_questions:generate")
    )
    assert event.detail["cost_usd"] == 0.001
    assert db_session.scalar(select(UsageCounter.used)) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"industry": " "},
        {"country": " "},
        {"language": "zz"},
        {"language": "english"},
        {"industry": "x" * 201},
        {"count": 100},
    ],
)
def test_invalid_inputs_never_call_provider(client, signed_in, llm, changes):
    signed_in()
    assert client.post(PATH, json={**BODY, **changes}).status_code == 422
    assert not llm.calls


@pytest.mark.parametrize(
    "text",
    [
        "bad JSON secret provider response",
        json.dumps({"questions": QUESTIONS[:9]}),
        json.dumps({"questions": [QUESTIONS[0]] * 10}),
        json.dumps({"questions": [" "] + QUESTIONS[1:]}),
    ],
)
def test_invalid_provider_response_is_not_returned(client, signed_in, llm, db_session, text):
    signed_in()
    llm.text = text
    response = client.post(PATH, json=BODY)
    assert response.status_code == 502
    assert "secret" not in response.text
    assert len(llm.calls) == 1
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "industry_questions:generate")
    )
    assert event.outcome == "error"
    assert event.detail["cost_usd"] == 0.001


def test_dry_run_returns_unavailable_without_fake_questions(client, signed_in, llm):
    signed_in()
    app.dependency_overrides[get_settings] = lambda: Settings(dry_run=True)
    assert client.post(PATH, json=BODY).status_code == 503
    assert not llm.calls


def test_hourly_limit_persists_and_blocks_before_spend(client, signed_in, llm, db_session):
    signed_in()
    assert client.post(PATH, json=BODY).status_code == 200
    counter = db_session.scalar(select(UsageCounter))
    counter.used = 10
    db_session.commit()
    response = client.post(PATH, json=BODY)
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 3600
    assert len(llm.calls) == 1


def test_other_org_is_denied(client, signed_in, llm):
    signed_in()
    assert client.post(PATH, json=BODY, headers={"X-Org-Id": str(uuid.uuid4())}).status_code == 403
    assert not llm.calls


def test_viewer_cannot_generate(client, signed_in, llm, db_session):
    user, org = signed_in()
    member = db_session.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.org_id == org.id)
    )
    member.role = "viewer"
    db_session.commit()
    assert client.post(PATH, json=BODY).status_code == 403
    assert not llm.calls
