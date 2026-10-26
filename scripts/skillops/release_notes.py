"""Work out which web skills changed in a push and describe them for the latest Release."""

import subprocess
from pathlib import Path

from skillops.catalog import Catalog


def git_changed_paths(root: Path, base: str | None, head: str) -> list[str] | None:
    if not base or set(base) == {"0"}:
        return None
    if base.startswith("-") or head.startswith("-"):
        return None
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "--end-of-options", base, head],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line]


def changed_skill_names(catalog: Catalog, changed_paths: list[str]) -> list[str]:
    by_rel = {s.rel_path: s.name for s in catalog.skills}
    names = set()
    for path in changed_paths:
        parts = path.split("/")
        if len(parts) >= 5 and parts[0] == "plugins" and parts[2] == "skills":
            name = by_rel.get("/".join(parts[:4]))
            if name:
                names.add(name)
    return sorted(names)


def render_release_notes(catalog: Catalog, changed: list[str] | None) -> str:
    web_skills = sorted((s for s in catalog.skills if s.web), key=lambda s: s.name)

    def link(name: str) -> str:
        return f"- [`{name}`]({catalog.repo_url}/releases/download/latest/{name}.zip)"

    to_upload = [s.name for s in web_skills if changed is None or s.name in changed]
    lines = ["## 需要重新上傳", ""]
    lines += [link(n) for n in to_upload] or ["_這次沒有網頁版 skill 變動。_"]
    lines += ["", "## 所有網頁版 skill", ""]
    lines += [link(s.name) for s in web_skills] or ["_目前沒有網頁版 skill。_"]
    return "\n".join(lines) + "\n"
