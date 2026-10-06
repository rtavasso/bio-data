"""Evaluation dashboard, cohorts and comparisons (M9.2–M9.4). Read-only.

Handlers never write: stale or missing `run_metrics` rows are computed in memory;
the operator stores them with `bio commons metrics refresh`.
"""
from fastapi import APIRouter

from daw.commons import metrics
from daw.commons.api.deps import View

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(view: View, cohort: str | None = None, participant: str | None = None, harness: str | None = None,
              task_type: str | None = None, bucket: str = "week"):
    return metrics.dashboard(view, cohort_id=cohort, participant=participant, harness=harness,
                             task_type=task_type, bucket=bucket)


@router.get("/metrics/runs")
def metric_runs(view: View, cohort: str | None = None, participant: str | None = None, harness: str | None = None,
                task_type: str | None = None):
    return metrics.run_rows(view, cohort_id=cohort, participant=participant, harness=harness, task_type=task_type)


@router.get("/cohorts")
def cohorts(view: View):
    return {"items": metrics.list_cohorts(view)}


@router.get("/cohorts/compare")
def compare(view: View, ids: str):
    return metrics.compare(view, [i for i in ids.split(",") if i.strip()])


@router.get("/cohorts/{identity}")
def cohort(identity: str, view: View, bucket: str = "week"):
    return metrics.cohort_view(view, identity, bucket)
