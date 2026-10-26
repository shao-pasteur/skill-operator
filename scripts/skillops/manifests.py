"""Render the marketplace and plugin manifests each platform reads."""

import json

from skillops.catalog import Catalog, Category

LICENSE_ID = "MIT"
MANIFEST_DIRS = (".claude-plugin", ".codex-plugin", ".cursor-plugin")


def dump_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def _plugin_common(catalog: Catalog, category: Category) -> dict:
    return {
        "name": category.id,
        "description": category.description,
        "author": {"name": catalog.owner.name},
        "license": LICENSE_ID,
    }


def render_manifests(catalog: Catalog) -> dict[str, str]:
    categories = catalog.active_categories()
    owner = {"name": catalog.owner.name}
    files: dict[str, str] = {}

    # Claude Code reads this one; Copilot CLI falls back to it as well.
    files[".claude-plugin/marketplace.json"] = dump_json({
        "name": catalog.marketplace,
        "owner": owner,
        "plugins": [
            {"name": c.id, "source": f"./plugins/{c.id}", "description": c.description}
            for c in categories
        ],
    })
    files[".agents/plugins/marketplace.json"] = dump_json({
        "name": catalog.marketplace,
        "interface": {"displayName": catalog.marketplace},
        "plugins": [
            {
                "name": c.id,
                "source": {"source": "local", "path": f"./plugins/{c.id}"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": c.title,
            }
            for c in categories
        ],
    })
    files[".cursor-plugin/marketplace.json"] = dump_json({
        "name": catalog.marketplace,
        "owner": owner,
        "plugins": [
            {"name": c.id, "source": f"./plugins/{c.id}", "description": c.description}
            for c in categories
        ],
    })

    for c in categories:
        common = _plugin_common(catalog, c)
        base = f"plugins/{c.id}"
        files[f"{base}/.claude-plugin/plugin.json"] = dump_json({**common, "repository": catalog.repo_url})
        files[f"{base}/.codex-plugin/plugin.json"] = dump_json({**common, "skills": "./skills/"})
        files[f"{base}/.cursor-plugin/plugin.json"] = dump_json({**common, "repository": catalog.repo_url})
    return files
