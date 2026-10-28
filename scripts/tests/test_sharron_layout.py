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


def test_registry_has_the_default_entries():
    reg = load("detect_stack").load_registry(SKILL_SRC / "registry.toml")
    names = {e.name for e in reg.skills}
    # Controller ruling: upstream ships static-analysis as a plugin, so its three skills are listed by folder name.
    assert {"research-method", "verify-evidence", "principle-prove-it-works", "principle-fix-root-causes", "tdd", "teach",
            "taste-skill", "threejs-fundamentals", "obsidian-markdown", "skill-creator", "security-guidance",
            "codeql", "semgrep", "sarif-parsing", "rust-review", "modern-python", "python-testing-patterns",
            "golang-security", "golang-project-layout", "k8s-security-policies", "helm-chart-scaffolding",
            "terraform-test", "bats-testing-patterns"} <= names
    assert "tw-stock-daily-tracker" not in names
    assert "static-analysis" not in names and "insecure-defaults" not in names
    assert {e.name for e in reg.skills if e.status == "disabled"} == {"obsidian-cli", "defuddle"}
    assert all(e.domains == ("coding",) for e in reg.skills if e.tags)
    assert len(names) == len(reg.skills)
    for e in reg.skills:
        assert e.ref == "self" or all(e.ref in cmd for cmd in e.install.values()), e.name
    assert [t.name for t in reg.tools] == ["skill-scanner", "skillspector", "agent-scan"]
    assert [t.name for t in reg.tools if t.sends_data] == ["agent-scan"]


REQUIRED_HEADINGS = {
    "references/platforms.md": ["## Detecting the platform", "## Installing skills", "## Verification log"],
}


def test_documents_have_their_required_sections():
    for rel, headings in REQUIRED_HEADINGS.items():
        text = (SKILL_SRC / rel).read_text(encoding="utf-8")
        assert [h for h in headings if h not in text] == [], rel
