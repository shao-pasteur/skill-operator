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
            "design-taste-frontend", "threejs-fundamentals", "obsidian-markdown", "skill-creator", "security-guidance",
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
    # Controller ruling: skillspector's SC4 check sends dependency names and versions to api.osv.dev even with --no-llm.
    assert [t.name for t in reg.tools if t.sends_data] == ["skillspector", "agent-scan"]


SKILLS_DIRS = {
    "claude-code": '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"',
    "codex": '"$HOME/.agents/skills"',
    "copilot": '"$HOME/.copilot/skills"',
    "cursor": '"$HOME/.cursor/skills"',
}
NOT_INSTALLABLE = {"principle-attack-the-premise", "fp-check", "rust-review", "cloudflare", "cloudflare-one",
                   "gateway-workers", "security-guidance"}


def test_pinned_install_commands_copy_one_folder_into_the_platform_skills_folder():
    reg = load("detect_stack").load_registry(SKILL_SRC / "registry.toml")
    pinned = [e for e in reg.skills if e.ref != "self"]
    assert {e.name for e in pinned if not e.install} == NOT_INSTALLABLE
    for e in pinned:
        if not e.install:
            continue
        assert set(e.install) == set(SKILLS_DIRS), e.name
        for platform, command in e.install.items():
            skills_dir = SKILLS_DIRS[platform]
            where = f"{e.name} on {platform}"
            assert command.startswith(f'[ ! -e {skills_dir[:-1]}/{e.name}" ] && d=$(mktemp -d) && {{ '), where
            assert f"github.com/{e.repo}.git" in command, where
            assert f"checkout -q {e.ref} -- " in command, where
            assert f"mkdir -p {skills_dir} && cp -R " in command, where
            assert command.endswith(f'{skills_dir[:-1]}/{e.name}" ; s=$?; rm -rf "$d"; [ "$s" -eq 0 ]; }}'), where
            assert command.count(e.ref) == 1, where


REQUIRED_HEADINGS = {
    "references/platforms.md": ["## Detecting the platform", "## Installing skills", "## Verification log"],
    "references/playbooks.md": ["## Playbooks", "## Plan-then-execute", "## Settings and help", "## Error analysis"],
    "references/intake.md": ["## The six dimensions", "## Playbook add-ons", "## Rules", "## Task card"],
    "references/delegation.md": ["## When to delegate", "## Brief", "## Report", "## Isolation levels", "## Fixed rules", "## Rule of Two"],
    "references/decisions-and-risk.md": ["## Decision levels", "## Decision card", "## Risk levels", "## Standing orders"],
    "references/budget-and-models.md": ["## Tiers", "## Difficulty and effort", "## Escalation ladder", "## Checkpoints"],
}


def test_documents_have_their_required_sections():
    for rel, headings in REQUIRED_HEADINGS.items():
        text = (SKILL_SRC / rel).read_text(encoding="utf-8")
        assert [h for h in headings if h not in text] == [], rel


ROLE_HEADINGS = ["## Identity", "## Expertise", "## Working method", "## Principles", "## Never"]


def test_every_role_has_a_prompt_with_five_parts():
    for role in load("config").ROLES:
        if role == "sharron":
            continue
        text = (SKILL_SRC / "roles" / f"{role}.md").read_text(encoding="utf-8")
        assert [h for h in ROLE_HEADINGS if h in text] == ROLE_HEADINGS, role
        assert len(text.splitlines()) <= 80, role
