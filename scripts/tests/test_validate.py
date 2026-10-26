import pytest

from skillops.catalog import load_catalog
from skillops.validate import validate_catalog

LONG_DESC = "測試用 skill，" + "說明" * 30


def run(repo):
    return validate_catalog(load_catalog(repo.root))


def errors(issues):
    return [i.message for i in issues if i.level == "error"]


def warnings(issues):
    return [i.message for i in issues if i.level == "warning"]


def test_valid_skill_has_no_issues(repo):
    repo.add_skill("dev", "foo")
    assert run(repo) == []


def test_name_must_match_dir(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "other", "description": LONG_DESC})
    assert any("資料夾" in m for m in errors(run(repo)))


@pytest.mark.parametrize("name", ["Foo", "-foo", "foo-", "foo--bar", "a" * 65, ""])
def test_invalid_name(repo, name):
    repo.add_skill("dev", "foo", frontmatter={"name": name, "description": LONG_DESC})
    assert any("name" in m for m in errors(run(repo)))


def test_missing_name_and_description(repo):
    repo.add_skill("dev", "foo", frontmatter={})
    errs = errors(run(repo))
    assert any("name" in m for m in errs)
    assert any("description" in m for m in errs)


def test_description_too_long(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": "x" * 1025})
    assert any("1024" in m for m in errors(run(repo)))


def test_description_todo_is_error(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": "TODO 描述這個 skill" + "。" * 50})
    assert any("樣板" in m for m in errors(run(repo)))


def test_compatibility_too_long(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": LONG_DESC, "compatibility": "x" * 501})
    assert any("500" in m for m in errors(run(repo)))


def test_metadata_bool_value_is_error(repo):
    repo.add_skill("dev", "foo", raw=f"---\nname: foo\ndescription: {LONG_DESC}\nmetadata:\n  web: false\n---\n# x\n")
    assert any('"false"' in m for m in errors(run(repo)))


def test_metadata_web_invalid_value(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": LONG_DESC, "metadata": {"web": "no"}})
    assert any("web" in m for m in errors(run(repo)))


def test_scripts_require_web(repo):
    repo.add_skill("dev", "foo", files={"scripts/a.py": "x = 1\n"})
    assert any("metadata.web" in m for m in errors(run(repo)))


def test_duplicate_names_across_categories(repo):
    repo.add_skill("dev", "foo")
    repo.add_skill("finance", "foo")
    assert len([m for m in errors(run(repo)) if "重複" in m]) == 2


def test_missing_referenced_file(repo):
    repo.add_skill("dev", "foo", body="見 [說明](references/guide.md) 與 scripts/run.py。\n",
                   frontmatter={"name": "foo", "description": LONG_DESC, "metadata": {"web": "true"}})
    errs = errors(run(repo))
    assert any("references/guide.md" in m for m in errs)
    assert any("scripts/run.py" in m for m in errs)


def test_existing_reference_and_urls_ok(repo):
    repo.add_skill(
        "dev", "foo",
        body="讀 references/a.md，參考 https://x.com/scripts/y.py 與 [a](#scripts)。\n",
        files={"references/a.md": "a"},
    )
    assert errors(run(repo)) == []


def test_python_syntax_error(repo):
    repo.add_skill("dev", "foo", files={"scripts/bad.py": "def (:\n"},
                   frontmatter={"name": "foo", "description": LONG_DESC, "metadata": {"web": "false"}})
    assert any("bad.py" in m for m in errors(run(repo)))


def test_shell_syntax_error(repo):
    repo.add_skill("dev", "foo", files={"scripts/bad.sh": "if then\n"},
                   frontmatter={"name": "foo", "description": LONG_DESC, "metadata": {"web": "false"}})
    assert any("bad.sh" in m for m in errors(run(repo)))


def test_python_check_writes_no_pycache(repo):
    path = repo.add_skill("dev", "foo", files={"scripts/ok.py": "x = 1\n"},
                          frontmatter={"name": "foo", "description": LONG_DESC, "metadata": {"web": "false"}})
    assert errors(run(repo)) == []
    assert not list(path.rglob("__pycache__"))


@pytest.mark.parametrize("text", ["/Users/alice/x", "/home/bob/x", r"C:\Users\carol\x"])
def test_personal_path_is_error(repo, text):
    repo.add_skill("dev", "foo", body="見 references/a.md\n", files={"references/a.md": text})
    issues = [i for i in run(repo) if i.level == "error"]
    assert any("個人路徑" in i.message and i.path == "plugins/dev/skills/foo/references/a.md" for i in issues)


def test_placeholder_path_ok(repo):
    repo.add_skill("dev", "foo", body="放在 /Users/<你>/x 底下\n")
    assert errors(run(repo)) == []


def test_email_is_warning(repo):
    repo.add_skill("dev", "foo", body="聯絡 me@example.com\n")
    issues = run(repo)
    assert errors(issues) == []
    assert any("email" in m for m in warnings(issues))


def test_long_skill_md_warning(repo):
    repo.add_skill("dev", "foo", body="行\n" * 501)
    assert any("500" in m for m in warnings(run(repo)))


def test_short_description_warning(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": "短"})
    assert any("50" in m for m in warnings(run(repo)))


def test_platform_field_warning(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": LONG_DESC, "allowed-tools": "Read"})
    issues = run(repo)
    assert errors(issues) == []
    assert any("allowed-tools" in m for m in warnings(issues))


def test_binary_files_skipped(repo):
    path = repo.add_skill("dev", "foo")
    (path / "assets").mkdir()
    (path / "assets" / "img.png").write_bytes(b"\x89PNG\x00\xff\xfe")
    assert errors(run(repo)) == []


def test_only_skill_dirs_are_reference_checked(repo):
    repo.add_skill("dev", "foo", body="報告內嵌 ![](../charts/{symbol}.png) 與 [筆記](notes.md)；見 ./references/a.md\n",
                   files={"references/a.md": "a"})
    assert errors(run(repo)) == []


def test_dot_slash_reference_checked(repo):
    repo.add_skill("dev", "foo", body="見 [說明](./references/missing.md)\n")
    assert any("references/missing.md" in m for m in errors(run(repo)))
