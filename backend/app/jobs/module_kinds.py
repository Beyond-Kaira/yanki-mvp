"""Standalone module worker job kinds (mod-6 / ADR-52)."""

from __future__ import annotations

JOB_KIND_SERP_RUN = "serp_run"
JOB_KIND_GEO_RUN = "geo_run"
JOB_KIND_KYC_EXTRACT = "kyc_extract"

MODULE_JOB_KINDS = frozenset({JOB_KIND_SERP_RUN, JOB_KIND_GEO_RUN, JOB_KIND_KYC_EXTRACT})
