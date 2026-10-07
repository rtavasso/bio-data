"""Spec v2 C1: no two repository paths may differ only by case (macOS filesystems are case-insensitive)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_case_collisions", ROOT / "scripts" / "check_case_collisions.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def test_the_checkout_has_no_case_collisions():
    paths = check.tracked(ROOT)
    if paths is None:  # not a git checkout: walk the source trees instead
        paths = [p for root in ("src", "web/src", "web/e2e", "tests") for p in
                 (f"{root}/{q}" for q in check.walk(ROOT / root))]
    assert {p.split("/")[0] for p in paths} >= {"src", "web", "tests"}
    assert check.collisions(paths) == []


def test_collisions_are_found_for_files_directories_and_import_specifiers(tmp_path):
    # The defect the review found: `./actions` resolved to Actions.tsx beside actions.ts on macOS.
    assert check.collisions(["web/src/c/actions.ts", "web/src/c/Actions.tsx"]) == [
        ["web/src/c/Actions.tsx", "web/src/c/actions.ts"]]
    assert check.collisions(["src/daw/Util.py", "src/daw/util.py"]) == [["src/daw/Util.py", "src/daw/util.py"]]
    assert check.collisions(["src/Daw/a.py", "src/daw/b.py"]) == [["src/Daw", "src/daw"]]
    assert check.collisions(["web/src/a.ts", "web/src/a.test.ts", "web/src/a.tsx", "docs/A.md", "docs/a.txt"]) == []
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "Writes.ts").write_text("")
    (tmp_path / "x" / "writes.tsx").write_text("")
    assert check.main([str(tmp_path)]) == 1
