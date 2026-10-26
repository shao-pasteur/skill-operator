# skill-operator 設計規格

- 日期：2026-10-26
- 狀態：待審閱
- Repo：`pasteur-yuan/skill-operator`（GitHub，公開）

## 1. 目標

用一個公開的 GitHub repo 管理自己開發的 AI agent skill，做到：

1. **一份內容，多家 AI 使用**：skill 以 [Agent Skills 開放標準](https://agentskills.io/specification)（`SKILL.md`）撰寫一次。
2. **CLI / IDE agent 透過 marketplace plugin 安裝**：Claude Code、Codex、Copilot CLI、Cursor。
3. **網頁版聊天 App 透過 zip 上傳**：claude.ai、ChatGPT、Gemini App。
4. **依用途分類，分類即安裝單位**：每個分類是一個 plugin，可以只裝需要的分類。

### 成功標準

- 在一台乾淨的機器上，Claude Code、Codex、Copilot CLI 都能加入 marketplace 並**只安裝單一分類**，安裝後 skill 可被觸發。
- 新增一個 skill 只需要「`make new` → 撰寫 → commit → push」，全程不手動編輯任何 JSON。
- push 後，其他機器的 CLI 能取得更新；網頁版相容的 skill 會自動出現在 `latest` Release 的 zip 中。
- `make check` 與 CI 全綠。

## 2. 範圍

### 範圍內

- Skill 格式規範與驗證
- 分類設定檔與各平台 manifest 的自動產生
- 本機與 CI 的驗證
- 網頁版 zip 打包與 Release 發佈
- 各平台安裝說明（README）
- 新增、搬移 skill 的工具（`make new`、`make import`）

### 範圍外（初版不做）

| 項目 | 原因 / 日後怎麼加 |
|---|---|
| Gemini CLI | 只讀 repo 根目錄的 `gemini-extension.json` 與 `skills/`，與「一分類一資料夾」衝突。日後要加：產生腳本多產出根目錄的平面鏡像 + `gemini-extension.json`，不需重構 |
| Grok | 沒有官方 skill 機制 |
| `all` plugin | 沒有平面鏡像時 Codex、Cursor 做不出來。改以 README 的迴圈指令一次裝多個分類 |
| Skill 效果評測（eval） | 需要 API key 與成本，等 skill 數量多了再接 `skill-creator` 的 eval 流程 |
| `meta` 分類底下的 skill | `AGENTS.md` + `make new` 已涵蓋需求；分類保留但為空 |
| 上架官方目錄（Cursor marketplace、OpenAI plugin directory 等） | repo 公開後可以做，但不在初版 |

## 3. 平台支援矩陣

| 平台 | 安裝方式 | 讀取的 manifest | 分類安裝 |
|---|---|---|---|
| Claude Code | marketplace | `.claude-plugin/marketplace.json`、`plugins/<id>/.claude-plugin/plugin.json` | ✅ |
| Codex | marketplace | `.agents/plugins/marketplace.json`、`plugins/<id>/.codex-plugin/plugin.json` | ✅ |
| Copilot CLI | marketplace | `.claude-plugin/marketplace.json`（Copilot 會讀此路徑）、plugin 資料夾內的 plugin.json | ✅ |
| Cursor | marketplace | `.cursor-plugin/marketplace.json`、`plugins/<id>/.cursor-plugin/plugin.json` | ✅ |
| claude.ai | 手動上傳 zip | — | 以 skill 為單位 |
| ChatGPT | 手動上傳 zip | — | 以 skill 為單位 |
| Gemini App | 手動上傳 zip 或 `SKILL.md` | — | 以 skill 為單位 |

## 4. Skill 格式

完全遵循 Agent Skills 開放標準，另外只使用 `metadata` 底下的一個自訂鍵。

```markdown
---
name: tw-stock-tracker
description: 在台股交易日…當使用者要求…時使用。
compatibility: 需要 Python 3.11+ 與網路連線
metadata:
  web: "false"
---
（指令內容）
```

| 欄位 | 必填 | 規則 |
|---|---|---|
| `name` | 是 | 1–64 字元；只能用 `a-z`、`0-9`、`-`；不能以 `-` 開頭或結尾；不能有 `--`；**必須與資料夾同名**；**全 repo 唯一** |
| `description` | 是 | 1–1024 字元；寫「做什麼」與「什麼時候用」 |
| `compatibility` | 否 | 1–500 字元；只有附腳本或有環境需求的 skill 才寫 |
| `license` | 否 | 不寫時沿用 repo 根目錄的 `LICENSE` |
| `metadata.web` | 視情況 | `"true"` 或 `"false"`（字串）。沒有 `scripts/` 的 skill 預設為 `"true"`；**有 `scripts/` 的 skill 必須明確填寫** |
| 平台專屬欄位（如 `allowed-tools`） | 否 | 允許；驗證時只發警告 |

其他規則：

- **分類由資料夾決定**，frontmatter 不寫分類。
- **skill 不帶版本號**（見第 9 節）。
- SKILL.md 建議少於 500 行；詳細資料放 `references/`，可執行檔放 `scripts/`，樣板與資料放 `assets/`。
- **不得包含個人資訊**（見第 12 節）。需要個人設定（例如 Obsidian vault 路徑）時，從環境變數或 repo 以外的設定檔讀取，並在 SKILL.md 中說明。

## 5. 分類

分類定義在 `categories.yaml`，是唯一需要手動維護的設定檔。分類 `id` 同時是 plugin 名稱與 Claude 中的 skill 前綴（如 `/dev:code-review`），所以要短。分類數量建議 5–8 個。

```yaml
marketplace: skill-operator
owner:
  name: Yuan
  github: pasteur-yuan
categories:
  - id: dev
    title: 軟體開發
    description: 程式碼審查、除錯、git、測試、架構設計
  - id: writing
    title: 寫作與文件
    description: 文章、翻譯、簡報、文件格式轉換
  - id: research
    title: 研究與知識管理
    description: 查資料、摘要、Obsidian 筆記整理
  - id: finance
    title: 投資與財務
    description: 台股追蹤、技術分析、財報整理
  - id: productivity
    title: 個人效率
    description: 排程、日常流程自動化
  - id: meta
    title: Skill 管理
    description: 在這個 repo 裡建立、檢查新 skill 的工具
```

一個 skill 只屬於一個分類；用途重疊時以主要用途為準。

## 6. Repo 結構

```
skill-operator/
├── categories.yaml                     # 手動維護
├── plugins/
│   └── <分類 id>/
│       ├── skills/<skill>/SKILL.md     # 手動維護（可附 scripts/、references/、assets/）
│       ├── .claude-plugin/plugin.json  # 產生
│       ├── .codex-plugin/plugin.json   # 產生
│       └── .cursor-plugin/plugin.json  # 產生
├── .claude-plugin/marketplace.json     # 產生
├── .agents/plugins/marketplace.json    # 產生
├── .cursor-plugin/marketplace.json     # 產生
├── scripts/                            # 產生、驗證、打包、腳手架的 Python CLI 與測試
├── .github/workflows/                  # CI 與 Release
├── Makefile
├── README.md                           # 安裝說明 + 產生的「Skill 目錄」區塊
├── AGENTS.md                           # 給 AI agent 的 repo 規則
├── CLAUDE.md                           # 內容只有一行：指向 AGENTS.md
├── LICENSE                             # MIT
├── .gitattributes                      # 將產生檔標為 linguist-generated
└── .gitignore                          # dist/ 等
```

### Makefile 目標

| 指令 | 作用 |
|---|---|
| `make build` | 從 `categories.yaml` 與 SKILL.md 產生所有 manifest 與 README 目錄區塊 |
| `make check` | 執行第 8 節的全部驗證 |
| `make package` | 打包網頁版 zip 到 `dist/` |
| `make new CATEGORY=<id> NAME=<name>` | 建立新 skill 的樣板 |
| `make import SRC=<path> CATEGORY=<id>` | 把既有 skill 資料夾複製進 repo 並驗證 |
| `make hooks` | 安裝 git pre-commit hook（執行 `make build && make check`） |
| `make test` | 執行 `scripts/` 的 pytest |

## 7. 產生腳本（`make build`）

- **技術**：Python 3.11+，透過 `uv run` 執行；依賴宣告在根目錄 `pyproject.toml`（uv 自動管理環境，不需手動建 venv），唯一執行期依賴為 PyYAML（測試另需 pytest）。GitHub repo 路徑由 `categories.yaml` 的 `owner.github` 與 `marketplace` 組成（`<owner.github>/<marketplace>`）。
- **輸入**：`categories.yaml`，加上掃描 `plugins/*/skills/*/SKILL.md` 的 frontmatter。
- **輸出**：
  - 每個分類 3 份 plugin.json（Claude、Codex、Cursor），`name` 與 `description` 取自 `categories.yaml`。
  - 根目錄 3 份 marketplace.json，各依該平台格式，例如：

    Claude（`.claude-plugin/marketplace.json`）：
    ```json
    {
      "name": "skill-operator",
      "owner": { "name": "Yuan", "url": "https://github.com/pasteur-yuan" },
      "plugins": [
        { "name": "dev", "source": "./plugins/dev", "description": "程式碼審查、除錯、git、測試、架構設計" }
      ]
    }
    ```

    Codex（`.agents/plugins/marketplace.json`）：
    ```json
    {
      "name": "skill-operator",
      "interface": { "displayName": "Skill Operator" },
      "plugins": [
        {
          "name": "dev",
          "source": { "source": "local", "path": "./plugins/dev" },
          "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
          "category": "軟體開發"
        }
      ]
    }
    ```
  - README 中 `<!-- catalog:start -->` 與 `<!-- catalog:end -->` 之間的「Skill 目錄」表格：分類 → skill → 一行說明 → 網頁版是否可用。
- **規則**：
  - 產生的檔案 commit 進 git（各家 marketplace 直接從 git 讀取）。
  - 輸出是確定性的（相同輸入產生逐位元組相同的輸出），以便 CI 比對。
  - 沒有任何 skill 的分類不出現在 marketplace 中，也不產生 plugin.json。
  - 任何錯誤（yaml 格式錯、`plugins/` 下有不在 `categories.yaml` 的資料夾、frontmatter 無法解析）都直接失敗，**不寫入任何檔案**。
  - 所有 manifest **不寫 `version`**（見第 9 節）。

## 8. 驗證與 CI

### `make check`

**錯誤（阻擋 commit 與 CI）：**

| 檢查 | 內容 |
|---|---|
| 標準格式 | 第 4 節的所有欄位規則 |
| repo 規則 | `name` 全 repo 唯一；分類資料夾必須在 `categories.yaml` 中；有 `scripts/` 的 skill 必須填 `metadata.web` |
| 檔案引用 | SKILL.md 中引用的相對路徑（`references/…`、`scripts/…`、`assets/…`）必須存在 |
| 產生檔同步 | 在暫存目錄重新 build，與 commit 的內容比對；不一致時提示執行 `make build` |
| 腳本語法 | `.py` 執行 `py_compile`，`.sh` 執行 `bash -n`（不執行腳本） |
| 個人資訊 | `plugins/**` 中出現使用者家目錄的絕對路徑（`/Users/<名稱>/`、`/home/<名稱>/`、`C:\Users\<名稱>\`）。`<…>` 形式的佔位符不算 |

**警告（不阻擋）：** SKILL.md 超過 500 行；frontmatter 含平台專屬欄位；`description` 少於 50 字元；`plugins/**` 中出現 email 地址。

### GitHub Actions

| Workflow | 觸發 | 內容 |
|---|---|---|
| `check.yml` | push、pull request | `make test`、`make check`、gitleaks 掃描 secret；額外執行 `claude plugin validate .`（若在 CI 中需要登入則移除此步） |
| `release.yml` | push 到 `main` 且有改到 `plugins/**` | 見第 10 節 |

## 9. 版本與更新（CLI 平台）

- 所有 plugin.json 與 marketplace.json **都不寫 `version`**。依 Claude Code 官方行為，此時以 git commit 判斷版本：**push 到 `main` 即發佈**，不需 bump 版本或打 tag。
- 代價：任何 commit 都會讓所有分類被視為有更新而重新複製；skill 都是小檔案，可忽略。
- Claude Code 的背景自動更新預設關閉，每台機器首次安裝後需在 `/plugin` → Marketplaces 開啟一次。
- **備案**：若 Codex、Cursor 或 Copilot 實測發現必須有 `version` 才能偵測更新，則由產生腳本自動將「該分類 `skills/` 內容的雜湊值」寫成版本號。內容不變則版本不變，只有改到的分類會更新，仍不需手動管理。

## 10. 網頁版 zip 發佈

- `make package`：將每個 `metadata.web` 為 `"true"`（或無 `scripts/` 而預設為 true）的 skill 打包成 `dist/<name>.zip`，zip 內為單一最上層資料夾 `<name>/`。`dist/` 不進 git。
- `release.yml`：重新打包所有 zip，覆蓋到固定 tag 的 **`latest` Release**。下載網址固定為 `https://github.com/pasteur-yuan/skill-operator/releases/download/latest/<name>.zip`。
- Release 說明自動列出本次 push 中有變動的 skill，提示哪些需要重新上傳（網頁版沒有自動更新）。
- 各平台上傳位置：claude.ai 為「設定 → Skills → 上傳 zip」；ChatGPT 與 Gemini App 實作時實測後寫入 README（見第 13 節）。
- 若某平台要求不同的 zip 格式（例如 `SKILL.md` 直接位於 zip 根目錄），打包腳本為該平台多產生一種格式，檔名加上平台後綴。

## 11. 安裝與工作流

### 安裝（README）

repo 公開，不需要任何 git 認證。

| 平台 | 加入 marketplace | 安裝分類 |
|---|---|---|
| Claude Code | `claude plugin marketplace add pasteur-yuan/skill-operator` | `claude plugin install dev@skill-operator`；之後到 `/plugin` → Marketplaces 開啟自動更新 |
| Codex | `codex plugin marketplace add pasteur-yuan/skill-operator` | 在 `/plugins` 中安裝 |
| Copilot CLI | `copilot plugin marketplace add pasteur-yuan/skill-operator` | `copilot plugin install dev@skill-operator` |
| Cursor | 依實測結果撰寫（見第 13 節） | — |

一次安裝多個分類：

```bash
for c in dev writing finance; do claude plugin install "$c@skill-operator"; done
```

### 新增 skill

1. `make new CATEGORY=dev NAME=foo`：建立 `plugins/dev/skills/foo/SKILL.md` 樣板。
2. 撰寫內容（自己寫或請 agent 寫；agent 依 `AGENTS.md` 的規則操作）。
3. 本機試用：`claude --plugin-dir ./plugins/dev`。
4. `git commit`：pre-commit hook 執行 `make build && make check`。
5. `git push`：CLI 透過更新取得；網頁版 zip 自動重建。

### 搬移既有 skill

1. `make import SRC=~/.claude/skills/<name> CATEGORY=<id>`：複製並驗證。
2. 修正驗證錯誤。最常見的是個人路徑，例如 `tw-stock-daily-tracker` 目前在 `SKILL.md` 與 `scripts/build_report.py` 中寫死了 Obsidian vault 路徑，需改為從環境變數讀取。
3. 確認安裝 plugin 版本後可用，再**刪除本機原本那份**，避免同一 skill 出現兩份造成誤觸發。

### `AGENTS.md` 內容要點

- 只編輯 `plugins/*/skills/**` 與 `categories.yaml`；不手動編輯任何產生的 JSON 或 README 目錄區塊。
- 修改後執行 `make build && make check`。
- 第 4 節的 skill 格式規則與第 12 節的個人資訊規則。

## 12. 公開 repo 注意事項

- **授權**：MIT，放在根目錄 `LICENSE`。
- **個人資訊**：skill 內容與腳本不得包含家目錄絕對路徑、帳號、email、API key。由 `make check` 的個人資訊檢查與 CI 的 gitleaks 把關。
- **個人設定**：需要個人化的值（路徑、帳號名稱）一律從環境變數或 `~/.config/<skill-name>/` 讀取，並在 SKILL.md 中寫明需要哪些設定、缺少時如何提示使用者。
- **git 歷史**：公開前確認歷史中沒有個人資訊；gitleaks 會掃描完整歷史。

## 13. 實作時需驗證的項目

每一項都已有決定好的備案，驗證結果只影響產生腳本或 README 的細節，不影響整體結構。

| # | 項目 | 備案 |
|---|---|---|
| 1 | Cursor marketplace.json 與 plugin.json 的確切格式；個人帳號如何加入 git marketplace | 依官方文件產生；若個人帳號無法使用 marketplace，README 改寫為手動複製 skill 資料夾的方式 |
| 2 | Copilot CLI 在 plugin 資料夾內讀取 plugin.json 的路徑 | 產生腳本多寫一份到 Copilot 要求的路徑 |
| 3 | Codex 的 CLI 安裝指令；未寫 `version` 時的更新行為 | 指令依實測寫入 README；更新行為依第 9 節備案 |
| 4 | ChatGPT 消費版的 skill 上傳入口；Gemini App 是否接受 zip 與其格式 | 依第 10 節多產生一種 zip 格式；Gemini App 不接受 zip 時，README 說明直接上傳 `SKILL.md`（僅適用無附檔的 skill） |
| 5 | `claude plugin validate` 在 CI 中是否需要登入 | 需要則從 CI 移除，保留在本機 `make check` 中選擇性執行 |
