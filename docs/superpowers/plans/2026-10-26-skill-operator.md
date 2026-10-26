# skill-operator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **History:** executed on 2026-10-26/27. The repo was later moved to the `shao-pasteur` organization and its content translated to English; repo names and message strings below reflect that current state.

**Goal:** Build a public repo that manages my own skills as `SKILL.md` files, groups them into plugins by purpose, installs them through marketplaces in Claude Code, Codex, Copilot CLI and Cursor, and packages zips for web apps automatically.

**Architecture:** Only `categories.yaml` and `plugins/<category>/skills/<skill>/` are maintained by hand. The Python package `scripts/skillops/` reads them (catalog), validates them (validate), generates each platform's manifests and the README catalog (manifests, readme, build), packages zips (package, release_notes) and scaffolds skills (scaffold). `scripts/cli.py` provides the subcommands and the Makefile wraps them. GitHub Actions run the checks and publish the `latest` release.

**Tech Stack:** Python 3.12 (managed by uv), PyYAML, pytest, GNU Make, GitHub Actions, gitleaks.

**Spec:** `docs/superpowers/specs/2026-10-26-skill-operator-design.md`

## Global Constraints

- Python `>=3.11`, `.python-version` is `3.12`; every Python command runs through `uv run`.
- The only runtime dependency is `pyyaml>=6.0`; the dev dependency is `pytest>=8`.
- GitHub repo: `shao-pasteur/skill-operator` (public), built from `owner.github` + `marketplace` in `categories.yaml`.
- License: MIT (`LICENSE` and the `license` of every generated plugin.json).
- No generated JSON may contain a `version` field.
- Generated JSON is always `json.dumps(obj, ensure_ascii=False, indent=2) + "\n"`; output must be deterministic (same input → byte-identical output).
- Skill `name` rules: `^[a-z0-9]+(?:-[a-z0-9]+)*$`, 1–64 characters, equal to the folder name, unique across the repo.
- `description` 1–1024 characters; `compatibility` 1–500 characters; `metadata` is a string → string mapping; `metadata.web` must be `"true"` or `"false"`.
- Standard frontmatter fields: `name`, `description`, `license`, `compatibility`, `metadata`; any other field only warns.
- User-facing messages (errors, warnings, templates, README, release notes) are in English. (The first version used Traditional Chinese; the repo was translated later.)
- Ask the user before any outward-facing action (creating the GitHub repo, pushing).

## Review Focus

1. **Unquoted `web: false` in YAML** parses as a boolean. The user expects a clear error saying to write the string `"false"`, not to have it treated as true or to crash → Task 2 `test_metadata_bool_value_is_error`.
2. **Deleting the last skill of a category**: `make build` must delete that category's three plugin.json files, and `make check` must report them before that, or the marketplace points at an empty plugin → Task 4 `test_build_removes_stale_manifests`, `test_check_reports_stale_manifests`.
3. **A SKILL.md edited on Windows (CRLF line endings)** must parse → Task 1 `test_parse_crlf`.
4. **A skill folder with `__pycache__`, `.DS_Store` and executable scripts**: the zip must leave out the junk, keep the executable bit and come out identical on every run → Task 5 `test_zip_excludes_junk_and_keeps_exec_bit`, `test_zip_is_deterministic`.
5. **The first push or a force push, where `github.event.before` is all zeros or an unknown commit**: the release notes must treat every web skill as changed instead of failing the workflow → Task 5 `test_git_changed_paths_unknown_base_returns_none`.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml`, `.python-version` | uv project settings, dependencies, pytest settings (`pythonpath = ["scripts"]`) |
| `categories.yaml` | The category list (spec §5) |
| `scripts/cli.py` | argparse subcommands: `build`, `check`, `package`, `new`, `import`, `release-notes` |
| `scripts/skillops/frontmatter.py` | Parse SKILL.md frontmatter |
| `scripts/skillops/catalog.py` | Data model and `load_catalog` |
| `scripts/skillops/validate.py` | `Issue` and every skill rule check |
| `scripts/skillops/manifests.py` | Render the six kinds of manifest |
| `scripts/skillops/readme.py` | The README Skill catalog table and marker replacement |
| `scripts/skillops/build.py` | Assemble every generated file, write, compare, remove stale files |
| `scripts/skillops/package.py` | Web zip packaging |
| `scripts/skillops/release_notes.py` | Work out changed skills and render the release notes |
| `scripts/skillops/scaffold.py` | `new_skill`, `import_skill` |
| `scripts/tests/conftest.py` | `RepoBuilder`, a mini repo for tests |
| `scripts/tests/test_*.py` | Tests for each module |
| `Makefile`, `.githooks/pre-commit` | Command wrappers and the pre-commit hook |
| `.github/workflows/check.yml`, `release.yml` | CI and the `latest` release |
| `README.md`, `AGENTS.md`, `CLAUDE.md`, `LICENSE`, `.gitignore`, `.gitattributes` | Docs and repo settings |

---

### Task 1: Project skeleton, frontmatter parsing and catalog loading

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `categories.yaml`
- Create: `scripts/skillops/__init__.py` (empty), `scripts/skillops/frontmatter.py`, `scripts/skillops/catalog.py`
- Create: `scripts/tests/conftest.py`
- Test: `scripts/tests/test_frontmatter.py`, `scripts/tests/test_catalog.py`

**Interfaces:**
- Produces (`skillops.frontmatter`):
  - `class FrontmatterError(ValueError)`
  - `parse_frontmatter(text: str) -> tuple[dict, str]`: returns `(frontmatter, body)`
- Produces (`skillops.catalog`):
  - `NAME_RE: re.Pattern` (`^[a-z0-9]+(?:-[a-z0-9]+)*$`)
  - `class CatalogError(Exception)`
  - `@dataclass(frozen=True) Owner(name: str, github: str)`
  - `@dataclass(frozen=True) Category(id: str, title: str, description: str)`
  - `@dataclass(frozen=True) Skill(category: str, dir_name: str, path: Path, frontmatter: dict, body: str)` with properties `name -> str` (the frontmatter `name`, or `dir_name` when missing), `description -> str` (`""` when missing), `has_scripts -> bool` (`path / "scripts"` is a folder), `web -> bool` (`metadata.web == "true"`; True when there is no `web` key and no scripts; otherwise False), `rel_path -> str` (POSIX path relative to the repo root)
  - `@dataclass(frozen=True) Catalog(root: Path, marketplace: str, owner: Owner, categories: list[Category], skills: list[Skill])` with `repo_slug -> str` (`f"{owner.github}/{marketplace}"`), `repo_url -> str` (`https://github.com/{repo_slug}`), `skills_in(category_id: str) -> list[Skill]`, `active_categories() -> list[Category]` (in YAML order, only categories with at least one skill)
  - `load_catalog(root: Path) -> Catalog`
- Produces (`scripts/tests/conftest.py`): fixture `repo` returning a `RepoBuilder` (with the default categories and a README containing the catalog markers already written):
  - `RepoBuilder.root: Path`
  - `write_categories(categories: list[dict] | None = None) -> None`: defaults to `marketplace: test-market`, `owner: {name: Tester, github: tester}`, categories `dev` (title `Development`, description `Dev tools`) and `finance` (title `Finance`, description `Finance tools`)
  - `add_skill(category: str, name: str, *, frontmatter: dict | None = None, body: str = "# Instructions\n", files: dict[str, str] | None = None, raw: str | None = None) -> Path`: default frontmatter `{"name": name, "description": "A test skill used by the toolkit tests. " + "x" * 20}`; `raw` writes the whole SKILL.md as given; `files` maps paths inside the skill folder to content
  - `write_readme(text: str | None = None) -> None`: default `"# Test\n\n<!-- catalog:start -->\n<!-- catalog:end -->\n"`

- [ ] **Step 1: Create `pyproject.toml`, `.python-version`, `.gitignore`**

`pyproject.toml`: `[project]` name `skill-operator`, version `0.0.0`, `requires-python = ">=3.11"`, `dependencies = ["pyyaml>=6.0"]`; `[dependency-groups] dev = ["pytest>=8"]`; `[tool.uv] package = false`; `[tool.pytest.ini_options] testpaths = ["scripts/tests"]`, `pythonpath = ["scripts"]`. `.python-version` contains `3.12`. `.gitignore`: `dist/`, `.venv/`, `__pycache__/`, `*.pyc`, `.DS_Store`, `.pytest_cache/`.

- [ ] **Step 2: Write the failing frontmatter tests**

```python
from skillops.frontmatter import parse_frontmatter, FrontmatterError
import pytest

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
```

- [ ] **Step 3: Run the tests and watch them fail**

Run: `uv run pytest scripts/tests/test_frontmatter.py -v`
Expected: FAIL (`ModuleNotFoundError: skillops.frontmatter`)

- [ ] **Step 4: Implement `parse_frontmatter(text: str) -> tuple[dict, str]`**

Normalize `\r\n` to `\n` first. The first line must be `---` (otherwise the message mentions "start"); find the next line that is only `---` (if none, the message mentions "closing"); parse what is between with `yaml.safe_load` (turn `yaml.YAMLError` into a `FrontmatterError` mentioning "YAML"); a non-dict result gives a message mentioning "mapping". Empty frontmatter returns `{}`.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `uv run pytest scripts/tests/test_frontmatter.py -v`
Expected: 6 passed

- [ ] **Step 6: Write `conftest.py` and the failing catalog tests**

```python
from skillops.catalog import load_catalog, CatalogError
import pytest

def test_load_basic(repo):
    repo.add_skill("dev", "foo")
    repo.add_skill("dev", "bar", files={"scripts/run.py": "print(1)\n"}, frontmatter={"name": "bar", "description": "x"})
    cat = load_catalog(repo.root)
    assert cat.marketplace == "test-market"
    assert cat.repo_slug == "tester/test-market"
    assert [s.dir_name for s in cat.skills] == ["bar", "foo"]
    assert [c.id for c in cat.active_categories()] == ["dev"]
    bar = cat.skills[0]
    assert bar.has_scripts and bar.web is False
    assert cat.skills[1].web is True
    assert bar.rel_path == "plugins/dev/skills/bar"

def test_skills_ordered_by_category_order(repo):
    repo.add_skill("finance", "aaa")
    repo.add_skill("dev", "zzz")
    assert [s.dir_name for s in load_catalog(repo.root).skills] == ["zzz", "aaa"]

def test_web_explicit_true_with_scripts(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": "x", "metadata": {"web": "true"}}, files={"scripts/a.sh": "echo\n"})
    assert load_catalog(repo.root).skills[0].web is True

def test_unknown_category_folder(repo):
    (repo.root / "plugins" / "ghost" / "skills").mkdir(parents=True)
    with pytest.raises(CatalogError, match="plugins/ghost"):
        load_catalog(repo.root)

def test_skill_dir_without_skill_md(repo):
    (repo.root / "plugins" / "dev" / "skills" / "empty").mkdir(parents=True)
    with pytest.raises(CatalogError, match="SKILL.md"):
        load_catalog(repo.root)

def test_bad_frontmatter_reports_path(repo):
    repo.add_skill("dev", "foo", raw="no frontmatter\n")
    with pytest.raises(CatalogError, match="plugins/dev/skills/foo/SKILL.md"):
        load_catalog(repo.root)

def test_missing_categories_yaml(tmp_path):
    with pytest.raises(CatalogError, match="categories.yaml"):
        load_catalog(tmp_path)

@pytest.mark.parametrize("bad", [
    {"marketplace": "m", "owner": {"name": "a"}, "categories": []},           # missing owner.github
    {"marketplace": "m", "owner": {"name": "a", "github": "g"}, "categories": [{"id": "Dev", "title": "t", "description": "d"}]},  # bad id
    {"marketplace": "m", "owner": {"name": "a", "github": "g"}, "categories": [{"id": "a", "title": "t", "description": "d"}, {"id": "a", "title": "t", "description": "d"}]},  # duplicate id
])
def test_invalid_categories_yaml(repo, bad):
    import yaml
    (repo.root / "categories.yaml").write_text(yaml.safe_dump(bad, allow_unicode=True), encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(repo.root)

def test_hidden_and_file_entries_ignored(repo):
    repo.add_skill("dev", "foo")
    (repo.root / "plugins" / ".DS_Store").write_text("")
    (repo.root / "plugins" / "dev" / "skills" / ".DS_Store").write_text("")
    assert len(load_catalog(repo.root).skills) == 1
```

- [ ] **Step 7: Run the tests and watch them fail**

Run: `uv run pytest scripts/tests/test_catalog.py -v`
Expected: FAIL (`ModuleNotFoundError: skillops.catalog`)

- [ ] **Step 8: Implement the `catalog.py` data model and `load_catalog(root: Path) -> Catalog`**

Validate the required keys of `categories.yaml` (`marketplace`, `owner.name`, `owner.github`, `categories[].id/title/description`, all non-empty strings; ids match `NAME_RE` and are unique). Scan the non-hidden folders under `plugins/`; a name that is not a category raises a `CatalogError` containing `plugins/<name>`. Scan the non-hidden folders under `plugins/<category>/skills/`; a missing `SKILL.md` or unparsable frontmatter raises a `CatalogError` containing that file's relative path. Sort skills by (category order in the YAML, `dir_name`).

- [ ] **Step 9: Run the tests and watch them pass**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 10: Create the real `categories.yaml`**

Use the YAML in spec §5 (`marketplace: skill-operator`, `owner: {name: Yuan, github: shao-pasteur}`, the six categories dev / writing / research / finance / productivity / meta with their titles and descriptions).

Run: `PYTHONPATH=scripts uv run python -c "from pathlib import Path; from skillops.catalog import load_catalog; print(load_catalog(Path('.')).repo_slug)"`
Expected: `shao-pasteur/skill-operator`

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml .python-version .gitignore uv.lock categories.yaml scripts/
git commit -m "feat: add catalog loading and frontmatter parsing"
```

---

### Task 2: Skill validation rules

**Files:**
- Create: `scripts/skillops/validate.py`
- Test: `scripts/tests/test_validate.py`

**Interfaces:**
- Consumes: `Catalog`, `Skill`, `NAME_RE` (Task 1)
- Produces:
  - `@dataclass(frozen=True) Issue(level: str, path: str, message: str)` where `level` is `"error"` or `"warning"`
  - `STANDARD_FIELDS = frozenset({"name", "description", "license", "compatibility", "metadata"})`
  - `validate_catalog(catalog: Catalog) -> list[Issue]` (ordered by skill, then by rule)

- [ ] **Step 1: Write the failing tests**

Helpers: `def errors(issues): return [i.message for i in issues if i.level == "error"]`, and `warnings` likewise. Each test creates a skill with `repo.add_skill(...)` and calls `validate_catalog(load_catalog(repo.root))`.

```python
def test_valid_skill_has_no_issues(repo):           # default skill → issues == []
def test_name_must_match_dir(repo):                 # frontmatter name "other" → an error mentions "folder"
@pytest.mark.parametrize("name", ["Foo", "-foo", "foo-", "foo--bar", "a" * 65, ""])
def test_invalid_name(repo, name):                  # folder "foo", frontmatter name from the parameter → at least one error mentions "name"
def test_missing_name_and_description(repo):        # frontmatter {} → errors mention "name" and "description"
def test_description_too_long(repo):                # "x" * 1025 → an error mentions "1024"
def test_description_todo_is_error(repo):           # "TODO describe…" → an error mentions "template"
def test_compatibility_too_long(repo):              # "x" * 501 → an error mentions "500"
def test_metadata_bool_value_is_error(repo):        # raw frontmatter "metadata:\n  web: false" → an error mentions '"false"'
def test_metadata_web_invalid_value(repo):          # metadata.web "no" → an error mentions "web"
def test_scripts_require_web(repo):                 # files={"scripts/a.py": "x=1\n"}, no metadata → an error mentions "metadata.web"
def test_duplicate_names_across_categories(repo):   # dev/foo and finance/foo → two errors mention "also used by"
def test_missing_referenced_file(repo):             # body "See [the guide](references/guide.md) and scripts/run.py." with neither file present → two errors, each with its path
def test_existing_reference_and_urls_ok(repo):      # body with "references/a.md" (exists), "https://x.com/scripts/y.py", "[a](#scripts)" → no errors
def test_python_syntax_error(repo):                 # scripts/bad.py "def (:\n", metadata.web "false" → an error mentions "bad.py"
def test_shell_syntax_error(repo):                  # scripts/bad.sh "if then\n" → an error mentions "bad.sh"
def test_python_check_writes_no_pycache(repo):      # valid scripts/ok.py → no __pycache__ in the skill folder after validation
@pytest.mark.parametrize("text", ["/Users/alice/x", "/home/bob/x", r"C:\Users\carol\x"])
def test_personal_path_is_error(repo, text):        # files={"references/a.md": text} referenced from the body → an error mentions "personal path", path is that file
def test_placeholder_path_ok(repo):                 # "/Users/<you>/x" → no errors
def test_email_is_warning(repo):                    # body contains "me@example.com" → a warning mentions "email", no errors
def test_long_skill_md_warning(repo):               # body of 501 lines → a warning mentions "500"
def test_short_description_warning(repo):           # description "Short" → a warning mentions "50"
def test_platform_field_warning(repo):              # adds "allowed-tools": "Read" → a warning mentions "allowed-tools"
def test_binary_files_skipped(repo):                # assets/img.png with b"\x89PNG\x00\xff" → no crash, no errors
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `uv run pytest scripts/tests/test_validate.py -v`
Expected: FAIL (`ModuleNotFoundError: skillops.validate`)

- [ ] **Step 3: Implement `validate_catalog(catalog: Catalog) -> list[Issue]`**

Rules and limits follow the Global Constraints and spec §4 and §8. Details to pin down:
- File references: take Markdown link targets `\]\(([^)\s]+)\)` and bare paths `(?<![\w/.:-])((?:scripts|references|assets)/[\w./-]+)` from the body, skip anything containing `://` or starting with `#`, strip trailing `.,;:)`, and check that `skill.path / ref` exists.
- Personal paths: match every file under `skill.path` (`rglob`, skipping `__pycache__` and files that are not UTF-8) against `/Users/[^/\s<>"'\`]+/`, `/home/[^/\s<>"'\`]+/`, `(?i)C:\\Users\\[^\\\s<>]+\\`; `Issue.path` is that file's repo-relative path.
- Email: `[\w.+-]+@[\w-]+\.[\w.-]+` over the same text files, as a warning.
- Python syntax uses the built-in `compile(source, filename, "exec")` (no `.pyc` written); shell uses `subprocess.run(["bash", "-n", path])`, and a non-zero exit is an error.
- When a `metadata` value is not a string, the message shows how to write it, for example `metadata.web must be a string; write it as "false"`.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add scripts/skillops/validate.py scripts/tests/test_validate.py
git commit -m "feat: add skill validation rules"
```

---

### Task 3: Manifest and README catalog generation

**Files:**
- Create: `scripts/skillops/manifests.py`, `scripts/skillops/readme.py`
- Test: `scripts/tests/test_manifests.py`, `scripts/tests/test_readme.py`

**Interfaces:**
- Consumes: `Catalog`, `CatalogError` (Task 1)
- Produces (`skillops.manifests`):
  - `LICENSE_ID = "MIT"`
  - `MANIFEST_DIRS = (".claude-plugin", ".codex-plugin", ".cursor-plugin")`
  - `dump_json(obj: object) -> str`
  - `render_manifests(catalog: Catalog) -> dict[str, str]` (repo-relative POSIX path → file content)
- Produces (`skillops.readme`):
  - `CATALOG_START = "<!-- catalog:start -->"`, `CATALOG_END = "<!-- catalog:end -->"`
  - `summarize(description: str, limit: int = 80) -> str`
  - `render_catalog_table(catalog: Catalog) -> str`
  - `replace_catalog_block(readme: str, table: str) -> str` (raises `CatalogError` mentioning "README.md" when the markers are missing or out of order)

- [ ] **Step 1: Write the failing manifest tests**

With the fixture (`test-market`, `Tester`, `tester`) and one skill in `dev` only:

```python
def test_manifest_paths(repo):
    repo.add_skill("dev", "foo")
    files = render_manifests(load_catalog(repo.root))
    assert sorted(files) == [
        ".agents/plugins/marketplace.json",
        ".claude-plugin/marketplace.json",
        ".cursor-plugin/marketplace.json",
        "plugins/dev/.claude-plugin/plugin.json",
        "plugins/dev/.codex-plugin/plugin.json",
        "plugins/dev/.cursor-plugin/plugin.json",
    ]  # finance has no skills → nothing generated

def test_manifest_contents(repo):
    repo.add_skill("dev", "foo")
    f = {k: json.loads(v) for k, v in render_manifests(load_catalog(repo.root)).items()}
    assert f[".claude-plugin/marketplace.json"] == {
        "name": "test-market", "owner": {"name": "Tester"},
        "plugins": [{"name": "dev", "source": "./plugins/dev", "description": "Dev tools"}]}
    assert f[".agents/plugins/marketplace.json"] == {
        "name": "test-market", "interface": {"displayName": "test-market"},
        "plugins": [{"name": "dev", "source": {"source": "local", "path": "./plugins/dev"},
                     "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                     "category": "Development"}]}
    assert f[".cursor-plugin/marketplace.json"] == {
        "name": "test-market", "owner": {"name": "Tester"},
        "plugins": [{"name": "dev", "source": "./plugins/dev", "description": "Dev tools"}]}
    common = {"name": "dev", "description": "Dev tools", "author": {"name": "Tester"}, "license": "MIT"}
    assert f["plugins/dev/.claude-plugin/plugin.json"] == {**common, "repository": "https://github.com/tester/test-market"}
    assert f["plugins/dev/.cursor-plugin/plugin.json"] == {**common, "repository": "https://github.com/tester/test-market"}
    assert f["plugins/dev/.codex-plugin/plugin.json"] == {**common, "skills": "./skills/"}

def test_no_version_anywhere(repo):          # no output contains '"version"'
def test_unicode_not_escaped(repo):          # output keeps non-ASCII text as is, with no "\\u" escapes
def test_deterministic(repo):                # two render_manifests calls give equal results
def test_trailing_newline(repo):             # every file ends with "\n"
```

- [ ] **Step 2: Write the failing readme tests**

```python
def test_summarize():
    assert summarize("One。Two。") == "One。"
    assert summarize("First sentence. Second.") == "First sentence."
    assert summarize("line1\nline2") == "line1"
    assert summarize("x" * 100) == "x" * 79 + "…"
    assert summarize("a | b") == "a \\| b"

def test_table(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": "Does foo. More text."})
    repo.add_skill("dev", "bar", frontmatter={"name": "bar", "description": "Does bar.", "metadata": {"web": "false"}})
    t = render_catalog_table(load_catalog(repo.root))
    assert "### Development (`dev`)" in t
    assert "| `foo` | Does foo. | [Download](https://github.com/tester/test-market/releases/download/latest/foo.zip) |" in t
    assert "| `bar` | Does bar. | — |" in t
    assert "Finance" not in t          # empty categories are not listed

def test_table_empty(repo):            # no skills → "_No skills yet._"
def test_replace_block():              # replace "OLD" in "a\n<!-- catalog:start -->\nOLD\n<!-- catalog:end -->\nb\n" with "NEW" → "a\n<!-- catalog:start -->\nNEW\n<!-- catalog:end -->\nb\n"
def test_replace_block_missing_markers():  # no markers → CatalogError mentioning "README.md"
```

Table format: one section per active category, `### {title} (\`{id}\`)`, a blank line, then the header `| Skill | Description | Web apps |` and `|---|---|---|`, and one row per skill, `| \`{name}\` | {summarize(description)} | {download link or —} |`; a blank line between sections.

- [ ] **Step 3: Run the tests and watch them fail**

Run: `uv run pytest scripts/tests/test_manifests.py scripts/tests/test_readme.py -v`
Expected: FAIL (modules missing)

- [ ] **Step 4: Implement `manifests.py` and `readme.py`**

`summarize`: take everything up to and including the first `。`, the first `.` followed by whitespace, or up to the first newline; beyond `limit` characters, cut to `limit - 1` characters plus `…`; turn `|` into `\|`.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add scripts/skillops/manifests.py scripts/skillops/readme.py scripts/tests/test_manifests.py scripts/tests/test_readme.py
git commit -m "feat: render platform manifests and README catalog"
```

---

### Task 4: build / check commands, Makefile and README skeleton

**Files:**
- Create: `scripts/skillops/build.py`, `scripts/cli.py`, `Makefile`, `.gitattributes`, `README.md` (skeleton, completed in Task 7)
- Test: `scripts/tests/test_build.py`, `scripts/tests/test_cli.py`

**Interfaces:**
- Consumes: `load_catalog` (Task 1), `validate_catalog`, `Issue` (Task 2), `render_manifests`, `MANIFEST_DIRS`, `render_catalog_table`, `replace_catalog_block` (Task 3)
- Produces (`skillops.build`):
  - `generated_files(catalog: Catalog) -> dict[str, str]` (the manifests plus the complete new `README.md`)
  - `stale_manifests(catalog: Catalog, expected: Iterable[str]) -> list[str]` (sorted paths on disk matching `plugins/*/<MANIFEST_DIRS>/plugin.json` that are not in expected)
  - `write_generated(catalog: Catalog) -> list[str]` (computes everything before writing; returns changed or deleted paths; removes a manifest folder that becomes empty)
  - `check_generated(catalog: Catalog) -> list[Issue]`
- Produces (`scripts/cli.py`): `main(argv: list[str] | None = None) -> int`; global option `--root` (defaults to the folder above `cli.py`); subcommands `build` and `check` (later tasks add `package`, `release-notes`, `new`, `import`). Issue output: `ERROR {path}: {message}` / `WARN  {path}: {message}`, then a final line `{n} error(s), {m} warning(s)`; returns 1 when there are errors. A `CatalogError` always prints `ERROR {message}` and returns 1.

- [ ] **Step 1: Write the failing build tests**

```python
def test_write_then_check_clean(repo):
    repo.add_skill("dev", "foo")
    cat = load_catalog(repo.root)
    assert write_generated(cat)                          # the first run writes files
    assert write_generated(load_catalog(repo.root)) == []  # the second run is idempotent
    assert check_generated(load_catalog(repo.root)) == []

def test_check_detects_outdated(repo):
    repo.add_skill("dev", "foo"); write_generated(load_catalog(repo.root))
    (repo.root / ".claude-plugin/marketplace.json").write_text("{}\n")
    issues = check_generated(load_catalog(repo.root))
    assert any("make build" in i.message and i.path == ".claude-plugin/marketplace.json" for i in issues)

def test_check_detects_missing(repo):          # never built → an error for every generated file
def test_build_removes_stale_manifests(repo):
    repo.add_skill("dev", "foo"); repo.add_skill("finance", "bar")
    write_generated(load_catalog(repo.root))
    shutil.rmtree(repo.root / "plugins/finance/skills/bar")
    changed = write_generated(load_catalog(repo.root))
    assert "plugins/finance/.claude-plugin/plugin.json" in changed
    assert not (repo.root / "plugins/finance/.claude-plugin").exists()

def test_check_reports_stale_manifests(repo):  # same, without rebuilding → check_generated reports finance's plugin.json
def test_build_writes_nothing_on_error(repo):  # README without markers → generated_files raises CatalogError and .claude-plugin/ does not exist
```

- [ ] **Step 2: Write the failing CLI tests**

```python
def test_cli_build_and_check(repo, capsys):
    repo.add_skill("dev", "foo")
    assert main(["--root", str(repo.root), "build"]) == 0
    assert main(["--root", str(repo.root), "check"]) == 0
    assert "0 error(s)" in capsys.readouterr().out

def test_cli_check_fails_on_error(repo, capsys):   # frontmatter name differs from the folder → returns 1, output contains "ERROR plugins/dev/skills/foo"
def test_cli_catalog_error(repo, capsys):          # create plugins/ghost/ → build returns 1, output contains "ERROR"
def test_cli_warnings_do_not_fail(repo, capsys):   # description "Short" → check returns 0, output contains "WARN"
```

- [ ] **Step 3: Run the tests and watch them fail**

Run: `uv run pytest scripts/tests/test_build.py scripts/tests/test_cli.py -v`
Expected: FAIL (modules missing)

- [ ] **Step 4: Implement `build.py` and `cli.py` (`build`, `check`)**

`cli.py` adds its own folder to `sys.path` first, so `uv run python scripts/cli.py` can `import skillops`. `check` = `validate_catalog` + `check_generated`, printed sorted by path.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 6: Create the `Makefile`, `.gitattributes` and README skeleton, and run them in the real repo**

`Makefile` (every target declared `.PHONY`):
```make
PY := uv run python scripts/cli.py
build: ; $(PY) build
check:
	$(PY) check
	@if command -v claude >/dev/null 2>&1 && [ -f .claude-plugin/marketplace.json ]; then claude plugin validate .; fi
test: ; uv run pytest
```
`.gitattributes`: `.claude-plugin/** linguist-generated=true`, `.agents/** linguist-generated=true`, `.cursor-plugin/** linguist-generated=true`, `plugins/*/.claude-plugin/** linguist-generated=true`, `plugins/*/.codex-plugin/** linguist-generated=true`, `plugins/*/.cursor-plugin/** linguist-generated=true`.
`README.md` skeleton: the title `# skill-operator`, one sentence, `## Skill catalog`, then `<!-- catalog:start -->` and `<!-- catalog:end -->`.

Run: `make build && make check`
Expected: build only updates the README catalog block (to `_No skills yet._`) and generates no manifests; check prints `0 error(s), 0 warning(s)` and exits 0. Without `.claude-plugin/marketplace.json`, `claude plugin validate .` is skipped; it runs for real once Task 8 adds the first skill.

- [ ] **Step 7: Commit**

```bash
git add scripts/ Makefile .gitattributes README.md
git commit -m "feat: add build and check commands"
```

---

### Task 5: Web zip packaging and release notes

**Files:**
- Create: `scripts/skillops/package.py`, `scripts/skillops/release_notes.py`
- Modify: `scripts/cli.py` (add the `package` and `release-notes` subcommands), `Makefile` (add `package`)
- Test: `scripts/tests/test_package.py`, `scripts/tests/test_release_notes.py`

**Interfaces:**
- Consumes: `Catalog`, `Skill.web`, `Skill.name`, `Catalog.repo_slug` (Task 1)
- Produces (`skillops.package`):
  - `EXCLUDE_NAMES = frozenset({"__pycache__", ".DS_Store", ".git"})`, `EXCLUDE_SUFFIXES = (".pyc",)` (later replaced by `EXCLUDE_PATTERNS` during the review fixes)
  - `package_skills(catalog: Catalog, out_dir: Path) -> list[Path]` (clears existing `*.zip` in `out_dir` first; packages only skills whose `web` is True; returns them sorted by name)
- Produces (`skillops.release_notes`):
  - `git_changed_paths(root: Path, base: str | None, head: str) -> list[str] | None` (returns None when `base` is None, empty, all zeros, or `git diff --name-only base head` fails, meaning "treat everything as changed")
  - `changed_skill_names(catalog: Catalog, changed_paths: list[str]) -> list[str]`
  - `render_release_notes(catalog: Catalog, changed: list[str] | None) -> str`
- CLI: `package --out <dir>` (default `dist`) prints each zip path; `release-notes --base <rev> --head <rev>` (`--base` optional) runs `git_changed_paths` → `changed=None` when that returns None, otherwise `changed=changed_skill_names(...)` → `render_release_notes`, and prints the notes to stdout.

- [ ] **Step 1: Write the failing package tests**

```python
def test_only_web_skills_packaged(repo, tmp_path):
    repo.add_skill("dev", "foo")
    repo.add_skill("dev", "bar", frontmatter={"name": "bar", "description": "x", "metadata": {"web": "false"}})
    out = package_skills(load_catalog(repo.root), tmp_path / "dist")
    assert [p.name for p in out] == ["foo.zip"]

def test_zip_layout(repo, tmp_path):
    repo.add_skill("dev", "foo", files={"references/a.md": "a"})
    [z] = package_skills(load_catalog(repo.root), tmp_path / "dist")
    assert sorted(zipfile.ZipFile(z).namelist()) == ["foo/SKILL.md", "foo/references/a.md"]

def test_zip_excludes_junk_and_keeps_exec_bit(repo, tmp_path):
    d = repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": "x", "metadata": {"web": "true"}},
                       files={"scripts/run.sh": "echo\n", "scripts/__pycache__/x.pyc": "", ".DS_Store": ""})
    (d / "scripts/run.sh").chmod(0o755)
    [z] = package_skills(load_catalog(repo.root), tmp_path / "dist")
    zf = zipfile.ZipFile(z)
    assert sorted(zf.namelist()) == ["foo/SKILL.md", "foo/scripts/run.sh"]
    assert (zf.getinfo("foo/scripts/run.sh").external_attr >> 16) & 0o111

def test_zip_is_deterministic(repo, tmp_path):   # package twice (touching a file's mtime in between) → identical zip bytes
def test_stale_zips_removed(repo, tmp_path):     # old.zip in out_dir → gone after packaging
```

- [ ] **Step 2: Write the failing release notes tests**

```python
def test_changed_skill_names(repo):
    repo.add_skill("dev", "foo"); repo.add_skill("finance", "bar")
    cat = load_catalog(repo.root)
    paths = ["plugins/dev/skills/foo/SKILL.md", "plugins/dev/.claude-plugin/plugin.json", "README.md", "plugins/finance/skills/gone/SKILL.md"]
    assert changed_skill_names(cat, paths) == ["foo"]

@pytest.mark.parametrize("base", [None, "", "0" * 40, "deadbeef" * 5])
def test_git_changed_paths_unknown_base_returns_none(tmp_path, base):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert git_changed_paths(tmp_path, base, "HEAD") is None

def test_git_changed_paths_real_diff(tmp_path):  # one file changed between two commits → [that file's path]

def test_notes_lists_changed_web_skills(repo):
    repo.add_skill("dev", "foo"); repo.add_skill("dev", "baz")
    repo.add_skill("dev", "bar", frontmatter={"name": "bar", "description": "x", "metadata": {"web": "false"}})
    notes = render_release_notes(load_catalog(repo.root), ["foo", "bar"])
    assert "## Re-upload needed" in notes
    assert "- [`foo`](https://github.com/tester/test-market/releases/download/latest/foo.zip)" in notes
    assert "`bar`" not in notes.split("## All web skills")[0]   # non-web skills are not listed for re-upload
    assert "## All web skills" in notes and "`baz`" in notes

def test_notes_all_changed_when_none(repo):      # changed=None → every web skill is listed under "Re-upload needed"
def test_notes_nothing_changed(repo):            # changed=[] → "Re-upload needed" shows "_No web skills changed in this push._"
```

Notes format: `## Re-upload needed` (download links for the changed web skills, or `_No web skills changed in this push._`), a blank line, `## All web skills` (download links for every web skill, or `_There are no web skills yet._`).

- [ ] **Step 3: Run the tests and watch them fail**

Run: `uv run pytest scripts/tests/test_package.py scripts/tests/test_release_notes.py -v`
Expected: FAIL (modules missing)

- [ ] **Step 4: Implement `package.py`, `release_notes.py` and the CLI subcommands**

Zip determinism: entries sorted by path, `ZipInfo.date_time = (1980, 1, 1, 0, 0, 0)`, `ZIP_DEFLATED`, `external_attr = (0o755 if the source file has any executable bit else 0o644) << 16`.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 6: Add `package: ; $(PY) package --out dist` to the Makefile**

Run: `make package`
Expected: exits successfully with no zips (there are no skills yet)

- [ ] **Step 7: Commit**

```bash
git add scripts/ Makefile
git commit -m "feat: package web skills and render release notes"
```

---

### Task 6: Scaffolding (new / import)

**Files:**
- Create: `scripts/skillops/scaffold.py`
- Modify: `scripts/cli.py` (add `new` and `import`), `Makefile`
- Test: `scripts/tests/test_scaffold.py`

**Interfaces:**
- Consumes: `load_catalog`, `NAME_RE` (Task 1), `validate_catalog` (Task 2), `EXCLUDE_NAMES`, `EXCLUDE_SUFFIXES` (Task 5)
- Produces:
  - `class ScaffoldError(Exception)`
  - `SKILL_TEMPLATE: str` (with a `{name}` placeholder)
  - `new_skill(root: Path, category: str, name: str) -> Path`
  - `import_skill(root: Path, src: Path, category: str) -> Path`
- CLI: `new --category <id> --name <name>` prints the created path and returns 0; `import --src <path> --category <id>` copies, runs `validate_catalog` over the whole catalog, prints only that skill's issues and returns 1 when there are errors (the files stay so the user can fix them). A `ScaffoldError` prints `ERROR {message}` and returns 1.

`SKILL_TEMPLATE`:

```markdown
---
name: {name}
description: TODO Describe what this skill does and when to use it, including words users are likely to say.
---

# {name}

TODO Write the instructions.
```

- [ ] **Step 1: Write the failing tests**

```python
def test_new_skill_creates_template(repo):
    p = new_skill(repo.root, "dev", "my-skill")
    assert p == repo.root / "plugins/dev/skills/my-skill"
    text = (p / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: my-skill\n")
    issues = validate_catalog(load_catalog(repo.root))
    assert any("template" in i.message for i in issues if i.level == "error")   # the TODO description blocks the commit

@pytest.mark.parametrize("name", ["Bad", "a--b", "x" * 65])
def test_new_skill_rejects_bad_name(repo, name):   # ScaffoldError mentioning "name"
def test_new_skill_unknown_category(repo):         # category "ghost" → ScaffoldError mentioning "ghost"
def test_new_skill_duplicate_name(repo):           # finance/foo exists, new dev/foo → ScaffoldError mentioning "already exists"

def test_import_copies_and_filters(repo, tmp_path):
    src = tmp_path / "ext" / "foo"
    (src / "scripts" / "__pycache__").mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: foo\ndescription: " + "A test skill used by the toolkit tests. " + "x" * 20 + "\nmetadata:\n  web: \"false\"\n---\n", encoding="utf-8")
    (src / "scripts" / "a.py").write_text("x = 1\n")
    (src / "scripts" / "__pycache__" / "a.pyc").write_text("")
    (src / ".DS_Store").write_text("")
    dest = import_skill(repo.root, src, "dev")
    assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()) == ["SKILL.md", "scripts/a.py"]

def test_import_requires_skill_md(repo, tmp_path):     # src without SKILL.md → ScaffoldError mentioning "SKILL.md"
def test_import_refuses_existing(repo, tmp_path):      # destination exists → ScaffoldError mentioning "already exists"
def test_cli_import_reports_issues(repo, tmp_path, capsys):  # src containing "/Users/alice/x" → main([... "import" ...]) returns 1, output mentions "personal path", files copied
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `uv run pytest scripts/tests/test_scaffold.py -v`
Expected: FAIL (module missing)

- [ ] **Step 3: Implement `scaffold.py` and the CLI subcommands**

Name uniqueness is checked against the `dir_name` of every skill in the catalog, plus whether the destination folder exists.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 5: Add `new` and `import` to the Makefile**

```make
new: ; $(PY) new --category $(CATEGORY) --name $(NAME)
import: ; $(PY) import --src $(SRC) --category $(CATEGORY)
```

Run: `make new CATEGORY=dev NAME=tmp-check && make check; rm -rf plugins/dev/skills/tmp-check`
Expected: `make new` prints the path; `make check` exits non-zero because the description is still the template.

- [ ] **Step 6: Commit**

```bash
git add scripts/ Makefile
git commit -m "feat: add new and import scaffolding commands"
```

---

### Task 7: Docs, pre-commit hook and GitHub Actions

**Files:**
- Create: `AGENTS.md`, `CLAUDE.md`, `LICENSE`, `.githooks/pre-commit`, `.github/workflows/check.yml`, `.github/workflows/release.yml`
- Modify: `README.md` (complete it), `Makefile` (add `hooks`)

**Interfaces:**
- Consumes: the CLI subcommands `build`, `check`, `package`, `release-notes` (Tasks 4–5); the Makefile targets (Tasks 4–6)

- [ ] **Step 1: Write `LICENSE`, `AGENTS.md`, `CLAUDE.md`**

`LICENSE`: MIT, year 2026, copyright holder `Yuan`. `CLAUDE.md` is the single line `@AGENTS.md`. `AGENTS.md` covers "What `AGENTS.md` covers" in spec §11: edit only `plugins/*/skills/**` and `categories.yaml`; list the generated files that must not be edited by hand; run `make build && make check` after changes; summarize the format rules in spec §4 and the personal information rules in §12; the commands for adding and importing skills.

- [ ] **Step 2: Write the pre-commit hook and `make hooks`**

`.githooks/pre-commit` (executable). The first version below diffed tracked files only; the review fixes replaced it with `exec uv run python scripts/cli.py precommit`, which also catches untracked generated files:

```sh
#!/bin/sh
set -e
uv run python scripts/cli.py build
if ! git diff --quiet -- README.md .claude-plugin .agents .cursor-plugin 'plugins/*/.claude-plugin' 'plugins/*/.codex-plugin' 'plugins/*/.cursor-plugin'; then
  echo "Generated files were updated; git add them and commit again." >&2
  exit 1
fi
uv run python scripts/cli.py check
```

Makefile: `hooks: ; git config core.hooksPath .githooks`.

Run: `make hooks && git config core.hooksPath`
Expected: `.githooks`

- [ ] **Step 3: Write `.github/workflows/check.yml`**

Triggers: `push`, `pull_request`. One job, `check`, on `ubuntu-latest`, with these steps in order: `actions/checkout@v5` (`fetch-depth: 0`), `astral-sh/setup-uv@v6`, `uv run pytest`, `uv run python scripts/cli.py check`, `gitleaks/gitleaks-action@v2` (env `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`), `if [ -f .claude-plugin/marketplace.json ]; then npx -y @anthropic-ai/claude-code plugin validate .; fi`. (The actions were later pinned to commit SHAs.)

- [ ] **Step 4: Check whether `claude plugin validate` works without a login**

Run: `env -i HOME="$(mktemp -d)" PATH="$PATH" npx -y @anthropic-ai/claude-code plugin validate .`
Expected: one of two outcomes:
- It validates (succeeds, or reports validation errors because there is no marketplace.json yet): keep the CI step.
- It asks for a login or credentials: remove the step from `check.yml` and note "fallback applied" for item 5 in spec §13.

- [ ] **Step 5: Write `.github/workflows/release.yml`**

Triggers: `push` to `main` with `paths: ['plugins/**']`, plus `workflow_dispatch`. `permissions: contents: write`. Steps in order: checkout (`fetch-depth: 0`), setup-uv, `uv run python scripts/cli.py package --out dist`, `uv run python scripts/cli.py release-notes --base "$BASE_SHA" --head "$HEAD_SHA" > notes.md` (with the SHAs passed through `env:`), then this shell (env `GH_TOKEN: ${{ github.token }}`):

```bash
shopt -s nullglob
files=(dist/*.zip)
gh release delete latest --yes --cleanup-tag || true
gh release create latest "${files[@]}" --title "latest" --notes-file notes.md --target "$HEAD_SHA"
```

- [ ] **Step 6: Complete `README.md`**

Add these sections around the catalog block, following spec §11 and §10:
1. `## Install`: the Claude Code, Codex and Copilot CLI commands from the table in spec §11 (`shao-pasteur/skill-operator`, `<category>@skill-operator`); Cursor marked "Not verified yet"; the loop that installs several categories; how to turn on Claude Code auto-update.
2. `## Web apps (claude.ai, ChatGPT, Gemini)`: the download URL format and that the release notes list skills to upload again; upload steps for claude.ai only for now, the other two "Not verified yet" until Task 9.
3. `## Skill catalog`: keep the catalog markers.
4. `## Development`: `make new`, `make import`, `make hooks`, `make build`, `make check`, `make package`, `make test`, and trying a category locally with `claude --plugin-dir ./plugins/<category>`.

Run: `make build && make check`
Expected: `0 error(s)` (the catalog block survives the hand-written content)

- [ ] **Step 7: Commit**

```bash
git add AGENTS.md CLAUDE.md LICENSE .githooks .github README.md Makefile
git commit -m "docs: add README, AGENTS.md, hooks and CI workflows"
```

---

### Task 8: Migrate `tw-stock-daily-tracker` into `finance`

**Files:**
- Create (copied by `make import`): `plugins/finance/skills/tw-stock-daily-tracker/**`
- Modify, inside that folder: `SKILL.md`, `references/workflow.md`, `references/cron_setup.md`, `scripts/build_report.py`, `scripts/install_launchd_jobs.sh`
- Generated: `finance`'s three plugin.json files, the three marketplace.json files, the README catalog

**Interfaces:**
- Consumes: `make import`, `make build`, `make check` (Tasks 4–6)
- New environment variable: `TW_STOCK_INVESTING_DIR`, the absolute path of the `Investing` folder in the Obsidian vault

- [ ] **Step 1: Import and check the validation results**

Run: `make import SRC=$HOME/.claude/skills/tw-stock-daily-tracker CATEGORY=finance`
Expected: non-zero exit, with at least these errors: personal paths in `SKILL.md` (original lines 52 and 106), a personal path in `scripts/build_report.py` (original line 282), and a missing `metadata.web`. Leave the original `~/.claude/skills/tw-stock-daily-tracker` untouched.

- [ ] **Step 2: Make `build_report.py` read the path from the environment**

`VAULT_INVESTING = os.environ.get("TW_STOCK_INVESTING_DIR")`; the defaults of `--base-dir` and `--config` are `{VAULT_INVESTING}/Daily` and `{VAULT_INVESTING}/config.json` when the variable is set, and `None` otherwise. After parsing, if either is still `None`, call `parser.error(...)` with a message naming `TW_STOCK_INVESTING_DIR` and the `--base-dir`/`--config` alternative. Add `import os` if needed.

Run: `env -u TW_STOCK_INVESTING_DIR uv run python plugins/finance/skills/tw-stock-daily-tracker/scripts/build_report.py --input /dev/null`
Expected: exit code 2, stderr mentions `TW_STOCK_INVESTING_DIR`

- [ ] **Step 3: Have `install_launchd_jobs.sh` pass the variable into each plist**

After `set -euo pipefail` and outside the `--uninstall` path, add a `: "${TW_STOCK_INVESTING_DIR:?...}"` guard, and add this inside the plist `<dict>`:

```xml
    <key>EnvironmentVariables</key>
    <dict>
        <key>TW_STOCK_INVESTING_DIR</key>
        <string>${TW_STOCK_INVESTING_DIR}</string>
    </dict>
```

Why: launchd does not read `~/.zshrc`, so scheduled runs never see variables set in the user's shell.

Run: `bash -n plugins/finance/skills/tw-stock-daily-tracker/scripts/install_launchd_jobs.sh`
Expected: no output, exit code 0

- [ ] **Step 4: Update SKILL.md and the references**

- Add `compatibility` (Python 3, network access to TWSE and news sources, and `TW_STOCK_INVESTING_DIR` pointing at the vault's Investing folder; scheduling supports macOS launchd only) and `metadata:` / `  web: "false"` to the frontmatter.
- Replace every `/Users/<you>/Library/Mobile Documents/iCloud~md~obsidian/Documents/<vault name>/Investing` and `.../<vault name>/Investing` with `$TW_STOCK_INVESTING_DIR`.
- Change "`build_report.py`'s default `--base-dir` already points at the vault path" to "`build_report.py` derives its default paths from `TW_STOCK_INVESTING_DIR`".
- Add a `## Required settings` section before "Output location": what `TW_STOCK_INVESTING_DIR` is for; when it is unset, the agent first asks the user for the path of the vault's Investing folder and suggests adding `export TW_STOCK_INVESTING_DIR="…"` to the shell profile; it must also be set before installing the launchd schedule.

- [ ] **Step 5: Generate and validate**

Run: `make build && make check`
Expected: `0 error(s)` (warnings are fine); `plugins/finance/.claude-plugin/plugin.json` and the other two plugin.json files plus the three marketplace.json files are generated; the README catalog shows an "Investing and finance (`finance`)" section with `—` in the web column for `tw-stock-daily-tracker`. The final `claude plugin validate .` passes (`✔ Validation passed`).

Run: `claude plugin validate ./plugins/finance`
Expected: `✔ Validation passed`

- [ ] **Step 6: Commit**

```bash
git add plugins/finance categories.yaml README.md .claude-plugin .agents .cursor-plugin
git commit -m "feat(finance): migrate tw-stock-daily-tracker with configurable vault path"
```

---

### Task 9: Publish and verify each platform (needs the user's confirmation)

**Files:**
- Modify: `README.md` (write in the verified commands), `docs/superpowers/specs/2026-10-26-skill-operator-design.md` (record each result in §13)
- May modify: `scripts/skillops/manifests.py` and its tests (when applying a fallback from spec §13)

- [ ] **Step 1: Get the user's confirmation**

Ask the user: "Create the public repo and push?" Do not continue without an explicit yes.

- [ ] **Step 2: Create the repo and push**

Run: `gh repo create <owner>/skill-operator --public --source . --push` (the repo was first created under the personal account and later transferred to `shao-pasteur`)
Then: `gh run watch --exit-status` (the check and release workflows in turn)
Expected: both workflows succeed and `gh release view latest` exists. There are no web skills yet, so the release has no zips.

- [ ] **Step 3: Verify Claude Code (isolated config folder)**

```bash
export CLAUDE_CONFIG_DIR="$(mktemp -d)"
claude plugin marketplace add shao-pasteur/skill-operator
claude plugin install finance@skill-operator
claude plugin details finance
unset CLAUDE_CONFIG_DIR
```
Expected: `Successfully added marketplace: skill-operator`, `Successfully installed plugin: finance@skill-operator`, and the details list `tw-stock-daily-tracker` under Skills.

- [ ] **Step 4: Verify Codex and Copilot CLI (spec §13 items 2 and 3)**

In an isolated home, run `npx -y @openai/codex plugin marketplace add shao-pasteur/skill-operator` (with `CODEX_HOME="$(mktemp -d)"`), and `npx -y @github/copilot plugin marketplace add shao-pasteur/skill-operator` followed by `plugin install finance@skill-operator`.
Expected: both add and install successfully; record the actual commands. If a login is required and automatic verification is impossible, put these on the list for the user to verify by hand rather than guessing. If a `version` turns out to be required for updates, apply the fallback in spec §9 in `manifests.py`: derive `version` from the first 12 hex digits of the SHA-256 of the category's `skills/` content (format `0.0.0-<hash>`), add the matching tests and rebuild.

- [ ] **Step 5: Update the docs and commit**

Write the verified commands into the README's install section; after each item in spec §13, note "verified", "fallback applied" or "left for the user to verify by hand".

Run: `make build && make check`
Expected: `0 error(s)`

```bash
git add README.md docs/ scripts/ .claude-plugin .agents .cursor-plugin plugins
git commit -m "docs: record platform verification results"
git push
```

- [ ] **Step 6: Report to the user**

List: each platform's verification result; what the user must verify by hand (Cursor, web uploads, and zip uploads once there are web skills); a reminder to set `TW_STOCK_INVESTING_DIR` in `~/.zshrc`; and that once the plugin version works, the user decides whether to delete `~/.claude/skills/tw-stock-daily-tracker` so the skill does not trigger twice.
