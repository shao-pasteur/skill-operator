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
