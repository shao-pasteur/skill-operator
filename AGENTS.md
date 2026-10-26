# AGENTS.md

這個 repo 用來管理 AI agent skill。skill 依用途分類，每個分類是一個 plugin，透過 marketplace 安裝到 Claude Code、Codex、Copilot CLI、Cursor；網頁版 App 則使用 CI 打包的 zip。

## 可以編輯的地方

- `plugins/<分類>/skills/<skill>/` 底下的所有檔案：`SKILL.md`，以及選用的 `scripts/`、`references/`、`assets/`
- `categories.yaml`：分類清單

## 不要手動編輯的檔案

以下檔案由 `make build` 產生，手動修改會在下次 build 時被覆蓋，`make check` 也會報錯：

- `.claude-plugin/marketplace.json`、`.agents/plugins/marketplace.json`、`.cursor-plugin/marketplace.json`
- `plugins/*/.claude-plugin/plugin.json`、`plugins/*/.codex-plugin/plugin.json`、`plugins/*/.cursor-plugin/plugin.json`
- `README.md` 中 `<!-- catalog:start -->` 與 `<!-- catalog:end -->` 之間的內容

## 修改之後

```bash
make build && make check
```

`make check` 有錯誤時必須修正；警告可以視情況保留。

## Skill 格式規則

- frontmatter 只用 Agent Skills 標準欄位：`name`、`description`、`license`、`compatibility`、`metadata`
- `name`：小寫英數字加單一連字號，最多 64 字元，必須與資料夾同名，全 repo 唯一
- `description`：1–1024 字元，寫清楚「做什麼」和「什麼時候用」，不能留下 `TODO`
- `compatibility`：只有附腳本或有環境需求時才寫，最多 500 字元
- `metadata.web`：字串 `"true"` 或 `"false"`，代表網頁版 App 能不能用。有 `scripts/` 的 skill 必須填寫
- 分類由資料夾決定，frontmatter 不寫分類
- SKILL.md 建議少於 500 行，細節放到 `references/`

## 個人資訊規則（這是公開 repo）

- 不得寫入家目錄的絕對路徑（`/Users/<名稱>/`、`/home/<名稱>/`、`C:\Users\<名稱>\`）、帳號、email、API key
- 需要個人化的值，一律從環境變數或 `~/.config/<skill 名稱>/` 讀取，並在 SKILL.md 寫明需要哪些設定、缺少時如何提示使用者
- 舉例時使用佔位符，例如 `/Users/<你>/...`

## 常用指令

| 指令 | 作用 |
|---|---|
| `make new CATEGORY=<分類> NAME=<名稱>` | 從樣板建立新 skill |
| `make import SRC=<路徑> CATEGORY=<分類>` | 把既有 skill 複製進來並驗證 |
| `make build` | 產生 manifest 與 README 目錄 |
| `make check` | 驗證所有 skill 與產生檔 |
| `make package` | 打包網頁版 zip 到 `dist/` |
| `make test` | 執行 `scripts/` 的測試 |
| `make hooks` | 安裝 pre-commit hook |
