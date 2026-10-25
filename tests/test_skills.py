from pathlib import Path

from claude_code.skills.registry import SkillRegistry


def test_registry_loads_frontmatter_and_support_files(tmp_path: Path) -> None:
    skill_dir = tmp_path / "review"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: review_code\ndescription: Review a change\n---\nReview carefully.",
        encoding="utf-8",
    )
    (skill_dir / "checklist.md").write_text("Check tests", encoding="utf-8")

    registry = SkillRegistry(tmp_path)
    registry.load()

    assert registry.skill_names == ["review_code"]
    loaded = registry.load_skill("review_code")
    assert "Review carefully." in loaded
    assert str(skill_dir / "checklist.md") in loaded
