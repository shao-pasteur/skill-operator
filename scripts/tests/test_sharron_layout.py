from pathlib import Path

from skillops.catalog import load_catalog
from sharron_support import SKILL_SRC, load

REPO = Path(__file__).resolve().parents[2]


def test_research_skills_are_scriptless_web_skills():
    skills = {s.name: s for s in load_catalog(REPO).skills}
    assert skills["research-method"].web and skills["verify-evidence"].web
    assert not skills["sharron"].web


def test_shipped_ledger_is_canonical():
    ledger = load("ledger")
    text = (SKILL_SRC / "ledger/costs.md").read_text(encoding="utf-8")
    assert ledger.render_ledger(ledger.parse_ledger(text)) == text


SOURCE_IDS = ["owasp-top10", "cwe-top25", "owasp-api", "owasp-llm", "owasp-agentic", "owasp-mcp", "owasp-ast10",
              "owasp-nhi", "owasp-cicd", "owasp-privacy", "cvss", "cve", "nvd", "osv", "github-advisories",
              "cisa-kev", "epss", "cwe", "capec", "mitre-attack", "mitre-atlas"]


def test_shipped_security_references():
    refcheck = load("refcheck")
    path = SKILL_SRC / "security-references.toml"
    data = refcheck.load_references(path)
    assert refcheck.render_references(data) == path.read_text(encoding="utf-8")
    assert [s["id"] for s in data["sources"]] == SOURCE_IDS
    for s in data["sources"]:
        expected = 10 if s["kind"] == "risk-list" else 25 if s["id"] == "cwe-top25" else 0
        assert len(s["items"]) == expected, s["id"]
        assert (s["probe"]["type"] == "none") == (s["edition"] == "live"), s["id"]
