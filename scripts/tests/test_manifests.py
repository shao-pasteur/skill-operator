import json

from skillops.catalog import load_catalog
from skillops.manifests import render_manifests


def test_manifest_paths(repo):
    repo.add_skill("dev", "foo")
    files = render_manifests(load_catalog(repo.root))
    assert sorted(files) == [
        ".agents/plugins/marketplace.json",
        ".claude-plugin/marketplace.json",
        ".cursor-plugin/marketplace.json",
        "plugins/dev/.claude-plugin/plugin.json",
        "plugins/dev/.codex-plugin/plugin.json",
        "plugins/dev/.cursor-plugin/plugin.json",
    ]


def test_manifest_contents(repo):
    repo.add_skill("dev", "foo")
    f = {k: json.loads(v) for k, v in render_manifests(load_catalog(repo.root)).items()}
    assert f[".claude-plugin/marketplace.json"] == {
        "name": "test-market",
        "owner": {"name": "Tester"},
        "plugins": [{"name": "dev", "source": "./plugins/dev", "description": "開發工具"}],
    }
    assert f[".agents/plugins/marketplace.json"] == {
        "name": "test-market",
        "interface": {"displayName": "test-market"},
        "plugins": [{
            "name": "dev",
            "source": {"source": "local", "path": "./plugins/dev"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "開發",
        }],
    }
    assert f[".cursor-plugin/marketplace.json"] == {
        "name": "test-market",
        "owner": {"name": "Tester"},
        "plugins": [{"name": "dev", "source": "./plugins/dev", "description": "開發工具"}],
    }
    common = {"name": "dev", "description": "開發工具", "author": {"name": "Tester"}, "license": "MIT"}
    repo_url = "https://github.com/tester/test-market"
    assert f["plugins/dev/.claude-plugin/plugin.json"] == {**common, "repository": repo_url}
    assert f["plugins/dev/.cursor-plugin/plugin.json"] == {**common, "repository": repo_url}
    assert f["plugins/dev/.codex-plugin/plugin.json"] == {**common, "skills": "./skills/"}


def test_two_categories_keep_yaml_order(repo):
    repo.add_skill("finance", "bar")
    repo.add_skill("dev", "foo")
    f = json.loads(render_manifests(load_catalog(repo.root))[".claude-plugin/marketplace.json"])
    assert [p["name"] for p in f["plugins"]] == ["dev", "finance"]


def test_no_version_anywhere(repo):
    repo.add_skill("dev", "foo")
    assert all('"version"' not in text for text in render_manifests(load_catalog(repo.root)).values())


def test_unicode_not_escaped(repo):
    repo.add_skill("dev", "foo")
    text = render_manifests(load_catalog(repo.root))[".claude-plugin/marketplace.json"]
    assert "開發工具" in text and "\\u" not in text


def test_deterministic(repo):
    repo.add_skill("dev", "foo")
    cat = load_catalog(repo.root)
    assert render_manifests(cat) == render_manifests(cat)


def test_trailing_newline(repo):
    repo.add_skill("dev", "foo")
    assert all(text.endswith("}\n") for text in render_manifests(load_catalog(repo.root)).values())
