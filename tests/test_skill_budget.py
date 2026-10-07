"""Spec v3 V13: skill text has a byte budget. A skill that grows must show a metric it moves (see
daw.skill_budget.BUDGET_BYTES, the only place budgets are recorded)."""
from daw.skill_budget import BUDGET_BYTES, SKILLS_DIR, skill_dirs, skill_sizes, skill_text_bytes, skill_text_files


def test_every_skill_has_a_budget_and_stays_under_it():
    skills = skill_dirs(SKILLS_DIR)
    assert skills, f"no skills under {SKILLS_DIR}"
    names = {p.name for p in skills}
    assert names == set(BUDGET_BYTES), (
        f"skills without a budget: {sorted(names - set(BUDGET_BYTES))}; "
        f"budgets without a skill: {sorted(set(BUDGET_BYTES) - names)}")
    over = {p.name: (skill_text_bytes(p), BUDGET_BYTES[p.name]) for p in skills
            if skill_text_bytes(p) > BUDGET_BYTES[p.name]}
    assert not over, ("skill text over budget (bytes, budget): "
                      f"{over}. Trim the text, or raise the budget in daw/skill_budget.py and name the metric it moves.")


def test_skill_text_is_skill_md_and_references_only(tmp_path):
    skill = tmp_path / "bio-example"
    (skill / "references").mkdir(parents=True)
    (skill / "scripts").mkdir()
    (skill / "SKILL.md").write_text("# Example\n")
    (skill / "references" / "notes.md").write_text("notes\n")
    (skill / "scripts" / "helper.py").write_text("print(1)\n" * 100)
    assert [p.name for p in skill_text_files(skill)] == ["SKILL.md", "notes.md"]
    assert skill_text_bytes(skill) == len("# Example\n") + len("notes\n")
    assert skill_sizes(tmp_path) == {"bio-example": {"bytes": 16, "budget": None}}
