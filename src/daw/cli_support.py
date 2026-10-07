"""Command resolution that names the right verb when an agent guesses a wrong one.

The PMP22 cohort guessed 25 commands that do not exist (`community reply`, `community register`,
`community status`, `community get/put/reuse/link`, `data inspect/study/derive`, `artifact uses`), each
costing a failure, a `--help` crawl and a retry. Click's "No such command" names nothing; this group
adds the closest existing commands and the known renames, so the first failure already carries the fix.
"""
import difflib

from typer.core import TyperGroup, _click

UsageError = _click.exceptions.UsageError  # Typer raises its own click's exception type

# Observed guess -> where that action actually lives (full invocation after `bio`).
RENAMES = {
    "community": {"respond": "community answer REQUEST --body FILE (a request to you) or community reply THREAD --body FILE",
                  "register": "register PATH --question Q --input ... --code ... (no community prefix)",
                  "status": "community inbox [--sent]",
                  "get": "community show POST, community fetch POST --question Q",
                  "put": "community publish TITLE --body FILE",
                  "post": "community publish TITLE --body FILE",
                  "reuse": "artifact use ARTIFACT --question Q --reason ...",
                  "link": "community publish --artifact ARTIFACT (evidence named at publication)",
                  "list": "community search [--family forum|artifact|work|claim]",
                  "read": "community show POST",
                  "question": "community ask TARGET --body FILE",
                  "reply-to": "community publish --reply-to POST"},
    "data": {"inspect": "inspect ASSET (top level), or peek.py PATH for a local file",
             "study": "data show SUBJECT",
             "derive": "register PATH (outputs are registered, never derived by the CLI)",
             "fetch": "fetch ASSET (top level)",
             "download": "fetch ASSET (top level)"},
    "artifact": {"uses": "artifact use ARTIFACT --question Q", "list": "artifact search --text ...",
                 "register": "register PATH (top level)", "get": "artifact show ARTIFACT"},
    "work": {"note": "edit LABBOOK.md directly, then work sync Q", "status": "work show Q",
             "log": "work show Q --events N", "gaps-withdraw": "work gap-withdraw Q EVENT --reason ..."},
    "": {"answer": "community answer REQUEST --body FILE", "publish": "community publish TITLE --body FILE",
         "inbox": "community inbox", "sync": "work sync Q", "gap": "work gap Q --need ...",
         "new": "work new TITLE", "show": "work show Q, data show SUBJECT, artifact show ARTIFACT, community show POST",
         "use": "artifact use ARTIFACT --question Q", "python": "./bin/python SCRIPT (save analysis code as a script so its receipt names it)"},
}


class SuggestingGroup(TyperGroup):
    """`No such command` plus the nearest existing commands and any known rename."""

    def resolve_command(self, ctx, args):
        try:
            return super().resolve_command(ctx, args)
        except UsageError as error:
            name = str(args[0]) if args else ""
            known = self.list_commands(ctx)
            close = difflib.get_close_matches(name, known, n=3, cutoff=0.5)
            group = (ctx.command_path.split(" ", 1) + [""])[1].strip()
            rename = RENAMES.get(group, {}).get(name)
            parts = [f"No such command {name!r} under {ctx.command_path!r}."]
            if rename:
                parts.append(f"Use: bio {rename}.")
            if close:
                parts.append("Closest: " + ", ".join(close) + ".")
            parts.append("Commands here: " + ", ".join(known) + ".")
            raise UsageError(" ".join(parts), ctx=ctx) from error
