"""Versioned prompt templates.

Promotion rule: a new vN+1 directory may only be set as the active
PROMPT_VERSION after `eval/run_eval.py` shows no regression on the
fixed eval set. MLflow logs the metric deltas for each version.
"""

from __future__ import annotations

from pathlib import Path

from ...agents.state import AnalyzerOutput, WriterOutput  # noqa: F401  re-export convenience
from ....core.config import get_settings

_HERE = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load prompts/{version}/{name}.md from disk."""
    version = get_settings().prompt_version
    path = _HERE / version / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path}")
    return path.read_text(encoding="utf-8")
