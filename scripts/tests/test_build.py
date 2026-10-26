import shutil

import pytest

from skillops.build import check_generated, generated_files, write_generated
from skillops.catalog import CatalogError, load_catalog


def test_write_then_check_clean(repo):
    repo.add_skill("dev", "foo")
    assert write_generated(load_catalog(repo.root))
    assert write_generated(load_catalog(repo.root)) == []
    assert check_generated(load_catalog(repo.root)) == []
    assert "`foo`" in (repo.root / "README.md").read_text(encoding="utf-8")


def test_check_detects_outdated(repo):
    repo.add_skill("dev", "foo")
    write_generated(load_catalog(repo.root))
    (repo.root / ".claude-plugin/marketplace.json").write_text("{}\n")
    issues = check_generated(load_catalog(repo.root))
    assert any("make build" in i.message and i.path == ".claude-plugin/marketplace.json" for i in issues)


def test_check_detects_missing(repo):
    repo.add_skill("dev", "foo")
    cat = load_catalog(repo.root)
    paths = {i.path for i in check_generated(cat) if i.level == "error"}
    assert paths == set(generated_files(cat))


def test_build_removes_stale_manifests(repo):
    repo.add_skill("dev", "foo")
    repo.add_skill("finance", "bar")
    write_generated(load_catalog(repo.root))
    shutil.rmtree(repo.root / "plugins/finance/skills/bar")
    changed = write_generated(load_catalog(repo.root))
    assert "plugins/finance/.claude-plugin/plugin.json" in changed
    assert not (repo.root / "plugins/finance/.claude-plugin").exists()
    assert not (repo.root / "plugins/finance/.codex-plugin").exists()
    assert check_generated(load_catalog(repo.root)) == []


def test_check_reports_stale_manifests(repo):
    repo.add_skill("dev", "foo")
    repo.add_skill("finance", "bar")
    write_generated(load_catalog(repo.root))
    shutil.rmtree(repo.root / "plugins/finance/skills/bar")
    issues = check_generated(load_catalog(repo.root))
    assert any(i.level == "error" and i.path == "plugins/finance/.claude-plugin/plugin.json" for i in issues)


def test_build_writes_nothing_on_error(repo):
    repo.add_skill("dev", "foo")
    repo.write_readme("# no markers\n")
    with pytest.raises(CatalogError):
        write_generated(load_catalog(repo.root))
    assert not (repo.root / ".claude-plugin").exists()


def test_missing_readme_is_catalog_error(repo):
    (repo.root / "README.md").unlink()
    with pytest.raises(CatalogError, match="README.md"):
        generated_files(load_catalog(repo.root))
