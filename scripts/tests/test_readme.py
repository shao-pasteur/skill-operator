import pytest

from skillops.catalog import CatalogError, load_catalog
from skillops.readme import render_catalog_table, replace_catalog_block, summarize


def test_summarize():
    assert summarize("One。Two。") == "One。"
    assert summarize("First sentence. Second.") == "First sentence."
    assert summarize("line1\nline2") == "line1"
    assert summarize("x" * 100) == "x" * 79 + "…"
    assert summarize("a | b") == "a \\| b"


def test_table(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": "Does foo. More text."})
    repo.add_skill("dev", "bar", frontmatter={"name": "bar", "description": "Does bar.", "metadata": {"web": "false"}})
    t = render_catalog_table(load_catalog(repo.root))
    assert "### Development (`dev`)" in t
    assert "| Skill | Description | Web apps |\n|---|---|---|" in t
    assert "| `foo` | Does foo. | [Download](https://github.com/tester/test-market/releases/download/latest/foo.zip) |" in t
    assert "| `bar` | Does bar. | — |" in t
    assert "Finance" not in t


def test_table_sections_separated(repo):
    repo.add_skill("dev", "foo")
    repo.add_skill("finance", "bar")
    t = render_catalog_table(load_catalog(repo.root))
    assert t.index("### Development") < t.index("### Finance")
    assert "|\n\n### Finance" in t


def test_table_empty(repo):
    assert render_catalog_table(load_catalog(repo.root)) == "_No skills yet._"


def test_replace_block():
    before = "a\n<!-- catalog:start -->\nOLD\n<!-- catalog:end -->\nb\n"
    assert replace_catalog_block(before, "NEW") == "a\n<!-- catalog:start -->\nNEW\n<!-- catalog:end -->\nb\n"


def test_replace_block_missing_markers():
    with pytest.raises(CatalogError, match="README.md"):
        replace_catalog_block("no markers\n", "NEW")


def test_replace_block_reversed_markers():
    with pytest.raises(CatalogError, match="README.md"):
        replace_catalog_block("<!-- catalog:end -->\n<!-- catalog:start -->\n", "NEW")
