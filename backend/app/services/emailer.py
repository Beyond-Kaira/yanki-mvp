"""Transactional email via the Resend REST API (P5.13).

One tiny surface: ``send_email`` POSTs to ``https://api.resend.com/emails`` with
a Bearer ``resend_api_key``, a 5s timeout, over plain ``httpx`` (no vendor SDK —
zero new deps; see ADR-25). It is deliberately **fail-open** and **env-gated**:

- a NO-OP (returns ``False``) unless ``emails_enabled`` AND ``resend_api_key`` is
  non-empty, so no environment sends mail until the operator opts in;
- it NEVER raises — every error (HTTP status, timeout, connection, anything) is
  swallowed, logged as a short warning that names neither the recipient nor the
  key, and reported as a ``False`` return.

Callers therefore treat email as best-effort telemetry: a waitlist signup is
recorded in ``waitlist_signups`` and a run is recorded in ``analyses``
regardless of whether the alert mail goes out.

The compose helpers (``send_waitlist_emails``, ``send_run_alert``) build the
bodies and route them, and inherit the same never-raises guarantee because they
only ever call ``send_email``.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.config import Settings
from app.db.models import Analysis

logger = logging.getLogger("yanki.emailer")

RESEND_ENDPOINT = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 5.0

_THANK_YOU_TEXT = (
    "Hi there, and welcome to Yanki!\n\n"
    "Yanki shows you how AI engines talk about your brand when people ask them "
    "for recommendations.\n\n"
    "Don't wait for launch to see it: run your first free analysis right now at\n"
    "https://yanki.beyondkaira.com\n\n"
    "It takes about a minute, and you'll get your GEO score plus every raw answer.\n\n"
    "- The Yanki team"
)


def send_email(to: str, subject: str, text: str, settings: Settings) -> bool:
    """Send one plain-text email via Resend. Returns True only on a 2xx.

    NO-OP (returns False) when email is disabled or unconfigured. NEVER raises:
    any failure is logged as a short warning (no recipient, no key) and returned
    as False.
    """
    if not settings.emails_enabled or not settings.resend_api_key:
        return False
    try:
        response = httpx.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "text": text,
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except Exception:
        # Deliberately log neither the recipient nor the key — just the subject,
        # which carries no PII, so a failure is diagnosable without leaking either.
        logger.warning("email send failed (subject=%r)", subject)
        return False


def send_waitlist_emails(email: str, total: int, settings: Settings) -> None:
    """On a NEW signup: thank the joiner, then alert the operator with the count.

    Best-effort — each call is a no-op when email is disabled and never raises.
    The operator notification is skipped when ``notify_email`` is unset.
    """
    send_email(email, "Thanks for joining the Yanki waitlist", _THANK_YOU_TEXT, settings)
    if settings.notify_email:
        body = f"New waitlist signup: {email}\n\nTotal signups: {total}"
        send_email(settings.notify_email, "New waitlist signup", body, settings)


def send_invitation_email(
    *,
    to: str,
    organization_name: str,
    role_label: str,
    accept_url: str,
    invited_by: str | None,
    expires_at: datetime,
    settings: Settings,
) -> bool:
    """Send one invitation link. Best-effort, like every other send here.

    Returns whether it went out, and the caller **surfaces that answer** rather
    than swallowing it: on a deployment with email disabled — which is every
    fresh one, since ``emails_enabled`` defaults False — an administrator who is
    told "invitation sent" would wait forever for something that never left the
    process. The API instead reports ``email_sent: false`` and hands back the
    link to pass on by hand.

    The body names who invited them and when the link dies, because an
    unexplained link asking for a password is indistinguishable from phishing.
    """

    inviter = f"{invited_by} has invited you" if invited_by else "You have been invited"
    body = (
        f"{inviter} to join {organization_name} on Yanki as a {role_label}.\n\n"
        f"Accept the invitation here:\n{accept_url}\n\n"
        f"The link works once and expires on {expires_at.strftime('%d %B %Y')}.\n"
        "If you were not expecting this, you can ignore this email — "
        "no account is created until you set a password.\n\n"
        "- The Yanki team"
    )
    return send_email(to, f"You're invited to {organization_name} on Yanki", body, settings)


def send_run_alert(analysis: Analysis, settings: Settings) -> None:
    """Alert the operator that a pipeline run reached a terminal status.

    Fired for ``done`` or ``failed`` runs. The record of the run lives in the
    ``analyses`` table — this is only an alert, so it is best-effort: a no-op when
    ``notify_email`` is unset or email is disabled, and it never raises.
    """
    if not settings.notify_email:
        return
    kind = analysis.kind or "mvp"
    if kind == "checker":
        target = f"{analysis.brand} / {analysis.category}"
    else:
        target = analysis.url
    lines = [
        f"kind: {kind}",
        f"target: {target}",
        f"status: {analysis.status}",
    ]
    if analysis.status == "done":
        lines.append(f"geo_score: {analysis.geo_score}")
    # Kind-aware public results page: checker runs live under /checker/<id>, all
    # other kinds under /analyses/<id>.
    path = "checker" if kind == "checker" else "analyses"
    lines.append(f"link: https://yanki.beyondkaira.com/{path}/{analysis.id}")
    send_email(
        settings.notify_email,
        f"Yanki run {analysis.status}",
        "\n".join(lines),
        settings,
    )
