"""Cohort number audit (V2, C11): for each final, the share of numbers resolvable to a cell, verified,
unverified, post-scoped and unpointed.

    uv run python scripts/cohort_number_audit.py fixtures/pmp22-cohort [--output docs/v3/receipts/cohort-number-audit.json]

Reads the commons through the read-only archive (no writes, no network, no model) with the same checker
the renderers use (`daw.commons.checks.audit`). The receipt is compact JSON: rules, board sequence, totals
and per-final counts by post id; no post text. Run it on a private copy when the commons is the committed
fixture (opening an archive never writes, but the copy keeps `bio commons fixture verify` trivially green).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, help="commons root (for example a copy of fixtures/pmp22-cohort)")
    parser.add_argument("--output", type=Path, help="write the receipt here (compact JSON)")
    parser.add_argument("--per-final", action="store_true", help="include per-final rows in stdout")
    args = parser.parse_args(argv)
    from daw.commons.archive import Archive
    from daw.commons.checks import audit
    root = args.root.expanduser().resolve()
    with Archive(root) as view:
        result = audit(view)
    fixture = root / "FIXTURE.json"
    receipt = {"receipt": "cohort-number-audit", "format": result["format"], "rules": result["rules"],
               "board_sequence": result["sequence"],
               "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest() if fixture.is_file() else None,
               "totals": result["totals"], "definitions": result["definitions"],
               "finals": [{k: r[k] for k in ("post", "requester_kind", "numbers", "scopes", "statuses",
                                             "cell_verified", "post_scoped_value_in_named_artifact")}
                          for r in result["finals"]],
               "command": "uv run python scripts/cohort_number_audit.py <copy of fixtures/pmp22-cohort> --output ..."}
    text = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    if args.output:
        args.output.write_text(text + "\n")
    shown = receipt if args.per_final else {k: v for k, v in receipt.items() if k != "finals"}
    json.dump(shown, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
