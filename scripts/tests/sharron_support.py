"""Helpers shared by the tests of the sharron skill."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

SKILL_SRC = Path(__file__).resolve().parents[2] / "plugins/workflow/skills/sharron"

_loaded: dict[str, ModuleType] = {}


def load(name: str) -> ModuleType:
    """Import the skill's scripts/<name>.py as the module sharron_<name>; each name is imported once.

    The scripts folder goes to the END of sys.path: sibling imports such as `import config` work,
    while stdlib names such as `trace` still resolve to the stdlib.
    """
    if name not in _loaded:
        scripts = SKILL_SRC / "scripts"
        if str(scripts) not in sys.path:
            sys.path.append(str(scripts))
        module_name = f"sharron_{name}"
        spec = importlib.util.spec_from_file_location(module_name, scripts / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module  # dataclasses look their module up by name
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[module_name]
            raise
        _loaded[name] = module
    return _loaded[name]


def git(cwd: Path, *args: str) -> str:
    """Run git in cwd and return its stripped stdout; a failing command raises CalledProcessError."""
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def make_skill(root: Path) -> Path:
    """Create <root>/plugins/workflow/skills/sharron/ with the real config.example.toml and an empty registry."""
    skill = root / "plugins/workflow/skills/sharron"
    skill.mkdir(parents=True, exist_ok=True)
    shutil.copy(SKILL_SRC / "config.example.toml", skill / "config.example.toml")
    (skill / "registry.toml").write_text("schema_version = 1\n", encoding="utf-8")
    return skill
