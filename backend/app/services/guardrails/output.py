"""Output guardrail: JSON-schema validation with retry-with-correction.

Every LangGraph agent node that calls an LLM must return structured JSON.
We validate with the node's Pydantic model; on failure we compose a
correction prompt containing the exact validator error and ask the LLM
to re-emit. Bounded by settings.output_validation_max_retries.

This is the interview claim "JSON schema validation on every agent output
before it passes downstream. Failed validation triggers a retry with a
corrected prompt or falls back to a safer handler" — implemented here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ...core.config import get_settings
from ...core.errors import ValidationRetryExceeded
from ...core.logging import get_logger

T = TypeVar("T", bound=BaseModel)
log = get_logger(__name__)

# Extractor for the first JSON object in a possibly-chatty LLM response.
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> str:
    m = _JSON_RE.search(raw)
    return m.group(0) if m else raw


def validate_output(raw: str, schema: type[T]) -> T:
    """One-shot validation. Raises ValidationError on failure."""
    return schema.model_validate_json(_extract_json(raw))


async def retry_with_correction(
    *,
    schema: type[T],
    call: Callable[[str | None], Awaitable[str]],
    max_retries: int | None = None,
) -> T:
    """Call an LLM that must return JSON conforming to `schema`.

    Strategy:
        attempt 1: call(correction=None)                     → parse
        attempt 2: call(correction=<pydantic error as string>) → parse
        ...
    After max_retries failed attempts, raises ValidationRetryExceeded —
    the LangGraph router is expected to route to the fallback node on
    that exception.
    """
    limit = max_retries if max_retries is not None else get_settings().output_validation_max_retries
    correction: str | None = None
    last_error: str | None = None

    for attempt in range(1, limit + 2):  # +1 original, +limit retries
        raw = await call(correction)
        try:
            return validate_output(raw, schema)
        except ValidationError as e:
            last_error = _format_error(e)
            log.warning(
                "output.validation_failed",
                attempt=attempt,
                error_preview=last_error[:300],
            )
            correction = _build_correction_prompt(schema, raw, last_error)
            continue

    raise ValidationRetryExceeded(
        "output failed schema validation after retries",
        detail={"schema": schema.__name__, "last_error": last_error},
    )


def _format_error(e: ValidationError) -> str:
    # Compact one-line-per-issue, no object dumps — safe to re-inject into a prompt.
    lines = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"])
        lines.append(f"- at `{loc}`: {err['msg']}")
    return "\n".join(lines)


def _build_correction_prompt(schema: type[BaseModel], previous_raw: str, error: str) -> str:
    try:
        json_schema = json.dumps(schema.model_json_schema(), indent=2)
    except Exception:  # noqa: BLE001
        json_schema = schema.__name__

    return (
        "Your previous response failed JSON-schema validation.\n\n"
        f"Validation errors:\n{error}\n\n"
        f"Required JSON schema:\n{json_schema}\n\n"
        "Return only a single valid JSON object that satisfies the schema. "
        "Do not include prose, markdown fences, or explanations."
    )
