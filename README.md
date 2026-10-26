# skill-operator

自己開發的 AI agent skill，依用途分類，透過 marketplace plugin 安裝到 Claude Code、Codex、Copilot CLI、Cursor，也提供網頁版 App 可上傳的 zip。

每個分類是一個 plugin，可以只裝需要的分類。所有 skill 都遵循 [Agent Skills 開放標準](https://agentskills.io/specification)（`SKILL.md`）。

## 安裝

repo 是公開的，不需要任何 git 認證。下方的 `<分類>` 換成「Skill 目錄」裡的分類 id，例如 `finance`。

| 平台 | 加入 marketplace | 安裝分類 |
|---|---|---|
| Claude Code | `claude plugin marketplace add pasteur-yuan/skill-operator` | `claude plugin install <分類>@skill-operator` |
| Codex | `codex plugin marketplace add pasteur-yuan/skill-operator` | 在 Codex 中執行 `/plugins` 選擇安裝 |
| Copilot CLI | `copilot plugin marketplace add pasteur-yuan/skill-operator` | `copilot plugin install <分類>@skill-operator` |
| Cursor | 待驗證 | 待驗證 |

一次安裝多個分類：

```bash
for c in dev writing finance; do claude plugin install "$c@skill-operator"; done
```

**Claude Code 自動更新**：預設是關閉的。安裝後在 Claude Code 中執行 `/plugin`，到 Marketplaces 選擇 `skill-operator`，再選 **Enable auto-update**。沒有開啟的話，可以手動執行 `claude plugin marketplace update skill-operator` 取得更新。

## 網頁版（claude.ai、ChatGPT、Gemini App）

網頁版可用的 skill 會自動打包成 zip，放在 [`latest` Release](https://github.com/pasteur-yuan/skill-operator/releases/tag/latest)：

```
https://github.com/pasteur-yuan/skill-operator/releases/download/latest/<skill 名稱>.zip
```

每次更新後，Release 說明的「需要重新上傳」會列出有變動的 skill。網頁版不會自動更新，要手動重新上傳。

| 平台 | 上傳方式 |
|---|---|
| claude.ai | 設定 → Skills → 上傳 zip |
| ChatGPT | 待驗證 |
| Gemini App | 待驗證 |

## Skill 目錄

<!-- catalog:start -->
_目前還沒有 skill。_
<!-- catalog:end -->

## 開發

需要 [uv](https://docs.astral.sh/uv/) 與 GNU Make。規則與限制寫在 [AGENTS.md](AGENTS.md)。

```bash
make hooks                                   # 安裝 pre-commit hook（第一次 clone 後執行）
make new CATEGORY=dev NAME=my-skill          # 從樣板建立新 skill
make import SRC=~/.claude/skills/foo CATEGORY=dev  # 匯入既有 skill
make build                                   # 產生 manifest 與 README 目錄
make check                                   # 驗證 skill 與產生檔
make package                                 # 打包網頁版 zip 到 dist/
make test                                    # 執行 scripts/ 的測試
```

在本機試用某個分類，不用 push：

```bash
claude --plugin-dir ./plugins/<分類>
```

新增分類：編輯 `categories.yaml`，再執行 `make build`。沒有任何 skill 的分類不會出現在 marketplace。
