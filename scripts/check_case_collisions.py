"""Fail when two repository paths differ only by letter case (spec v2 C1).

On a case-insensitive filesystem (the macOS default) such paths collide: git checks out only one of them,
and a TypeScript import such as `./actions` resolves to `Actions.tsx` beside `actions.ts`. Module files are
also compared without their extension, because that is how imports name them.

    uv run python scripts/check_case_collisions.py [ROOT ...]     (default: the tracked files of this checkout)

Exit status 1 lists every colliding group. Run in CI on Linux, where the collision would otherwise be silent.
"""
import subprocess
import sys
from pathlib import Path

MODULE_SUFFIXES = (".d.ts", ".tsx", ".ts", ".jsx", ".mjs", ".js", ".py")
SKIP = {"node_modules", "__pycache__", ".git", ".venv", "dist", ".out"}


def module_stem(path):
    """The import specifier of a module file (its path without the extension), or None for other files."""
    for suffix in MODULE_SUFFIXES:
        if path.lower().endswith(suffix):
            return path[: -len(suffix)]
    return None


def collisions(paths):
    """Groups of distinct paths (files or directories) equal ignoring case, and module files whose import
    specifiers are equal ignoring case (`actions.ts` beside `Actions.tsx`)."""
    names, modules = {}, {}
    for path in sorted(set(paths)):
        parts = path.split("/")
        for depth in range(1, len(parts) + 1):
            prefix = "/".join(parts[:depth])
            names.setdefault(prefix.lower(), set()).add(prefix)
        stem = module_stem(path)
        if stem is not None:
            modules.setdefault(stem.lower(), {}).setdefault(stem, []).append(path)
    found = [sorted(members) for members in names.values() if len(members) > 1]
    for stems in modules.values():
        if len(stems) > 1:
            group = sorted(p for files in stems.values() for p in files)
            if not any(set(group) <= set(g) for g in found):
                found.append(group)
    return sorted(found)


def tracked(root):
    try:
        result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return [p for p in result.stdout.decode().split("\0") if p]


def walk(root):
    root = Path(root)
    out = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in SKIP for part in relative.parts) or not path.is_file():
            continue
        out.append(relative.as_posix())
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    roots = argv or [Path(__file__).resolve().parents[1]]
    problems = []
    for root in roots:
        paths = tracked(root) if not argv else None
        groups = collisions(paths if paths is not None else walk(root))
        problems += [(root, g) for g in groups]
    for root, group in problems:
        print(f"case collision under {root}: " + "  ".join(group))
    if not problems:
        print("no case collisions")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
