"""Evaluation dashboard, cohorts and comparisons (M9.2–M9.4). Read-only.

Handlers never write: stale or missing `run_metrics` rows are computed in memory;
the operator stores them with `bio commons metrics refresh`.
"""
from fastapi import APIRouter

from daw.commons import metrics
from daw.commons.api.deps import View
from daw.commons.api.scoping import Scoped, question_lookup, scoped

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(view: View, cohort: str | None = None, participant: str | None = None, harness: str | None = None,
              task_type: str | None = None, bucket: str = "week"):
    return metrics.dashboard(view, cohort_id=cohort, participant=participant, harness=harness,
                             task_type=task_type, bucket=bucket)


@router.get("/metrics/runs")
def metric_runs(view: View, scope: Scoped, cohort: str | None = None, participant: str | None = None,
                harness: str | None = None, task_type: str | None = None):
    result = metrics.run_rows(view, cohort_id=cohort, participant=participant, harness=harness, task_type=task_type)
    if scope is None:
        return result
    questions = question_lookup(view)
    posts = {r["id"]: r["post"] for r in view.rows("SELECT id,post FROM request")}
    return scoped(result, scope, lambda r: ({r["participant"]}, questions(posts.get(r["request"])), r["created"],
                                            r.get("finished")))


@router.get("/cohorts")
def cohorts(view: View):
    return {"items": metrics.list_cohorts(view)}


@router.get("/cohorts/compare")
def compare(view: View, ids: str):
    return metrics.compare(view, [i for i in ids.split(",") if i.strip()])


@router.get("/harnesses/compare")
def harness_compare(view: View, cohorts: str = ""):
    """V17: one column per harness, criteria as separate cells, live only with a passing harness-check receipt."""
    return metrics.harness_comparison(view, [i for i in cohorts.split(",") if i.strip()])


@router.get("/cohorts/{identity}")
def cohort(identity: str, view: View, bucket: str = "week"):
    return metrics.cohort_view(view, identity, bucket)
