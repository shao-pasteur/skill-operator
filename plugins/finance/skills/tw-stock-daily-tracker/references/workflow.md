# 詳細執行流程

執行任何階段之前，先確認：
1. 今天日期、現在時間（台灣時區 Asia/Taipei）
2. Obsidian vault 內的 `$TW_STOCK_INVESTING_DIR/Daily/{今天日期}/` 資料夾是否存在，不存在就建立好完整子資料夾結構（`build_report.py` 會自動建立；報告直接以 Obsidian 格式寫進 vault）
3. 今天是不是台股交易日（週一~五、非國定假日）。可以用網頁搜尋「台股 今天 {日期} 開盤」或查台灣證交所公告確認，非交易日就寫一行 log 到 `logs/run_{HHMM}.log` 然後直接結束，不用往下做。

---

## 階段 1：開盤前簡報

### Step 1.1 — 收集美股與國際新聞重點
用網頁搜尋工具查詢類似：
- 「美股 收盤 {昨天日期}」「S&P500 那斯達克 道瓊 費城半導體 收盤」
- 「Fed 利率 最新」「地緣政治 供應鏈 台股 影響」
只需要抓重點（漲跌幅、主要驅動因素、對台股權值股/半導體供應鏈的潛在影響），整理成 3~6 條重點摘要，不用整篇翻譯。

### Step 1.2 — 判斷 3 個熱門產業
用網頁搜尋查詢類似「台股 今日 熱門族群」「台股 早盤 焦點股」「台股 概念股 今日」，讀 2~3 篇財經新聞（MoneyDJ、鉅亨網、經濟日報、工商時報等常見來源皆可），依報導熱度/篇幅自行判斷當天最受關注的 3 個產業（例如：AI 伺服器、半導體設備、航運、金融、生技等），並簡短寫下判斷依據。

### Step 1.3 — 動態 9 檔 + 固定 9 檔，去重後寫入狀態檔

**先讀設定檔**：`$TW_STOCK_INVESTING_DIR/config.json`（在 vault 內；格式見 SKILL.md「設定檔 config.json」）。不存在就用預設值建立並寫回。拿到 `capital_twd`（本金，預設 500000）與 `fixed_industries`（固定三產業各三檔）。

**動態 9 檔**：針對 Step 1.2 選定的 3 個熱門產業，用網頁搜尋（例如「Yahoo奇摩股市 {產業名} 類股」「{產業名} 概念股 成交值排行」）找出當天成交值或市值排名前 3 大的個股，記下代號與名稱，標記 `source: dynamic`。

**固定 9 檔**：直接取 `config.json` 的 `fixed_industries`（記憶體/電子元件/航海各三檔），標記 `source: fixed`。

**去重**：動態與固定合併，同一 `symbol` 只保留一筆（若重複，保留 `dynamic` 並在 `also_fixed: true` 註記），最多 18 檔。寫入：

```
state/selected_stocks.json
```

格式：
```json
{
  "date": "2026-07-13",
  "capital_twd": 500000,
  "dynamic_industries": [
    {"name": "半導體", "reason": "簡短判斷依據"},
    {"name": "AI伺服器", "reason": "..."},
    {"name": "航運", "reason": "..."}
  ],
  "fixed_industries": ["記憶體", "電子元件", "航海"],
  "stocks": [
    {"symbol": "2330", "name": "台積電", "industry": "半導體", "source": "dynamic"},
    {"symbol": "2408", "name": "南亞科", "industry": "記憶體", "source": "fixed"},
    ...去重後最多 18 檔
  ]
}
```

**之後階段 2、3 每次執行都先讀這個檔案，不要重新選股。**

### Step 1.4 — 抓歷史收盤價，算布林通道基準
對這 9 檔，用 `references/data_sources.md` 裡的 TWSE STOCK_DAY 端點抓最近至少 20 個交易日的收盤價。如果環境裡有 `data-context-extractor`、`explore-data`、`validate-data` 這幾個 skill，抓到資料後先用它們理解欄位、探索資料、檢查有沒有缺值或異常，確認資料乾淨了再餵給 `scripts/bollinger.py` 算出目前的布林通道（20 日均線 ± 2 倍標準差）與目前價格相對位置（詳見 SKILL.md「搭配其他 data-analysis 相關 skills」段落）。

### Step 1.5 — 產出開盤前報告
呼叫 `scripts/build_report.py`（用法見腳本內 docstring），帶入：9 檔股票資料、布林通道計算結果、美股/新聞摘要、產業判斷理由。如果環境裡有 `create-viz` skill，可以用它產生比內建 matplotlib 更好的圖表再嵌入報告；沒有的話用內建的就好。腳本會：
- 產生 `reports/0850_premarket.md`
- 每檔股票畫一張價格＋布林通道圖存到 `charts/`
- 把這次的訊號狀態寫入 `state/signals_state.json`（第一次沒有比較對象，不用觸發通知）

---

## 階段 2：盤中動態更新（09:00~12:00，每 30 分鐘）

### Step 2.1 — 讀取已選股票
直接讀 `state/selected_stocks.json`，拿到 9 檔股票清單。**不要重新判斷熱門產業或重新選股。**

### Step 2.2 — 抓即時價格
用 `references/data_sources.md` 裡的 TWSE 即時報價端點（`mis.twse.com.tw`），對 9 檔股票各抓一次目前成交價、開盤價、最高最低價。

### Step 2.3 — 重新計算布林通道位置
把最新價格丟給 `scripts/bollinger.py`，拿到每檔目前的通道位置狀態（例如 `below_lower` / `near_lower` / `within` / `near_upper` / `above_upper`）。

### Step 2.4 — 比對訊號變化並觸發通知
`scripts/build_report.py` 會自動讀取 `state/signals_state.json` 裡上一次的狀態，跟這次比對：
- 有股票狀態改變（尤其是變成 `below_lower` 或 `near_lower`，過去技術分析上常視為潛在支撐/進場區）→ 在報告裡特別標示「⚠️ 訊號變化」，並觸發 macOS 系統通知
- 沒有變化 → 正常更新報告，不特別提醒

### Step 2.5 — 更新報告
產出 `reports/{HHMM}_update.md`，更新對應的圖表，更新 `signals_state.json`。

---

## 階段 3：收盤前賣點追蹤（`phase: close_watch`，12:30~13:25，每 30 分鐘；13:30 後做總結 `phase: close_summary`）

流程跟階段 2 幾乎一樣（讀已選股票 → 抓最新價 → 算布林通道 → 比對訊號 → 更新報告），差別在於報告的敘述重點改成「技術面上偏向什麼區間、過去類似位置在技術分析上通常怎麼被解讀」，用來輔助使用者自行判斷是否要在收盤前調整部位，**不要給精確的「幾點該賣」預測**，也不要用肯定語氣。

13:30 台股收盤後的第一次執行，額外產出 `reports/summary_close.md`，總結當天所有股票從開盤到收盤的價格變化、布林通道訊號變化次數與時間點、以及全天的新聞/產業重點回顧。

**這份收盤總結要用「股市新手向」呈現**（詳見 SKILL.md「收盤總結：新手向呈現」），包含：白話「今天發生什麼事」、名詞小教室（布林通道/上中下軌/%B/位置代表什麼，只解釋不下買賣結論）、每檔白話技術面說明、以 `capital_twd`（本金，預設 50 萬）計算的**中性資金試算**表（一張所需金額、本金約可買幾張、佔本金 %，標明「非建議買進」）、以及給新手的一般性風險提醒。

⚠️ **絕對不要**在總結寫「哪幾檔適合買/賣」或「50 萬建議怎麼配置買進」——那是個人化投資建議，本 skill 不做。資金試算只是「以這個本金，這些股票各自一張大概多少錢、買得起幾張」的算術，不含推薦。可用 `python3 scripts/build_report.py --input payload.json --capital 500000` 讓腳本自動附上中性的資金試算表格。

如果環境裡有 `build-dashboard` skill，這一步很適合用它把當天多次快照整合成一個儀表板畫面，而不只是純文字的 Markdown 總結；`analyze` skill 也適合在這裡用來補充布林通道以外的技術面分析。

### Step 3.x — 收盤後寫 Obsidian 索引（收盤總結後必做）
報告寫進 vault 後，補上 Obsidian 導覽用的兩個檔（見 SKILL.md「Obsidian 格式要求」）：
1. **當日總覽 `Investing/Daily/{date}/台股日報 {date}.md`**（檔名帶日期，別用 README）：含 frontmatter（`tags: [investing, daily-stock]`、`date`），內容 = 一句話總結、15 檔漲跌與收盤通道位置表、全日訊號軌跡（premarket→update→收盤），並用 `[[0850_premarket]]`、`[[summary_close]]` 等 wikilink 串接各報告，結尾附免責。
2. **更新 `Investing/watchlist.md` 的「每日資料索引」**：加一行 `- [[台股日報 {date}|{date}]] — 一句話重點`。

---

## 每份報告的建議結構

```markdown
# 台股追蹤報告 — {日期} {時間}（階段：開盤前 / 盤中更新 / 收盤前追蹤）

## 市場背景
（美股重點、國際新聞重點 — 只有開盤前報告需要完整寫，盤中更新可以省略或只留一行提醒）

## 今日熱門產業與選股邏輯
（3 個產業＋判斷依據 — 只有開盤前報告需要完整寫）

## 9 檔股票技術面追蹤

### {代號} {名稱}（{產業}）
- 目前價格：xxx（漲跌 x.xx%）
- 布林通道：上軌 xxx／中軌(20MA) xxx／下軌 xxx
- 目前位置：{狀態描述}
- ⚠️ 訊號變化（如果有）：從 {舊狀態} 變成 {新狀態}
- 圖表：![](../charts/{代號}_bollinger.png)

（9 檔重複上面格式）

## 免責聲明
（照抄 SKILL.md 裡的免責聲明文字）
```
