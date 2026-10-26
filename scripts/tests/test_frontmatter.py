import pytest

from skillops.frontmatter import FrontmatterError, parse_frontmatter


def test_parse_basic():
    fm, body = parse_frontmatter("---\nname: foo\ndescription: bar\n---\n# Hi\n")
    assert fm == {"name": "foo", "description": "bar"}
    assert body == "# Hi\n"


def test_parse_crlf():
    fm, body = parse_frontmatter("---\r\nname: foo\r\n---\r\nbody\r\n")
    assert fm == {"name": "foo"}
    assert body.strip() == "body"


def test_missing_opening_delimiter():
    with pytest.raises(FrontmatterError, match="start"):
        parse_frontmatter("name: foo\n")


def test_missing_closing_delimiter():
    with pytest.raises(FrontmatterError, match="closing"):
        parse_frontmatter("---\nname: foo\n")


def test_not_a_mapping():
    with pytest.raises(FrontmatterError, match="mapping"):
        parse_frontmatter("---\n- a\n- b\n---\n")


def test_invalid_yaml():
    with pytest.raises(FrontmatterError, match="YAML"):
        parse_frontmatter("---\nname: [unclosed\n---\n")
