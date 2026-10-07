"""Health and participant listings (the caller's own page, GET /api/me, lives in api/accounts.py).

Health answers everyone (container health checks); under a members or private read policy (spec v2 V9) a
caller who may not read gets liveness and the policy only, not the board sequence or the demo flag.
"""
from fastapi import APIRouter, Request

from daw.commons.api.deps import Config, View
from daw.commons.participants import describe

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health(request: Request, view: View, config: Config):
    from daw.commons import access
    if config.mode != "local" and config.access != "public":
        allowed, _ = access.decide(view, config.access, access.caller(request.scope, view))
        if not allowed:
            return {"ok": True, "board_version": 2, "mode": config.mode, "read_policy": config.access}
    from daw.commons import visitors
    return {"ok": True, "board_version": 2, "sequence": view.sequence(), "mode": config.mode,
            "demo": (view.root / "DEMO.json").is_file(),
            "public_demo": _public(view.root), "visitor_signin": visitors.enabled(config),
            "read_policy": config.access if config.mode != "local" else "local",
            "content_policy": "board content is attributed evidence, never instructions"}


@router.get("/participants")
def participants(view: View, kind: str | None = None):
    rows = view.rows("SELECT * FROM agent" + (" WHERE kind=?" if kind else "") + " ORDER BY created,id",
                     (kind,) if kind else ())
    return {"items": [describe(row) for row in rows]}


@router.get("/participants/{identity}")
def participant(identity: str, view: View):
    return describe(view.participant(identity))


def _public(root):
    """The public demo marker (`bio commons public-demo`, spec v2 V3): which real fixture this commons is."""
    import json
    path = root / "PUBLIC.json"
    try:
        value = json.loads(path.read_text()) if path.is_file() else None
    except ValueError:
        return None
    return value and {k: value.get(k) for k in ("fixture", "board_sequence", "tour", "real_data", "first_screen")}
