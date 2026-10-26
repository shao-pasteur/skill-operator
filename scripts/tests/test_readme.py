import pytest

from skillops.catalog import CatalogError, load_catalog
from skillops.readme import render_catalog_table, replace_catalog_block, summarize


def test_summarize():
    assert summarize("第一句。第二句。") == "第一句。"
    assert summarize("First sentence. Second.") == "First sentence."
    assert summarize("line1\nline2") == "line1"
    assert summarize("字" * 100) == "字" * 79 + "…"
    assert summarize("a | b") == "a \\| b"


def test_table(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": "做 foo 的事。其他。"})
    repo.add_skill("dev", "bar", frontmatter={"name": "bar", "description": "做 bar。", "metadata": {"web": "false"}})
    t = render_catalog_table(load_catalog(repo.root))
    assert "### 開發（`dev`）" in t
    assert "| Skill | 說明 | 網頁版 |\n|---|---|---|" in t
    assert "| `foo` | 做 foo 的事。 | [下載](https://github.com/tester/test-market/releases/download/latest/foo.zip) |" in t
    assert "| `bar` | 做 bar。 | — |" in t
    assert "財務" not in t


def test_table_sections_separated(repo):
    repo.add_skill("dev", "foo")
    repo.add_skill("finance", "bar")
    t = render_catalog_table(load_catalog(repo.root))
    assert t.index("### 開發") < t.index("### 財務")
    assert "|\n\n### 財務" in t


def test_table_empty(repo):
    assert render_catalog_table(load_catalog(repo.root)) == "_目前還沒有 skill。_"


def test_replace_block():
    before = "a\n<!-- catalog:start -->\nOLD\n<!-- catalog:end -->\nb\n"
    assert replace_catalog_block(before, "NEW") == "a\n<!-- catalog:start -->\nNEW\n<!-- catalog:end -->\nb\n"


def test_replace_block_missing_markers():
    with pytest.raises(CatalogError, match="README.md"):
        replace_catalog_block("no markers\n", "NEW")


def test_replace_block_reversed_markers():
    with pytest.raises(CatalogError, match="README.md"):
        replace_catalog_block("<!-- catalog:end -->\n<!-- catalog:start -->\n", "NEW")
