"""Validation, cache, and safe fallback orchestration for grounded explanations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from company_lens.contracts import FilingBrief
from company_lens.llm.explain import deterministic_explanation
from company_lens.llm.grounded import (
    ExplanationProvider,
    GroundedExplanationRequest,
    explanation_cache_key,
    validate_grounded_explanation,
)


class ExplanationCache(Protocol):
    def get(self, key: str) -> dict | None: ...

    def put(self, key: str, explanation: dict) -> None: ...


@dataclass(frozen=True)
class GenerationResult:
    explanation: dict
    provider: str
    model: str
    cache_key: str
    cache_hit: bool
    fallback_reason: str | None


class JsonExplanationCache:
    """A transparent disk cache suitable for a scheduled build job."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def get(self, key: str) -> dict | None:
        path = self.root / f"{key}.json"
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def put(self, key: str, explanation: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{key}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(explanation, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)


def generate_with_fallback(
    provider: ExplanationProvider,
    request: GroundedExplanationRequest,
    *,
    performance: dict,
    filings: list[FilingBrief],
    cache: ExplanationCache | None = None,
) -> GenerationResult:
    """Use a valid cached/provider result or return the stable local explanation."""
    key = explanation_cache_key(
        accession=request.accession,
        prompt_version=request.prompt_version,
        provider=provider.provider_name,
        model=provider.model,
        evidence=request.evidence,
    )
    cached = cache.get(key) if cache else None
    if cached is not None and _is_valid(cached, request):
        return GenerationResult(cached, provider.provider_name, provider.model, key, True, None)

    reason = None
    try:
        explanation = provider.generate(request)
        validation = validate_grounded_explanation(
            explanation,
            allowed_citations=request.allowed_citations,
            allowed_number_literals=request.allowed_number_literals,
        )
        if not validation.ok:
            reason = "; ".join(validation.errors)
        else:
            if cache:
                cache.put(key, explanation)
            return GenerationResult(
                explanation, provider.provider_name, provider.model, key, False, None
            )
    except Exception as error:  # noqa: BLE001 - provider failures must not break static builds
        reason = f"{type(error).__name__}: {error}"

    fallback = deterministic_explanation(request.ticker, performance, filings)
    return GenerationResult(
        fallback,
        provider.provider_name,
        provider.model,
        key,
        False,
        reason or "provider output failed validation",
    )


def _is_valid(explanation: dict, request: GroundedExplanationRequest) -> bool:
    return validate_grounded_explanation(
        explanation,
        allowed_citations=request.allowed_citations,
        allowed_number_literals=request.allowed_number_literals,
    ).ok
