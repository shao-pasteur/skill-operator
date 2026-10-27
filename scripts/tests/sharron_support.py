"""Helpers shared by the tests of the sharron skill."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

SKILL_SRC = Path(__file__).resolve().parents[2] / "plugins/workflow/skills/sharron"

_loaded: dict[str, ModuleType] = {}


def _load_from_file(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # dataclasses look their module up by name
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[module_name]
        raise
    return module


def load(name: str) -> ModuleType:
    """Return the skill's scripts/<name>.py as a module; each name is loaded once.

    The scripts folder goes to the END of sys.path and the module is imported by its own name, so
    load("ledger") is exactly the module that `import ledger` gives a sibling script. Exception and
    dataclass classes therefore match, whether a test or a sibling script imported them.

    The one exception is a name that is also a stdlib module (today: trace). Importing it by its own
    name would return the stdlib module, so it is loaded from its file as sharron_<name> instead.
    """
    if name not in _loaded:
        scripts = SKILL_SRC / "scripts"
        if str(scripts) not in sys.path:
            sys.path.append(str(scripts))
        if name in sys.stdlib_module_names:
            _loaded[name] = _load_from_file(f"sharron_{name}", scripts / f"{name}.py")
        else:
            _loaded[name] = importlib.import_module(name)
    return _loaded[name]


ROW = {
    "task_id": "t-20261027-01", "date": "2026-10-27", "platform": "claude-code", "playbook": "research",
    "domain": "finance", "difficulty": "3", "subagents": "2", "models": "claude-haiku-5-5,claude-opus-5-5",
    "input_tokens": "1200", "output_tokens": "800", "cache_tokens": "50000", "cost_usd": "0.4200",
    "outcome": "done", "verified": "3/3", "measurement": "measured",
}


def row(**changes: str) -> dict[str, str]:
    """A valid ledger task row with the given fields changed; a new dict on every call."""
    return {**ROW, **changes}


def git(cwd: Path, *args: str) -> str:
    """Run git in cwd and return its stripped stdout; a failing command raises CalledProcessError."""
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def make_skill(root: Path) -> Path:
    """Create <root>/plugins/workflow/skills/sharron/ with the real config.example.toml, an empty registry and an empty ledger."""
    skill = root / "plugins/workflow/skills/sharron"
    skill.mkdir(parents=True, exist_ok=True)
    shutil.copy(SKILL_SRC / "config.example.toml", skill / "config.example.toml")
    (skill / "registry.toml").write_text("schema_version = 1\n", encoding="utf-8")
    ledger = load("ledger")
    (skill / "ledger").mkdir(exist_ok=True)
    (skill / "ledger/costs.md").write_text(ledger.render_ledger(ledger.Ledger([], [])), encoding="utf-8")
    return skill
