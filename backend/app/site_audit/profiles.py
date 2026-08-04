"""Browser/robots identities exposed by the Site Audit API."""

from app.site_audit.models import AuditProfileId, CrawlerProfile

_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Mobile Safari/537.36 "
    "(compatible; YankiSiteAuditBot/0.1)"
)

_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 "
    "(compatible; YankiSiteAuditBot/0.1)"
)


PROFILES: dict[AuditProfileId, CrawlerProfile] = {
    "site_audit_mobile": CrawlerProfile(
        profile_id="site_audit_mobile",
        label="Site Audit Bot (Mobile)",
        browser_user_agent=_MOBILE_UA,
        robots_user_agent="YankiSiteAuditBot",
        viewport_width=390,
        viewport_height=844,
        is_mobile=True,
        has_touch=True,
    ),
    "site_audit_desktop": CrawlerProfile(
        profile_id="site_audit_desktop",
        label="Site Audit Bot (Desktop)",
        browser_user_agent=_DESKTOP_UA,
        robots_user_agent="YankiSiteAuditBot",
        viewport_width=1440,
        viewport_height=900,
        is_mobile=False,
        has_touch=False,
    ),
}


def get_profile(profile_id: AuditProfileId) -> CrawlerProfile:
    return PROFILES[profile_id]
