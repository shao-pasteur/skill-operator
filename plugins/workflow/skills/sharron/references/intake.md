# Intake

Step 1 of the main flow. sharron fills in what it can and asks only what would change the plan. Questions are asked in Traditional Chinese.

Contents:

- [The six dimensions](#the-six-dimensions)
- [Playbook add-ons](#playbook-add-ons)
- [Rules](#rules)
- [Task card](#task-card)

## The six dimensions

| # | Dimension | Question (ask in Traditional Chinese) | Example options | Decides |
|---|---|---|---|---|
| 1 | Outcome | 做完之後你希望拿到什麼？怎樣算完成？ | 一個結論／一張比較表／完整報告／完成一個動作 | Goal, done-when, output format |
| 2 | Purpose | 這是為了什麼決定或問題？誰會用到？ | 我自己決定／給別人看／留作紀錄 | Challenging the premise (often reveals a simpler way); the audience |
| 3 | Authority | 你希望 sharron 代你做到哪裡？ | 只查資料並建議／做草稿給你確認／可逆的部分直接執行 | Pre-approves L2–L3 work within that scope; never overrides L4 |
| 4 | Constraints | 有期限、預算或不能碰的範圍嗎？ | 今天／這週／不急；帳本建議的預算／上限 X | Constraints and budget |
| 5 | Depth | 要快速版還是完整版？ | 快速（少數來源、幾分鐘）／完整（多方交叉查證） | Difficulty, number of subagents, tiers |
| 6 | Knowns and preferences | 你已經知道什麼？有要用或要避開的來源、方法嗎？ | 自由填寫，或「沒有」 | Context and preferences given to subagents |

## Playbook add-ons

Asked only when relevant and unknown.

| Playbook | Add-on questions (ask in Traditional Chinese) |
|---|---|
| Research | 這個結果會用來做什麼決定？資料可以多舊？ |
| Planning | 哪些條件是固定的（日期、人、地點）？成本、時間、體驗哪個優先？ |
| Action | 對象是誰？有沒有不可逆的部分？要先看草稿嗎？ |
| Decision support | 你最在意的 2–3 個標準和權重？有已經排除的選項嗎？ |
| Learning | 你現在的程度？想到什麼程度、什麼時候前？ |
| Coding | 哪個 repo 和檔案？怎麼驗證有效（例如測試指令）？ |

## Rules

1. **Fill in first.** Draft all six from the request, `MEMORY.md` (preferences and past tasks), files in the workspace and the config defaults. Mark each as known, assumed or unknown.
2. **Ask only what changes the plan.** Rank the unknowns by impact: would a wrong guess change the deliverable, the cost or the risk level? Ask at most 3 questions, normally in one round, each with 2–4 options and a recommended default. "Use the defaults" (「照預設」) is a valid answer.
3. **Authority is always asked for actions,** unless the request already states it.
4. **Difficulty 1–2: no questions.** The reply states the assumptions made.
5. **Background or scheduled runs: no questions.** Use the defaults and write the assumptions to `MEMORY.md`.
6. **Lasting answers are remembered** as preferences marked 〔你說的〕, so they are not asked again.

## Task card

After the answers, show a task card. For difficulty 4–5 the card also serves as the plan confirmation in step 5 of the main flow (L3). The budget comes from `sh <skill>/scripts/run.sh finance.py suggest --playbook <id> --difficulty <1-5>`.

```
任務卡
- 目標：…
- 完成條件：…
- 用途：…
- 限制：期限 …／預算約 US$…（帳本建議）／不碰 …
- 授權：只查資料／草稿／可逆的部分直接執行
- 深度：完整版（難度 3，預計派 2 個 subagent）
- 假設：…（沒問你、先這樣假設的部分）
```
