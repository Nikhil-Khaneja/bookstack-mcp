"""Thin MLflow facade. No-op when MLFLOW_TRACKING_URI is unset.

Used by eval/run_eval.py to log each evaluation run (parameters,
retrieval metrics, prompt version). When enabled, runs become browsable
at the MLflow UI; when disabled, code that calls log_eval_run() just
returns a context manager that does nothing.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext

from ...core.config import get_settings
from ...core.logging import get_logger

log = get_logger(__name__)


@contextmanager
def log_eval_run(*, run_name: str, params: dict, metrics: dict):
    """Context manager that logs params+metrics if MLflow is configured."""
    s = get_settings()
    if not s.mlflow_enabled:
        with nullcontext():
            yield None
        return
    try:
        import mlflow  # local import so MLflow is truly optional at runtime

        mlflow.set_tracking_uri(s.mlflow_tracking_uri)
        mlflow.set_experiment("bookstack-mcp-rag")
        with mlflow.start_run(run_name=run_name) as run:
            for k, v in (params or {}).items():
                mlflow.log_param(k, v)
            for k, v in (metrics or {}).items():
                try:
                    mlflow.log_metric(k, float(v))
                except (TypeError, ValueError):
                    pass
            yield run
    except Exception as e:  # noqa: BLE001
        log.warning("mlflow.skip", error=str(e))
        with nullcontext():
            yield None
