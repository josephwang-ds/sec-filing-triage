"""Which named settings exist. Values are never returned or logged."""

from __future__ import annotations

import os
from collections.abc import Mapping

CONFIG_NAMES = (
    "FINNHUB_API_KEY",
    "EDGAR_USER_AGENT",
    "BLOB_READ_WRITE_TOKEN",
    "VERCEL_TOKEN",
    "VERCEL_ORG_ID",
    "VERCEL_PROJECT_ID",
    "COMPANY_LENS_ASK_KV_REST_URL",
    "COMPANY_LENS_ASK_KV_REST_TOKEN",
    "EVENTS_RERUN_TOKEN",
    "EVENTS_MONITOR_WEBHOOK",
)


def presence(environ: Mapping[str, str] | None = None) -> dict[str, bool]:
    source = os.environ if environ is None else environ
    return {name: bool(str(source.get(name, "")).strip()) for name in CONFIG_NAMES}


def format_presence(flags: dict[str, bool]) -> str:
    lines = [f"{name}={'present' if flags[name] else 'missing'}" for name in CONFIG_NAMES]
    return "\n".join(lines)
