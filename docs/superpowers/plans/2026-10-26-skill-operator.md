# skill-operator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一個公開 repo，用 `SKILL.md` 管理自己的 skill，依用途分類成 plugin，透過 marketplace 安裝到 Claude Code、Codex、Copilot CLI、Cursor，並為網頁版 App 自動打包 zip。

**Architecture:** 手動維護的只有 `categories.yaml` 與 `plugins/<分類>/skills/<skill>/`。`scripts/skillops/` 這個 Python 套件負責讀取它們（catalog）、驗證（validate）、產生各平台 manifest 與 README 目錄（manifests、readme、build）、打包 zip（package、release_notes）與腳手架（scaffold），由 `scripts/cli.py` 提供子命令，Makefile 包裝。GitHub Actions 負責檢查與 `latest` Release。

**Tech Stack:** Python 3.12（uv 管理）、PyYAML、pytest、GNU Make、GitHub Actions、gitleaks。

**Spec:** `docs/superpowers/specs/2026-10-26-skill-operator-design.md`

## Global Constraints

- Python `>=3.11`，`.python-version` 為 `3.12`；所有 Python 指令都透過 `uv run` 執行。
- 唯一執行期依賴：`pyyaml>=6.0`；開發依賴：`pytest>=8`。
- GitHub repo：`pasteur-yuan/skill-operator`（公開），由 `categories.yaml` 的 `owner.github` + `marketplace` 組成。
- 授權：MIT（`LICENSE` 與所有產生的 plugin.json 的 `license`）。
- 所有產生的 JSON **不得有 `version` 欄位**。
- 產生的 JSON 一律 `json.dumps(obj, ensure_ascii=False, indent=2) + "\n"`；輸出必須確定性（相同輸入 → 逐位元組相同）。
- skill `name` 規則：`^[a-z0-9]+(?:-[a-z0-9]+)*$`、長度 1–64、等於資料夾名、全 repo 唯一。
- `description` 1–1024 字元；`compatibility` 1–500 字元；`metadata` 為 字串→字串 的 mapping；`metadata.web` 只能是 `"true"` 或 `"false"`。
- 標準 frontmatter 欄位：`name`、`description`、`license`、`compatibility`、`metadata`；其他欄位只發警告。
- 使用者看得到的訊息（錯誤、警告、樣板、README、Release 說明）一律用繁體中文。
- 任何對外動作（建立 GitHub repo、push）執行前必須先取得使用者確認。

## Review Focus

1. **YAML 沒加引號的 `web: false`**：會被解析成布林值。使用者預期看到「要寫成字串 `"false"`」的明確錯誤，而不是被當成 true 或直接崩潰 → Task 2 `test_metadata_bool_value_is_error`。
2. **刪掉某分類的最後一個 skill**：該分類的 3 份 plugin.json 必須被 `make build` 刪除，`make check` 在刪除前要報錯，否則 marketplace 會指向空 plugin → Task 4 `test_build_removes_stale_manifests`、`test_check_reports_stale_manifests`。
3. **在 Windows 編輯過的 SKILL.md（CRLF 換行）**：frontmatter 要能正常解析 → Task 1 `test_parse_crlf`。
4. **skill 資料夾裡有 `__pycache__`、`.DS_Store`、可執行腳本**：zip 要排除垃圾檔、保留執行權限，而且重複打包結果相同 → Task 5 `test_zip_excludes_junk_and_keeps_exec_bit`、`test_zip_is_deterministic`。
5. **第一次 push 或 force push，`github.event.before` 是全 0 或不存在的 commit**：Release 說明要把所有網頁版 skill 視為有變動，而不是讓 workflow 失敗 → Task 5 `test_git_changed_paths_unknown_base_returns_none`。

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `pyproject.toml`、`.python-version` | uv 專案設定、依賴、pytest 設定（`pythonpath = ["scripts"]`） |
| `categories.yaml` | 分類清單（spec §5） |
| `scripts/cli.py` | argparse 子命令：`build`、`check`、`package`、`new`、`import`、`release-notes` |
| `scripts/skillops/frontmatter.py` | 解析 SKILL.md frontmatter |
| `scripts/skillops/catalog.py` | 資料模型與 `load_catalog` |
| `scripts/skillops/validate.py` | `Issue` 與所有 skill 規則檢查 |
| `scripts/skillops/manifests.py` | 產生 6 種 manifest 的內容 |
| `scripts/skillops/readme.py` | README 的 Skill 目錄表格與標記替換 |
| `scripts/skillops/build.py` | 組合所有產生檔、寫入、比對同步、清除過期檔 |
| `scripts/skillops/package.py` | 網頁版 zip 打包 |
| `scripts/skillops/release_notes.py` | 計算變動的 skill 並產生 Release 說明 |
| `scripts/skillops/scaffold.py` | `new_skill`、`import_skill` |
| `scripts/tests/conftest.py` | `RepoBuilder` 測試用迷你 repo |
| `scripts/tests/test_*.py` | 各模組測試 |
| `Makefile`、`.githooks/pre-commit` | 指令包裝與 pre-commit hook |
| `.github/workflows/check.yml`、`release.yml` | CI 與 `latest` Release |
| `README.md`、`AGENTS.md`、`CLAUDE.md`、`LICENSE`、`.gitignore`、`.gitattributes` | 文件與 repo 設定 |

---

### Task 1: 專案骨架、frontmatter 解析與 catalog 載入

**Files:**
- Create: `pyproject.toml`、`.python-version`、`.gitignore`、`categories.yaml`
- Create: `scripts/skillops/__init__.py`（空）、`scripts/skillops/frontmatter.py`、`scripts/skillops/catalog.py`
- Create: `scripts/tests/conftest.py`
- Test: `scripts/tests/test_frontmatter.py`、`scripts/tests/test_catalog.py`

**Interfaces:**
- Produces（`skillops.frontmatter`）：
  - `class FrontmatterError(ValueError)`
  - `parse_frontmatter(text: str) -> tuple[dict, str]`：回傳 `(frontmatter, body)`
- Produces（`skillops.catalog`）：
  - `NAME_RE: re.Pattern`（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）
  - `class CatalogError(Exception)`
  - `@dataclass(frozen=True) Owner(name: str, github: str)`
  - `@dataclass(frozen=True) Category(id: str, title: str, description: str)`
  - `@dataclass(frozen=True) Skill(category: str, dir_name: str, path: Path, frontmatter: dict, body: str)`，屬性：`name -> str`（frontmatter 的 `name`，缺少時用 `dir_name`）、`description -> str`（缺少時為 `""`）、`has_scripts -> bool`（`path / "scripts"` 是資料夾）、`web -> bool`（`metadata.web == "true"`；沒有 `web` 鍵且沒有 scripts 時為 True；其他情況 False）、`rel_path -> str`（相對 repo 根目錄的 POSIX 路徑）
  - `@dataclass(frozen=True) Catalog(root: Path, marketplace: str, owner: Owner, categories: list[Category], skills: list[Skill])`，方法：`repo_slug -> str`（`f"{owner.github}/{marketplace}"`）、`repo_url -> str`（`https://github.com/{repo_slug}`）、`skills_in(category_id: str) -> list[Skill]`、`active_categories() -> list[Category]`（依 yaml 順序，只含至少一個 skill 的分類）
  - `load_catalog(root: Path) -> Catalog`
- Produces（`scripts/tests/conftest.py`）：fixture `repo` 回傳 `RepoBuilder`（已寫好預設 categories 與含 catalog 標記的 README）：
  - `RepoBuilder.root: Path`
  - `write_categories(categories: list[dict] | None = None) -> None`：預設 `marketplace: test-market`、`owner: {name: Tester, github: tester}`、分類 `dev`（title `開發`，description `開發工具`）與 `finance`（title `財務`，description `財務工具`）
  - `add_skill(category: str, name: str, *, frontmatter: dict | None = None, body: str = "# 指令\n", files: dict[str, str] | None = None, raw: str | None = None) -> Path`：預設 frontmatter 為 `{"name": name, "description": "測試用 skill，" + "說明" * 30}`；`raw` 給定時直接寫成 SKILL.md 全文；`files` 是 skill 資料夾內的 相對路徑→內容
  - `write_readme(text: str | None = None) -> None`：預設內容 `"# Test\n\n<!-- catalog:start -->\n<!-- catalog:end -->\n"`

- [ ] **Step 1: 建立 `pyproject.toml`、`.python-version`、`.gitignore`**

`pyproject.toml`：`[project]` name `skill-operator`、version `0.0.0`、`requires-python = ">=3.11"`、`dependencies = ["pyyaml>=6.0"]`；`[dependency-groups] dev = ["pytest>=8"]`；`[tool.uv] package = false`；`[tool.pytest.ini_options] testpaths = ["scripts/tests"]`、`pythonpath = ["scripts"]`。`.python-version` 內容 `3.12`。`.gitignore`：`dist/`、`.venv/`、`__pycache__/`、`*.pyc`、`.DS_Store`、`.pytest_cache/`。

- [ ] **Step 2: 寫 frontmatter 的失敗測試**

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
    with pytest.raises(FrontmatterError, match="開頭"):
        parse_frontmatter("name: foo\n")

def test_missing_closing_delimiter():
    with pytest.raises(FrontmatterError, match="結尾"):
        parse_frontmatter("---\nname: foo\n")

def test_not_a_mapping():
    with pytest.raises(FrontmatterError, match="mapping"):
        parse_frontmatter("---\n- a\n- b\n---\n")

def test_invalid_yaml():
    with pytest.raises(FrontmatterError, match="YAML"):
        parse_frontmatter("---\nname: [unclosed\n---\n")
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `uv run pytest scripts/tests/test_frontmatter.py -v`
Expected: FAIL（`ModuleNotFoundError: skillops.frontmatter`）

- [ ] **Step 4: 實作 `parse_frontmatter(text: str) -> tuple[dict, str]`**

先把 `\r\n` 正規化為 `\n`；第一行必須是 `---`（否則訊息含「開頭」），找下一個只有 `---` 的行（找不到訊息含「結尾」），中間用 `yaml.safe_load`（`yaml.YAMLError` 轉成訊息含「YAML」的 `FrontmatterError`），結果不是 dict 時訊息含「mapping」。空的 frontmatter 回傳 `{}`。

- [ ] **Step 5: 執行測試確認通過**

Run: `uv run pytest scripts/tests/test_frontmatter.py -v`
Expected: 6 passed

- [ ] **Step 6: 寫 `conftest.py` 與 catalog 的失敗測試**

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
    {"marketplace": "m", "owner": {"name": "a"}, "categories": []},           # 缺 owner.github
    {"marketplace": "m", "owner": {"name": "a", "github": "g"}, "categories": [{"id": "Dev", "title": "t", "description": "d"}]},  # id 格式錯
    {"marketplace": "m", "owner": {"name": "a", "github": "g"}, "categories": [{"id": "a", "title": "t", "description": "d"}, {"id": "a", "title": "t", "description": "d"}]},  # id 重複
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

- [ ] **Step 7: 執行測試確認失敗**

Run: `uv run pytest scripts/tests/test_catalog.py -v`
Expected: FAIL（`ModuleNotFoundError: skillops.catalog`）

- [ ] **Step 8: 實作 `catalog.py` 的資料模型與 `load_catalog(root: Path) -> Catalog`**

驗證 `categories.yaml` 的必要鍵（`marketplace`、`owner.name`、`owner.github`、`categories[].id/title/description`，皆為非空字串；id 符合 `NAME_RE` 且不重複）。掃描 `plugins/` 下非隱藏的資料夾，名稱不在分類中就丟出含 `plugins/<名稱>` 的 `CatalogError`；掃描 `plugins/<分類>/skills/` 下非隱藏的資料夾，沒有 `SKILL.md` 或 frontmatter 解析失敗時，丟出含該檔案相對路徑的 `CatalogError`。skills 依（分類在 yaml 的順序, `dir_name`）排序。所有 `CatalogError` 訊息用繁體中文。

- [ ] **Step 9: 執行測試確認通過**

Run: `uv run pytest -v`
Expected: 全部通過

- [ ] **Step 10: 建立真正的 `categories.yaml`**

內容照 spec §5 的 yaml（`marketplace: skill-operator`、`owner: {name: Yuan, github: pasteur-yuan}`、6 個分類 dev / writing / research / finance / productivity / meta 及其 title、description）。

Run: `PYTHONPATH=scripts uv run python -c "from pathlib import Path; from skillops.catalog import load_catalog; print(load_catalog(Path('.')).repo_slug)"`
Expected: `pasteur-yuan/skill-operator`

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml .python-version .gitignore uv.lock categories.yaml scripts/
git commit -m "feat: add catalog loading and frontmatter parsing"
```

---

### Task 2: Skill 驗證規則

**Files:**
- Create: `scripts/skillops/validate.py`
- Test: `scripts/tests/test_validate.py`

**Interfaces:**
- Consumes: `Catalog`、`Skill`、`NAME_RE`（Task 1）
- Produces:
  - `@dataclass(frozen=True) Issue(level: str, path: str, message: str)`，`level` 為 `"error"` 或 `"warning"`
  - `STANDARD_FIELDS = frozenset({"name", "description", "license", "compatibility", "metadata"})`
  - `validate_catalog(catalog: Catalog) -> list[Issue]`（依 skill 順序、再依規則順序排列）

- [ ] **Step 1: 寫失敗測試**

測試輔助：`def errors(issues): return [i.message for i in issues if i.level == "error"]`，`warnings` 同理。每個測試用 `repo.add_skill(...)` 建一個 skill 後呼叫 `validate_catalog(load_catalog(repo.root))`。

```python
def test_valid_skill_has_no_issues(repo):           # 預設 skill → issues == []
def test_name_must_match_dir(repo):                 # frontmatter name "other" → errors 含 "資料夾"
@pytest.mark.parametrize("name", ["Foo", "-foo", "foo-", "foo--bar", "a" * 65, ""])
def test_invalid_name(repo, name):                  # 資料夾名用 "foo"，frontmatter name 用參數 → 至少一個 error 含 "name"
def test_missing_name_and_description(repo):        # frontmatter {} → errors 含 "name" 與 "description"
def test_description_too_long(repo):                # "x" * 1025 → error 含 "1024"
def test_description_todo_is_error(repo):           # "TODO 描述…" → error 含 "樣板"
def test_compatibility_too_long(repo):              # "x" * 501 → error 含 "500"
def test_metadata_bool_value_is_error(repo):        # raw frontmatter "metadata:\n  web: false" → error 含 '"false"'
def test_metadata_web_invalid_value(repo):          # metadata.web "no" → error 含 "web"
def test_scripts_require_web(repo):                 # files={"scripts/a.py": "x=1\n"}，無 metadata → error 含 "metadata.web"
def test_duplicate_names_across_categories(repo):   # dev/foo 與 finance/foo → 兩個 error 都含 "重複"
def test_missing_referenced_file(repo):             # body "見 [說明](references/guide.md) 與 scripts/run.py" 且兩檔都不存在 → 兩個 error，分別含各自路徑
def test_existing_reference_and_urls_ok(repo):      # body 含 "references/a.md"（存在）、"https://x.com/scripts/y.py"、"[a](#scripts)" → 無 error
def test_python_syntax_error(repo):                 # scripts/bad.py "def (:\n"，metadata.web "false" → error 含 "bad.py"
def test_shell_syntax_error(repo):                  # scripts/bad.sh "if then\n" → error 含 "bad.sh"
def test_python_check_writes_no_pycache(repo):      # 合法 scripts/ok.py → 驗證後 skill 資料夾內沒有 __pycache__
@pytest.mark.parametrize("text", ["/Users/alice/x", "/home/bob/x", r"C:\Users\carol\x"])
def test_personal_path_is_error(repo, text):        # files={"references/a.md": text}，body 引用它 → error 含 "個人路徑"，path 為該檔
def test_placeholder_path_ok(repo):                 # "/Users/<你>/x" → 無 error
def test_email_is_warning(repo):                    # body 含 "me@example.com" → warning 含 "email"、無 error
def test_long_skill_md_warning(repo):               # body 501 行 → warning 含 "500"
def test_short_description_warning(repo):           # description "短" → warning 含 "50"
def test_platform_field_warning(repo):              # 加 "allowed-tools": "Read" → warning 含 "allowed-tools"
def test_binary_files_skipped(repo):                # assets/img.png 寫入 b"\x89PNG\x00\xff" → 不崩潰、無 error
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest scripts/tests/test_validate.py -v`
Expected: FAIL（`ModuleNotFoundError: skillops.validate`）

- [ ] **Step 3: 實作 `validate_catalog(catalog: Catalog) -> list[Issue]`**

規則與門檻依 Global Constraints 與 spec §4、§8。需要明確的細節：
- 檔案引用：從 body 擷取 Markdown 連結目標 `\]\(([^)\s]+)\)` 與裸路徑 `(?<![\w/.:-])((?:scripts|references|assets)/[\w./-]+)`，略過含 `://` 或以 `#` 開頭者，去掉結尾的 `.,;:)`，檢查 `skill.path / ref` 是否存在。
- 個人路徑：對 `skill.path` 下所有檔案（`rglob`，略過 `__pycache__` 與無法用 UTF-8 解碼者）比對 `/Users/[^/\s<>"'\`]+/`、`/home/[^/\s<>"'\`]+/`、`(?i)C:\\Users\\[^\\\s<>]+\\`；`Issue.path` 為該檔的 repo 相對路徑。
- email：`[\w.+-]+@[\w-]+\.[\w.-]+`，同樣掃描所有文字檔，層級為 warning。
- Python 語法用內建 `compile(source, filename, "exec")`（不產生 `.pyc`）；shell 用 `subprocess.run(["bash", "-n", path])`，回傳碼非 0 即為 error。
- `metadata` 值不是字串時的訊息要寫出建議寫法，例如 `metadata.web 的值必須是字串，請寫成 "false"`。

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest -v`
Expected: 全部通過

- [ ] **Step 5: Commit**

```bash
git add scripts/skillops/validate.py scripts/tests/test_validate.py
git commit -m "feat: add skill validation rules"
```

---

### Task 3: Manifest 與 README 目錄產生

**Files:**
- Create: `scripts/skillops/manifests.py`、`scripts/skillops/readme.py`
- Test: `scripts/tests/test_manifests.py`、`scripts/tests/test_readme.py`

**Interfaces:**
- Consumes: `Catalog`、`CatalogError`（Task 1）
- Produces（`skillops.manifests`）：
  - `LICENSE_ID = "MIT"`
  - `MANIFEST_DIRS = (".claude-plugin", ".codex-plugin", ".cursor-plugin")`
  - `dump_json(obj: object) -> str`
  - `render_manifests(catalog: Catalog) -> dict[str, str]`（repo 相對 POSIX 路徑 → 檔案內容）
- Produces（`skillops.readme`）：
  - `CATALOG_START = "<!-- catalog:start -->"`、`CATALOG_END = "<!-- catalog:end -->"`
  - `summarize(description: str, limit: int = 80) -> str`
  - `render_catalog_table(catalog: Catalog) -> str`
  - `replace_catalog_block(readme: str, table: str) -> str`（標記缺少或順序錯誤時丟出 `CatalogError`，訊息含「README.md」）

- [ ] **Step 1: 寫 manifests 的失敗測試**

用 fixture（`test-market`、`Tester`、`tester`），只在 `dev` 加一個 skill：

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
    ]  # finance 沒有 skill → 不產生

def test_manifest_contents(repo):
    repo.add_skill("dev", "foo")
    f = {k: json.loads(v) for k, v in render_manifests(load_catalog(repo.root)).items()}
    assert f[".claude-plugin/marketplace.json"] == {
        "name": "test-market", "owner": {"name": "Tester"},
        "plugins": [{"name": "dev", "source": "./plugins/dev", "description": "開發工具"}]}
    assert f[".agents/plugins/marketplace.json"] == {
        "name": "test-market", "interface": {"displayName": "test-market"},
        "plugins": [{"name": "dev", "source": {"source": "local", "path": "./plugins/dev"},
                     "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                     "category": "開發"}]}
    assert f[".cursor-plugin/marketplace.json"] == {
        "name": "test-market", "owner": {"name": "Tester"},
        "plugins": [{"name": "dev", "source": "./plugins/dev", "description": "開發工具"}]}
    common = {"name": "dev", "description": "開發工具", "author": {"name": "Tester"}, "license": "MIT"}
    assert f["plugins/dev/.claude-plugin/plugin.json"] == {**common, "repository": "https://github.com/tester/test-market"}
    assert f["plugins/dev/.cursor-plugin/plugin.json"] == {**common, "repository": "https://github.com/tester/test-market"}
    assert f["plugins/dev/.codex-plugin/plugin.json"] == {**common, "skills": "./skills/"}

def test_no_version_anywhere(repo):          # 所有輸出字串都不含 '"version"'
def test_unicode_not_escaped(repo):          # 輸出含 "開發工具" 原文，不含 "\\u"
def test_deterministic(repo):                # 呼叫兩次 render_manifests 結果相等
def test_trailing_newline(repo):             # 每個檔案內容以 "\n" 結尾
```

- [ ] **Step 2: 寫 readme 的失敗測試**

```python
def test_summarize():
    assert summarize("第一句。第二句。") == "第一句。"
    assert summarize("First sentence. Second.") == "First sentence."
    assert summarize("line1\nline2") == "line1"
    assert summarize("字" * 100) == "字" * 79 + "…"
    assert summarize("a | b") == "a \\| b"

def test_table(repo):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": "做 foo 的事。其他。"})
    repo.add_skill("dev", "bar", frontmatter={"name": "bar", "description": "做 bar。", "metadata": {"web": "false"}})
    t = render_catalog_table(load_catalog(repo.root))
    assert "### 開發（`dev`）" in t
    assert "| `foo` | 做 foo 的事。 | [下載](https://github.com/tester/test-market/releases/download/latest/foo.zip) |" in t
    assert "| `bar` | 做 bar。 | — |" in t
    assert "財務" not in t          # 空分類不列出

def test_table_empty(repo):            # 沒有 skill → "_目前還沒有 skill。_"
def test_replace_block():              # "a\n<!-- catalog:start -->\nOLD\n<!-- catalog:end -->\nb\n" 換成 "NEW" → "a\n<!-- catalog:start -->\nNEW\n<!-- catalog:end -->\nb\n"
def test_replace_block_missing_markers():  # 沒有標記 → CatalogError 含 "README.md"
```

表格格式：每個 active 分類一段 `### {title}（\`{id}\`）`，空一行，接表頭 `| Skill | 說明 | 網頁版 |`、`|---|---|---|`，每列 `| \`{name}\` | {summarize(description)} | {下載連結或 —} |`；分類段落之間空一行。

- [ ] **Step 3: 執行測試確認失敗**

Run: `uv run pytest scripts/tests/test_manifests.py scripts/tests/test_readme.py -v`
Expected: FAIL（模組不存在）

- [ ] **Step 4: 實作 `manifests.py` 與 `readme.py`**

`summarize`：取到第一個 `。`（含）、`. `（含句點）或換行之前；超過 `limit` 字元時截成 `limit - 1` 字元加 `…`；`|` 轉成 `\|`。

- [ ] **Step 5: 執行測試確認通過**

Run: `uv run pytest -v`
Expected: 全部通過

- [ ] **Step 6: Commit**

```bash
git add scripts/skillops/manifests.py scripts/skillops/readme.py scripts/tests/test_manifests.py scripts/tests/test_readme.py
git commit -m "feat: render platform manifests and README catalog"
```

---

### Task 4: build / check 指令、Makefile 與 README 骨架

**Files:**
- Create: `scripts/skillops/build.py`、`scripts/cli.py`、`Makefile`、`.gitattributes`、`README.md`（骨架，Task 7 補完）
- Test: `scripts/tests/test_build.py`、`scripts/tests/test_cli.py`

**Interfaces:**
- Consumes: `load_catalog`（Task 1）、`validate_catalog`、`Issue`（Task 2）、`render_manifests`、`MANIFEST_DIRS`、`render_catalog_table`、`replace_catalog_block`（Task 3）
- Produces（`skillops.build`）：
  - `generated_files(catalog: Catalog) -> dict[str, str]`（manifests 加上完整的新 `README.md`）
  - `stale_manifests(catalog: Catalog, expected: Iterable[str]) -> list[str]`（磁碟上符合 `plugins/*/<MANIFEST_DIRS>/plugin.json` 但不在 expected 的路徑，已排序）
  - `write_generated(catalog: Catalog) -> list[str]`（先算完全部內容才寫入；回傳有變動或被刪除的路徑；刪除後若 manifest 目錄變空就一併刪除）
  - `check_generated(catalog: Catalog) -> list[Issue]`
- Produces（`scripts/cli.py`）：`main(argv: list[str] | None = None) -> int`；全域參數 `--root`（預設為 `cli.py` 上一層目錄）；子命令 `build`、`check`（後續 Task 再加 `package`、`release-notes`、`new`、`import`）。issue 輸出格式：`ERROR {path}: {message}` / `WARN  {path}: {message}`，最後一行 `{n} 個錯誤，{m} 個警告`；有 error 時回傳 1。`CatalogError` 一律印出 `ERROR {訊息}` 並回傳 1。

- [ ] **Step 1: 寫 build 的失敗測試**

```python
def test_write_then_check_clean(repo):
    repo.add_skill("dev", "foo")
    cat = load_catalog(repo.root)
    assert write_generated(cat)                          # 第一次有寫入
    assert write_generated(load_catalog(repo.root)) == []  # 第二次冪等
    assert check_generated(load_catalog(repo.root)) == []

def test_check_detects_outdated(repo):
    repo.add_skill("dev", "foo"); write_generated(load_catalog(repo.root))
    (repo.root / ".claude-plugin/marketplace.json").write_text("{}\n")
    issues = check_generated(load_catalog(repo.root))
    assert any("make build" in i.message and i.path == ".claude-plugin/marketplace.json" for i in issues)

def test_check_detects_missing(repo):          # 從未 build → 每個產生檔都有 error
def test_build_removes_stale_manifests(repo):
    repo.add_skill("dev", "foo"); repo.add_skill("finance", "bar")
    write_generated(load_catalog(repo.root))
    shutil.rmtree(repo.root / "plugins/finance/skills/bar")
    changed = write_generated(load_catalog(repo.root))
    assert "plugins/finance/.claude-plugin/plugin.json" in changed
    assert not (repo.root / "plugins/finance/.claude-plugin").exists()

def test_check_reports_stale_manifests(repo):  # 同上但不重新 build → check_generated 有 error，path 為 finance 的 plugin.json
def test_build_writes_nothing_on_error(repo):  # README 沒有標記 → generated_files 丟 CatalogError，且 .claude-plugin/ 不存在
```

- [ ] **Step 2: 寫 CLI 的失敗測試**

```python
def test_cli_build_and_check(repo, capsys):
    repo.add_skill("dev", "foo")
    assert main(["--root", str(repo.root), "build"]) == 0
    assert main(["--root", str(repo.root), "check"]) == 0
    assert "0 個錯誤" in capsys.readouterr().out

def test_cli_check_fails_on_error(repo, capsys):   # frontmatter name 與資料夾不同 → 回傳 1，輸出含 "ERROR plugins/dev/skills/foo"
def test_cli_catalog_error(repo, capsys):          # 建立 plugins/ghost/ → build 回傳 1，輸出含 "ERROR"
def test_cli_warnings_do_not_fail(repo, capsys):   # description "短" → check 回傳 0，輸出含 "WARN"
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `uv run pytest scripts/tests/test_build.py scripts/tests/test_cli.py -v`
Expected: FAIL（模組不存在）

- [ ] **Step 4: 實作 `build.py` 與 `cli.py`（`build`、`check`）**

`cli.py` 開頭把自身所在目錄加入 `sys.path`，所以 `uv run python scripts/cli.py` 可以 `import skillops`。`check` = `validate_catalog` + `check_generated`，依 path 排序後輸出。

- [ ] **Step 5: 執行測試確認通過**

Run: `uv run pytest -v`
Expected: 全部通過

- [ ] **Step 6: 建立 `Makefile`、`.gitattributes`、README 骨架並在真實 repo 執行**

`Makefile`（`.PHONY` 宣告所有目標）：
```make
PY := uv run python scripts/cli.py
build: ; $(PY) build
check:
	$(PY) check
	@if command -v claude >/dev/null 2>&1 && [ -f .claude-plugin/marketplace.json ]; then claude plugin validate .; fi
test: ; uv run pytest
```
`.gitattributes`：`.claude-plugin/** linguist-generated=true`、`.agents/** linguist-generated=true`、`.cursor-plugin/** linguist-generated=true`、`plugins/*/.claude-plugin/** linguist-generated=true`、`plugins/*/.codex-plugin/** linguist-generated=true`、`plugins/*/.cursor-plugin/** linguist-generated=true`。
`README.md` 骨架：標題 `# skill-operator`、一句說明、`## Skill 目錄`，底下是 `<!-- catalog:start -->` 與 `<!-- catalog:end -->`。

Run: `make build && make check`
Expected: build 只更新 README 目錄區塊（內容為 `_目前還沒有 skill。_`），不產生任何 manifest；check 輸出 `0 個錯誤，0 個警告`，回傳碼 0。因為還沒有 `.claude-plugin/marketplace.json`，`claude plugin validate .` 會被跳過；Task 8 加入第一個 skill 後才會實際執行。

- [ ] **Step 7: Commit**

```bash
git add scripts/ Makefile .gitattributes README.md
git commit -m "feat: add build and check commands"
```

---

### Task 5: 網頁版 zip 打包與 Release 說明

**Files:**
- Create: `scripts/skillops/package.py`、`scripts/skillops/release_notes.py`
- Modify: `scripts/cli.py`（加入 `package`、`release-notes` 子命令）、`Makefile`（加入 `package`）
- Test: `scripts/tests/test_package.py`、`scripts/tests/test_release_notes.py`

**Interfaces:**
- Consumes: `Catalog`、`Skill.web`、`Skill.name`、`Catalog.repo_slug`（Task 1）
- Produces（`skillops.package`）：
  - `EXCLUDE_NAMES = frozenset({"__pycache__", ".DS_Store", ".git"})`、`EXCLUDE_SUFFIXES = (".pyc",)`
  - `package_skills(catalog: Catalog, out_dir: Path) -> list[Path]`（先刪除 `out_dir` 內既有的 `*.zip`；只打包 `web` 為 True 的 skill；依名稱排序回傳）
- Produces（`skillops.release_notes`）：
  - `git_changed_paths(root: Path, base: str | None, head: str) -> list[str] | None`（`base` 為 None、空字串、全為 `0`，或 `git diff --name-only base head` 失敗時回傳 None，代表全部視為有變動）
  - `changed_skill_names(catalog: Catalog, changed_paths: list[str]) -> list[str]`
  - `render_release_notes(catalog: Catalog, changed: list[str] | None) -> str`
- CLI：`package --out <dir>`（預設 `dist`），印出每個 zip 路徑；`release-notes --base <rev> --head <rev>`（`--base` 可省略），流程為 `git_changed_paths` → 結果為 None 時 `changed=None`，否則 `changed=changed_skill_names(...)` → `render_release_notes`，把說明印到 stdout。

- [ ] **Step 1: 寫 package 的失敗測試**

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

def test_zip_is_deterministic(repo, tmp_path):   # 打包兩次（中間 touch 檔案改 mtime）→ 兩個 zip 的 bytes 相同
def test_stale_zips_removed(repo, tmp_path):     # out_dir 先放 old.zip → 打包後不存在
```

- [ ] **Step 2: 寫 release notes 的失敗測試**

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

def test_git_changed_paths_real_diff(tmp_path):  # 兩個 commit 之間改一個檔 → 回傳 [該檔路徑]

def test_notes_lists_changed_web_skills(repo):
    repo.add_skill("dev", "foo"); repo.add_skill("dev", "baz")
    repo.add_skill("dev", "bar", frontmatter={"name": "bar", "description": "x", "metadata": {"web": "false"}})
    notes = render_release_notes(load_catalog(repo.root), ["foo", "bar"])
    assert "## 需要重新上傳" in notes
    assert "- [`foo`](https://github.com/tester/test-market/releases/download/latest/foo.zip)" in notes
    assert "`bar`" not in notes.split("## 所有網頁版 skill")[0]   # 非網頁版不列入重新上傳
    assert "## 所有網頁版 skill" in notes and "`baz`" in notes

def test_notes_all_changed_when_none(repo):      # changed=None → 所有網頁版 skill 都列在「需要重新上傳」
def test_notes_nothing_changed(repo):            # changed=[] → 「需要重新上傳」底下為 "_這次沒有網頁版 skill 變動。_"
```

說明格式：`## 需要重新上傳`（列出變動的網頁版 skill 下載連結，沒有時寫 `_這次沒有網頁版 skill 變動。_`），空一行，`## 所有網頁版 skill`（列出全部網頁版 skill 的下載連結，沒有時寫 `_目前沒有網頁版 skill。_`）。

- [ ] **Step 3: 執行測試確認失敗**

Run: `uv run pytest scripts/tests/test_package.py scripts/tests/test_release_notes.py -v`
Expected: FAIL（模組不存在）

- [ ] **Step 4: 實作 `package.py`、`release_notes.py` 與 CLI 子命令**

zip 確定性：條目依路徑排序、`ZipInfo.date_time = (1980, 1, 1, 0, 0, 0)`、`ZIP_DEFLATED`、`external_attr = (0o755 if 原檔有任何執行位元 else 0o644) << 16`。

- [ ] **Step 5: 執行測試確認通過**

Run: `uv run pytest -v`
Expected: 全部通過

- [ ] **Step 6: Makefile 加入 `package: ; $(PY) package --out dist`**

Run: `make package`
Expected: 成功結束，沒有輸出 zip（目前沒有 skill）

- [ ] **Step 7: Commit**

```bash
git add scripts/ Makefile
git commit -m "feat: package web skills and render release notes"
```

---

### Task 6: 腳手架（new / import）

**Files:**
- Create: `scripts/skillops/scaffold.py`
- Modify: `scripts/cli.py`（加入 `new`、`import`）、`Makefile`
- Test: `scripts/tests/test_scaffold.py`

**Interfaces:**
- Consumes: `load_catalog`、`NAME_RE`（Task 1）、`validate_catalog`（Task 2）、`EXCLUDE_NAMES`、`EXCLUDE_SUFFIXES`（Task 5）
- Produces:
  - `class ScaffoldError(Exception)`
  - `SKILL_TEMPLATE: str`（含 `{name}` 佔位）
  - `new_skill(root: Path, category: str, name: str) -> Path`
  - `import_skill(root: Path, src: Path, category: str) -> Path`
- CLI：`new --category <id> --name <name>`：印出建立的路徑，回傳 0；`import --src <path> --category <id>`：複製後對整個 catalog 執行 `validate_catalog`，只印出該 skill 的 issue，有 error 時回傳 1（檔案保留，讓使用者修正）。`ScaffoldError` 印出 `ERROR {訊息}` 並回傳 1。

`SKILL_TEMPLATE` 內容：

```markdown
---
name: {name}
description: TODO 描述這個 skill 做什麼，以及什麼時候該使用它（寫進使用者可能會說的關鍵字）。
---

# {name}

TODO 撰寫指令。
```

- [ ] **Step 1: 寫失敗測試**

```python
def test_new_skill_creates_template(repo):
    p = new_skill(repo.root, "dev", "my-skill")
    assert p == repo.root / "plugins/dev/skills/my-skill"
    text = (p / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: my-skill\n")
    issues = validate_catalog(load_catalog(repo.root))
    assert any("樣板" in i.message for i in issues if i.level == "error")   # TODO description 擋下 commit

@pytest.mark.parametrize("name", ["Bad", "a--b", "x" * 65])
def test_new_skill_rejects_bad_name(repo, name):   # ScaffoldError 含 "name"
def test_new_skill_unknown_category(repo):         # category "ghost" → ScaffoldError 含 "ghost"
def test_new_skill_duplicate_name(repo):           # finance/foo 已存在，new dev/foo → ScaffoldError 含 "已存在"

def test_import_copies_and_filters(repo, tmp_path):
    src = tmp_path / "ext" / "foo"
    (src / "scripts" / "__pycache__").mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: foo\ndescription: " + "說明" * 30 + "\nmetadata:\n  web: \"false\"\n---\n", encoding="utf-8")
    (src / "scripts" / "a.py").write_text("x = 1\n")
    (src / "scripts" / "__pycache__" / "a.pyc").write_text("")
    (src / ".DS_Store").write_text("")
    dest = import_skill(repo.root, src, "dev")
    assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()) == ["SKILL.md", "scripts/a.py"]

def test_import_requires_skill_md(repo, tmp_path):     # src 沒有 SKILL.md → ScaffoldError 含 "SKILL.md"
def test_import_refuses_existing(repo, tmp_path):      # 目的地已存在 → ScaffoldError 含 "已存在"
def test_cli_import_reports_issues(repo, tmp_path, capsys):  # src 內含 "/Users/alice/x" → main([... "import" ...]) 回傳 1，輸出含 "個人路徑"，且檔案已複製
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest scripts/tests/test_scaffold.py -v`
Expected: FAIL（模組不存在）

- [ ] **Step 3: 實作 `scaffold.py` 與 CLI 子命令**

名稱唯一性的判斷對象是 catalog 中所有 skill 的 `dir_name`，以及目的地資料夾是否存在。

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest -v`
Expected: 全部通過

- [ ] **Step 5: Makefile 加入 `new` 與 `import`**

```make
new: ; $(PY) new --category $(CATEGORY) --name $(NAME)
import: ; $(PY) import --src $(SRC) --category $(CATEGORY)
```

Run: `make new CATEGORY=dev NAME=tmp-check && make check; rm -rf plugins/dev/skills/tmp-check`
Expected: `make new` 印出路徑；`make check` 因為 description 是樣板而回傳非 0。

- [ ] **Step 6: Commit**

```bash
git add scripts/ Makefile
git commit -m "feat: add new and import scaffolding commands"
```

---

### Task 7: 文件、pre-commit hook 與 GitHub Actions

**Files:**
- Create: `AGENTS.md`、`CLAUDE.md`、`LICENSE`、`.githooks/pre-commit`、`.github/workflows/check.yml`、`.github/workflows/release.yml`
- Modify: `README.md`（補完）、`Makefile`（加入 `hooks`）

**Interfaces:**
- Consumes: CLI 子命令 `build`、`check`、`package`、`release-notes`（Task 4–5）；Makefile 目標（Task 4–6）

- [ ] **Step 1: 撰寫 `LICENSE`、`AGENTS.md`、`CLAUDE.md`**

`LICENSE`：MIT，年份 2026，著作權人 `Yuan`。`CLAUDE.md` 只有一行 `@AGENTS.md`。`AGENTS.md` 涵蓋 spec §11「AGENTS.md 內容要點」：只能編輯 `plugins/*/skills/**` 與 `categories.yaml`；列出不可手動編輯的產生檔；修改後執行 `make build && make check`；摘要 spec §4 的格式規則與 §12 的個人資訊規則；新增與匯入 skill 的指令。

- [ ] **Step 2: 撰寫 pre-commit hook 與 `make hooks`**

`.githooks/pre-commit`（可執行）：

```sh
#!/bin/sh
set -e
uv run python scripts/cli.py build
if ! git diff --quiet -- README.md .claude-plugin .agents .cursor-plugin 'plugins/*/.claude-plugin' 'plugins/*/.codex-plugin' 'plugins/*/.cursor-plugin'; then
  echo "產生檔已更新，請 git add 後再 commit 一次。" >&2
  exit 1
fi
uv run python scripts/cli.py check
```

Makefile：`hooks: ; git config core.hooksPath .githooks`。

Run: `make hooks && git config core.hooksPath`
Expected: `.githooks`

- [ ] **Step 3: 撰寫 `.github/workflows/check.yml`**

觸發：`push`、`pull_request`。單一 job `check`，`ubuntu-latest`，步驟依序為：`actions/checkout@v5`（`fetch-depth: 0`）、`astral-sh/setup-uv@v6`、`uv run pytest`、`uv run python scripts/cli.py check`、`gitleaks/gitleaks-action@v2`（env `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`）、`if [ -f .claude-plugin/marketplace.json ]; then npx -y @anthropic-ai/claude-code plugin validate .; fi`。

- [ ] **Step 4: 確認 `claude plugin validate` 在沒有登入時能不能執行**

Run: `env -i HOME="$(mktemp -d)" PATH="$PATH" npx -y @anthropic-ai/claude-code plugin validate .`
Expected: 以下兩種結果之一
- 有跑驗證（成功，或因目前還沒有 marketplace.json 而回報驗證錯誤）：保留 CI 的這一步。
- 要求登入或認證：從 `check.yml` 移除這一步，並在 spec §13 第 5 項註記「已套用備案」。

- [ ] **Step 5: 撰寫 `.github/workflows/release.yml`**

觸發：`push` 到 `main` 且 `paths: ['plugins/**']`，另加 `workflow_dispatch`。`permissions: contents: write`。步驟依序為：checkout（`fetch-depth: 0`）、setup-uv、`uv run python scripts/cli.py package --out dist`、`uv run python scripts/cli.py release-notes --base "${{ github.event.before }}" --head "${{ github.sha }}" > notes.md`，最後執行以下 shell（env `GH_TOKEN: ${{ github.token }}`）：

```bash
shopt -s nullglob
files=(dist/*.zip)
gh release delete latest --yes --cleanup-tag || true
gh release create latest "${files[@]}" --title "latest" --notes-file notes.md --target "${{ github.sha }}"
```

- [ ] **Step 6: 補完 `README.md`**

在 catalog 區塊之前與之後補上以下段落，內容依 spec §11、§10：
1. `## 安裝`：照 spec §11 的表格寫 Claude Code、Codex、Copilot CLI 的指令（`pasteur-yuan/skill-operator`、`<分類>@skill-operator`）；Cursor 先寫「待驗證」；一次裝多個分類的迴圈指令；Claude Code 開啟自動更新的步驟。
2. `## 網頁版（claude.ai、ChatGPT、Gemini App）`：下載網址格式、Release 說明會列出需要重新上傳的 skill；上傳步驟目前只寫 claude.ai，其他兩家寫「待驗證」，Task 9 補上。
3. `## Skill 目錄`：保留 catalog 標記。
4. `## 開發`：`make new`、`make import`、`make hooks`、`make build`、`make check`、`make package`、`make test`，以及用 `claude --plugin-dir ./plugins/<分類>` 在本機試用。

Run: `make build && make check`
Expected: `0 個錯誤`（catalog 區塊未被手寫內容破壞）

- [ ] **Step 7: Commit**

```bash
git add AGENTS.md CLAUDE.md LICENSE .githooks .github README.md Makefile
git commit -m "docs: add README, AGENTS.md, hooks and CI workflows"
```

---

### Task 8: 搬移 `tw-stock-daily-tracker` 到 `finance`

**Files:**
- Create（由 `make import` 複製）：`plugins/finance/skills/tw-stock-daily-tracker/**`
- Modify: 上述資料夾內的 `SKILL.md`、`references/workflow.md`、`references/cron_setup.md`、`scripts/build_report.py`、`scripts/install_launchd_jobs.sh`
- Generated: `finance` 的 3 份 plugin.json、3 份 marketplace.json、README 目錄

**Interfaces:**
- Consumes: `make import`、`make build`、`make check`（Task 4–6）
- 新的環境變數：`TW_STOCK_INVESTING_DIR`，指向 Obsidian vault 裡 `Investing` 資料夾的絕對路徑

- [ ] **Step 1: 匯入並確認驗證結果**

Run: `make import SRC=$HOME/.claude/skills/tw-stock-daily-tracker CATEGORY=finance`
Expected: 回傳非 0。至少要有以下錯誤：`SKILL.md` 的個人路徑（原第 52、106 行）、`scripts/build_report.py` 的個人路徑（原第 282 行）、缺少 `metadata.web`。原本的 `~/.claude/skills/tw-stock-daily-tracker` 不要動。

- [ ] **Step 2: `build_report.py` 改成從環境變數讀取路徑**

`VAULT_INVESTING = os.environ.get("TW_STOCK_INVESTING_DIR")`；`--base-dir` 與 `--config` 的預設值，在環境變數有設定時為 `{VAULT_INVESTING}/Daily` 與 `{VAULT_INVESTING}/config.json`，沒有設定時為 `None`。解析參數後，若兩者仍為 `None`，就呼叫 `parser.error("請設定環境變數 TW_STOCK_INVESTING_DIR（Obsidian vault 中 Investing 資料夾的路徑），或傳入 --base-dir 與 --config")`。必要時補 `import os`。

Run: `env -u TW_STOCK_INVESTING_DIR uv run python plugins/finance/skills/tw-stock-daily-tracker/scripts/build_report.py --input /dev/null`
Expected: 回傳碼 2，stderr 含 `TW_STOCK_INVESTING_DIR`

- [ ] **Step 3: `install_launchd_jobs.sh` 把環境變數帶進 plist**

在 `set -euo pipefail` 之後、不是 `--uninstall` 時，加上 `: "${TW_STOCK_INVESTING_DIR:?請先設定 TW_STOCK_INVESTING_DIR（Obsidian vault 中 Investing 資料夾的路徑）}"`，並在 plist 的 `<dict>` 裡加上：

```xml
    <key>EnvironmentVariables</key>
    <dict>
        <key>TW_STOCK_INVESTING_DIR</key>
        <string>${TW_STOCK_INVESTING_DIR}</string>
    </dict>
```

原因：launchd 不會讀 `~/.zshrc`，排程執行時拿不到使用者 shell 裡設定的環境變數。

Run: `bash -n plugins/finance/skills/tw-stock-daily-tracker/scripts/install_launchd_jobs.sh`
Expected: 沒有輸出，回傳碼 0

- [ ] **Step 4: 修改 SKILL.md 與 references**

- frontmatter 加上 `compatibility: 需要 Python 3、網路連線（TWSE 與新聞來源），以及環境變數 TW_STOCK_INVESTING_DIR 指向 Obsidian vault 的 Investing 資料夾；排程功能僅支援 macOS launchd。`，以及 `metadata:` / `  web: "false"`。
- 把所有 `/Users/<你>/Library/Mobile Documents/iCloud~md~obsidian/Documents/<vault 名稱>/Investing` 與 `.../<vault 名稱>/Investing` 換成 `$TW_STOCK_INVESTING_DIR`。
- 「`build_report.py` 預設 `--base-dir` 已指向上述 vault 路徑」改成「`build_report.py` 會從 `TW_STOCK_INVESTING_DIR` 推出預設路徑」。
- 在「產出位置」之前新增 `## 必要設定`：說明 `TW_STOCK_INVESTING_DIR` 的用途；若執行時沒有設定，agent 要先詢問使用者 vault 中 Investing 資料夾的路徑，並提示使用者把 `export TW_STOCK_INVESTING_DIR="…"` 加進 shell 設定檔；安裝 launchd 排程前也必須先設定。

- [ ] **Step 5: 產生與驗證**

Run: `make build && make check`
Expected: `0 個錯誤`（警告可接受）；產生 `plugins/finance/.claude-plugin/plugin.json` 等 3 份 plugin.json 與 3 份 marketplace.json；README 目錄出現「投資與財務（`finance`）」段落，`tw-stock-daily-tracker` 的網頁版欄位為 `—`。最後的 `claude plugin validate .` 要通過（`✔ Validation passed`）。

Run: `claude plugin validate ./plugins/finance`
Expected: `✔ Validation passed`

- [ ] **Step 6: Commit**

```bash
git add plugins/finance categories.yaml README.md .claude-plugin .agents .cursor-plugin
git commit -m "feat(finance): migrate tw-stock-daily-tracker with configurable vault path"
```

---

### Task 9: 發佈並驗證各平台（需要使用者確認）

**Files:**
- Modify: `README.md`（寫入驗證過的指令）、`docs/superpowers/specs/2026-10-26-skill-operator-design.md`（§13 記錄每項結果）
- 可能修改: `scripts/skillops/manifests.py` 與測試（套用 spec §13 的備案時）

- [ ] **Step 1: 取得使用者確認**

先詢問使用者：「要建立公開 repo `pasteur-yuan/skill-operator` 並 push 嗎？」得到明確同意之前，不執行下一步。

- [ ] **Step 2: 建立 repo 並 push**

Run: `gh repo create pasteur-yuan/skill-operator --public --source . --push`
接著：`gh run watch --exit-status`（依序看 check 與 release 兩個 workflow）
Expected: 兩個 workflow 都成功；`gh release view latest` 存在。目前沒有網頁版 skill，所以 Release 沒有 zip。

- [ ] **Step 3: 驗證 Claude Code（隔離設定目錄）**

```bash
export CLAUDE_CONFIG_DIR="$(mktemp -d)"
claude plugin marketplace add pasteur-yuan/skill-operator
claude plugin install finance@skill-operator
claude plugin details finance
unset CLAUDE_CONFIG_DIR
```
Expected: `Successfully added marketplace: skill-operator`、`Successfully installed plugin: finance@skill-operator`，details 的 Skills 列出 `tw-stock-daily-tracker`。

- [ ] **Step 4: 驗證 Codex 與 Copilot CLI（spec §13 第 2、3 項）**

在隔離的 home 下執行 `npx -y @openai/codex plugin marketplace add pasteur-yuan/skill-operator`（`CODEX_HOME="$(mktemp -d)"`），以及 `npx -y @github/copilot plugin marketplace add pasteur-yuan/skill-operator` 加上 `plugin install finance@skill-operator`。
Expected: 成功加入並安裝，記錄實際指令。若需要登入而無法自動驗證，把這兩項列入交給使用者手動驗證的清單，不要猜測結果。若發現必須有 `version` 才能更新，依 spec §9 備案修改 `manifests.py`：以分類 `skills/` 內容的 SHA-256 前 12 碼產生 `version`（格式 `0.0.0-<hash>`），補上對應測試後重新 build。

- [ ] **Step 5: 更新文件並 commit**

把驗證過的指令寫進 README 的安裝段落；在 spec §13 每一項後面註記「已驗證」「已套用備案」或「待使用者手動驗證」。

Run: `make build && make check`
Expected: `0 個錯誤`

```bash
git add README.md docs/ scripts/ .claude-plugin .agents .cursor-plugin plugins
git commit -m "docs: record platform verification results"
git push
```

- [ ] **Step 6: 回報使用者**

列出：各平台驗證結果；需要使用者手動驗證的項目（Cursor、網頁版上傳；有網頁版 skill 之後的 zip 上傳）；提醒在 `~/.zshrc` 設定 `TW_STOCK_INVESTING_DIR`；確認 plugin 版可用後，再由使用者決定是否刪除 `~/.claude/skills/tw-stock-daily-tracker`，避免重複觸發。
