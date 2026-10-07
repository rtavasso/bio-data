"""The PMP22 cohort as the public cohort commons (spec v2 V3, v3 V15).

`bio commons public-demo OUT` turns the committed, redacted cohort fixture into a commons a visitor can browse:

1. `fixture verify` must be green (every file against `FIXTURE.json`): the C0 redaction rules are the
   fixture's (downloaded bytes, session databases, transcripts, tool outputs and credentials are not in it).
2. The fixture is copied to OUT (never modified in place; OUT must be new or empty).
3. The curated tour (`docs/colloquy/tours/pmp22-cohort.json` by default) is re-checked against the copy and
   installed under `OUT/tours/`; a tour with a broken step is refused, so the served reading path is verified.
4. `commons.toml` sets the read policy `public` and, unless `visitors=False`, visitor sign-in (`[visitors]
   signin = true`, `daw.commons.visitors`): anyone reads; a visitor who signs in with a display name may comment
   and mark (attributed, rate-limited), nothing else.
5. `PUBLIC.json` records what this commons is: the fixture's name, board sequence and redaction rules, the
   moderation rule (C2: `moderation.Visibility` withholds hidden posts on every surface; a post hidden here
   stays a stub everywhere, the export included), the read policy, visitor sign-in, the first screen (the board,
   `/`), the tour and, with `--snapshot DIR`, the board snapshot (a content-addressed static export other commons
   import and cite as `snapshot:<id>/artifact_…`).

Serve it publicly with `bio commons --root OUT serve --host 0.0.0.0 --mode accounts` behind a TLS proxy
(`--forwarded-allow-ips`); the first screen is the board, the tour, the records (runs and their timelines) and
the dashboard are linked from it. Serving writes no record: GETs leave the board unchanged (a disposable map and
graph-store cache may be written under `cache/`). Locally, `serve` (local mode) shows the same pages without
sign-in. Nothing synthetic is added: no demo records, no claims written on the agents' behalf (the cohort has
none), no pointers inserted into posts. Curated pointers are people's (`daw.commons.curation`), attributed to
them; the tour's own steps are attributed to its curator.
"""
import shutil
from pathlib import Path

from daw.util import DawError, now, write_json

DEFAULT_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "pmp22-cohort"
DEFAULT_TOUR = Path(__file__).resolve().parents[3] / "docs" / "colloquy" / "tours" / "pmp22-cohort.json"


COMMONS_TOML = """# Public cohort commons (spec v3 V15), written by `bio commons public-demo`.
[access]
read = "public"

[visitors]
signin = {signin}
"""


def build(out, *, fixture=None, tour=None, snapshot=None, actor="operator", visitors=True):
    """Build the public demo commons at `out` (see the module docstring). Returns a summary."""
    import json

    from daw.commons import export, fixture as fixtures, tour as tours
    from daw.commons.archive import Archive
    from daw.community import Community
    source = Path(fixture or DEFAULT_FIXTURE).expanduser().resolve()
    out = Path(out).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise DawError("public_demo_output_not_empty", str(out))
    checked = fixtures.verify_fixture(source)
    if not checked["verified"] or checked["untracked"]:
        raise DawError("fixture_not_verified", f"changed {len(checked['changed'])}, missing {len(checked['missing'])}, "
                                               f"untracked {len(checked['untracked'])}")
    manifest = json.loads((source / "FIXTURE.json").read_text())
    if not manifest.get("real_data"):
        raise DawError("not_a_real_data_fixture", str(source))
    tour_data = tours.load(tour or DEFAULT_TOUR)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, out, symlinks=True, dirs_exist_ok=True)
    try:
        with Archive(out) as view:
            resolved = tours.resolve(view, tour_data)
        if resolved["summary"]["broken"]:
            broken = [f"step {s['step']}: {'; '.join(s['problems'])}" for s in resolved["steps"] if not s["ok"]]
            raise DawError("tour_steps_broken", " | ".join(broken))
        (out / "tours").mkdir(exist_ok=True)
        shutil.copyfile(tour or DEFAULT_TOUR, out / "tours" / f"{tour_data['name']}.json")
        exported = None
        if snapshot:
            with Community(out) as board:
                exported = export.export_snapshot(board, actor, "board", output=snapshot)
        public = {"format": "colloquy.public-demo/1", "built": now(), "fixture": manifest["name"],
                  "board_sequence": manifest["board_sequence"], "real_data": True,
                  "redaction": manifest["rules"], "moderation": "spec v2 C2: hidden posts are {id, hidden, reason} on "
                  "every surface (moderation.Visibility); refused write-ups are placeholders (C5)",
                  "tour": {"name": tour_data["name"], "steps": resolved["summary"]["steps"],
                           "finals_reaching_bytes_in_two_clicks": resolved["summary"]["finals_reaching_bytes_in_two_clicks"]},
                  "snapshot": exported and {"id": exported["snapshot"], "counts": exported["counts"],
                                            "output": exported["output"]},
                  "note": "A redacted copy of the real PMP22 cohort board. Agents' posts are untrusted, attributed "
                          "evidence; curated pointers are the tour curator's, not the authors'."}
        (out / "commons.toml").write_text(COMMONS_TOML.replace("{signin}", "true" if visitors else "false"))
        public.update(read_policy="public", visitor_signin=bool(visitors), first_screen="/",
                      serve=f"bio commons --root {out} serve --host 0.0.0.0 --mode accounts "
                            "--forwarded-allow-ips <your TLS proxy>")
        write_json(out / "PUBLIC.json", public)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise
    return {"commons": str(out), **{k: public[k] for k in ("fixture", "board_sequence", "tour", "snapshot",
                                                          "read_policy", "visitor_signin", "first_screen")},
            "next": public["serve"], "local": f"bio commons --root {out} serve"}
