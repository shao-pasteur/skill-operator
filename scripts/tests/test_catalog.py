import pytest
import yaml

from skillops.catalog import CatalogError, load_catalog


def test_load_basic(repo):
    repo.add_skill("dev", "foo")
    repo.add_skill(
        "dev", "bar",
        files={"scripts/run.py": "print(1)\n"},
        frontmatter={"name": "bar", "description": "x"},
    )
    cat = load_catalog(repo.root)
    assert cat.marketplace == "test-market"
    assert cat.repo_slug == "tester/test-market"
    assert cat.repo_url == "https://github.com/tester/test-market"
    assert [s.dir_name for s in cat.skills] == ["bar", "foo"]
    assert [c.id for c in cat.active_categories()] == ["dev"]
    bar = cat.skills[0]
    assert bar.has_scripts and bar.web is False
    assert cat.skills[1].web is True
    assert bar.rel_path == "plugins/dev/skills/bar"
    assert bar.name == "bar" and bar.description == "x"


def test_skills_ordered_by_category_order(repo):
    repo.add_skill("finance", "aaa")
    repo.add_skill("dev", "zzz")
    assert [s.dir_name for s in load_catalog(repo.root).skills] == ["zzz", "aaa"]


def test_skills_in(repo):
    repo.add_skill("finance", "aaa")
    repo.add_skill("dev", "zzz")
    assert [s.dir_name for s in load_catalog(repo.root).skills_in("finance")] == ["aaa"]


def test_web_explicit_true_with_scripts(repo):
    repo.add_skill(
        "dev", "foo",
        frontmatter={"name": "foo", "description": "x", "metadata": {"web": "true"}},
        files={"scripts/a.sh": "echo\n"},
    )
    assert load_catalog(repo.root).skills[0].web is True


def test_name_falls_back_to_dir(repo):
    repo.add_skill("dev", "foo", frontmatter={})
    skill = load_catalog(repo.root).skills[0]
    assert skill.name == "foo" and skill.description == ""


def test_unknown_category_folder(repo):
    (repo.root / "plugins" / "ghost" / "skills").mkdir(parents=True)
    with pytest.raises(CatalogError, match="plugins/ghost"):
        load_catalog(repo.root)


def test_skill_dir_without_skill_md(repo):
    (repo.root / "plugins" / "dev" / "skills" / "empty").mkdir(parents=True)
    with pytest.raises(CatalogError, match="SKILL.md"):
        load_catalog(repo.root)


def test_bad_frontmatter_reports_path(repo):
    repo.add_skill("dev", "foo", raw="no frontmatter\n")
    with pytest.raises(CatalogError, match="plugins/dev/skills/foo/SKILL.md"):
        load_catalog(repo.root)


def test_missing_categories_yaml(tmp_path):
    with pytest.raises(CatalogError, match="categories.yaml"):
        load_catalog(tmp_path)


@pytest.mark.parametrize("bad", [
    {"marketplace": "m", "owner": {"name": "a"}, "categories": []},
    {"marketplace": "m", "owner": {"name": "a", "github": "g"},
     "categories": [{"id": "Dev", "title": "t", "description": "d"}]},
    {"marketplace": "m", "owner": {"name": "a", "github": "g"},
     "categories": [{"id": "a", "title": "t", "description": "d"},
                    {"id": "a", "title": "t", "description": "d"}]},
    {"marketplace": "m", "owner": {"name": "a", "github": "g"},
     "categories": [{"id": "a", "title": "", "description": "d"}]},
    ["not", "a", "mapping"],
])
def test_invalid_categories_yaml(repo, bad):
    (repo.root / "categories.yaml").write_text(yaml.safe_dump(bad, allow_unicode=True), encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(repo.root)


def test_hidden_and_file_entries_ignored(repo):
    repo.add_skill("dev", "foo")
    (repo.root / "plugins" / ".DS_Store").write_text("")
    (repo.root / "plugins" / "dev" / "skills" / ".DS_Store").write_text("")
    assert len(load_catalog(repo.root).skills) == 1


def test_no_plugins_dir(repo):
    cat = load_catalog(repo.root)
    assert cat.skills == [] and cat.active_categories() == []
