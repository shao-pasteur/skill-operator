import json
import subprocess
from collections import Counter
from pathlib import Path

from skillops.catalog import load_catalog
from skillops.frontmatter import parse_frontmatter
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
            assert command.startswith(
                f'[ ! -e {skills_dir[:-1]}/{e.name}" ] && d=$(mktemp -d "${{TMPDIR:-/tmp}}/sharron.XXXXXX") && {{ '
                "git -c maintenance.auto=false clone "
            ), where
            assert f"github.com/{e.repo}.git" in command, where
            assert f'git -c maintenance.auto=false -C "$d" checkout -q {e.ref} -- ' in command, where
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
REQUIRED_HEADINGS.update({
    "references/finance.md": ["## Measuring usage", "## Ledger", "## Budget suggestions", "## Data sync", "## Reply lines"],
    "references/registry.md": ["## Registry format", "## Service list", "## Installing a missing skill", "## Recording an install",
                               "## Editing the registry"],
    "references/memory.md": ["## Format", "## Rules", "## Git safety", "## Task ids"],
    "references/security-review.md": ["## When the security role runs", "## Checklist", "## Findings", "## Handling",
                                      "## Background reference updates"],
    "GUIDE.md": ["## Install", "## First run", "## Calling sharron", "## The intake and the task card",
                 "## Confirmations and decision cards", "## Memory", "## Talking to sharron about settings",
                 "## Settings and files you can edit", "## Manual commands", "## Troubleshooting"],
})


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


def test_skill_md_is_short_and_triggers_only_on_sharron():
    text = (SKILL_SRC / "SKILL.md").read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    assert len(text.splitlines()) <= 200
    assert "/workflow:sharron" in fm["description"] and "Do not use" in fm["description"]
    for script in ["memory_guard.py", "refcheck.py", "detect_stack.py", "finance.py", "trace.py", "config.py", "datasync.py"]:
        assert f"run.sh {script}" in body, script


def test_eval_sets_have_the_planned_size():
    evals = json.loads((SKILL_SRC / "evals/evals.json").read_text(encoding="utf-8"))
    assert evals["skill_name"] == "sharron" and len(evals["evals"]) >= 23
    assert all(e["prompt"] and e["expectations"] for e in evals["evals"])
    trigger = json.loads((SKILL_SRC / "evals/trigger-eval.json").read_text(encoding="utf-8"))
    assert sum(q["should_trigger"] for q in trigger) >= 10 and sum(not q["should_trigger"] for q in trigger) >= 10


def test_eval_cases_follow_the_planned_distribution_and_point_at_real_files():
    cases = json.loads((SKILL_SRC / "evals/evals.json").read_text(encoding="utf-8"))["evals"]
    assert [c["id"] for c in cases] == list(range(1, len(cases) + 1))
    assert len({c["name"] for c in cases}) == len(cases)
    tasks = Counter(c["playbook"] for c in cases if c["group"] == "task")
    assert tasks == {"simple-answer": 1, "research": 4, "planning": 2, "action": 3, "decision-support": 2,
                     "learning": 2, "coding": 3, "settings-help": 3}
    assert all(c["playbook"] in load("config").PLAYBOOKS for c in cases)
    assert sum(c["group"] == "skill-recommendation" for c in cases) == 3
    for case in cases:
        for rel in case["files"]:
            assert (SKILL_SRC / rel).is_file(), rel


def test_eval_fixtures_have_the_stack_tags_the_recommendation_cases_expect():
    detect_stack = load("detect_stack")
    expected = {"python-backend": ["python"], "helm-chart": ["helm", "kubernetes"], "bash-tool": ["bash"]}
    for name, tags in expected.items():
        assert sorted(detect_stack.detect_tags(SKILL_SRC / "evals/files" / name)) == tags, name
    result = subprocess.run(["bash", "-n", str(SKILL_SRC / "evals/files/bash-tool/backup.sh")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_trigger_queries_are_strings_with_boolean_flags():
    trigger = json.loads((SKILL_SRC / "evals/trigger-eval.json").read_text(encoding="utf-8"))
    assert all(isinstance(q["query"], str) and q["query"].strip() for q in trigger)
    assert all(type(q["should_trigger"]) is bool for q in trigger)
    assert len({q["query"] for q in trigger}) == len(trigger)


def test_scripted_turns_are_replies_and_fixture_page_exists():
    cases = json.loads((SKILL_SRC / "evals/evals.json").read_text(encoding="utf-8"))["evals"]
    for case in cases:
        turns = case.get("turns", [])
        assert all(isinstance(t, str) and t.strip() for t in turns), case["id"]
    page = (SKILL_SRC / "evals/files/quote-page/quote.html").read_text(encoding="utf-8")
    assert "AI ASSISTANT" in page and "@" not in page


# (case id, role, tier, --tags, fixture) for the select calls the recommendation cases are built on.
RECOMMENDATION_SELECTIONS = [
    (21, "engineer", "T2", "backend", "python-backend"),
    (21, "engineer", "T2", "backend,testing", "python-backend"),
    (21, "security", "T3", "backend", "python-backend"),
    (22, "engineer", "T2", "infra", "helm-chart"),
    (22, "security", "T3", "infra", "helm-chart"),
    (23, "engineer", "T2", "cli", "bash-tool"),
    (23, "engineer", "T2", "cli,lint,testing", "bash-tool"),
]


def test_recommendation_cases_name_every_skill_that_select_returns(capsys):
    detect_stack = load("detect_stack")
    cases = {c["id"]: c for c in json.loads((SKILL_SRC / "evals/evals.json").read_text(encoding="utf-8"))["evals"]}
    for case_id, role, tier, tags, fixture in RECOMMENDATION_SELECTIONS:
        argv = ["--skill-dir", str(SKILL_SRC), "select", "--role", role, "--playbook", "coding", "--domain", "coding",
                "--tier", tier, "--tags", tags, "--workspace", str(SKILL_SRC / "evals/files" / fixture)]
        assert detect_stack.main(argv) == 0
        selected = [s["name"] for s in json.loads(capsys.readouterr().out)["skills"]]
        assert selected, (case_id, role, tags)
        text = " ".join(cases[case_id]["expectations"])
        assert [name for name in selected if name not in text] == [], (case_id, role, tags)
