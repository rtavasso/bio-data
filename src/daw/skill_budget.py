"""Skill text byte budget (spec v3 V13).

Skill text is what a harness loads into the model's context when an agent reads a skill: each skill's
`SKILL.md` plus its `references/*.md`. Scripts and agent metadata are not skill text (they are run or
parsed, not read into context). `tests/test_skill_budget.py` fails when a skill outgrows its budget, and
the evaluation dashboard shows each skill's size beside its budget and how often a turn reads it
(`daw.commons.economics`).
"""
import hashlib
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[2] / ".agents" / "skills"

# Bytes of skill text per skill, set at the v3 size plus modest headroom (about 15%, rounded up to 512 bytes).
# This is the only place budgets are recorded. Growing one requires naming, in the same change, the dashboard
# metric the added text moves (turn economics: help or re-orientation calls per turn, skill reads per turn,
# ceremony tail, compactions, or cost per useful datum) and the direction it is expected to move it.
BUDGET_BYTES = {
    "bio-artifact-reuse": 4096,
    "bio-community": 12288,
    "bio-data-discovery": 17408,
    "bio-evaluation-review": 8704,
    "bio-hypothesis-discovery": 27648,
    "bio-mechanism-exploration": 17408,
    "bio-research": 14336,
    "bio-research-consolidation": 5120,
}


def skill_text_files(skill):
    """The model-facing text files of one skill directory: SKILL.md, then references/**/*.md in path order."""
    skill = Path(skill)
    files = [skill / "SKILL.md"] if (skill / "SKILL.md").is_file() else []
    references = skill / "references"
    if references.is_dir() and not references.is_symlink():
        files += sorted(p for p in references.rglob("*.md") if p.is_file() and not p.is_symlink())
    return files


def skill_text_bytes(skill):
    return sum(path.stat().st_size for path in skill_text_files(skill))


def skill_digest(skill):
    """sha256 over the skill's text files (relative path and bytes), or None when it has no SKILL.md."""
    skill = Path(skill)
    files = skill_text_files(skill)
    if not files:
        return None
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(skill).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def skill_dirs(root=SKILLS_DIR):
    root = Path(root)
    if not root.is_dir():
        return []
    return [p for p in sorted(root.iterdir()) if p.is_dir() and not p.is_symlink() and (p / "SKILL.md").is_file()]


def skill_sizes(root=SKILLS_DIR):
    """{skill: {bytes, budget}} for the skills under `root` (the platform's own skills by default); an empty
    dict when the skills are not present (an installed package without a source checkout)."""
    return {p.name: {"bytes": skill_text_bytes(p), "budget": BUDGET_BYTES.get(p.name)} for p in skill_dirs(root)}
